from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class StepResult:
    """Tek bir pipeline adımının sonucunu tutar."""
    step_name: str
    success: bool
    duration_ms: int
    output: Any = None
    error: Optional[str] = None

@dataclass
class PipelineResult:
    """Pipeline'ın tam sonucunu tutar."""
    # Adım sonuçları
    step1_static: Optional[StepResult] = None
    step2_analysis: Optional[StepResult] = None
    step3_code_fix: Optional[StepResult] = None
    step4_critique: Optional[StepResult] = None

    # Birleşik rapor
    score: float = 10.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    severity_counts: Dict[str, int] = field(default_factory=dict)
    total_smells: int = 0
    summary: str = ""
    total_duration_ms: int = 0

    # Final çıktılar
    analysis_text: str = ""   # Açıklama
    fixed_code: str = ""      # Düzeltilmiş kod
    combined_response: str = ""  # Frontend'e gösterilecek birleşik metin

    # Self-Critique verileri (Single Agent Enhanced)
    game_feel_data: Optional[Dict] = None  # Game Feel kategorileri
    retry_count: int = 0  # Kaç deneme yapıldı

    # Clarification Gate (Phase 9)
    clarification_needed: bool = False   # True ise pipeline durduruldu
    clarification_questions: str = ""    # Kullanıcıya gösterilecek soru metni

    # Scope Warning (Phase 9 — Token Maliyet Kontrolü)
    scope_warning: bool = False          # True ise plan büyük, kullanıcı onayı bekleniyor
    scope_warning_plan: str = ""         # Architect planı (devam seçilirse kullanılır)
    scope_file_count: int = 0            # Planlanan dosya sayısı

    # Batch Continuation — çok dosyalı sistemlerde kademeli üretim
    has_continuation: bool = False               # True ise daha yazılacak dosya var
    remaining_files: list = field(default_factory=list)   # Kalan dosyalar
    all_planned_files: list = field(default_factory=list) # Architect'in tam dosya listesi

    def to_dict(self) -> Dict[str, Any]:
        """Frontend'e gönderilecek pipeline bilgisini döndürür."""
        return {
            "score": self.score,
            "score_breakdown": self.score_breakdown,
            "severity_counts": self.severity_counts,
            "total_smells": self.total_smells,
            "summary": self.summary,
            "total_duration_ms": self.total_duration_ms,
            "steps": {
                "step1": {
                    "name": "Statik Analiz",
                    "duration_ms": self.step1_static.duration_ms if self.step1_static else 0,
                    "success": self.step1_static.success if self.step1_static else False,
                },
                "step2": {
                    "name": "Derin AI Analizi",
                    "duration_ms": self.step2_analysis.duration_ms if self.step2_analysis else 0,
                    "success": self.step2_analysis.success if self.step2_analysis else False,
                },
                "step3": {
                    "name": "Kod Düzeltme",
                    "duration_ms": self.step3_code_fix.duration_ms if self.step3_code_fix else 0,
                    "success": self.step3_code_fix.success if self.step3_code_fix else False,
                },
                "step4": {
                    "name": "Self-Critique",
                    "duration_ms": self.step4_critique.duration_ms if self.step4_critique else 0,
                    "success": self.step4_critique.success if self.step4_critique else False,
                },
            },
            "game_feel_data": self.game_feel_data,
            "retry_count": self.retry_count,
        }

class BasePipeline:
    """Tüm pipeline sınıfları için temel arayüz"""
    def __init__(self, prompt: str = "", code: str = "", provider: Any = None,
                 language: str = "tr", context: str = "", learned_rules: str = "",
                 user_message: str = "", provider_type: str = "", progress_callback=None):
        self.prompt = prompt
        self.code = code
        self.provider = provider
        self.language = language
        self.context = context
        self.learned_rules = learned_rules
        self.user_message = user_message
        self.provider_type = provider_type
        self.progress_callback = progress_callback
        
        self._result = PipelineResult()

    async def run(self) -> PipelineResult:
        raise NotImplementedError("run() methodu alt sınıflarda implement edilmelidir.")
