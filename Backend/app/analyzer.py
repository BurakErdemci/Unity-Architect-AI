import re

class CodeProcessor:
    """Gelen metnin niyetini ve kod olup olmadığını kontrol eden sınıf."""
    
    @staticmethod
    def is_actually_code(text: str):
        """Metnin gerçekten bir C# kodu olup olmadığını kontrol eder."""
        indicators = ["{", "}", ";", "void ", "public ", "class ", "using ", "private "]
        score = sum(1 for indicator in indicators if indicator in text)
        return score >= 2

    @staticmethod
    def detect_intent(query: str):
        """Kullanıcının niyetini (Selam, Kapsam Dışı, Analiz) belirler."""
        q = query.lower().strip()
        
        # 1. Kapsam Dışı Kontrolü
        out_of_scope_terms = ["unreal", "godot", "cryengine", "web", "react", "django", "javascript", "python", "atatürk"]
        if any(term in q for term in out_of_scope_terms):
            return "OUT_OF_SCOPE"
        
        # 2. Selamlaşma ve Sohbet
        chat_words = ["selam", "merhaba", "hi", "hello", "nasılsın", "kimsin", "eyw", "saol", "teşekkür"]
        if any(word in q for word in chat_words) and len(q.split()) < 15:
            return "GREETING"
        
        return "ANALYSIS"

class UnityAnalyzer:
    """Unity scriptlerini statik olarak analiz eden ana sınıf."""
    
    def __init__(self, code: str):
        self.code = code
        self.lines = code.split('\n')

    def analyze(self):
        """Tüm analizleri sırayla çalıştıran ana motor."""
        smells = []
        smells.extend(self._check_heavy_update())
        smells.extend(self._check_string_searches())
        smells.extend(self._check_input_logic())
        smells.extend(self._check_camera_access())
        
        return {
            "smells": smells, 
            "stats": {
                "total_lines": len(self.lines),
                "has_update": "Update()" in self.code
            }
        }

    def _check_heavy_update(self):
        smells = []
        in_update = False
        patterns = {
            r"GetComponent": "GetComponent her karede çağrılmamalı. Değişkeni Awake/Start içinde önbelleğe (cache) almalısın.",
            r"FindObjectOfType": "FindObjectOfType çok yavaştır. Bunun yerine Singleton veya doğrudan referans kullanmalısın.",
            r"GameObject\.Find": "GameObject.Find tüm sahneyi tarar. Referans (SerializeField) kullanmak çok daha hızlıdır.",
            r"Object\.Instantiate": "Update içinde sürekli Instantiate bellek sorunlarına yol açar. Object Pooling kullanmayı dene."
        }
        for i, line in enumerate(self.lines):
            if "void Update()" in line: in_update = True
            if in_update:
                for pattern, msg in patterns.items():
                    if re.search(pattern, line):
                        smells.append({"line": i+1, "type": "Performans", "msg": msg})
            if "}" in line and in_update: in_update = False
        return smells

    def _check_string_searches(self):
        smells = []
        for i, line in enumerate(self.lines):
            if '.tag == "' in line or '.tag.Equals(' in line:
                smells.append({"line": i+1, "type": "Optimizasyon", "msg": "Tag karşılaştırması yaparken '.tag == ' yerine 'CompareTag()' kullanmalısın."})
        return smells

    def _check_input_logic(self):
        smells = []
        in_fixed_update = False
        for i, line in enumerate(self.lines):
            if "void FixedUpdate()" in line: in_fixed_update = True
            if in_fixed_update:
                if "Input.GetKeyDown" in line or "Input.GetKeyUp" in line:
                    smells.append({"line": i+1, "type": "Mantık Hatası", "msg": "FixedUpdate içinde Input tespiti güvenilmezdir. Bunu Update'e taşı."})
            if "}" in line and in_fixed_update: in_fixed_update = False
        return smells

    def _check_camera_access(self):
        smells = []
        if "Camera.main" in self.code and "Update()" in self.code:
             smells.append({"line": "Genel", "type": "Performans", "msg": "Camera.main kullanımı Update içinde performans kaybına yol açar. Cache'lemelisin."})
        return smells