"""
Report Engine — Ağırlıklı puanlama ve rapor üretimi.
Statik analiz sonuçlarını alır, deterministik (AI'dan bağımsız) puan hesaplar.
"""

from typing import List, Dict, Any
from collections import Counter
import time


# ─── AĞIRLIK TABLOSU ───
# Kategori bazında ağırlık: ne kadar yüksekse, o kategorideki hata puanı o kadar düşürür.
CATEGORY_WEIGHTS = {
    "performance":    3.0,   # En kritik — FPS'i doğrudan etkiler
    "physics":        2.5,   # Fizik hataları oynanışı bozar
    "logic":          2.5,   # Mantık hataları bug'a yol açar
    "architecture":   2.0,   # Mimari sorunlar bakımı zorlaştırır
    "best_practice":  1.5,   # İyi pratikler kod kalitesini artırır
    "style":          1.0,   # Stil önerileri en az kritik
}

# ─── SEVERITY SEVİYELERİ ───
SEVERITY_LEVELS = {
    "critical": {"label": "🔴 Kritik", "weight": 3.0, "description": "Oyunu bozabilir"},
    "warning":  {"label": "🟡 Uyarı",  "weight": 1.5, "description": "Performans/kalite sorunu"},
    "info":     {"label": "🔵 Bilgi",   "weight": 0.5, "description": "İyileştirme önerisi"},
}

# Hangi tip mesajlar hangi severity'ye gider?
SEVERITY_MAP = {
    "⚡ Performans":   "warning",
    "🔧 Düzeltme":     "warning",
    "🐛 Mantık Hatası": "critical",
    "🎯 Fizik":        "warning",
    "💡 Öneri":        "info",
}

# Hangi tip mesajlar hangi kategoriye gider?
CATEGORY_MAP = {
    "⚡ Performans":   "performance",
    "🔧 Düzeltme":     "best_practice",
    "🐛 Mantık Hatası": "logic",
    "🎯 Fizik":        "physics",
    "💡 Öneri":        "style",
}


class ReportEngine:
    """Statik analiz sonuçlarından deterministik skor ve rapor üretir."""

    @staticmethod
    def classify_smell(smell: Dict[str, Any]) -> Dict[str, Any]:
        """Bir smell'e severity ve category bilgisi ekler."""
        smell_type = smell.get("type", "")
        return {
            **smell,
            "severity": SEVERITY_MAP.get(smell_type, "info"),
            "category": CATEGORY_MAP.get(smell_type, "style"),
        }

    @staticmethod
    def classify_all(smells: List[Dict]) -> List[Dict]:
        """Tüm smell'leri sınıflandırır."""
        return [ReportEngine.classify_smell(s) for s in smells]

    @staticmethod
    def calculate_score(smells: List[Dict]) -> float:
        """
        0-10 arası ağırlıklı puan hesaplar.
        Hata yoksa 10, her hata ağırlığına göre puanı düşürür.
        Aynı kategoride tekrar eden hatalar azalan ceza alır (diminishing returns).
        """
        if not smells:
            return 10.0

        classified = ReportEngine.classify_all(smells)
        
        # Kategori bazında ceza biriktir (diminishing returns)
        category_counts: Dict[str, int] = {}
        total_penalty = 0.0

        for smell in classified:
            category = smell.get("category", "style")
            severity = smell.get("severity", "info")

            cat_weight = CATEGORY_WEIGHTS.get(category, 1.0)
            sev_weight = SEVERITY_LEVELS.get(severity, {}).get("weight", 0.5)

            # Aynı kategoriden kaçıncı hata?
            category_counts[category] = category_counts.get(category, 0) + 1
            count = category_counts[category]

            # Diminishing returns: ilk hata tam ceza, sonrakiler azalır
            # 1. hata: ×1.0, 2. hata: ×0.5, 3.: ×0.33, 4.: ×0.25 ...
            diminish_factor = 1.0 / count

            # Ceza = kategori ağırlığı × severity ağırlığı × azaltma × temel çarpan
            total_penalty += cat_weight * sev_weight * diminish_factor * 0.2

        # Puan: 10 - toplam ceza, minimum 0
        score = max(0.0, 10.0 - total_penalty)
        return round(score, 1)

    @staticmethod
    def get_severity_counts(smells: List[Dict]) -> Dict[str, int]:
        """Severity bazlı sayaç döndürür."""
        classified = ReportEngine.classify_all(smells)
        counts = Counter(s.get("severity", "info") for s in classified)
        return {
            "critical": counts.get("critical", 0),
            "warning":  counts.get("warning", 0),
            "info":     counts.get("info", 0),
        }

    @staticmethod
    def get_category_scores(smells: List[Dict]) -> Dict[str, float]:
        """
        Kategori bazlı skor döndürür; 0-10 arası.
        Her kategori kendi içinde değerlendirilir.
        """
        classified = ReportEngine.classify_all(smells)

        category_penalties: Dict[str, float] = {}
        for smell in classified:
            cat = smell.get("category", "style")
            sev = smell.get("severity", "info")
            penalty = SEVERITY_LEVELS.get(sev, {}).get("weight", 0.5) * 0.5
            category_penalties[cat] = category_penalties.get(cat, 0) + penalty

        # Her kategoriye 10 üzerinden puan ver
        scores = {}
        for cat in CATEGORY_WEIGHTS:
            penalty = category_penalties.get(cat, 0)
            scores[cat] = round(max(0.0, 10.0 - penalty), 1)

        return scores

    @staticmethod
    def generate_summary(smells: List[Dict]) -> str:
        """İnsan tarafından okunabilir özet üretir."""
        if not smells:
            return "✅ Kodda herhangi bir sorun bulunamadı. Harika iş!"

        classified = ReportEngine.classify_all(smells)
        category_counts = Counter(s.get("category", "style") for s in classified)

        category_labels = {
            "performance": "performans",
            "physics": "fizik",
            "logic": "mantık",
            "architecture": "mimari",
            "best_practice": "best practice",
            "style": "stil",
        }

        parts = []
        for cat, count in category_counts.most_common():
            label = category_labels.get(cat, cat)
            parts.append(f"{count} {label}")

        return f"Toplam {len(smells)} bulgu: {', '.join(parts)}."

    @staticmethod
    def build_report(smells: List[Dict], duration_ms: int = 0) -> Dict[str, Any]:
        """Tam rapor nesnesi üretir."""
        return {
            "score": ReportEngine.calculate_score(smells),
            "score_breakdown": ReportEngine.get_category_scores(smells),
            "severity_counts": ReportEngine.get_severity_counts(smells),
            "total_smells": len(smells),
            "summary": ReportEngine.generate_summary(smells),
            "step1_duration_ms": duration_ms,
        }
