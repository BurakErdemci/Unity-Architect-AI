import re

class CodeProcessor:
    """Gelen metnin niyetini ve dilini kontrol eden zeka katmanı."""
    
    @staticmethod
    def is_actually_code(text: str):
        """Metnin gerçekten Unity C# kodu olup olmadığını kesinleştirir."""
        general = ["{", "}", ";"]
        unity_specific = ["using UnityEngine", "MonoBehaviour", "SerializeField", "void Update", "void Start", "GetComponent"]
        
        score = sum(1 for ind in general if ind in text)
        unity_score = sum(1 for ind in unity_specific if ind in text)
        
        return score >= 2 and unity_score >= 1

    @staticmethod
    def detect_intent(query: str):
        q = query.lower().strip()
        
        out_of_scope = ["unreal", "godot", "python", "react", "django", "javascript", "html", "css", "atatürk", "yemek"]
        if any(term in q for term in out_of_scope):
            return "OUT_OF_SCOPE"
        
        chat_words = ["selam", "merhaba", "hi", "nasılsın", "kimsin", "eyw", "saol", "teşekkür"]
        if any(word in q for word in chat_words) and len(q.split()) < 15:
            return "GREETING"
        
        return "ANALYSIS"

class UnityAnalyzer:
    """Unity scriptlerini analiz eden motor."""
    
    def __init__(self, code: str):
        self.code = code
        self.lines = code.split('\n')

    def analyze(self):
        smells = []
        smells.extend(self._check_heavy_update())
        smells.extend(self._check_string_searches())
        smells.extend(self._check_input_logic())
        smells.extend(self._check_camera_access())
        smells.extend(self._check_public_fields())
        smells.extend(self._check_destroy_usage())
        smells.extend(self._check_physics_misuse())
        
        return {
            "smells": smells, 
            "stats": {
                "total_lines": len(self.lines),
                "class_name": self._extract_class_name(),
                "has_update": "Update()" in self.code
            }
        }

    def _is_commented(self, line: str):
        return line.strip().startswith("//") or line.strip().startswith("/*")

    def _extract_class_name(self):
        match = re.search(r'class\s+(\w+)', self.code)
        return match.group(1) if match else "UnknownScript"

    # ─── PERFORMANS ───
    def _check_heavy_update(self):
        smells = []
        in_update = False
        brace_depth = 0
        patterns = {
            r"GetComponent": "⚠️ GetComponent her karede çağrılıyor — oyunu yavaşlatır. Awake() içinde bir değişkene ata, sonra onu kullan.",
            r"GameObject\.Find": "⚠️ Find her karede tüm sahneyi tarar — çok yavaş. Oyuncuyu Awake'de bir kere bul ve değişkende tut.",
            r"FindObjectOfType": "⚠️ FindObjectOfType çok ağır bir arama yapar. Referansı Inspector'dan sürükle-bırak ile ata.",
            r"Object\.Instantiate": "⚠️ Update içinde sürekli obje oluşturmak belleği şişirir. Object Pooling ile önceden oluşturup tekrar kullan.",
        }
        for i, line in enumerate(self.lines):
            if "void Update()" in line:
                in_update = True
                brace_depth = 0
            if in_update:
                brace_depth += line.count("{") - line.count("}")
                if not self._is_commented(line):
                    for pattern, msg in patterns.items():
                        if re.search(pattern, line):
                            smells.append({"line": i+1, "type": "⚡ Performans", "msg": msg})
                if brace_depth <= 0 and in_update and "{" in self.code:
                    in_update = False
        return smells

    # ─── TAG KONTROLÜ ───
    def _check_string_searches(self):
        smells = []
        for i, line in enumerate(self.lines):
            if not self._is_commented(line):
                if '.tag == "' in line or '.tag.Equals(' in line:
                    smells.append({
                        "line": i+1, 
                        "type": "🔧 Düzeltme", 
                        "msg": "⚠️ Tag karşılaştırmasında == yerine CompareTag() kullan — daha hızlı ve yazım hatasını yakalar."
                    })
        return smells

    # ─── INPUT LOGIC ───
    def _check_input_logic(self):
        smells = []
        in_fixed = False
        brace_depth = 0
        for i, line in enumerate(self.lines):
            if "void FixedUpdate()" in line:
                in_fixed = True
                brace_depth = 0
            if in_fixed:
                brace_depth += line.count("{") - line.count("}")
                if not self._is_commented(line):
                    if "Input.Get" in line:
                        smells.append({
                            "line": i+1, 
                            "type": "🐛 Mantık Hatası", 
                            "msg": "⚠️ FixedUpdate içinde tuş kontrolü güvenilmez — bazen basışı kaçırır. Input kontrolünü Update'e taşı."
                        })
                if brace_depth <= 0 and in_fixed:
                    in_fixed = False
        return smells

    # ─── CAMERA.MAIN ───
    def _check_camera_access(self):
        smells = []
        for i, line in enumerate(self.lines):
            if "Camera.main" in line and not self._is_commented(line):
                smells.append({
                    "line": i+1, 
                    "type": "⚡ Performans", 
                    "msg": "⚠️ Camera.main her kullanıldığında kamerayı arar. Awake'de bir değişkene ata ve onu kullan."
                })
        return smells

    # ─── PUBLIC FIELD ───
    def _check_public_fields(self):
        smells = []
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if not self._is_commented(line) and stripped.startswith("public "):
                # public method değil, field kontrolü
                if "void " not in stripped and "static " not in stripped and "class " not in stripped and "(" not in stripped:
                    smells.append({
                        "line": i+1, 
                        "type": "💡 Öneri", 
                        "msg": "💡 Bu değişken public — dışarıdan herkes değiştirebilir. [SerializeField] private yaparak Inspector'dan ayarlanabilir ama güvende tut."
                    })
        return smells

    # ─── DESTROY KULLANIMI ───
    def _check_destroy_usage(self):
        smells = []
        destroy_count = 0
        for i, line in enumerate(self.lines):
            if not self._is_commented(line) and "Destroy(" in line:
                destroy_count += 1
        if destroy_count >= 2:
            smells.append({
                "line": "Genel", 
                "type": "💡 Öneri", 
                "msg": f"💡 Kodda {destroy_count} yerde Destroy kullanılmış. Sık yok edilen objeler için Object Pooling düşün — performansı artırır."
            })
        return smells

    # ─── FİZİK YANLIŞ KULLANIMI ───
    def _check_physics_misuse(self):
        smells = []
        has_rigidbody = "Rigidbody" in self.code or "rigidbody" in self.code or "GetComponent<Rigidbody>" in self.code
        
        if has_rigidbody:
            for i, line in enumerate(self.lines):
                if not self._is_commented(line):
                    if "transform.position" in line and "=" in line and "Distance" not in line:
                        smells.append({
                            "line": i+1, 
                            "type": "🎯 Fizik", 
                            "msg": "⚠️ Rigidbody varken transform.position ile hareket fizik motorunu atlar. rb.MovePosition veya rb.velocity kullan."
                        })
                    elif "transform.Translate" in line:
                        smells.append({
                            "line": i+1, 
                            "type": "🎯 Fizik", 
                            "msg": "⚠️ Rigidbody varken Translate kullanmak çarpışmaları bozar. Rigidbody ile hareket ettir."
                        })
        return smells