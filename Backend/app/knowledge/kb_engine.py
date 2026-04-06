"""
KB Engine — Unity Yerel Bilgi Bankası Motoru
============================================

Kullanıcı mesajını analiz eder ve unity_kb.json içindeki
bilgi bankasıyla eşleştirir.

Eğer eşleşme bulunursa: anında yerel yanıt (0ms, 0 token)
Eğer eşleşme yoksa: None döner → LLM fallback devreye girer

Kullanım:
    kb = KBEngine()
    result = kb.lookup("bana hareket kodu yaz", intent="generation")
    if result:
        response = kb.format_response(result, intent="generation")
    # result None ise → LLM çağrısı yap
"""

import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# CodeFixer: kb_engine ile aynı dizinde değil, bir üst dizinde
sys.path.insert(0, str(Path(__file__).parent.parent))
from code_fixer import CodeFixer

logger = logging.getLogger(__name__)

# ─── Sabitler ───────────────────────────────────────────────────────────────
KB_FILE = Path(__file__).parent / "unity_kb.json"

# Türkçe karakterleri normalize etmek için eşleştirme tablosu
_TR_NORMALIZE = str.maketrans(
    "çğıöşüÇĞİÖŞÜ",
    "cgiosucgiosu"
)


# ─── Veri Sınıfı ─────────────────────────────────────────────────────────────
@dataclass
class KBResult:
    """KB araması sonucunda dönen eşleşme."""
    entry_id: str
    title: str
    explanation: str
    code: str
    tips: list
    unity_version: str
    score: float                                    # 0.0 - 1.0 arasında güven skoru
    matched_keywords: list
    setup_steps: list = field(default_factory=list)            # Adım adım Unity kurulum rehberi
    # Varyant/clarification alanları
    clarification_needed: bool = False              # True → kullanıcıya seçenek sor
    clarification_options: list = field(default_factory=list)  # [{id, title, variant_tags, variant_label}]


# ─── KB Engine ───────────────────────────────────────────────────────────────
class KBEngine:
    """
    Unity bilgi bankası motoru.

    Startup'ta JSON'ı tek seferinde yükler.
    Her lookup() çağrısı O(n * k) karmaşıklığında çalışır
    (n = entry sayısı, k = keyword sayısı — her ikisi de küçük).
    """

    # Variant sinyal sözlüğü: normalize edilmiş tag → eşleşen token'lar
    # Kullanıcı mesajında bu token'lardan biri geçerse ilgili variant seçilir.
    _VARIANT_SIGNALS: dict[str, list[str]] = {
        "2d":            ["2d", "iki boyutlu", "platformer", "platform", "sidescroller"],
        "3d":            ["3d", "uc boyutlu", "fps", "tps", "birinci sahis", "ucuncu sahis",
                          "first person", "third person"],
        "platformer":    ["platformer", "platform", "side scroller", "sidescroller", "2d"],
        "fps":           ["fps", "first person", "birinci sahis", "birinci sahis"],
        "tps":           ["tps", "third person", "ucuncu sahis"],
        "topdown":       ["topdown", "top down", "yukari", "overhead"],
        "rigidbody":     ["rigidbody", "fizik", "physics"],
        "top-down":      ["topdown", "top down", "overhead"],
        "side scroller": ["platformer", "platform", "2d", "sidescroller"],
    }

    def __init__(self, kb_path: Path = KB_FILE):
        self._entries: list = []
        self._load(kb_path)

    # ── Yükleme ──────────────────────────────────────────────────────────────
    def _load(self, path: Path) -> None:
        """JSON bilgi bankasını yükler. Dosya yoksa boş başlar."""
        if not path.exists():
            logger.warning(f"[KBEngine] Bilgi bankası bulunamadı: {path}")
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._entries = data.get("entries", [])
            logger.info(f"[KBEngine] {len(self._entries)} KB girdisi yüklendi.")
        except Exception as e:
            logger.error(f"[KBEngine] JSON yüklenemedi: {e}")

    # ── Ana Arama ─────────────────────────────────────────────────────────────
    def lookup(self, message: str, intent: str = "chat") -> Optional[KBResult]:
        """
        Kullanıcı mesajına en uygun KB girdisini döner.

        Parametreler
        ────────────
        message : str   → Kullanıcının ham mesajı
        intent  : str   → "chat" veya "generation"

        Dönüş
        ─────
        KBResult  → Eşleşme bulunduysa
        None      → Eşleşme yoksa (LLM fallback)
        """
        if not self._entries:
            return None

        tokens = self._tokenize(message)
        raw_candidates: list[tuple[float, KBResult, dict]] = []  # (score, result, raw_entry)

        for entry in self._entries:
            # Bu entry istenilen intent'i destekliyor mu?
            supported_intents = entry.get("intent_types", ["chat", "generation"])
            if intent not in supported_intents:
                continue

            score, matched = self._score(tokens, entry)

            if score > 0:
                raw_candidates.append((score, KBResult(
                    entry_id=entry["id"],
                    title=entry["title"],
                    explanation=entry.get("explanation", ""),
                    code=entry.get("code", ""),
                    tips=entry.get("tips", []),
                    unity_version=entry.get("unity_version", "2021.3+"),
                    score=score,
                    matched_keywords=matched,
                    setup_steps=entry.get("setup_steps", []),
                ), entry))

        if not raw_candidates:
            logger.info(f"[KBEngine] Miss → intent={intent}, tokens={list(tokens)[:5]}")
            return None

        # ── Varyant / Clarification Logic ────────────────────────────────────
        # Aynı group'tan birden fazla entry eşleştiyse → variant algıla veya clarification sor
        grouped: dict[str, list] = defaultdict(list)
        ungrouped: list[tuple[float, KBResult]] = []

        for score, result, entry in raw_candidates:
            grp = entry.get("group")
            if grp:
                grouped[grp].append((score, result, entry))
            else:
                ungrouped.append((score, result))

        final_candidates: list[tuple[float, KBResult]] = list(ungrouped)

        for grp_name, grp_candidates in grouped.items():
            if len(grp_candidates) == 1:
                # Grupta tek eşleşme — direkt ekle
                s, r, _ = grp_candidates[0]
                final_candidates.append((s, r))
            else:
                # Birden fazla eşleşme — variant sinyali ara
                matched_variant = self._detect_variant(tokens, grp_candidates)
                if matched_variant:
                    s, r, _ = matched_variant
                    logger.info(f"[KBEngine] Variant match → '{r.entry_id}' (group={grp_name})")
                    final_candidates.append((s, r))
                else:
                    # Variant belirtilmemiş → clarification sor
                    options = [
                        {
                            "id": r.entry_id,
                            "title": r.title,
                            "variant_tags": e.get("variant_tags", []),
                            "variant_label": e.get("variant_label", r.title),
                        }
                        for s, r, e in sorted(grp_candidates, key=lambda x: x[0], reverse=True)
                    ]
                    best_score = max(s for s, _, _ in grp_candidates)
                    clarification = KBResult(
                        entry_id=f"clarification_{grp_name}",
                        title="Hangi türü istiyorsun?",
                        explanation="",
                        code="",
                        tips=[],
                        unity_version="",
                        score=best_score,
                        matched_keywords=[],
                        clarification_needed=True,
                        clarification_options=options,
                    )
                    logger.info(f"[KBEngine] Clarification needed → group={grp_name}, options={[o['id'] for o in options]}")
                    final_candidates.append((best_score, clarification))

        if not final_candidates:
            return None

        # En yüksek skor
        best_score, best_result = max(final_candidates, key=lambda x: x[0])

        # Minimum skor eşiği — çok zayıf eşleşmeleri filtrele (false positive önleme)
        MIN_SCORE_THRESHOLD = 0.16
        if best_score < MIN_SCORE_THRESHOLD and not best_result.clarification_needed:
            logger.info(f"[KBEngine] Miss (skor eşiği altı) → skor={best_score:.2f} < {MIN_SCORE_THRESHOLD}")
            return None

        logger.info(
            f"[KBEngine] Hit → '{best_result.title}' "
            f"(skor={best_score:.2f}, clarification={best_result.clarification_needed})"
        )
        return best_result

    # ── Variant Algılama ─────────────────────────────────────────────────────
    def _detect_variant(self, tokens: set, group_candidates: list) -> Optional[tuple]:
        """
        Query token'larından variant sinyali algılar.
        En yüksek skorlu eşleşen entry'yi döner, eşleşme yoksa None.

        Örnek:
            tokens = {"3d", "fps", "karakter", "kontrolcusu"}
            → character_controller_3d'nin variant_tags'i ["3d", "fps", "tps"] ile eşleşir
        """
        # Her entry'nin variant_tag'lerini normalize ederek token'larla karşılaştır
        best_match: Optional[tuple] = None
        best_signal_len = 0  # Daha uzun/spesifik sinyal öncelikli

        for score, result, entry in group_candidates:
            variant_tags: list[str] = entry.get("variant_tags", [])
            for tag in variant_tags:
                tag_norm = tag.lower().translate(_TR_NORMALIZE).strip()
                # Variant sinyali sözlüğünden genişletilmiş sinyal listesini al
                signals = self._VARIANT_SIGNALS.get(tag_norm, [tag_norm])
                for signal in signals:
                    sig_norm = signal.lower().translate(_TR_NORMALIZE)
                    # Token seti ile eşleştir (tam veya substring)
                    for token in tokens:
                        if sig_norm == token or (len(sig_norm) >= 3 and (sig_norm in token or token in sig_norm)):
                            if len(sig_norm) > best_signal_len:
                                best_signal_len = len(sig_norm)
                                best_match = (score, result, entry)
                            break

        return best_match

    # ── Skor Hesaplama ────────────────────────────────────────────────────────
    def _score(self, tokens: set, entry: dict) -> tuple[float, list]:
        """
        Bir entry için eşleşme skoru hesaplar.

        İki katmanlı eşleştirme:
        1. Exact match: token == keyword
        2. Substring match: keyword token'ın içinde mi VEYA token keyword'ün içinde mi
           Örnek: "ziplama" → "zipla" (keyword token içinde), "ziplasin" → "zipla" (keyword token içinde)

        Kural 1 (Zorunlu): triggers listesinden en az 1'i eşleşmeli.
        Kural 2 (Zorunlu): Toplam eşleşme >= min_total_matches.
        Kural 3 (Skor):    Toplam eşleşme / toplam keyword sayısı.
        """
        triggers = set(entry.get("triggers", []))
        keywords = set(entry.get("keywords", []))
        tr_keywords = set(entry.get("turkish_keywords", []))
        all_keywords = keywords | tr_keywords
        min_total = entry.get("min_total_matches", 1)

        # İki katmanlı eşleştirme
        trigger_matches = self._fuzzy_match(tokens, triggers)
        keyword_matches = self._fuzzy_match(tokens, all_keywords)

        # Tüm eşleşmeler (trigger'lar da keyword sayılır)
        all_matches = trigger_matches | keyword_matches

        # Kural 1: En az 1 trigger eşleşmeli
        if len(trigger_matches) == 0:
            return 0.0, []

        # Kural 2: Minimum toplam eşleşme sayısı
        if len(all_matches) < min_total:
            return 0.0, []

        # Skor hesapla (normalize)
        total_keywords = len(triggers | all_keywords)
        score = len(all_matches) / total_keywords if total_keywords > 0 else 0.0

        # Trigger eşleşmesi bonus: trigger'lar yüksek sinyal, skoru hafif artır
        trigger_bonus = len(trigger_matches) * 0.1
        score = min(score + trigger_bonus, 1.0)

        return round(score, 3), sorted(all_matches)

    @staticmethod
    def _fuzzy_match(tokens: set, keywords: set) -> set:
        """
        Token-keyword fuzzy eşleştirme.
        Exact match + substring match (min 3 karakter).

        "ziplasin" → "zipla" bulur (keyword token'ın içinde)
        "coroutine" → "coroutine" bulur (exact)
        "sg" → eşleşmez (2 karakter, çok kısa)
        "ai hareket" → sadece "hareket" tokeni ile eşleşmez; her iki parça da gerekli
        """
        matched = set()
        for kw in keywords:
            # Çok kelimeli keyword: boşluk içeriyorsa parçaların TÜMÜ token setinde olmalı
            if " " in kw:
                parts = kw.split()
                if all(p in tokens for p in parts):
                    matched.add(kw)
                continue

            if kw in tokens:
                # Exact match
                matched.add(kw)
                continue
            if len(kw) < 4:
                # 3 karakter ve altı keyword'ler sadece exact match ile eşleşir
                # "so", "ai", "hp" gibi kısaltmalar substring'de false positive yaratır
                continue
            for token in tokens:
                if len(token) < 4:
                    continue
                # keyword token'ın içinde mi? ("zipla" in "ziplasin")
                # veya token keyword'ün içinde mi? ("pool" in "pooling")
                if kw in token or token in kw:
                    matched.add(kw)
                    break
        return matched

    # ── Tokenizer ─────────────────────────────────────────────────────────────
    @staticmethod
    def _tokenize(text: str) -> set:
        """
        Metni token setine çevirir.

        - Küçük harfe çevirir
        - Türkçe karakterleri normalize eder
        - Noktalama işaretlerini temizler
        - Tek karakterli token'ları atar
        """
        lowered = text.lower()
        normalized = lowered.translate(_TR_NORMALIZE)
        # Harf ve rakam olmayan karakterleri boşluğa çevir
        cleaned = re.sub(r"[^a-z0-9\s]", " ", normalized)
        tokens = {t for t in cleaned.split() if len(t) > 1}
        return tokens

    # ── Yanıt Formatlama ──────────────────────────────────────────────────────
    def format_clarification(self, result: KBResult) -> str:
        """
        Kullanıcıya varyant seçimi soran yanıt.
        Clarification_needed=True olan KBResult için kullanılır.
        """
        lines = ["Sana en uygun kodu verebilmem için biraz daha bilgiye ihtiyacım var:\n"]

        for opt in result.clarification_options:
            tags = " · ".join(opt["variant_tags"][:3])
            lines.append(f"**{opt['variant_label']}** `({tags})`")

        lines.append(
            "\nHangisini istediğini mesajına ekle. "
            "Örneğin: **\"2D platformer karakter kontrolcüsü yaz\"** "
            "veya **\"3D FPS karakter kontrolcüsü istiyorum\"**"
        )
        return "\n".join(lines)

    def format_response(self, result: KBResult, intent: str = "chat") -> str:
        """
        KBResult'ı kullanıcıya gönderilecek markdown yanıta çevirir.
        intent="generation" ise kodu öne çıkarır.
        intent="chat" ise açıklamayı öne çıkarır.
        """
        if intent == "generation":
            return self._format_generation(result)
        return self._format_chat(result)

    def _format_generation(self, r: KBResult) -> str:
        """Generation isteği için kod öncelikli yanıt."""
        lines = [f"## {r.title}"]

        if r.explanation:
            lines.append(f"\n{r.explanation}\n")

        if r.code:
            lines.append(f"```csharp\n{r.code}\n```")

        if r.setup_steps:
            lines.append("\n### 📋 Unity Kurulum Adımları")
            for i, step in enumerate(r.setup_steps, 1):
                prefix = f"{i}." if not step.startswith("===") else "\n**"
                suffix = "**" if step.startswith("===") else ""
                lines.append(f"{prefix} {step.strip('= ')}{suffix}")

        if r.tips:
            lines.append("\n### ⚠️ Önemli Notlar")
            for tip in r.tips:
                lines.append(f"- {tip}")

        lines.append(f"\n> Unity {r.unity_version} için optimize edilmiş kod.")

        return "\n".join(lines)

    def _format_chat(self, r: KBResult) -> str:
        """Chat sorusu için açıklama öncelikli yanıt."""
        lines = [f"## {r.title}"]

        if r.explanation:
            lines.append(f"\n{r.explanation}")

        if r.code:
            lines.append(f"\n### Örnek Uygulama\n\n```csharp\n{r.code}\n```")

        if r.setup_steps:
            lines.append("\n### 📋 Unity Kurulum Adımları")
            for i, step in enumerate(r.setup_steps, 1):
                prefix = f"{i}." if not step.startswith("===") else "\n**"
                suffix = "**" if step.startswith("===") else ""
                lines.append(f"{prefix} {step.strip('= ')}{suffix}")

        if r.tips:
            lines.append("\n### İpuçları")
            for tip in r.tips:
                lines.append(f"- {tip}")

        lines.append(f"\n> Unity {r.unity_version} için geçerlidir.")

        return "\n".join(lines)

    # ── Statik Analiz Formatlama ─────────────────────────────────────────────

    @staticmethod
    def _generate_fix_snippet(smell: dict) -> str:
        """
        Bir smell dict'inden (msg + code alanlarını kullanarak) somut,
        kopyala-yapıştır fix snippet'i üretir. AI yok, tamamen kural tabanlı.
        """
        code = smell.get("code", "")
        if not code:
            return ""

        # ── GameObject.Find / FindWithTag / FindObjectOfType ──────────────────
        if re.search(r"GameObject\.Find|FindWithTag|FindObjectOfType", code):
            m = re.search(r"(\w+)\s*=\s*(GameObject\.\w+\([^)]*\)(?:\.\w+)*)", code)
            if m:
                var, expr = m.group(1), m.group(2)
            else:
                var, expr = "target", code.strip().rstrip(";")
            return (
                f"```csharp\n"
                f"// ❌ Kötü (Update'de her kare çağrılıyor):\n"
                f"// {code}\n\n"
                f"// ✅ İyi — Awake'de bir kere bul, sonra field'ı kullan:\n"
                f"private Transform _{var};\n"
                f"void Awake() {{\n    _{var} = {expr};\n}}\n"
                f"```"
            )

        # ── Camera.main ───────────────────────────────────────────────────────
        if "Camera.main" in code:
            return (
                f"```csharp\n"
                f"// ❌ Kötü (her kullanımda kamerayı arar):\n"
                f"// {code}\n\n"
                f"// ✅ İyi — Awake'de cache et:\n"
                f"private Camera _cam;\n"
                f"void Awake() {{ _cam = Camera.main; }}\n"
                f"// Sonra Camera.main yerine _cam kullan\n"
                f"```"
            )

        # ── Vector3.Distance / Vector2.Distance ───────────────────────────────
        if re.search(r"Vector[23]\.Distance", code):
            m = re.search(r"(Vector[23])\.Distance\(([^,]+),\s*([^)]+)\)", code)
            if m:
                a, b = m.group(2).strip(), m.group(3).strip()
                return (
                    f"```csharp\n"
                    f"// ❌ Kötü (karekök hesaplar, her kare pahalı):\n"
                    f"// {code}\n\n"
                    f"// ✅ İyi — sqrMagnitude karekök hesaplamaz:\n"
                    f"float sqrDist = ({a} - {b}).sqrMagnitude;\n"
                    f"if (sqrDist < range * range) {{ /* ... */ }}\n"
                    f"```"
                )

        # ── new WaitForSeconds / WaitForEndOfFrame ────────────────────────────
        if re.search(r"new WaitFor\w+", code):
            m = re.search(r"new (WaitFor\w+)\(([^)]*)\)", code)
            if m:
                cls, arg = m.group(1), m.group(2)
                field_name = f"_wait{cls.replace('WaitFor', '')}"
                return (
                    f"```csharp\n"
                    f"// ❌ Kötü (her döngüde yeni GC allocation):\n"
                    f"// {code}\n\n"
                    f"// ✅ İyi — class field olarak bir kere oluştur:\n"
                    f"private {cls} {field_name} = new {cls}({arg});\n"
                    f"// while döngüsünde: yield return {field_name};\n"
                    f"```"
                )

        # ── SendMessage / BroadcastMessage ────────────────────────────────────
        if re.search(r"SendMessage\(|BroadcastMessage\(|SendMessageUpwards\(", code):
            m = re.search(r'(Send|Broadcast)Message\("(\w+)",?\s*([^)]*)\)', code)
            if m:
                method = m.group(2)
                arg = m.group(3).strip() or "value"
                return (
                    f"```csharp\n"
                    f"// ❌ Kötü (reflection, yavaş, yazım hatası yakalanmaz):\n"
                    f"// {code}\n\n"
                    f"// ✅ İyi — interface veya doğrudan GetComponent:\n"
                    f"var target = other.GetComponent<I{method}>();\n"
                    f"target?.{method}({arg});\n"
                    f"// Alternatif: C# event/delegate kullan\n"
                    f"```"
                )

        # ── transform.position = ... (Rigidbody varken) ───────────────────────
        if "transform.position" in code and "=" in code and "Distance" not in code:
            return (
                f"```csharp\n"
                f"// ❌ Kötü (Rigidbody varken fizik motorunu atlar):\n"
                f"// {code}\n\n"
                f"// ✅ İyi — Rigidbody ile hareket et:\n"
                f"rb.MovePosition(rb.position + direction * speed * Time.fixedDeltaTime);\n"
                f"// veya: rb.velocity = direction * speed;\n"
                f"```"
            )

        # ── transform.Translate (Rigidbody varken) ───────────────────────────
        if "transform.Translate" in code:
            return (
                f"```csharp\n"
                f"// ❌ Kötü (Rigidbody varken çarpışmaları bozar):\n"
                f"// {code}\n\n"
                f"// ✅ İyi:\n"
                f"rb.MovePosition(rb.position + direction * speed * Time.fixedDeltaTime);\n"
                f"```"
            )

        # ── GetComponent in Update ────────────────────────────────────────────
        if "GetComponent" in code:
            m = re.search(r"GetComponent<(\w+)>", code)
            comp = m.group(1) if m else "Component"
            field_name = f"_{comp[0].lower()}{comp[1:]}"
            return (
                f"```csharp\n"
                f"// ❌ Kötü (her karede component arar):\n"
                f"// {code}\n\n"
                f"// ✅ İyi — Awake'de cache et:\n"
                f"private {comp} {field_name};\n"
                f"void Awake() {{ {field_name} = GetComponent<{comp}>(); }}\n"
                f"```"
            )

        # ── Animator string params ────────────────────────────────────────────
        if re.search(r'(SetBool|SetFloat|SetTrigger|SetInteger|GetBool|GetFloat)\s*\("', code):
            m = re.search(r'(Set|Get)\w+\("(\w+)"', code)
            if m:
                param = m.group(2)
                return (
                    f"```csharp\n"
                    f"// ❌ Kötü (her çağrıda hash hesaplar):\n"
                    f"// {code}\n\n"
                    f"// ✅ İyi — hash'i bir kere hesapla:\n"
                    f"private static readonly int _{param}Hash = Animator.StringToHash(\"{param}\");\n"
                    f"// Kullanım: animator.SetXxx(_{param}Hash, value);\n"
                    f"```"
                )

        # ── public field ─────────────────────────────────────────────────────
        if code.startswith("public ") and "void " not in code and "(" not in code:
            fixed = code.replace("public ", "[SerializeField] private ", 1)
            return (
                f"```csharp\n"
                f"// ❌ Kötü (dışarıdan değiştirilebilir):\n"
                f"// {code}\n\n"
                f"// ✅ İyi (Inspector'da görünür, güvende):\n"
                f"{fixed}\n"
                f"```"
            )

        return ""

    @staticmethod
    def format_analysis(static_results: dict, original_code: str = "") -> str:
        """
        UnityAnalyzer sonuçlarını LLM'siz markdown yanıta çevirir.
        KB mode'da kullanıcı C# kod yapıştırdığında devreye girer.
        Her sorun için somut fix snippet + otomatik düzeltilmiş kod bloğu gösterir.

        original_code verilirse CodeFixer ile güvenli auto-fix uygulanır.
        """
        smells = static_results.get("smells", [])
        stats = static_results.get("stats", {})
        class_name = stats.get("class_name", "Script")
        total_lines = stats.get("total_lines", 0)
        has_update = stats.get("has_update", False)

        lines = [f"## 🔍 Statik Analiz — `{class_name}`"]
        lines.append(f"\n**{total_lines} satır** kod analiz edildi.")

        if has_update:
            lines.append("Bu script bir `Update()` döngüsü içeriyor.\n")

        if not smells:
            lines.append("\n### ✅ Sorun Bulunamadı")
            lines.append(
                "Statik analizde herhangi bir code smell veya performans sorunu tespit edilmedi. "
                "Kodun temiz görünüyor!"
            )
            lines.append(
                "\n> Daha derin bir analiz (AI destekli) için **Model Seç** menüsünden "
                "bir AI modeli seçebilirsin."
            )
            return "\n".join(lines)

        # Smell'leri kategorize et
        categories: dict[str, list] = {}
        for smell in smells:
            cat = smell.get("type", "Diğer")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(smell)

        lines.append(f"\n### 🚨 {len(smells)} Sorun Tespit Edildi\n")

        for cat, items in categories.items():
            lines.append(f"#### {cat} ({len(items)})\n")
            for item in items:
                line_num = item.get("line", "?")
                msg = item.get("msg", "")
                if line_num != "Genel":
                    lines.append(f"**Satır {line_num}:** {msg}\n")
                else:
                    lines.append(f"**Genel:** {msg}\n")

                # Somut fix snippet (kural tabanlı, AI yok)
                fix = KBEngine._generate_fix_snippet(item)
                if fix:
                    lines.append(fix)
                lines.append("")  # boş satır

        lines.append(
            "> Bu analiz yerel statik analiz motoruyla yapıldı (0ms, AI kullanılmadı). "
            "Daha detaylı öneriler ve düzeltilmiş kod için bir AI modeli seçebilirsin."
        )

        # ── Otomatik Düzeltilmiş Kod ─────────────────────────────────────────
        if original_code:
            fix_result = CodeFixer(original_code, smells).apply_all()
            if fix_result.changed:
                lines.append("\n---\n")
                lines.append(f"## 🔧 Otomatik Düzeltilmiş Kod ({len(fix_result.applied)} düzeltme uygulandı)\n")
                for a in fix_result.applied:
                    lines.append(f"- ✅ {a}")
                lines.append("")
                lines.append(f"```csharp\n{fix_result.fixed_code}\n```")
                if fix_result.manual:
                    lines.append("\n**⚠️ Manuel düzeltme gerektiren kalan sorunlar:**")
                    for m in fix_result.manual:
                        lines.append(f"- {m}")

        return "\n".join(lines)

    # ── Kod Tabanlı KB Eşleştirme ────────────────────────────────────────────

    # C# kodu içindeki Unity pattern'lerini KB entry ID'leriyle eşleştirir.
    # Her pattern → ilgili KB entry ID.
    _CODE_PATTERN_MAP: list[tuple[str, str]] = [
        (r"Rigidbody2D|CharacterController2D|coyoteTime|wallSlide", "character_controller_2d"),
        (r"CharacterController\b.*Mouse|Mouse.*CharacterController\b|CursorLockMode|cameraPitch", "character_controller_3d"),
        (r"AudioSource|AudioClip|PlayOneShot|sfxPool|PlayMusic", "audio_manager"),
        (r"File\.WriteAllText|JsonUtility\.ToJson|SaveData|persistentDataPath|JsonUtility\.FromJson", "save_load_system"),
        (r"CanvasGroup|UIManager|OpenPanel|ClosePanel|fadeDuration", "ui_manager"),
        (r"ItemData|InventorySlot|OnInventoryChanged|isStackable|maxStackSize", "inventory_system"),
        (r"WaveData|WaveManager|EnemyKilled|enemyCount|spawnInterval", "spawn_wave_system"),
        (r"DialogueLine|DialogueData|DialogueManager|typewriter|StartDialogue", "dialogue_system"),
        (r"SceneManager\.LoadScene|AsyncOperation|loadingScreen|LoadSceneAsync", "scene_manager"),
        (r"InputAction|InputSystem|PlayerInput|performed\.AddListener|rebind", "input_system"),
        (r"Projectile|BulletPool|Shoot\b|fireRate|muzzle", "projectile_shooting"),
        (r"Collectible|OnTriggerEnter.*collect|magnetRadius|PickUp", "collectible_pickup"),
        (r"AnimationController|SetBool.*anim|SetFloat.*anim|SetTrigger.*anim|blendTree", "animation_controller"),
        (r"ParallaxBackground|parallaxFactor|infiniteScroll|scrollSpeed.*layer", "parallax_background"),
        (r"NavMeshAgent|NavMesh\.SamplePosition|SetDestination|AStarGrid", "pathfinding"),
        (r"CountdownTimer|cooldownTimer|remainingTime|TimerManager", "timer_countdown"),
        (r"RenderTexture.*minimap|minimapCamera|MinimapIcon", "minimap"),
        (r"ObjectPool|Queue<GameObject>|_pools\[|Warmup\b|Return.*pool", "object_pooling"),
        (r"Singleton<|DontDestroyOnLoad", "singleton"),
        (r"enum\s+\w*State|switch.*currentState|FSM|IState\b", "state_machine"),
        (r"UnityEvent|System\.Action|delegate\s+\w|event\s+Action", "events_delegates"),
        (r"StartCoroutine|yield\s+return|IEnumerator", "coroutine_basic"),
        (r"CreateAssetMenu|ScriptableObject\b", "scriptable_object"),
        (r"smoothFollow|cameraOffset|ScreenShake|trauma\b", "camera_follow"),
        (r"Physics\.Raycast|Physics2D\.Raycast|RaycastHit\b", "raycast_basic"),
        (r"jumpForce|fallMultiplier|jumpBuffer|coyoteTime", "jump_mechanics"),
        (r"IDamageable|TakeDamage|maxHealth|invincibilityDuration", "health_system"),
        (r"rb\.linearVelocity|_rb\.velocity|moveSpeed.*FixedUpdate|GetAxisRaw.*Horizontal", "movement_basic"),
    ]

    def lookup_for_code(self, code: str) -> Optional[KBResult]:
        """
        Mevcut C# koduna en uygun KB referans şablonunu bulur.

        Kullanım: Kullanıcı kod yapıştırdığında, statik analiz sonrası
        "Doğru implementasyon şu" şeklinde KB'den referans göstermek için.

        Önce deterministik pattern eşleştirme (regex) dener.
        Pattern bulamazsa token tabanlı normal lookup'a düşer.
        """
        import re as _re

        # 1. Önce deterministik pattern map ile dene
        for pattern, entry_id in self._CODE_PATTERN_MAP:
            if _re.search(pattern, code):
                # Entry ID ile doğrudan KB'den çek
                for entry in self._entries:
                    if entry["id"] == entry_id:
                        logger.info(f"[KBEngine] lookup_for_code HIT → '{entry_id}' (pattern: {pattern[:30]})")
                        return KBResult(
                            entry_id=entry["id"],
                            title=entry["title"],
                            explanation=entry.get("explanation", ""),
                            code=entry.get("code", ""),
                            tips=entry.get("tips", []),
                            unity_version=entry.get("unity_version", "2021.3+"),
                            score=1.0,
                            matched_keywords=[pattern[:30]],
                            setup_steps=entry.get("setup_steps", []),
                        )

        # 2. Fallback: kod metnini normal lookup'a gönder
        logger.info("[KBEngine] lookup_for_code: pattern miss → token lookup fallback")
        return self.lookup(code, intent="chat")

    def format_fix_response(self, analysis_text: str, kb_result: KBResult) -> str:
        """
        Statik analiz raporu + KB referans implementasyonunu birleştirir.

        Kullanıcıya şunu gösterir:
          1. Analizde bulunan sorunlar
          2. Bu sistem türü için doğru/referans implementasyon
        """
        lines = [
            analysis_text,
            "\n---\n",
            f"## ✅ Referans İmplementasyon: {kb_result.title}",
            "\nBu sistem türü için önerilen temiz implementasyon:\n",
        ]

        if kb_result.explanation:
            lines.append(f"{kb_result.explanation}\n")

        if kb_result.code:
            lines.append(f"```csharp\n{kb_result.code}\n```")

        if kb_result.tips:
            lines.append("\n### 💡 Dikkat Edilecekler")
            for tip in kb_result.tips:
                lines.append(f"- {tip}")

        lines.append(f"\n> Unity {kb_result.unity_version} için optimize edilmiş referans kod.")

        return "\n".join(lines)

    # ── Geçiş Mesajı ─────────────────────────────────────────────────────────
    @staticmethod
    def fallback_message(intent: str = "chat") -> str:
        """
        KB miss olduğunda kullanıcıya gösterilecek geçiş mesajı.
        Bu mesaj pipeline response'ının önüne eklenmez —
        main.py'da ayrı bir log/UI mesajı olarak kullanılabilir.
        """
        if intent == "generation":
            return (
                "Bu istek bilgi bankamda yok. "
                "AI asistanımı devreye alıyorum, lütfen bekleyin..."
            )
        return (
            "Bu konu bilgi bankamda yer almıyor. "
            "AI asistanımı devreye alıyorum..."
        )

    # ── Debug / İstatistik ────────────────────────────────────────────────────
    def stats(self) -> dict:
        """Yüklü KB hakkında özet bilgi döner (debug için)."""
        return {
            "total_entries": len(self._entries),
            "entry_ids": [e["id"] for e in self._entries],
        }
