import logging
import uvicorn
import re
import os
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

# Modüllerimiz
from database import DatabaseManager
from analyzer import UnityAnalyzer, CodeProcessor
from validator import ResponseValidator
from ai_providers import AIProviderManager
from prompts import (
    SYSTEM_CORE, PROMPT_ANALYZER_TEMPLATE, PROMPT_OUT_OF_SCOPE, 
    PROMPT_GREETING, UNITY_POLICIES, get_language_instr
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
    db.save_ai_config(req.user_id, req.provider_type, req.model_name, req.api_key)
    return {"status": "success"}

@app.get("/get-ai-config/{user_id}")
async def get_config(user_id: int):
    c = db.get_ai_config(user_id)
    return {"provider_type": c[0], "model_name": c[1], "api_key": c[2]}

@app.post("/analyze")
async def analyze_code(request: AnalysisRequest):
    logger.info(f"Analiz İsteği - User ID: {request.user_id}")
    
    intent = CodeProcessor.detect_intent(request.code)
    is_csharp = CodeProcessor.is_actually_code(request.code)
    
    if intent == "GREETING" and not is_csharp:
        return {"intent": "GREETING", "ai_suggestion": PROMPT_GREETING, "static_results": {"smells": []}}
    
    p_type, m_name, api_key = db.get_ai_config(request.user_id)
    provider = AIProviderManager.get_provider({"provider_type": p_type, "model_name": m_name, "api_key": api_key})

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
            response = await asyncio.to_thread(provider.analyze_code, prompt)
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
#                   YENİ ENDPOINTLER (Chat Sistemi)
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
    Chat endpoint — Mesaj gönder, AI yanıtı al, ikisini de kaydet.
    Sohbet geçmişini context olarak AI'a gönderir.
    """
    logger.info(f"Chat İsteği - User: {request.user_id}, Conv: {request.conversation_id}")

    # 1. Kullanıcı mesajını kaydet
    db.add_message(request.conversation_id, "user", request.message)

    # 2. Intent ve kod tespiti
    intent = CodeProcessor.detect_intent(request.message)
    is_csharp = CodeProcessor.is_actually_code(request.message)

    # 3. Selamlama kontrolü
    if intent == "GREETING" and not is_csharp:
        db.add_message(request.conversation_id, "assistant", PROMPT_GREETING)
        return {
            "role": "assistant",
            "content": PROMPT_GREETING,
            "intent": "GREETING",
            "static_results": {"smells": []}
        }

    # 4. Kapsam dışı kontrolü
    if intent == "OUT_OF_SCOPE" and not is_csharp:
        db.add_message(request.conversation_id, "assistant", PROMPT_OUT_OF_SCOPE)
        return {
            "role": "assistant",
            "content": PROMPT_OUT_OF_SCOPE,
            "intent": "OUT_OF_SCOPE",
            "static_results": {"smells": []}
        }

    # 5. AI Sağlayıcısını hazırla
    p_type, m_name, api_key = db.get_ai_config(request.user_id)
    provider = AIProviderManager.get_provider({"provider_type": p_type, "model_name": m_name, "api_key": api_key})

    # 6. Statik analiz (C# kodu varsa)
    static_results = {"smells": [], "stats": {"total_lines": 0, "class_name": "Analiz"}}
    if is_csharp:
        static_results = UnityAnalyzer(request.message).analyze()

    # 7. Sohbet geçmişini yükle (context için)
    history_messages = db.get_conversation_messages(request.conversation_id)
    lang_instr = get_language_instr(request.language)

    # 8. Katmanlı prompt oluştur
    try:
      if p_type == "ollama":
        # Yerel model için multi-turn messages dizisi
        policies_str = json.dumps(UNITY_POLICIES, indent=2, ensure_ascii=False)
        messages_for_ai = [
            {"role": "system", "content": f"{SYSTEM_CORE.format(policies=policies_str)}\n{lang_instr}"}
        ]
        # Son 10 mesajı context olarak ekle (token limiti için)
        recent_messages = history_messages[-10:]
        for msg in recent_messages:
            messages_for_ai.append({"role": msg["role"], "content": msg["content"]})
        
        # Statik bulgular varsa ekle
        if static_results["smells"]:
            smells_info = f"\n\n[STATİK BULGULAR]: {json.dumps(static_results['smells'], ensure_ascii=False)}"
            messages_for_ai[-1]["content"] += smells_info

        # Ollama multi-turn çağrı (non-blocking)
        import ollama
        def _ollama_call():
            return ollama.chat(model=m_name or "qwen2.5-coder:7b", messages=messages_for_ai)
        
        response = await asyncio.wait_for(
            asyncio.to_thread(_ollama_call), timeout=120
        )
        final_suggestion = clean_response(response['message']['content'])
      else:
        # Bulut API için temiz tek istek (kota dostu)
        context_summary = ""
        recent = history_messages[-6:]
        if len(recent) > 1:
            context_summary = "\n[ÖNCEKİ SOHBET BAĞLAMI]:\n"
            for msg in recent[:-1]:
                role_label = "Kullanıcı" if msg["role"] == "user" else "AI"
                context_summary += f"- {role_label}: {msg['content'][:200]}...\n" if len(msg['content']) > 200 else f"- {role_label}: {msg['content']}\n"

        prompt = f"""Sen Senior Unity Mimarsın. {lang_instr}
{context_summary}
[KULLANICI MESAJI]:
{request.message}

[STATİK BULGULAR]: {static_results['smells']}

Kodu analiz et, [PERF_001], [PHYS_001], [LOGIC_001] kodlarıyla hataları açıkla ve düzeltilmiş TAM C# kodunu yaz."""
        
        final_suggestion = await asyncio.to_thread(provider.analyze_code, prompt)
    except asyncio.TimeoutError:
        final_suggestion = "⏱️ AI yanıt süresi aşıldı (120 saniye). Lütfen daha kısa bir kod deneyin veya daha hafif bir model seçin."
    except Exception as e:
        final_suggestion = f"❌ AI Hatası: {str(e)}"

    # 9. AI yanıtını kaydet
    db.add_message(request.conversation_id, "assistant", final_suggestion, static_results.get("smells", []))

    # 10. Sohbet başlığını otomatik güncelle (ilk mesajsa)
    if len(history_messages) <= 1:
        auto_title = request.message[:40].strip()
        if len(request.message) > 40:
            auto_title += "..."
        db.rename_conversation(request.conversation_id, auto_title)

    return {
        "role": "assistant",
        "content": final_suggestion,
        "intent": intent,
        "static_results": static_results
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)