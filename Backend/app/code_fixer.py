"""
CodeFixer — Kural tabanlı Unity C# Otomatik Düzeltici
======================================================

Kullanıcının orijinal kodunu alır, tespit edilen smells'e göre
gerçek dönüşümler uygular ve düzeltilmiş kodu döner.

AI yok — tamamen deterministic, regex tabanlı.

Güvenli otomatik fix:
  - Camera.main → private Camera _cam (Awake cache)
  - new WaitForSeconds → field cache
  - public field → [SerializeField] private

Manuel fix (işaret eder, uygulamaz):
  - GameObject.Find/FindWithTag (class sınırları karmaşık)
  - Vector3.Distance → sqrMagnitude (eşik değeri değişir)
  - SendMessage (hedef interface bilinmez)
  - transform.position + Rigidbody
"""

import re
from dataclasses import dataclass, field


@dataclass
class FixResult:
    fixed_code: str
    applied: list = field(default_factory=list)   # uygulandı
    manual: list = field(default_factory=list)    # manuel gerekli
    changed: bool = False


class CodeFixer:
    """
    Unity C# scriptini kural bazlı dönüştürür.
    Güvenli olan fix'leri otomatik uygular, risklileri işaretler.
    """

    def __init__(self, code: str, smells: list):
        self.original = code
        self.smells = smells
        self._applied: list[str] = []
        self._manual: list[str] = []

    def apply_all(self) -> FixResult:
        code = self.original
        code = self._fix_camera_main(code)
        code = self._fix_waitforseconds(code)
        code = self._fix_public_fields(code)
        self._collect_manual(code)
        return FixResult(
            fixed_code=code,
            applied=self._applied,
            manual=self._manual,
            changed=(code != self.original),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # FIX 1: Camera.main → private Camera _cam
    # ──────────────────────────────────────────────────────────────────────────
    def _fix_camera_main(self, code: str) -> str:
        if "Camera.main" not in code:
            return code
        if "_cam" in code:
            return code  # zaten cache edilmiş

        # Her Camera.main kullanımı hangi class'ta? Tekrar eden for her class.
        for cls_name, cls_start, cls_end in self._iter_classes(code):
            cls_body = code[cls_start:cls_end]
            if "Camera.main" not in cls_body:
                continue

            # Field ekle
            cls_body = self._insert_field(cls_body, "private Camera _cam; // Cache edildi")
            # Tüm Camera.main → _cam (önce replace, sonra Awake ekle — double-replace önlenir)
            cls_body = cls_body.replace("Camera.main", "_cam")
            # Awake'e ekle (literal "Camera.main" artık replace edilmez)
            cls_body = self._ensure_awake_statement(cls_body, "_cam = Camera.main;")

            code = code[:cls_start] + cls_body + code[cls_end:]

        self._applied.append("Camera.main → private Camera _cam (Awake'de cache edildi)")
        return code

    # ──────────────────────────────────────────────────────────────────────────
    # FIX 2: yield return new WaitForSeconds(x) → field
    # ──────────────────────────────────────────────────────────────────────────
    def _fix_waitforseconds(self, code: str) -> str:
        pattern = re.compile(r'yield\s+return\s+new\s+WaitForSeconds\(([^)]+)\)\s*;')
        if not pattern.search(code):
            return code

        for cls_name, cls_start, cls_end in self._iter_classes(code):
            cls_body = code[cls_start:cls_end]
            matches = list(pattern.finditer(cls_body))
            if not matches:
                continue

            # Benzersiz arg'ları topla
            arg_to_field: dict[str, str] = {}
            for m in matches:
                arg = m.group(1).strip()
                if arg not in arg_to_field:
                    suffix = "" if not arg_to_field else str(len(arg_to_field) + 1)
                    arg_to_field[arg] = f"_wait{suffix}"

            # Terse replace (sondan başa indis kaymaması için)
            for m in reversed(matches):
                arg = m.group(1).strip()
                fname = arg_to_field[arg]
                cls_body = cls_body[:m.start()] + f"yield return {fname}; // GC optimize" + cls_body[m.end():]

            # Field'ları ekle
            for arg, fname in arg_to_field.items():
                if fname not in cls_body:
                    cls_body = self._insert_field(
                        cls_body,
                        f"private readonly WaitForSeconds {fname} = new WaitForSeconds({arg}); // GC optimize"
                    )

            code = code[:cls_start] + cls_body + code[cls_end:]

        self._applied.append("WaitForSeconds → readonly field (coroutine GC optimize edildi)")
        return code

    # ──────────────────────────────────────────────────────────────────────────
    # FIX 3: public field → [SerializeField] private
    # ──────────────────────────────────────────────────────────────────────────
    def _fix_public_fields(self, code: str) -> str:
        # Sadece field tanımı — method/class/static değil
        pattern = re.compile(
            r'^(\s+)public\s+'
            r'(?!void|class|static|abstract|virtual|override|interface|enum|readonly)'
            r'(\w[\w<>\[\],\s]*?\s+\w+\s*(?:=|;))',
            re.MULTILINE,
        )
        count = len(pattern.findall(code))
        if count == 0:
            return code

        new_code = pattern.sub(
            lambda m: m.group(0).replace("public ", "[SerializeField] private ", 1),
            code,
        )
        if new_code != code:
            self._applied.append(f"public field → [SerializeField] private ({count} alan, Inspector erişimi korundu)")
        return new_code

    # ──────────────────────────────────────────────────────────────────────────
    # Manuel fix toplama
    # ──────────────────────────────────────────────────────────────────────────
    def _collect_manual(self, fixed_code: str) -> None:
        has_find = any(
            re.search(r"GameObject\.Find|FindWithTag|FindObjectOfType", s.get("code", ""))
            for s in self.smells
        )
        has_dist = any(
            re.search(r"Vector[23]\.Distance", s.get("code", ""))
            for s in self.smells
        )
        has_send = any(
            re.search(r"SendMessage\(|BroadcastMessage\(", s.get("code", ""))
            for s in self.smells
        )
        has_rb_pos = any(
            "transform.position" in s.get("code", "") and "=" in s.get("code", "")
            for s in self.smells
            if s.get("type") == "🎯 Fizik"
        )

        if has_find:
            self._manual.append(
                "**GameObject.Find/FindWithTag** → Awake'de cache et "
                "(sınıf sınırları karmaşık, elle Awake'e taşı ve private field ekle)"
            )
        if has_dist:
            self._manual.append(
                "**Vector3.Distance** → `sqrMagnitude` "
                "(eşik değerini de karesi ile değiştirmeyi unutma: `dist > 2f` → `sqrDist > 4f`)"
            )
        if has_send:
            self._manual.append(
                "**SendMessage** → interface veya GetComponent "
                "(`ITakeDamage target = other.GetComponent<ITakeDamage>(); target?.TakeDamage(val);`)"
            )
        if has_rb_pos:
            self._manual.append(
                "**transform.position** → `rb.MovePosition(rb.position + dir * speed * Time.fixedDeltaTime)` "
                "(FixedUpdate içinde çağır)"
            )

    # ──────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────────
    def _iter_classes(self, code: str):
        """
        (class_name, body_start, body_end) üçlüsü yield eder.
        body_start: açık '{' sonrası, body_end: kapama '}' öncesi.
        """
        for cm in re.finditer(r'\bclass\s+(\w+)[^{]*\{', code):
            cls_name = cm.group(1)
            start = cm.end()
            depth = 1
            i = start
            while i < len(code) and depth > 0:
                if code[i] == '{':
                    depth += 1
                elif code[i] == '}':
                    depth -= 1
                i += 1
            yield cls_name, start, i - 1  # -1: kapama '}' dahil değil

    def _insert_field(self, cls_body: str, field_decl: str) -> str:
        """
        Field bildirimini class body başına (ilk method öncesine) ekler.
        """
        # İlk void/private/protected/public method veya property'den önce
        m = re.search(
            r'\n(\s+)((?:private|public|protected|internal|void|IEnumerator|async|static)\s)',
            cls_body,
        )
        if m:
            indent = re.match(r'\s*', m.group(1)).group(0)
            # En az 4 boşluk/1 tab indent
            indent = indent if indent else "    "
            pos = m.start()
            return cls_body[:pos] + f"\n{indent}{field_decl}" + cls_body[pos:]

        # Fallback: başa ekle
        return f"\n    {field_decl}\n" + cls_body

    def _ensure_awake_statement(self, cls_body: str, statement: str) -> str:
        """
        Awake() varsa başına statement ekler; yoksa Awake() oluşturur.
        """
        awake_m = re.search(r'([ \t]*)void\s+Awake\s*\(\s*\)\s*\{', cls_body)
        if awake_m:
            indent = awake_m.group(1)
            inner = indent + "    "
            pos = awake_m.end()
            return cls_body[:pos] + f"\n{inner}{statement}" + cls_body[pos:]

        # Awake yok — Start'tan önce oluştur
        start_m = re.search(r'([ \t]*)void\s+Start\s*\(\s*\)', cls_body)
        if start_m:
            indent = start_m.group(1)
            inner = indent + "    "
            pos = start_m.start()
            new_awake = f"{indent}void Awake()\n{indent}{{\n{inner}{statement}\n{indent}}}\n\n"
            return cls_body[:pos] + new_awake + cls_body[pos:]

        # Fallback: ilk method öncesine ekle
        m = re.search(r'([ \t]*)void\s+', cls_body)
        if m:
            indent = m.group(1)
            inner = indent + "    "
            pos = m.start()
            new_awake = f"{indent}void Awake()\n{indent}{{\n{inner}{statement}\n{indent}}}\n\n"
            return cls_body[:pos] + new_awake + cls_body[pos:]

        return cls_body
