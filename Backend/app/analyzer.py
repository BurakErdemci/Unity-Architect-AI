import re

class UnityAnalyzer:
    """Unity scriptlerini analiz eden motor."""

    def __init__(self, code: str):
        self.code = code
        self.lines = code.split('\n')

    def analyze(self):
        smells = []
        # 15 kontrol
        smells.extend(self._check_heavy_update())
        smells.extend(self._check_string_searches())
        smells.extend(self._check_input_logic())
        smells.extend(self._check_camera_access())
        smells.extend(self._check_public_fields())
        smells.extend(self._check_destroy_usage())
        smells.extend(self._check_physics_misuse())
        smells.extend(self._check_empty_callbacks())
        smells.extend(self._check_send_message())
        smells.extend(self._check_ongui_usage())
        smells.extend(self._check_string_concat_in_update())
        smells.extend(self._check_uncached_waitforseconds())
        smells.extend(self._check_distance_in_update())
        smells.extend(self._check_animator_string_params())
        smells.extend(self._check_addcomponent_in_update())

        # Her smell'e gerçek kod satırını ekle (format_analysis somut fix gösterebilsin)
        for smell in smells:
            line_num = smell.get("line")
            if isinstance(line_num, int) and 0 < line_num <= len(self.lines):
                smell["code"] = self.lines[line_num - 1].strip()

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

    # ─── ORTAK HELPER: Metod gövdesindeki satırları döner ───
    def _iter_method_body(self, method_signatures):
        """
        Verilen metod imzalarının gövdesindeki satırları yield eder.
        Allman style (açık parantez ayrı satırda) destekler.

        Kullanım:
            for i, line in self._iter_method_body(["void Update()", "void LateUpdate()"]):
                # i = satır indexi (0-based), line = satır metni

        Mantık:
            1. Metod imzası bulunca "bekleme" moduna geç
            2. İlk '{' görünce brace_depth sayacını başlat
            3. brace_depth tekrar 0'a düşünce metod bitti
        """
        waiting_for_brace = False
        in_method = False
        brace_depth = 0

        for i, line in enumerate(self.lines):
            # Yeni metod imzası bul
            if not in_method and not waiting_for_brace:
                for sig in method_signatures:
                    if sig in line:
                        # İmza satırında { varsa direkt gir
                        if "{" in line:
                            in_method = True
                            brace_depth = line.count("{") - line.count("}")
                        else:
                            waiting_for_brace = True
                        break
                continue

            # İmza bulundu, ilk '{' bekleniyor (Allman style)
            if waiting_for_brace:
                if "{" in line:
                    in_method = True
                    waiting_for_brace = False
                    brace_depth = line.count("{") - line.count("}")
                continue

            # Metod gövdesindeyiz
            if in_method:
                brace_depth += line.count("{") - line.count("}")
                if not self._is_commented(line):
                    yield i, line
                if brace_depth <= 0:
                    in_method = False

    # ─── 1: AĞIR UPDATE İŞLEMLERİ ───
    def _check_heavy_update(self):
        smells = []
        patterns = {
            r"GetComponent": "⚠️ GetComponent her karede çağrılıyor — oyunu yavaşlatır. Awake() içinde bir değişkene ata, sonra onu kullan.",
            r"GameObject\.Find": "⚠️ Find her karede tüm sahneyi tarar — çok yavaş. Oyuncuyu Awake'de bir kere bul ve değişkende tut.",
            r"FindObjectOfType": "⚠️ FindObjectOfType çok ağır bir arama yapar. Referansı Inspector'dan sürükle-bırak ile ata.",
            r"Object\.Instantiate": "⚠️ Update içinde sürekli obje oluşturmak belleği şişirir. Object Pooling ile önceden oluşturup tekrar kullan.",
        }
        for i, line in self._iter_method_body(["void Update()"]):
            for pattern, msg in patterns.items():
                if re.search(pattern, line):
                    smells.append({"line": i + 1, "type": "⚡ Performans", "msg": msg})
        return smells

    # ─── 2: TAG KONTROLÜ ───
    def _check_string_searches(self):
        smells = []
        for i, line in enumerate(self.lines):
            if not self._is_commented(line):
                if '.tag == "' in line or '.tag.Equals(' in line:
                    smells.append({
                        "line": i + 1,
                        "type": "🔧 Düzeltme",
                        "msg": "⚠️ Tag karşılaştırmasında == yerine CompareTag() kullan — daha hızlı ve yazım hatasını yakalar."
                    })
        return smells

    # ─── 3: FIXEDUPDATE İÇİNDE INPUT ───
    def _check_input_logic(self):
        smells = []
        for i, line in self._iter_method_body(["void FixedUpdate()"]):
            if "Input.Get" in line:
                smells.append({
                    "line": i + 1,
                    "type": "🐛 Mantık Hatası",
                    "msg": "⚠️ FixedUpdate içinde tuş kontrolü güvenilmez — bazen basışı kaçırır. Input kontrolünü Update'e taşı."
                })
        return smells

    # ─── 4: CAMERA.MAIN ───
    def _check_camera_access(self):
        smells = []
        for i, line in enumerate(self.lines):
            if "Camera.main" in line and not self._is_commented(line):
                smells.append({
                    "line": i + 1,
                    "type": "⚡ Performans",
                    "msg": "⚠️ Camera.main her kullanıldığında kamerayı arar. Awake'de bir değişkene ata ve onu kullan."
                })
        return smells

    # ─── 5: PUBLIC FIELD ───
    def _check_public_fields(self):
        smells = []
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if not self._is_commented(line) and stripped.startswith("public "):
                if "void " not in stripped and "static " not in stripped and "class " not in stripped and "(" not in stripped:
                    smells.append({
                        "line": i + 1,
                        "type": "💡 Öneri",
                        "msg": "💡 Bu değişken public — dışarıdan herkes değiştirebilir. [SerializeField] private yaparak Inspector'dan ayarlanabilir ama güvende tut."
                    })
        return smells

    # ─── 6: DESTROY KULLANIMI ───
    def _check_destroy_usage(self):
        smells = []
        destroy_count = sum(
            1 for line in self.lines
            if not self._is_commented(line) and "Destroy(" in line
        )
        if destroy_count >= 2:
            smells.append({
                "line": "Genel",
                "type": "💡 Öneri",
                "msg": f"💡 Kodda {destroy_count} yerde Destroy kullanılmış. Sık yok edilen objeler için Object Pooling düşün — performansı artırır."
            })
        return smells

    # ─── 7: FİZİK YANLIŞ KULLANIMI ───
    def _check_physics_misuse(self):
        smells = []
        has_rigidbody = "Rigidbody" in self.code or "rigidbody" in self.code or "GetComponent<Rigidbody>" in self.code

        if has_rigidbody:
            for i, line in enumerate(self.lines):
                if not self._is_commented(line):
                    if "transform.position" in line and "=" in line and "Distance" not in line:
                        smells.append({
                            "line": i + 1,
                            "type": "🎯 Fizik",
                            "msg": "⚠️ Rigidbody varken transform.position ile hareket fizik motorunu atlar. rb.MovePosition veya rb.velocity kullan."
                        })
                    elif "transform.Translate" in line:
                        smells.append({
                            "line": i + 1,
                            "type": "🎯 Fizik",
                            "msg": "⚠️ Rigidbody varken Translate kullanmak çarpışmaları bozar. Rigidbody ile hareket ettir."
                        })
        return smells

    # ─── 8: BOŞ CALLBACK ───
    def _check_empty_callbacks(self):
        """Boş Update/Start/FixedUpdate performansı boşa harcar."""
        smells = []
        callbacks = ["void Update()", "void Start()", "void FixedUpdate()", "void LateUpdate()", "void Awake()"]
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            for cb in callbacks:
                if cb in stripped and not self._is_commented(line):
                    body_lines = []
                    for j in range(i + 1, min(i + 5, len(self.lines))):
                        s = self.lines[j].strip()
                        if s == "{" or s == "}" or s == "":
                            body_lines.append(s)
                        else:
                            break
                    content = "".join(body_lines).replace(" ", "")
                    if content == "{}":
                        smells.append({
                            "line": i + 1,
                            "type": "⚡ Performans",
                            "msg": f"⚠️ `{cb.split('void ')[1]}` boş tanımlanmış — Unity her karede çağırır ama hiçbir iş yapmıyor. Sil veya kullanana kadar yorum satırına al."
                        })
        return smells

    # ─── 9: SENDMESSAGE ───
    def _check_send_message(self):
        """SendMessage yavaş ve tip güvenliği yok."""
        smells = []
        for i, line in enumerate(self.lines):
            if not self._is_commented(line):
                if "SendMessage(" in line or "BroadcastMessage(" in line or "SendMessageUpwards(" in line:
                    smells.append({
                        "line": i + 1,
                        "type": "⚡ Performans",
                        "msg": "⚠️ SendMessage reflection kullanır — yavaş ve yazım hatası sessizce geçer. Doğrudan referans veya C# event/delegate kullan."
                    })
        return smells

    # ─── 10: ONGUI KULLANIMI ───
    def _check_ongui_usage(self):
        """OnGUI legacy sistem, her karede birden fazla çağrılır."""
        smells = []
        for i, line in enumerate(self.lines):
            if "void OnGUI()" in line and not self._is_commented(line):
                smells.append({
                    "line": i + 1,
                    "type": "⚡ Performans",
                    "msg": "⚠️ OnGUI() eski bir sistemdir ve her karede birden fazla çağrılır. UI için Unity'nin yeni UI Toolkit veya Canvas sistemini kullan."
                })
        return smells

    # ─── 11: UPDATE İÇİNDE STRING BİRLEŞTİRME ───
    def _check_string_concat_in_update(self):
        """Update içinde string + string GC baskısı yaratır."""
        smells = []
        for i, line in self._iter_method_body(["void Update()"]):
            if re.search(r'\".*\"\s*\+\s*', line) or re.search(r'\+\s*\".*\"', line):
                smells.append({
                    "line": i + 1,
                    "type": "⚡ Performans",
                    "msg": "⚠️ Update içinde string birleştirme her karede yeni string oluşturur (GC baskısı). StringBuilder veya önbellek kullan."
                })
        return smells

    # ─── 12: ÖNBELLEKSİZ WAITFORSECONDS ───
    def _check_uncached_waitforseconds(self):
        """Coroutine döngüsünde new WaitForSeconds her seferinde GC allocation yapar."""
        smells = []
        in_while = False
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if "while" in stripped and not self._is_commented(line):
                in_while = True
            if in_while:
                if "new WaitForSeconds" in stripped or "new WaitForEndOfFrame" in stripped:
                    smells.append({
                        "line": i + 1,
                        "type": "⚡ Performans",
                        "msg": "⚠️ Döngü içinde `new WaitForSeconds()` her seferinde bellek ayırır. Bir kere oluşturup değişkende tut: `WaitForSeconds wait = new WaitForSeconds(1f);`"
                    })
                if stripped == "}" or "break" in stripped or "return" in stripped:
                    in_while = False
        return smells

    # ─── 13: UPDATE İÇİNDE Vector3.Distance ───
    def _check_distance_in_update(self):
        """Vector3.Distance karekök hesaplar, sqrMagnitude daha hızlı."""
        smells = []
        for i, line in self._iter_method_body(["void Update()", "void FixedUpdate()"]):
            if "Vector3.Distance" in line or "Vector2.Distance" in line:
                smells.append({
                    "line": i + 1,
                    "type": "⚡ Performans",
                    "msg": "⚠️ Distance() karekök hesaplar, her karede pahalıdır. Mesafe karşılaştırması için `(a - b).sqrMagnitude < range * range` kullan."
                })
        return smells

    # ─── 14: ANİMATOR STRING PARAMETRELERİ ───
    def _check_animator_string_params(self):
        """Animator.SetX(\"string\") her çağrıda hash hesaplar."""
        smells = []
        animator_methods = ["SetBool", "SetFloat", "SetInteger", "SetTrigger", "GetBool", "GetFloat", "GetInteger"]
        for i, line in enumerate(self.lines):
            if not self._is_commented(line):
                for method in animator_methods:
                    if method + "(\"" in line or method + "('" in line:
                        smells.append({
                            "line": i + 1,
                            "type": "⚡ Performans",
                            "msg": f"⚠️ `{method}(\"string\")` her çağrıda hash hesaplar. `Animator.StringToHash()` ile bir kere hesapla ve int olarak kullan."
                        })
                        break
        return smells

    # ─── 15: UPDATE İÇİNDE ADDCOMPONENT ───
    def _check_addcomponent_in_update(self):
        """Update içinde AddComponent çok ağır bir işlem."""
        smells = []
        for i, line in self._iter_method_body(["void Update()"]):
            if "AddComponent" in line:
                smells.append({
                    "line": i + 1,
                    "type": "⚡ Performans",
                    "msg": "⚠️ Update içinde AddComponent çok ağır — her karede yeni component eklemek belleği şişirir. Awake/Start'ta ekle veya Object Pooling kullan."
                })
        return smells
