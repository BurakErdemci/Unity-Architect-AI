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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
    score: float          # 0.0 - 1.0 arasında güven skoru
    matched_keywords: list


# ─── KB Engine ───────────────────────────────────────────────────────────────
class KBEngine:
    """
    Unity bilgi bankası motoru.

    Startup'ta JSON'ı tek seferinde yükler.
    Her lookup() çağrısı O(n * k) karmaşıklığında çalışır
    (n = entry sayısı, k = keyword sayısı — her ikisi de küçük).
    """

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
        candidates: list[tuple[float, KBResult]] = []

        for entry in self._entries:
            # Bu entry istenilen intent'i destekliyor mu?
            supported_intents = entry.get("intent_types", ["chat", "generation"])
            if intent not in supported_intents:
                continue

            score, matched = self._score(tokens, entry)

            if score > 0:
                candidates.append((score, KBResult(
                    entry_id=entry["id"],
                    title=entry["title"],
                    explanation=entry.get("explanation", ""),
                    code=entry.get("code", ""),
                    tips=entry.get("tips", []),
                    unity_version=entry.get("unity_version", "2021.3+"),
                    score=score,
                    matched_keywords=matched,
                )))

        if not candidates:
            logger.info(f"[KBEngine] Miss → intent={intent}, tokens={list(tokens)[:5]}")
            return None

        # En yüksek skor
        best_score, best_result = max(candidates, key=lambda x: x[0])
        logger.info(
            f"[KBEngine] Hit → '{best_result.title}' "
            f"(skor={best_score:.2f}, eşleşen={best_result.matched_keywords})"
        )
        return best_result

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
        """
        matched = set()
        for kw in keywords:
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

        if r.tips:
            lines.append("\n### Önemli Notlar")
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

        if r.tips:
            lines.append("\n### İpuçları")
            for tip in r.tips:
                lines.append(f"- {tip}")

        lines.append(f"\n> Unity {r.unity_version} için geçerlidir.")

        return "\n".join(lines)

    # ── Statik Analiz Formatlama ─────────────────────────────────────────────
    @staticmethod
    def format_analysis(static_results: dict) -> str:
        """
        UnityAnalyzer sonuçlarını LLM'siz markdown yanıta çevirir.
        KB mode'da kullanıcı C# kod yapıştırdığında devreye girer.
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
            lines.append(f"#### {cat} ({len(items)})")
            for item in items:
                line_num = item.get("line", "?")
                msg = item.get("msg", "")
                if line_num != "Genel":
                    lines.append(f"- **Satır {line_num}:** {msg}")
                else:
                    lines.append(f"- **Genel:** {msg}")
            lines.append("")  # boş satır

        lines.append(
            "> Bu analiz yerel statik analiz motoruyla yapıldı (0ms, AI kullanılmadı). "
            "Daha detaylı öneriler ve düzeltilmiş kod için bir AI modeli seçebilirsin."
        )

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
