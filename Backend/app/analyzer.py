import re

class CodeProcessor:
    """Gelen metnin niyetini ve dilini kontrol eden zeka katmanı."""
    
    @staticmethod
    def is_actually_code(text: str):
        """Metnin gerçekten Unity C# kodu olup olmadığını kesinleştirir."""
        # Genel işaretçiler
        general = ["{", "}", ";"]
        # Unity'ye özgü anahtar kelimeler
        unity_specific = ["using UnityEngine", "MonoBehaviour", "SerializeField", "void Update", "void Start", "GetComponent"]
        
        score = sum(1 for ind in general if ind in text)
        unity_score = sum(1 for ind in unity_specific if ind in text)
        
        # En az 2 genel işaretçi VE en az 1 Unity terimi olmalı
        return score >= 2 and unity_score >= 1

    @staticmethod
    def detect_intent(query: str):
        q = query.lower().strip()
        
        # 1. Kapsam Dışı (Genişletilmiş liste)
        out_of_scope = ["unreal", "godot", "python", "react", "django", "javascript", "html", "css", "atatürk", "yemek"]
        if any(term in q for term in out_of_scope):
            return "OUT_OF_SCOPE"
        
        # 2. Sohbet ve Selamlaşma
        chat_words = ["selam", "merhaba", "hi", "nasılsın", "kimsin", "eyw", "saol", "teşekkür"]
        if any(word in q for word in chat_words) and len(q.split()) < 15:
            return "GREETING"
        
        return "ANALYSIS"

class UnityAnalyzer:
    """Unity scriptlerini cerrah titizliğiyle analiz eden motor."""
    
    def __init__(self, code: str):
        self.code = code
        self.lines = code.split('\n')

    def analyze(self):
        smells = []
        smells.extend(self._check_heavy_update())
        smells.extend(self._check_string_searches())
        smells.extend(self._check_input_logic())
        smells.extend(self._check_camera_access())
        
        return {
            "smells": smells, 
            "stats": {
                "total_lines": len(self.lines),
                "class_name": self._extract_class_name(),
                "has_update": "Update()" in self.code
            }
        }

    def _is_commented(self, line: str):
        """Satırın yorum satırı olup olmadığını kontrol eder."""
        return line.strip().startswith("//") or line.strip().startswith("/*")

    def _extract_class_name(self):
        """Kodun içindeki sınıf ismini yakalar (DB başlığı için)."""
        match = re.search(r'class\s+(\w+)', self.code)
        return match.group(1) if match else "UnknownScript"

    def _check_heavy_update(self):
        smells = []
        in_update = False
        patterns = {
            r"GetComponent": "GetComponent her karede çağrılmamalı. Awake/Start içinde cache'le.",
            r"GameObject\.Find": "GameObject.Find tüm sahneyi tarar. [SerializeField] ile referans kullan.",
            r"FindObjectOfType": "FindObjectOfType çok yavaştır. Singleton veya referans kullan.",
            r"Object\.Instantiate": "Update içinde Instantiate bellek tüketir. Object Pooling kullan."
        }
        for i, line in enumerate(self.lines):
            if "void Update()" in line: in_update = True
            if in_update and not self._is_commented(line):
                for pattern, msg in patterns.items():
                    if re.search(pattern, line):
                        smells.append({"line": i+1, "type": "Performans", "msg": msg})
            if "}" in line and in_update: in_update = False
        return smells

    def _check_string_searches(self):
        smells = []
        for i, line in enumerate(self.lines):
            if not self._is_commented(line):
                if '.tag == "' in line or '.tag.Equals(' in line:
                    smells.append({"line": i+1, "type": "Optimizasyon", "msg": "Tag kontrolünde '==' yerine 'CompareTag()' kullan."})
        return smells

    def _check_input_logic(self):
        smells = []
        in_fixed = False
        for i, line in enumerate(self.lines):
            if "void FixedUpdate()" in line: in_fixed = True
            if in_fixed and not self._is_commented(line):
                if "Input.Get" in line:
                    smells.append({"line": i+1, "type": "Mantık Hatası", "msg": "FixedUpdate içinde Input tespiti güvenilmezdir. Update'e taşı."})
            if "}" in line and in_fixed: in_fixed = False
        return smells

    def _check_camera_access(self):
        smells = []
        if "Camera.main" in self.code and "Update()" in self.code:
             smells.append({"line": "Genel", "type": "Performans", "msg": "Camera.main her karede arama yapar. Awake'de bir değişkene ata."})
        return smells