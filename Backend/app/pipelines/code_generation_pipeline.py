import logging
import re
import asyncio
from typing import Any

from pipelines.base import BasePipeline, PipelineResult, StepResult
from pipelines.agents.architect_generation import ArchitectGenerationAgent
from pipelines.agents.clarification_gate import ClarificationGateAgent
from pipelines.agents.coder_generation import CoderGenerationAgent
from pipelines.agents.game_feel_agent import GameFeelAgent
from prompts import get_language_instr, get_relevant_rules
from validator import ResponseValidator

logger = logging.getLogger(__name__)

class CodeGenerationPipeline(BasePipeline):
    """
    Sıfırdan kod üretmek için kullanılan Multi-Agent sistemi.
    0. Clarification Gate: Eksik detay varsa pipeline'ı durdurur, kullanıcıya soru sorar
    1. Architect (Mimar): Kodu planlar
    2. Coder (Yazılımcı): Plana göre kodu üretir
    3. Game Feel Agent (Sessiz): Kodu değerlendirir, düşük skorsa Coder'a geri gönderir
    """

    GAME_FEEL_THRESHOLD = 7.0  # Bu skorun altındaysa Coder tekrar yazar
    BATCH_SIZE = 10            # Tek seferde max yazılacak dosya sayısı

    def __init__(
        self,
        prompt: str,
        provider: Any,
        language: str = "tr",
        context: str = "",
        user_message: str = "",
        provider_type: str = "unknown",
        progress_callback=None,
        scope_confirmed: bool = False,
        coding_provider: Any = None,        # Coder + GameFeel için ayrı provider (opsiyonel)
        coding_provider_type: str = "",     # Örn: "openrouter"
        existing_plan: str = "",            # Scope onayında architect tekrar çalışmasın
        batch_files: list = None,           # Sadece bu dosyaları yaz (continuation modu)
        skip_gate: bool = False,            # Gate daha önce soru sorduysa tekrar çalıştırma
    ):
        super().__init__("", "", provider, language, context, "", user_message, provider_type, progress_callback)
        self.prompt = prompt
        self.scope_confirmed = scope_confirmed
        self.existing_plan = existing_plan
        self.batch_files = batch_files or []
        self.skip_gate = skip_gate

        # Hybrid provider: planlama Claude, kod yazma OpenRouter gibi
        _coding = coding_provider or provider
        self.coding_provider_type = coding_provider_type or provider_type

        # Ajanları başlat — planlama ajanları her zaman ana provider'ı kullanır
        self.gate = ClarificationGateAgent(self.provider)
        self.architect = ArchitectGenerationAgent(self.provider)
        self.coder = CoderGenerationAgent(_coding)
        self.game_feel = GameFeelAgent(_coding)

    _TOKEN_LIMITS = {
        "groq": 32000,
        "openai": 16384,
        "openrouter": 16384,
        "deepseek": 16384,
        "anthropic": 16384,
        "google": 65536,
        "ollama": -1,
    }

    def _get_coder_max_tokens(self) -> int:
        return self._TOKEN_LIMITS.get(self.coding_provider_type, 16384)

    async def run(self) -> PipelineResult:
        logger.info("✨ CodeGenerationPipeline başlatılıyor...")

        rules_str = get_relevant_rules(self.prompt)
        lang_instr = get_language_instr(self.language)

        # --- ADIM 0: CLARIFICATION GATE (batch/continuation/skip modunda atla) ---
        if not self.batch_files and not self.skip_gate:
            logger.info("  Step 0: Clarification Gate kontrol ediliyor...")
            gate_result = await asyncio.to_thread(
                self.gate.check,
                self.prompt,
                self.context or "",
            )

            if gate_result.get("status") == "NEEDS_CLARIFICATION":
                questions = gate_result.get("questions", [])
                formatted = self.gate.format_questions(questions)
                logger.info(f"  [Gate] NEEDS_CLARIFICATION — {len(questions)} soru döndürüldü.")
                self._result.clarification_needed = True
                self._result.clarification_questions = formatted
                self._result.combined_response = formatted
                return self._result

            logger.info("  [Gate] PROCEED — Architect başlatılıyor.")

        # --- ADIM 1: ARCHITECT PLANLAMASI (batch/onay senaryosunda atla) ---
        if self.existing_plan or self.batch_files:
            plan = self.existing_plan
            logger.info("  Step 1: Mevcut plan kullanılıyor (Architect atlandı).")
            if self.progress_callback: self.progress_callback("step1", "completed", 0)
        else:
            if self.progress_callback: self.progress_callback("step1", "in-progress")
            start1 = asyncio.get_event_loop().time()
            logger.info("  Step 1: Architect Planı oluşturuluyor...")
            plan = await asyncio.to_thread(
                self.architect.plan_architecture,
                self.prompt,
                lang_instr,
                rules_str
            )
            dur1 = int((asyncio.get_event_loop().time() - start1) * 1000)
            if self.progress_callback: self.progress_callback("step1", "completed", dur1)
        self._result.step2_analysis = StepResult("Mimari Plan", True, 0, plan)

        # --- SCOPE CHECK: Çok büyük sistemlerde onay iste, diğerlerinde bilgi ver ---
        planned_files = self._count_planned_files(plan) if plan else []
        self._result.all_planned_files = planned_files

        # batch_files verilmişse scope check atla (continuation modu)
        if not self.batch_files and len(planned_files) >= 15 and not self.scope_confirmed:
            logger.info(f"  [Scope] {len(planned_files)} dosya planlandı — kullanıcı onayı bekleniyor.")
            warning_msg = self._format_scope_warning(planned_files)
            self._result.scope_warning = True
            self._result.scope_warning_plan = plan
            self._result.scope_file_count = len(planned_files)
            self._result.combined_response = warning_msg
            return self._result

        # --- BATCH SPLIT: İlk çalıştırmada BATCH_SIZE'a göre böl ---
        if self.batch_files:
            # Continuation modu: sadece verilen dosyaları yaz
            active_files = self.batch_files
            logger.info(f"  [Batch] Continuation modu — {len(active_files)} dosya yazılacak: {active_files}")
        elif len(planned_files) > self.BATCH_SIZE:
            # İlk çalıştırma: ilk batch'i al, kalanları kaydet
            active_files = planned_files[:self.BATCH_SIZE]
            remaining = planned_files[self.BATCH_SIZE:]
            self._result.has_continuation = True
            self._result.remaining_files = remaining
            logger.info(f"  [Batch] {len(planned_files)} dosya planlandı — ilk {len(active_files)} yazılıyor, {len(remaining)} kaldı.")
        else:
            active_files = planned_files

        # --- ADIM 2: CODER + GAME FEEL SILENT LOOP ---
        MAX_ATTEMPTS = 2
        final_response = ""
        gf_score = 10.0  # Varsayılan: yeterli
        gf_result = {}

        # Coder'a sadece active_files kısıtını ver
        files_constraint = ""
        if active_files:
            files_list = ", ".join(active_files)
            files_constraint = (
                f"\n\n[KAPSAM KISITI — KESİNLİKLE UYULMALI]\n"
                f"Sadece şu {len(active_files)} dosyayı üret: {files_list}\n"
                f"Bu listede OLMAYAN hiçbir dosya üretme — interface, base class, helper dahil.\n"
                f"Listenin dışına çıkmak yasaktır. Fazladan dosya eklersen sistem bozulur.\n"
                f"Listedeki her dosyanın içeriğini tam ve eksiksiz yaz."
            )

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self.progress_callback: self.progress_callback("step2", "in-progress")
            start2 = asyncio.get_event_loop().time()
            if attempt == 1:
                logger.info("  Step 2: Coder Kodu üretiyor...")
                current_plan = plan + files_constraint
            else:
                logger.info(f"  Step 2 (Retry): 🎮 Game Feel düşük ({gf_score:.1f}), Coder mevcut kodu düzeltiyor...")
                suggestions = "\n".join(f"- {s}" for s in gf_result.get("suggestions", []))
                movement = gf_result.get("movement", {})
                combat = gf_result.get("combat", {})
                physics = gf_result.get("physics", {})

                # Önceki kodu coder'a göster — sıfırdan yazmasın, sadece düzeltsin
                prev_code_section = f"\n\n[ÖNCEKİ KOD — BU KODU TEMEL AL]\n{final_response}\n"

                game_feel_feedback = f"""

[🎮 OYUN HİSSİYATI DÜZELTMESİ]
Skor: {gf_score:.1f}/10 — Yetersiz.

Hareket: {movement.get('verdict', '?')} — {movement.get('detail', '')}
Combat: {combat.get('verdict', '?')} — {combat.get('detail', '')}
Fizik: {physics.get('verdict', '?')} — {physics.get('detail', '')}

Düzeltme talimatları:
{suggestions}
- rb.velocity veya CharacterController kullan, AddForce KULLANMA
- Gravity multiplier ekle (havada asılı kalmasın)
- Input anında tepki versin (snappy)

[KESİNLİKLE UYULMALI]
- Yukarıdaki ÖNCEKİ KODU temel al, sıfırdan yazma.
- Oyun hissiyatını etkileyen kısımları düzelt.
- Dosya sayısını ve isimlerini ASLA değiştirme.
- Düzeltilmiş veya düzeltilmemiş BÜTÜN dosyaları eksiksiz yaz (hiçbirini atma).
"""
                current_plan = plan + files_constraint + prev_code_section + game_feel_feedback

            final_response = await asyncio.to_thread(
                self.coder.generate_code,
                self.prompt,
                current_plan,
                lang_instr,
                rules_str,
                max_tokens=self._get_coder_max_tokens()
            )
            dur2 = int((asyncio.get_event_loop().time() - start2) * 1000)
            if self.progress_callback: self.progress_callback("step2", "completed", dur2)
            
            # Game Feel değerlendirmesi (sessiz — kullanıcıya gösterilmez)
            # Sadece hareket/combat içeren kodlarda çalıştır
            code_block = self._extract_csharp(final_response)
            has_gameplay = self._has_gameplay_code(final_response)
            if code_block and len(code_block.strip()) > 20 and attempt < MAX_ATTEMPTS and has_gameplay:
                if self.progress_callback: self.progress_callback("step3", "in-progress")
                start3 = asyncio.get_event_loop().time()
                logger.info(f"  [Game Feel Check] Deneme {attempt}: Sessiz değerlendirme...")
                gf_result = await asyncio.to_thread(
                    self.game_feel.evaluate,
                    code=code_block,
                    context=self.prompt
                )
                dur3 = int((asyncio.get_event_loop().time() - start3) * 1000)
                gf_score = gf_result.get("game_feel_score", 10.0)
                logger.info(f"  [Game Feel Check] Skor: {gf_score:.1f}/10 (Eşik: {self.GAME_FEEL_THRESHOLD})")
                
                if gf_score >= self.GAME_FEEL_THRESHOLD:
                    if self.progress_callback: self.progress_callback("step3", "completed", dur3)
                    logger.info(f"  ✅ Game Feel yeterli, loop sonlandırıldı (deneme {attempt})")
                    break
                else:
                    if self.progress_callback: 
                        self.progress_callback("step3", "pending")
                        self.progress_callback("step2", "in-progress")
                # else: döngü devam eder, Coder tekrar yazar
            else:
                break
        
        final_response = self._fix_truncated_response(final_response)
        self._result.step3_code_fix = StepResult("Kod Üretimi", True, 0, final_response)

        # Dosya listesi bilgi prefix'i — kullanıcıya ne üretildiğini göster
        if active_files:
            plan_prefix = self._format_plan_prefix(active_files)
            final_response = plan_prefix + final_response

        # Finalize — kullanıcıya sadece temiz kod gösterilir
        self._result.analysis_text = final_response
        self._result.combined_response = final_response

        return self._result

    def _count_planned_files(self, plan: str) -> list:
        """Plan metnindeki 'DOSYALAR: ...' satırından dosya listesini çıkarır.
        Bulunamazsa fallback olarak .cs referanslarını say."""
        primary_files = []

        # Birincil: DOSYALAR: bloğunu çok satırlı olarak yakala
        # Architect bazen 29 dosyayı birden fazla satıra bölebilir
        match = re.search(r'DOSYALAR\s*:\s*(.+?)(?:\n\n|\Z)', plan, re.IGNORECASE | re.DOTALL)
        if match:
            raw = match.group(1)
            # Hem | hem satır sonu hem virgül ayraçlarını destekle
            parts = re.split(r'[|\n,]+', raw)
            files = [f.strip() for f in parts if f.strip() and not f.strip().startswith('#')]
            # .cs uzantısı yoksa ekle, sadece gerçek dosya isimlerini al
            files = [
                (f if f.endswith('.cs') else f + '.cs')
                for f in files
                if re.match(r'^[A-Za-z][A-Za-z0-9_]*(?:\.cs)?$', f.strip())
            ]
            primary_files = files

        # Fallback: tüm .cs referanslarını bul
        fallback_matches = re.findall(r'\b[A-Za-z][A-Za-z0-9_]*\.cs\b', plan)
        fallback_files = list(dict.fromkeys(fallback_matches))

        # İkisinden daha büyük olanı kullan (architect satırı böldüyse fallback daha doğru olabilir)
        if len(primary_files) >= len(fallback_files):
            result = primary_files
            logger.info(f"  [Scope] DOSYALAR satırından {len(result)} dosya tespit edildi.")
        else:
            result = fallback_files
            logger.info(f"  [Scope] Fallback regex ile {len(result)} dosya tespit edildi (DOSYALAR satırı: {len(primary_files)}).")

        return result

    def _format_plan_prefix(self, files: list) -> str:
        """Üretilen dosyaları yanıtın başına bilgi olarak ekler."""
        n = len(files)
        if n <= 1:
            return ""
        file_list = " · ".join(f"`{f}`" for f in files)
        return (
            f"📦 **{n} dosya üretildi:** {file_list}\n\n"
            f"---\n\n"
        )

    def _format_scope_warning(self, files: list) -> str:
        """Scope uyarı mesajını formatlar."""
        n = len(files)
        file_list = "\n".join(f"- `{f}`" for f in files)
        token_est = "çok yüksek (💸)" if n >= 15 else "yüksek ⚠️"
        return (
            f"📋 **Mimari Plan Hazır — Onay Gerekiyor**\n\n"
            f"Planlanan sistem **{n} dosya** içeriyor:\n\n"
            f"{file_list}\n\n"
            f"---\n"
            f"⚠️ Bu boyutta bir sistem **token kullanımı {token_est}** gerektirebilir.\n\n"
            f"Nasıl devam edelim?\n\n"
            f"**✅ Tam Sistemi Üret** → Tüm {n} dosyayı üret *(yüksek token)*\n\n"
            f"**⚡ Basit Versiyon** → Sadece 4-5 temel dosya *(hızlı ve hafif)*\n\n"
            f"<!-- SCOPE_WARNING_ACTIVE -->"
        )

    def _is_truncated(self, text: str) -> bool:
        """Yanıtın token limitinde kesilip kesilmediğini kontrol eder (açık ``` bloğu var mı)."""
        if not text:
            return False
        blocks = re.findall(r'```', text)
        return len(blocks) % 2 == 1

    def _fix_truncated_response(self, text: str) -> str:
        """Kesilmiş yanıtı kapatır ve kullanıcıya devam mesajı ekler."""
        if not self._is_truncated(text):
            return text
        logger.warning("  [Truncation] Yanıt token limitinde kesildi — devam mesajı ekleniyor.")
        fixed = text.rstrip() + "\n// ... (yanıt kesildi)\n```"
        fixed += (
            "\n\n---\n"
            "⏳ **Token limitine ulaşıldı — yanıt kesildi.**\n\n"
            "Kalan dosyaları yazmamı ister misin? **Devam et** yazman yeterli. ✋"
        )
        return fixed

    def _has_gameplay_code(self, text: str) -> bool:
        """Kodun GameFeel değerlendirmesine tabi tutulacak hareket/combat içerip içermediğini kontrol eder."""
        gameplay_keywords = [
            "Rigidbody", "CharacterController", "rb.velocity", "AddForce",
            "Input.Get", "GetAxis", "OnTriggerEnter", "OnCollisionEnter",
            "NavMeshAgent", "Animator", "animator.", "FixedUpdate",
            "TakeDamage", "Attack", "Combat", "Health", "Enemy", "Player",
            "Jump", "Move", "Shoot", "Ability", "Skill", "Weapon",
        ]
        text_lower = text.lower()
        hits = sum(1 for kw in gameplay_keywords if kw.lower() in text_lower)
        return hits >= 3  # En az 3 gameplay keyword varsa gerçek gameplay kodu

    def _extract_csharp(self, text: str) -> str:
        """Markdown'daki C# kod bloğunu çıkarır."""
        if not text:
            return ""
        match = re.search(r'```(?:csharp|cs)\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
