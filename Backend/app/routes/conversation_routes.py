import asyncio
import logging

from fastapi import APIRouter, Header

from ai_providers import AIProviderManager
from analyzer import UnityAnalyzer
from auth_utils import require_conversation_owner, require_user
from code_detector import CodeDetector
from pipelines import (
    CodeGenerationPipeline,
    MultiAgentPipeline,
    SingleAgentCodeGenerationPipeline,
    SingleAgentPipeline,
)
from pipelines.agents.intent_classifier import IntentClassifierAgent
from prompts import (
    PROMPT_ANALYZE,
    PROMPT_GREETING,
    PROMPT_OUT_OF_SCOPE,
    SYSTEM_PROMPT,
    get_language_instr,
    get_relevant_rules,
)
from schemas import ChatRequest, NewConversationRequest, RenameRequest


logger = logging.getLogger(__name__)


scope_plan_store: dict = {}        # conversation_id → {plan, original_prompt}
continuation_store: dict = {}      # conversation_id → {plan, all_files, next_start, original_prompt}
BATCH_SIZE = 10


def _is_batch_continuation_msg(msg: str) -> bool:
    """Kullanıcının batch devam isteği gönderip göndermediğini kontrol eder."""
    msg_lower = msg.strip().lower()
    if len(msg_lower) > 150:
        return False
    triggers = ["devam et", "continue", "kalan dosyaları", "sonraki dosyaları", "next batch"]
    return any(t in msg_lower for t in triggers)


def create_conversation_router(db, kb, progress_store):
    router = APIRouter()

    @router.get("/chat-progress/{conv_id}")
    async def get_chat_progress(conv_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_conversation_owner(db, x_session_token, conv_id)
        return progress_store.get(conv_id, [])

    @router.post("/conversations")
    async def create_conversation(req: NewConversationRequest, x_session_token: str = Header(alias="X-Session-Token")):
        user_id, _ = require_user(db, x_session_token, req.user_id)
        conv_id = db.create_conversation(user_id, req.title)
        return {"id": conv_id, "title": req.title, "status": "success"}

    @router.get("/conversations/{user_id}")
    async def get_conversations(user_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_user(db, x_session_token, user_id)
        return db.get_user_conversations(user_id)

    @router.get("/conversations/{conv_id}/messages")
    async def get_messages(conv_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_conversation_owner(db, x_session_token, conv_id)
        return db.get_conversation_messages(conv_id)

    @router.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: int, x_session_token: str = Header(alias="X-Session-Token")):
        require_conversation_owner(db, x_session_token, conv_id)
        db.delete_conversation(conv_id)
        return {"status": "success"}

    @router.put("/conversations/{conv_id}")
    async def rename_conversation(conv_id: int, req: RenameRequest, x_session_token: str = Header(alias="X-Session-Token")):
        require_conversation_owner(db, x_session_token, conv_id)
        db.rename_conversation(conv_id, req.title)
        return {"status": "success"}

    @router.post("/chat")
    async def chat(request: ChatRequest, x_session_token: str = Header(alias="X-Session-Token")):
        user_id, _ = require_user(db, x_session_token, request.user_id)
        require_conversation_owner(db, x_session_token, request.conversation_id)
        logger.info(f"Chat İsteği - User: {user_id}, Conv: {request.conversation_id}")

        db.add_message(request.conversation_id, "user", request.message)

        if request.use_kb:
            is_csharp = CodeDetector.is_csharp(request.message)
            classifier = IntentClassifierAgent(None)
            intent = classifier._static_prefilter(request.message) or CodeDetector.detect_intent(request.message)
            logger.info(f"  [KB MODE] Intent: {intent}, Is C#: {is_csharp}")

            if intent == "GREETING" and not is_csharp:
                db.add_message(request.conversation_id, "assistant", PROMPT_GREETING)
                return {"role": "assistant", "content": PROMPT_GREETING, "intent": "GREETING",
                        "static_results": {"smells": []}, "pipeline": None, "source": "kb"}

            if intent == "OUT_OF_SCOPE" and not is_csharp:
                db.add_message(request.conversation_id, "assistant", PROMPT_OUT_OF_SCOPE)
                return {"role": "assistant", "content": PROMPT_OUT_OF_SCOPE, "intent": "OUT_OF_SCOPE",
                        "static_results": {"smells": []}, "pipeline": None, "source": "kb"}

            if is_csharp:
                pure_code = CodeDetector.extract_code(request.message)
                static_results = UnityAnalyzer(pure_code).analyze()
                analysis_text = kb.format_analysis(static_results, original_code=pure_code)
                kb_ref = kb.lookup_for_code(pure_code)
                if kb_ref:
                    final_response = kb.format_fix_response(analysis_text, kb_ref)
                    source = "kb_analysis_with_fix"
                else:
                    final_response = analysis_text
                    source = "kb_analysis"

                db.add_message(request.conversation_id, "assistant", final_response, static_results.get("smells", []))
                history_messages = db.get_conversation_messages(request.conversation_id)
                if len(history_messages) <= 2:
                    class_name = static_results.get("stats", {}).get("class_name", "Analiz")
                    db.rename_conversation(request.conversation_id, f"Analiz: {class_name}")

                return {"role": "assistant", "content": final_response, "intent": "ANALYSIS",
                        "static_results": static_results, "pipeline": None, "source": source}

            kb_intent = "generation" if intent == "GENERATION" else "chat"
            kb_result = kb.lookup(request.message, intent=kb_intent)

            if kb_result:
                if kb_result.clarification_needed:
                    clarification_text = kb.format_clarification(kb_result)
                    db.add_message(request.conversation_id, "assistant", clarification_text)
                    return {"role": "assistant", "content": clarification_text, "intent": intent,
                            "static_results": {"smells": [], "stats": {}}, "pipeline": None, "source": "kb_clarification"}

                final_suggestion = kb.format_response(kb_result, intent=kb_intent)
                db.add_message(request.conversation_id, "assistant", final_suggestion)
                return {"role": "assistant", "content": final_suggestion, "intent": intent,
                        "static_results": {"smells": [], "stats": {}}, "pipeline": None, "source": "kb"}

            kb_miss_msg = (
                "🔍 Bu konu bilgi bankamda yer almıyor.\n\n"
                "Daha gelişmiş yanıtlar için **Model Seç** menüsünden bir AI modeli seçip "
                "API key girebilirsin. Böylece karmaşık konularda da yardımcı olabilirim!\n\n"
                "> **İpucu:** Groq ücretsiz bir seçenek olarak kullanılabilir."
            )
            db.add_message(request.conversation_id, "assistant", kb_miss_msg)
            history_messages = db.get_conversation_messages(request.conversation_id)
            if len(history_messages) <= 2:
                auto_title = request.message[:40].strip()
                if len(request.message) > 40:
                    auto_title += "..."
                db.rename_conversation(request.conversation_id, auto_title)
            return {"role": "assistant", "content": kb_miss_msg, "intent": intent,
                    "static_results": {"smells": [], "stats": {}}, "pipeline": None, "source": "kb_miss"}

        provider_type, model_name, _, use_multi_agent, force_claude_coder = db.get_ai_config(user_id)
        api_key = (db.get_api_key(user_id, provider_type) or "") if provider_type not in ("ollama", "kb") else ""

        try:
            provider = AIProviderManager.get_provider(
                {"provider_type": provider_type, "model_name": model_name, "api_key": api_key}
            )
        except ValueError as exc:
            error_msg = str(exc)
            db.add_message(request.conversation_id, "assistant", error_msg)
            return {"role": "assistant", "content": error_msg, "intent": "ERROR", "static_results": {"smells": []}, "pipeline": None}

        # Hybrid provider: Anthropic planlama/mimari yapar, GPT kod yazar
        # use_or_for_coder=True ise OR tercih edilir, yoksa OpenAI native öncelikli
        coding_provider = None
        coding_provider_type = provider_type
        if provider_type == "anthropic" and not force_claude_coder:
            _oa_key = db.get_api_key(user_id, "openai") or ""
            _or_key = db.get_api_key(user_id, "openrouter") or ""
            prefer_or = request.use_or_for_coder and bool(_or_key)
            if prefer_or:
                _or_model = "openai/gpt-5.4"
                try:
                    coding_provider = AIProviderManager.get_provider(
                        {"provider_type": "openrouter", "model_name": _or_model, "api_key": _or_key}
                    )
                    coding_provider_type = "openrouter"
                    logger.info(f"[Hybrid] Planlama: Anthropic ({model_name}) | Kod yazma: OpenRouter ({_or_model})")
                except Exception:
                    pass
            elif _oa_key:
                _oa_model = "gpt-5.4"
                try:
                    coding_provider = AIProviderManager.get_provider(
                        {"provider_type": "openai", "model_name": _oa_model, "api_key": _oa_key}
                    )
                    coding_provider_type = "openai"
                    logger.info(f"[Hybrid] Planlama: Anthropic ({model_name}) | Kod yazma: OpenAI ({_oa_model})")
                except Exception:
                    pass
            elif _or_key:
                _or_model = "openai/gpt-5.4"
                try:
                    coding_provider = AIProviderManager.get_provider(
                        {"provider_type": "openrouter", "model_name": _or_model, "api_key": _or_key}
                    )
                    coding_provider_type = "openrouter"
                    logger.info(f"[Hybrid] Planlama: Anthropic ({model_name}) | Kod yazma: OpenRouter ({_or_model})")
                except Exception:
                    pass

        classifier = IntentClassifierAgent(provider)
        intent = await classifier.classify_async(request.message)
        is_csharp = CodeDetector.is_csharp(request.message)

        if request.mode != "generation" and intent == "GREETING" and not is_csharp:
            db.add_message(request.conversation_id, "assistant", PROMPT_GREETING)
            return {"role": "assistant", "content": PROMPT_GREETING, "intent": "GREETING", "static_results": {"smells": []}, "pipeline": None}

        if request.mode != "generation" and intent == "OUT_OF_SCOPE" and not is_csharp:
            db.add_message(request.conversation_id, "assistant", PROMPT_OUT_OF_SCOPE)
            return {"role": "assistant", "content": PROMPT_OUT_OF_SCOPE, "intent": "OUT_OF_SCOPE", "static_results": {"smells": []}, "pipeline": None}

        if request.mode != "generation" and intent == "GENERATION" and not is_csharp:
            redirect_msg = (
                "Şu an **Kod Analizi** modundasın — kod üretmek için lütfen üstten **Sıfırdan Üret** sekmesine geç. 🚀"
            )
            db.add_message(request.conversation_id, "assistant", redirect_msg)
            return {"role": "assistant", "content": redirect_msg, "intent": "GENERATION_REDIRECT", "static_results": {"smells": []}, "pipeline": None}

        history_messages = db.get_conversation_messages(request.conversation_id)
        context_summary = ""
        recent = history_messages[-6:]
        if len(recent) > 1:
            context_summary = "\n".join(
                f"{'Kullanıcı' if msg['role'] == 'user' else 'AI'}: {msg['content'][:800]}"
                for msg in recent[:-1]
            )

        # Gate daha önce soru sorduysa (NEEDS_CLARIFICATION) kullanıcı cevap veriyor demektir.
        # Gate'i tekrar çalıştırma — direkt pipeline'a geç.
        # Ayrıca orijinal uzun promptu + cevapları birleştir ki architect tam bağlamı görsün.
        _last_assistant_content = next(
            (m["content"] for m in reversed(history_messages[:-1]) if m["role"] == "assistant"), ""
        )
        _gate_already_asked = (
            "Sistemi en iyi şekilde tasarlayabilmem için" in _last_assistant_content
            or "Cevapladıktan sonra hemen kodu üretmeye başlayacağım" in _last_assistant_content
        )
        _combined_prompt = request.message
        if _gate_already_asked:
            # İlk kullanıcı mesajını bul (orijinal istek) ve mevcut cevaplarla birleştir
            _first_user_msg = next(
                (m["content"] for m in history_messages if m["role"] == "user"), ""
            )
            if _first_user_msg and _first_user_msg != request.message:
                _combined_prompt = (
                    f"{_first_user_msg}\n\n"
                    f"[KULLANICI EK BİLGİLERİ]\n{request.message}"
                )

        if request.mode == "generation":
            # ——— BATCH CONTINUATION: Kademeli üretimde sonraki batch'i yaz ———
            batch_state = continuation_store.get(request.conversation_id)

            # Devam mesajı var ama store boş (backend yeniden başlatıldı)
            # Token truncation devamı değilse hata ver (single agent truncation'ı bu guard'a takılmasın)
            _last_assistant_for_guard = next(
                (m for m in reversed(history_messages) if m["role"] == "assistant"), None
            )
            _is_token_truncation = (
                _last_assistant_for_guard is not None
                and "Token limitine ulaşıldı" in _last_assistant_for_guard.get("content", "")
            )
            if not batch_state and _is_batch_continuation_msg(request.message) and not _is_token_truncation:
                no_state_msg = (
                    "⚠️ **Devam bilgisi bulunamadı.**\n\n"
                    "Uygulama yeniden başlatıldığı için önceki üretim bilgisi kayboldu. "
                    "Kalan dosyaları üretmek için lütfen orijinal isteğini tekrar gönder."
                )
                db.add_message(request.conversation_id, "assistant", no_state_msg)
                return {"role": "assistant", "content": no_state_msg, "intent": "BATCH_NO_STATE",
                        "static_results": {"smells": [], "stats": {}}, "pipeline": None}

            if batch_state and _is_batch_continuation_msg(request.message):
                logger.info(f"  [Batch Continuation] Conv {request.conversation_id} için sonraki batch başlatılıyor.")
                next_start = batch_state["next_start"]
                all_files = batch_state["all_files"]
                batch_files = all_files[next_start:next_start + BATCH_SIZE]
                remaining_after = all_files[next_start + BATCH_SIZE:]

                try:
                    _coding_provider = None
                    _coding_provider_type = provider_type
                    if provider_type == "anthropic":
                        _oa_key = db.get_api_key(user_id, "openai") or ""
                        _or_key = db.get_api_key(user_id, "openrouter") or ""
                        _prefer_or = request.use_or_for_coder and bool(_or_key)
                        if _prefer_or:
                            try:
                                _coding_provider = AIProviderManager.get_provider(
                                    {"provider_type": "openrouter", "model_name": "openai/gpt-5.4", "api_key": _or_key}
                                )
                                _coding_provider_type = "openrouter"
                            except Exception:
                                pass
                        elif _oa_key:
                            try:
                                _coding_provider = AIProviderManager.get_provider(
                                    {"provider_type": "openai", "model_name": "gpt-5.4", "api_key": _oa_key}
                                )
                                _coding_provider_type = "openai"
                            except Exception:
                                pass
                        elif _or_key:
                            try:
                                _coding_provider = AIProviderManager.get_provider(
                                    {"provider_type": "openrouter", "model_name": "openai/gpt-5.4", "api_key": _or_key}
                                )
                                _coding_provider_type = "openrouter"
                            except Exception:
                                pass

                    progress_store[request.conversation_id] = [
                        {"id": "step2", "title": f"Kod Üretimi (Batch {next_start // BATCH_SIZE + 2})", "status": "in-progress", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                        {"id": "step3", "title": "Oyun Hissiyatı Testi", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                    ]

                    def _batch_progress(step_id, progress_status, duration_ms=None):
                        tasks = progress_store.get(request.conversation_id, [])
                        for task in tasks:
                            if task["id"] == step_id:
                                task["status"] = progress_status
                                if duration_ms is not None:
                                    task["description"] = f"{duration_ms}ms"

                    batch_pipeline = CodeGenerationPipeline(
                        prompt=batch_state["original_prompt"],
                        provider=provider,
                        language=request.language,
                        context=context_summary or "Yeni sohbet.",
                        user_message=request.message,
                        provider_type=provider_type,
                        progress_callback=_batch_progress,
                        scope_confirmed=True,
                        coding_provider=_coding_provider,
                        coding_provider_type=_coding_provider_type,
                        existing_plan=batch_state["plan"],
                        batch_files=batch_files,
                    )

                    batch_result = await asyncio.wait_for(batch_pipeline.run(), timeout=900)
                    batch_response = batch_result.combined_response

                    if remaining_after:
                        continuation_store[request.conversation_id]["next_start"] = next_start + BATCH_SIZE
                        remaining_str = " · ".join(f"`{f}`" for f in remaining_after)
                        batch_response += (
                            f"\n\n---\n"
                            f"📦 **Bu batch tamamlandı.** Kalan **{len(remaining_after)} dosya:** {remaining_str}\n\n"
                            f"**Devam et** yazman yeterli. ✋"
                        )
                    else:
                        continuation_store.pop(request.conversation_id, None)
                        batch_response += "\n\n---\n✅ **Tüm sistem tamamlandı!**"

                    db.add_message(request.conversation_id, "assistant", batch_response)
                    return {
                        "role": "assistant",
                        "content": batch_response,
                        "intent": "BATCH_CONTINUATION",
                        "static_results": {"smells": [], "stats": {}},
                        "pipeline": None,
                    }
                except Exception as exc:
                    logger.error(f"[Batch Continuation] Hata: {exc}")
                    # Hata olursa normal pipeline'a düş

            # ——— DEVAM ET: Önceki yanıt token limitinde kesilmişse pipeline'ı atla ———
            last_assistant = next((m for m in reversed(history_messages) if m["role"] == "assistant"), None)
            is_continuation = (
                last_assistant is not None
                and "Token limitine ulaşıldı" in last_assistant.get("content", "")
                and len(request.message.strip()) < 120
            )
            if is_continuation:
                import re as _re
                logger.info("  [Continuation] Kesilmiş yanıt tespit edildi — devam ediliyor.")
                progress_store[request.conversation_id] = [
                    {"id": "step1", "title": "Devam Kodu Üretiliyor", "status": "in-progress",
                     "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                ]
                full_history_text = "\n\n".join(
                    f"{'Kullanıcı' if m['role'] == 'user' else 'AI'}: {m['content']}"
                    for m in history_messages[-8:]
                )
                continuation_prompt = (
                    "[DEVAM İSTEĞİ — ÖNCEKİ YANIT TOKEN LİMİTİNDE KESİLDİ]\n\n"
                    f"{full_history_text}\n\n"
                    "[GÖREV]\n"
                    "Yukarıdaki kodun DEVAMI isteniyor. Zaten yazılmış dosyaları TEKRAR YAZMA.\n"
                    "Sadece henüz yazılmamış dosyaları/sınıfları yaz. Aynı formatı kullan:\n\n"
                    "**📄 DosyaAdi.cs**\n"
                    "```csharp\n// tam kod\n```\n\n"
                    "Eğer bu yanıtta da tüm sistemi tamamlayamazsan, yanıtın sonuna şunu ekle:\n"
                    "⏳ **Token limitine ulaşıldı — yanıt kesildi.**\n"
                    "Kalan dosyaları yazmamı ister misin? **Devam et** yazman yeterli. ✋"
                )
                try:
                    continuation = await asyncio.to_thread(provider.analyze_code, continuation_prompt, 8192)
                    backtick_count = len(_re.findall(r'```', continuation))
                    if backtick_count % 2 == 1:
                        continuation = continuation.rstrip() + "\n// ... (yanıt kesildi)\n```"
                        continuation += (
                            "\n\n---\n⏳ **Token limitine ulaşıldı — yanıt kesildi.**\n\n"
                            "Kalan dosyaları yazmamı ister misin? **Devam et** yazman yeterli. ✋"
                        )
                    progress_store[request.conversation_id][0]["status"] = "completed"
                    db.add_message(request.conversation_id, "assistant", continuation)
                    return {
                        "role": "assistant",
                        "content": continuation,
                        "intent": "CONTINUATION",
                        "static_results": {"smells": [], "stats": {}},
                        "pipeline": None,
                    }
                except Exception as exc:
                    logger.error(f"[Continuation] Hata: {exc}")
                    # Hata olursa normal pipeline'a düş

            # ——— SCOPE CHOICE: Kullanıcı scope uyarısına yanıt veriyor mu? ———
            scope_confirmed_flag = False
            effective_prompt = _combined_prompt

            scope_last_assistant = next((m for m in reversed(history_messages) if m["role"] == "assistant"), None)
            if scope_last_assistant and "SCOPE_WARNING_ACTIVE" in scope_last_assistant.get("content", ""):
                msg_lower = request.message.strip().lower()
                stored = scope_plan_store.get(request.conversation_id, {})
                if any(kw in msg_lower for kw in ["tam", "full", "hepsini", "orijinal", "tüm", "devam", "üret", "evet"]):
                    scope_confirmed_flag = True
                    if stored.get("original_prompt"):
                        effective_prompt = stored["original_prompt"]
                    logger.info("  [Scope] Kullanıcı TAM SİSTEM seçti.")
                elif any(kw in msg_lower for kw in ["basit", "simple", "minimal", "hafif", "az", "temel", "kısa"]):
                    scope_confirmed_flag = True  # Basit versiyon da scope check'i atlar (< 8 dosya gelir)
                    original = stored.get("original_prompt", request.message)
                    effective_prompt = original + "\n\n[SCOPE CONSTRAINT] Maksimum 5 dosya. Sadece en temel çalışır sistemi üret. Yardımcı sınıfları çıkar, monolitik tut."
                    logger.info("  [Scope] Kullanıcı BASİT VERSİYON seçti.")

            try:
                use_multi_pipeline = use_multi_agent and provider_type == "anthropic"
                if use_multi_pipeline:
                    progress_store[request.conversation_id] = [
                        {"id": "step1", "title": "Mimari Planlama", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                        {"id": "step2", "title": "Kod Üretimi", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                        {"id": "step3", "title": "Oyun Hissiyatı Testi", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                    ]
                else:
                    progress_store[request.conversation_id] = [
                        {"id": "step1", "title": "Kod Üretimi", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"}
                    ]

                def update_progress(step_id: str, progress_status: str, duration_ms: int = None):
                    tasks = progress_store.get(request.conversation_id, [])
                    for task in tasks:
                        if task["id"] == step_id:
                            task["status"] = progress_status
                            if duration_ms is not None:
                                task["description"] = f"{duration_ms}ms"

                if use_multi_pipeline:
                    stored_plan = scope_plan_store.get(request.conversation_id, {}).get("plan", "") if scope_confirmed_flag else ""
                    pipeline = CodeGenerationPipeline(
                        prompt=effective_prompt,
                        provider=provider,
                        language=request.language,
                        context=context_summary or "Yeni sohbet.",
                        user_message=request.message,
                        provider_type=provider_type,
                        progress_callback=update_progress,
                        scope_confirmed=scope_confirmed_flag,
                        coding_provider=coding_provider,
                        coding_provider_type=coding_provider_type,
                        existing_plan=stored_plan,
                        skip_gate=_gate_already_asked,
                    )
                else:
                    pipeline = SingleAgentCodeGenerationPipeline(
                        prompt=effective_prompt,
                        provider=provider,
                        language=request.language,
                        context=context_summary or "Yeni sohbet.",
                        user_message=request.message,
                        provider_type=provider_type,
                        progress_callback=update_progress,
                    )

                gen_timeout = 900 if use_multi_pipeline else 300
                result = await asyncio.wait_for(pipeline.run(), timeout=gen_timeout)

                # Clarification Gate tetiklendiyse pipeline durmuştur — soruları döndür
                if result.clarification_needed:
                    db.add_message(request.conversation_id, "assistant", result.clarification_questions)
                    return {
                        "role": "assistant",
                        "content": result.clarification_questions,
                        "intent": "CLARIFICATION",
                        "static_results": {"smells": [], "stats": {}},
                        "pipeline": None,
                        "source": "clarification_gate",
                    }

                # Scope Warning: Plan çok büyük — kullanıcı onayı bekleniyor
                if result.scope_warning:
                    scope_plan_store[request.conversation_id] = {
                        "plan": result.scope_warning_plan,
                        "original_prompt": effective_prompt,
                    }
                    db.add_message(request.conversation_id, "assistant", result.combined_response)
                    return {
                        "role": "assistant",
                        "content": result.combined_response,
                        "intent": "SCOPE_WARNING",
                        "static_results": {"smells": [], "stats": {}},
                        "pipeline": None,
                        "source": "scope_check",
                    }

                # Batch Continuation: İlk batch tamamlandı, devam var
                if result.has_continuation and result.remaining_files:
                    plan_text = result.step2_analysis.output if result.step2_analysis else ""
                    continuation_store[request.conversation_id] = {
                        "plan": plan_text,
                        "all_files": result.all_planned_files,
                        "next_start": BATCH_SIZE,
                        "original_prompt": effective_prompt,
                    }
                    remaining_str = " · ".join(f"`{f}`" for f in result.remaining_files)
                    continuation_msg = (
                        f"\n\n---\n"
                        f"📦 **İlk {BATCH_SIZE} dosya tamamlandı.** Kalan **{len(result.remaining_files)} dosya:** {remaining_str}\n\n"
                        f"**Devam et** yazman yeterli. ✋"
                    )
                    result.combined_response += continuation_msg

                final_suggestion = result.combined_response
                static_results = {"smells": [], "stats": {}}
                pipeline_info = None
            except asyncio.TimeoutError:
                final_suggestion = "⏱️ Pipeline süresi aşıldı. Lütfen daha basit bir üretim isteği deneyin veya sistemi parçalara bölün."
                static_results = {"smells": [], "stats": {}}
                pipeline_info = None
            except Exception as exc:
                logger.error(f"Generation Pipeline hatası: {exc}")
                final_suggestion = f"❌ Pipeline Hatası: {str(exc)}"
                static_results = {"smells": [], "stats": {}}
                pipeline_info = None
        elif is_csharp:
            try:
                progress_store[request.conversation_id] = [
                    {"id": "step1", "title": "Statik Analiz", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                    {"id": "step2", "title": "Derin AI Analizi", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                    {"id": "step3", "title": "Kod Düzeltme", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                    {"id": "step4", "title": "Self-Critique", "status": "pending", "description": "", "subtasks": [], "dependencies": [], "level": 0, "priority": "high"},
                ]

                def update_progress(step_id: str, progress_status: str, duration_ms: int = None):
                    tasks = progress_store.get(request.conversation_id, [])
                    for task in tasks:
                        if task["id"] == step_id:
                            task["status"] = progress_status
                            if duration_ms is not None:
                                task["description"] = f"{duration_ms}ms"

                if provider_type == "anthropic" and use_multi_agent:
                    pipeline = MultiAgentPipeline(
                        code=request.message,
                        provider=provider,
                        language=request.language,
                        context=context_summary or "Yeni sohbet.",
                        learned_rules="",
                        user_message=request.message,
                        provider_type=provider_type,
                        progress_callback=update_progress,
                        coding_provider=coding_provider,
                        coding_provider_type=coding_provider_type,
                    )
                else:
                    pipeline = SingleAgentPipeline(
                        code=request.message,
                        provider=provider,
                        language=request.language,
                        context=context_summary or "Yeni sohbet.",
                        learned_rules="",
                        user_message=request.message,
                        provider_type=provider_type,
                        progress_callback=update_progress,
                    )

                analysis_timeout = 900 if (provider_type == "anthropic" and use_multi_agent) else 300
                result = await asyncio.wait_for(pipeline.run(), timeout=analysis_timeout)
                final_suggestion = result.combined_response
                static_results = result.step1_static.output if result.step1_static and result.step1_static.output else {"smells": [], "stats": {}}
                pipeline_info = result.to_dict()
            except asyncio.TimeoutError:
                final_suggestion = "⏱️ Pipeline süresi aşıldı. Lütfen daha kısa bir kod deneyin veya daha hafif bir model seçin."
                static_results = {"smells": [], "stats": {}}
                pipeline_info = None
            except Exception as exc:
                logger.error(f"Pipeline hatası: {exc}")
                final_suggestion = f"❌ Pipeline Hatası: {str(exc)}"
                static_results = {"smells": [], "stats": {}}
                pipeline_info = None
        else:
            lang_instr = get_language_instr(request.language)
            rules_str = get_relevant_rules(request.message)
            prompt = PROMPT_ANALYZE.format(
                system_prompt=SYSTEM_PROMPT,
                lang_instr=lang_instr,
                context=context_summary or "Yeni sohbet.",
                user_message=request.message,
                rules=rules_str,
                smells="Kod gönderilmedi, genel soru.",
            )

            try:
                final_suggestion = await asyncio.to_thread(provider.analyze_code, prompt)
            except Exception as exc:
                final_suggestion = f"❌ AI Hatası: {str(exc)}"

            static_results = {"smells": [], "stats": {}}
            pipeline_info = None

        db.add_message(request.conversation_id, "assistant", final_suggestion, static_results.get("smells", []))
        if len(history_messages) <= 1:
            auto_title = request.message[:40].strip()
            if len(request.message) > 40:
                auto_title += "..."
            db.rename_conversation(request.conversation_id, auto_title)

        return {
            "role": "assistant",
            "content": final_suggestion,
            "intent": intent,
            "static_results": static_results,
            "pipeline": pipeline_info,
        }

    return router
