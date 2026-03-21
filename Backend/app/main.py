import logging
import uvicorn

# --- LOGGING SETUP (En başta olmalı!) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import re
import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasını yükle (Backend/.env)
load_dotenv(Path(__file__).parent.parent / ".env")
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

# Modüllerimiz
from database import DatabaseManager
from analyzer import UnityAnalyzer, CodeProcessor
from validator import ResponseValidator
from ai_providers import AIProviderManager
from pipelines import SingleAgentPipeline, MultiAgentPipeline, CodeGenerationPipeline
from pipelines.agents.intent_classifier import IntentClassifierAgent
from report_engine import ReportEngine
from knowledge import KBEngine
from prompts import (
    SYSTEM_PROMPT, PROMPT_ANALYZE, PROMPT_OUT_OF_SCOPE,
    PROMPT_GREETING, get_language_instr, get_relevant_rules
)

# --- VERİTABANI YOLU ---
home_dir = str(Path.home())
db_folder = os.path.join(home_dir, ".unity_architect_ai")
os.makedirs(db_folder, exist_ok=True)
db_path = os.path.join(db_folder, "unity_master_v3.db")

# --- AYARLAR ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unity Architect AI")
db = DatabaseManager(db_path=db_path)
kb = KBEngine()  # Yerel Unity bilgi bankası (0ms, 0 token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELLER ---
class AuthRequest(BaseModel):
    username: str
    password: str

class AnalysisRequest(BaseModel):
    code: str
    language: str = "tr"
    user_id: int

class AIConfigRequest(BaseModel):
    user_id: int
    provider_type: str
    model_name: str
    api_key: str
    use_multi_agent: bool = True

class UpdateFileRequest(BaseModel):
    file_path: str
    new_code: str

class RenameRequest(BaseModel):
    title: str

# --- YENİ MODELLER (Chat Sistemi) ---
class NewConversationRequest(BaseModel):
    user_id: int
    title: str = "Yeni Sohbet"

class ChatRequest(BaseModel):
    conversation_id: int
    message: str
    language: str = "tr"
    user_id: int
    mode: str = "analysis"
    use_kb: bool = True  # Yerel Bilgi Bankası aktif/pasif

class WorkspaceRequest(BaseModel):
    user_id: int
    path: str

class WriteFileRequest(BaseModel):
    file_path: str
    content: str
    workspace_path: str  # Güvenlik: dosya bu workspace içinde olmalı

# --- YARDIMCI FONKSİYONLAR ---
def clean_response(text: str) -> str:
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

# =====================================================================
#                         ESKİ ENDPOINTLER
# =====================================================================

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/register")
async def register(req: AuthRequest):
    if db.create_user(req.username, req.password):
        return {"status": "success"}
    raise HTTPException(400, "Kullanıcı adı alınmış.")

@app.post("/login")
async def login(req: AuthRequest):
    user = db.verify_user(req.username, req.password)
    if user:
        return {"user_id": user[0], "username": user[1]}
    raise HTTPException(401, "Hatalı giriş.")

@app.post("/save-ai-config")
async def save_config(req: AIConfigRequest):
    db.save_ai_config(req.user_id, req.provider_type, req.model_name, req.api_key, req.use_multi_agent)
    return {"status": "success"}

@app.get("/get-ai-config/{user_id}")
async def get_config(user_id: int):
    c = db.get_ai_config(user_id)
    return {"provider_type": c[0], "model_name": c[1], "api_key": c[2], "use_multi_agent": c[3]}

@app.get("/available-models")
async def get_available_models():
    models = {
        "local": [],
        "cloud": [
            {"id": "claude-sonnet-4-6", "name": "Claude 4.6 Sonnet", "provider": "anthropic"},
            {"id": "claude-opus-4-6", "name": "Claude 4.6 Opus", "provider": "anthropic"},
            {"id": "claude-haiku-4-6", "name": "Claude 4.6 Haiku", "provider": "anthropic"},
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B (Groq)", "provider": "groq"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B (Groq)", "provider": "groq"},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "google"},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "provider": "google"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai"},
            {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai"},
            {"id": "deepseek-chat", "name": "DeepSeek V3", "provider": "deepseek"},
        ]
    }
    try:
        import urllib.request, json as _json
        def _fetch_ollama():
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return _json.loads(resp.read())
        ollama_data = await asyncio.to_thread(_fetch_ollama)
        for m in ollama_data.get("models", []):
            model_name = m.get("name", "")
            if model_name:
                models["local"].append({
                    "id": model_name,
                    "name": model_name.split(":")[0].title() + " (Local)",
                    "provider": "ollama"
                })
    except Exception as e:
        logger.warning(f"Ollama list fetch failed: {e}")
        
    return models

@app.post("/analyze")
async def analyze_code(request: AnalysisRequest):
    logger.info(f"Analiz İsteği - User ID: {request.user_id}")
    
    is_csharp = CodeProcessor.is_actually_code(request.code)
    
    # Intent tespiti: Provider'ı al ve LLM-based classifier kullan
    p_type, m_name, api_key, use_multi_agent = db.get_ai_config(request.user_id)
    provider = AIProviderManager.get_provider({"provider_type": p_type, "model_name": m_name, "api_key": api_key})
    
    classifier = IntentClassifierAgent(provider)
    intent = await classifier.classify_async(request.code)
    
    if intent == "GREETING" and not is_csharp:
        return {"intent": "GREETING", "ai_suggestion": PROMPT_GREETING, "static_results": {"smells": []}}
    
    static_results = {"smells": [], "stats": {"total_lines": 0, "class_name": "Analiz"}}
    if is_csharp:
        static_results = UnityAnalyzer(request.code).analyze()

    lang_instr = get_language_instr(request.language)
    final_suggestion = ""

    if p_type == "ollama":
        policies_str = json.dumps(UNITY_POLICIES, indent=2, ensure_ascii=False)
        prompt = f"{SYSTEM_CORE.format(policies=policies_str)}\n{lang_instr}\n"
        prompt += PROMPT_ANALYZER_TEMPLATE.format(code=request.code, smells=static_results['smells'])
        
        for attempt in range(2):
            response = await asyncio.to_thread(provider.analyze_code, prompt, max_tokens=8192)
            clean_res = clean_response(response)
            is_valid, _ = ResponseValidator.validate(clean_res)
            if is_valid:
                final_suggestion = clean_res
                break
            prompt = "HATALARINI DÜZELT: Kod bloğu (```csharp) eksik!\n" + prompt
        if not final_suggestion:
            final_suggestion = clean_res
    else:
        prompt = f"""
        Sen Senior Unity Mimarsın. {lang_instr}
        Şu Unity kodunu analiz et ve [PERF_001], [PHYS_001], [LOGIC_001] kodlarıyla hataları açıkla.
        Ardından hataların tamamen düzeltildiği TAM bir C# kodu yaz.
        
        KOD: {request.code}
        STATİK BULGULAR: {static_results['smells']}
        """
        final_suggestion = await asyncio.to_thread(provider.analyze_code, prompt)

    title = static_results.get('stats', {}).get('class_name', 'Analiz')
    db.save_analysis(request.user_id, title, intent, request.code, final_suggestion, static_results['smells'])
    
    return {"intent": intent, "static_results": static_results, "ai_suggestion": final_suggestion}

@app.get("/history/{user_id}")
async def get_history(user_id: int):
    rows = db.get_user_history(user_id)
    return [{"id": r[0], "timestamp": r[1], "title": r[2], "intent": r[3]} for r in rows]

@app.get("/analysis-detail/{item_id}")
async def get_detail(item_id: int):
    detail = db.get_analysis_detail(item_id)
    if not detail:
        raise HTTPException(404)
    return detail

@app.delete("/history/{item_id}")
async def delete_item(item_id: int):
    db.delete_analysis(item_id)
    return {"status": "success"}

@app.put("/history/{item_id}")
async def rename_item(item_id: int, req: RenameRequest):
    db.rename_analysis(item_id, req.title)
    return {"status": "success"}

@app.post("/update-file")
async def update_file(req: UpdateFileRequest):
    try:
        with open(req.file_path, "w", encoding="utf-8") as f:
            f.write(req.new_code)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

# =====================================================================
#                   WORKSPACE ENDPOINTLERİ
# =====================================================================

@app.post("/save-workspace")
async def save_workspace(req: WorkspaceRequest):
    """Kullanıcının workspace yolunu kaydeder."""
    db.save_workspace(req.user_id, req.path)
    return {"status": "success"}

@app.get("/last-workspace/{user_id}")
async def get_last_workspace(user_id: int):
    """Kullanıcının en son açtığı workspace yolunu getirir."""
    path = db.get_last_workspace(user_id)
    return {"path": path}

@app.post("/write-file")
async def write_file(req: WriteFileRequest):
    """AI tarafından üretilen dosyayı workspace'e yazar."""
    # Güvenlik: dosya workspace dışına yazılmasın
    abs_file = os.path.abspath(req.file_path)
    abs_workspace = os.path.abspath(req.workspace_path)
    if not abs_file.startswith(abs_workspace):
        raise HTTPException(403, "Dosya workspace dışına yazılamaz!")
    
    try:
        os.makedirs(os.path.dirname(abs_file), exist_ok=True)
        with open(abs_file, 'w', encoding='utf-8') as f:
            f.write(req.content)
        return {"status": "success", "path": abs_file}
    except Exception as e:
        raise HTTPException(500, str(e))

# =====================================================================
#                   YENİ ENDPOINTLERİ (Chat Sistemi)
# =====================================================================

@app.post("/conversations")
async def create_conversation(req: NewConversationRequest):
    """Yeni bir sohbet oluşturur."""
    conv_id = db.create_conversation(req.user_id, req.title)
    return {"id": conv_id, "title": req.title, "status": "success"}

@app.get("/conversations/{user_id}")
async def get_conversations(user_id: int):
    """Kullanıcının tüm sohbetlerini listeler."""
    return db.get_user_conversations(user_id)

@app.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: int):
    """Bir sohbetteki tüm mesajları getirir."""
    return db.get_conversation_messages(conv_id)

@app.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int):
    """Sohbeti ve tüm mesajlarını siler."""
    db.delete_conversation(conv_id)
    return {"status": "success"}

@app.put("/conversations/{conv_id}")
async def rename_conversation(conv_id: int, req: RenameRequest):
    """Sohbet başlığını değiştirir."""
    db.rename_conversation(conv_id, req.title)
    return {"status": "success"}

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint — Kademeli Pipeline ile analiz.
    Step 1: Statik Analiz (Python) → Step 2: AI Derin Analiz → Step 3: AI Kod Düzeltme
    """
    logger.info(f"Chat İsteği - User: {request.user_id}, Conv: {request.conversation_id}")

    # 1. Kullanıcı mesajını kaydet
    db.add_message(request.conversation_id, "user", request.message)

    # ─── KB MODU (provider_type='kb') — LLM'siz, tamamen yerel ───────────
    if request.use_kb:
        is_csharp = CodeProcessor.is_actually_code(request.message)

        # Statik intent tespiti (LLM'siz)
        classifier = IntentClassifierAgent(None)
        intent = classifier._static_prefilter(request.message) or ("GENERATION" if request.mode == "generation" else "CHAT")
        logger.info(f"  [KB MODE] Intent: {intent}, Is C#: {is_csharp}")

        # Selamlama
        if intent == "GREETING" and not is_csharp:
            db.add_message(request.conversation_id, "assistant", PROMPT_GREETING)
            return {"role": "assistant", "content": PROMPT_GREETING, "intent": "GREETING",
                    "static_results": {"smells": []}, "pipeline": None, "source": "kb"}

        # Kapsam dışı
        if intent == "OUT_OF_SCOPE" and not is_csharp:
            db.add_message(request.conversation_id, "assistant", PROMPT_OUT_OF_SCOPE)
            return {"role": "assistant", "content": PROMPT_OUT_OF_SCOPE, "intent": "OUT_OF_SCOPE",
                    "static_results": {"smells": []}, "pipeline": None, "source": "kb"}

        # C# Kod Analizi (LLM'siz statik analiz)
        if is_csharp:
            logger.info(f"  [KB MODE] C# kodu tespit edildi → Statik Analiz başlıyor")
            static_results = UnityAnalyzer(request.message).analyze()
            analysis_response = kb.format_analysis(static_results)
            db.add_message(request.conversation_id, "assistant", analysis_response, static_results.get("smells", []))

            # Başlık güncelle (ilk mesajsa)
            history_messages = db.get_conversation_messages(request.conversation_id)
            if len(history_messages) <= 2:
                class_name = static_results.get("stats", {}).get("class_name", "Analiz")
                db.rename_conversation(request.conversation_id, f"Analiz: {class_name}")

            return {"role": "assistant", "content": analysis_response, "intent": "ANALYSIS",
                    "static_results": static_results, "pipeline": None, "source": "kb_analysis"}

        # KB Lookup (soru/istek — kod değilse)
        kb_intent = "generation" if request.mode == "generation" else "chat"
        kb_result = kb.lookup(request.message, intent=kb_intent)

        if kb_result:
            logger.info(f"  [KB HIT] '{kb_result.title}' (skor={kb_result.score})")
            final_suggestion = kb.format_response(kb_result, intent=kb_intent)
            db.add_message(request.conversation_id, "assistant", final_suggestion)
            return {"role": "assistant", "content": final_suggestion, "intent": intent,
                    "static_results": {"smells": [], "stats": {}}, "pipeline": None, "source": "kb"}

        # KB Miss — kullanıcıya bilgi ver
        kb_miss_msg = (
            "🔍 Bu konu bilgi bankamda yer almıyor.\n\n"
            "Daha gelişmiş yanıtlar için **Model Seç** menüsünden bir AI modeli seçip "
            "API key girebilirsin. Böylece karmaşık konularda da yardımcı olabilirim!\n\n"
            "> **İpucu:** Groq ücretsiz bir seçenek olarak kullanılabilir."
        )
        db.add_message(request.conversation_id, "assistant", kb_miss_msg)

        # Başlık güncelle (ilk mesajsa)
        history_messages = db.get_conversation_messages(request.conversation_id)
        if len(history_messages) <= 2:
            auto_title = request.message[:40].strip()
            if len(request.message) > 40:
                auto_title += "..."
            db.rename_conversation(request.conversation_id, auto_title)

        return {"role": "assistant", "content": kb_miss_msg, "intent": intent,
                "static_results": {"smells": [], "stats": {}}, "pipeline": None, "source": "kb_miss"}

    # ─── AI MODU (Groq, Claude, Gemini, OpenAI, Ollama...) ───────────────
    # 2. AI Sağlayıcısını hazırla (intent için de lazım)
    p_type, m_name, api_key, use_multi_agent = db.get_ai_config(request.user_id)
    provider = AIProviderManager.get_provider({"provider_type": p_type, "model_name": m_name, "api_key": api_key})

    # 3. Intent ve kod tespiti (LLM-powered)
    classifier = IntentClassifierAgent(provider)
    intent = await classifier.classify_async(request.message)
    is_csharp = CodeProcessor.is_actually_code(request.message)
    logger.info(f"  Intent: {intent}, Is C#: {is_csharp}")

    # 4. Selamlama kontrolü (GREETING sadece selamlama + kod yoksa)
    if request.mode != "generation" and intent == "GREETING" and not is_csharp:
        db.add_message(request.conversation_id, "assistant", PROMPT_GREETING)
        return {
            "role": "assistant",
            "content": PROMPT_GREETING,
            "intent": "GREETING",
            "static_results": {"smells": []},
            "pipeline": None
        }

    # 5. Kapsam dışı kontrolü
    if request.mode != "generation" and intent == "OUT_OF_SCOPE" and not is_csharp:
        db.add_message(request.conversation_id, "assistant", PROMPT_OUT_OF_SCOPE)
        return {
            "role": "assistant",
            "content": PROMPT_OUT_OF_SCOPE,
            "intent": "OUT_OF_SCOPE",
            "static_results": {"smells": []},
            "pipeline": None
        }

    # 6. Sohbet geçmişini yükle (context için)
    history_messages = db.get_conversation_messages(request.conversation_id)
    context_summary = ""
    recent = history_messages[-6:]
    if len(recent) > 1:
        context_summary = "\n".join(
            f"{'Kullanıcı' if msg['role'] == 'user' else 'AI'}: {msg['content'][:200]}"
            for msg in recent[:-1]
        )

    # 7. Kod Üretme (Generation) Modu Kontrolü
    if request.mode == "generation":
        try:
            pipeline = CodeGenerationPipeline(
                prompt=request.message,
                provider=provider,
                language=request.language,
                context=context_summary or "Yeni sohbet.",
                user_message=request.message,
                provider_type=p_type,
            )
            result = await asyncio.wait_for(pipeline.run(), timeout=300)
            
            final_suggestion = result.combined_response
            static_results = {"smells": [], "stats": {}}
            pipeline_info = None # Generation modunda skor gösterilmez
        except asyncio.TimeoutError:
            final_suggestion = "⏱️ Pipeline süresi aşıldı (300 saniye). Lütfen daha basit bir üretim isteği deneyin."
            static_results = {"smells": [], "stats": {}}
            pipeline_info = None
        except Exception as e:
            logger.error(f"Generation Pipeline hatası: {e}")
            final_suggestion = f"❌ Pipeline Hatası: {str(e)}"
            static_results = {"smells": [], "stats": {}}
            pipeline_info = None

    # 8. C# kodu varsa → Kademeli Pipeline çalıştır (Analysis)
    elif is_csharp:
        try:
            if p_type == "anthropic" and use_multi_agent:
                pipeline = MultiAgentPipeline(
                    code=request.message,
                    provider=provider,
                    language=request.language,
                    context=context_summary or "Yeni sohbet.",
                    learned_rules="",  # Feedback sistemi eklenince buraya gelecek
                    user_message=request.message,
                    provider_type=p_type,
                )
            else:
                pipeline = SingleAgentPipeline(
                    code=request.message,
                    provider=provider,
                    language=request.language,
                    context=context_summary or "Yeni sohbet.",
                    learned_rules="",  # Feedback sistemi eklenince buraya gelecek
                    user_message=request.message,
                    provider_type=p_type,
                )

            result = await asyncio.wait_for(pipeline.run(), timeout=300)

            final_suggestion = result.combined_response
            static_results = result.step1_static.output if result.step1_static and result.step1_static.output else {"smells": [], "stats": {}}
            pipeline_info = result.to_dict()

        except asyncio.TimeoutError:
            final_suggestion = "⏱️ Pipeline süresi aşıldı (300 saniye). Lütfen daha kısa bir kod deneyin veya daha hafif bir model seçin."
            static_results = {"smells": [], "stats": {}}
            pipeline_info = None
        except Exception as e:
            logger.error(f"Pipeline hatası: {e}")
            final_suggestion = f"❌ Pipeline Hatası: {str(e)}"
            static_results = {"smells": [], "stats": {}}
            pipeline_info = None
    else:
        # C# kodu değilse → Basit tek adımlı AI çağrısı (soru-cevap)
        lang_instr = get_language_instr(request.language)
        rules_str = get_relevant_rules(request.message)

        prompt = PROMPT_ANALYZE.format(
            system_prompt=SYSTEM_PROMPT,
            lang_instr=lang_instr,
            context=context_summary or "Yeni sohbet.",
            user_message=request.message,
            rules=rules_str,
            smells="Kod gönderilmedi, genel soru."
        )

        try:
            final_suggestion = await asyncio.to_thread(provider.analyze_code, prompt)
        except Exception as e:
            final_suggestion = f"❌ AI Hatası: {str(e)}"

        static_results = {"smells": [], "stats": {}}
        pipeline_info = None

    # 8. AI yanıtını kaydet
    db.add_message(request.conversation_id, "assistant", final_suggestion, static_results.get("smells", []))

    # 9. Sohbet başlığını otomatik güncelle (ilk mesajsa)
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
        "pipeline": pipeline_info
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)