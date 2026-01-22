import logging
import uvicorn
import re
import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# Modüllerimiz
from database import DatabaseManager
from analyzer import UnityAnalyzer, CodeProcessor
from validator import ResponseValidator
from ai_providers import AIProviderManager
from prompts import (
    SYSTEM_CORE, PROMPT_ANALYZER_TEMPLATE, PROMPT_OUT_OF_SCOPE, 
    PROMPT_GREETING, UNITY_POLICIES, get_language_instr
)

# --- RESET BUG ÇÖZÜMÜ: VERİTABANI YOLU ---
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

# --- YARDIMCI FONKSİYONLAR ---
def clean_response(text: str):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

# --- ENDPOINTLER ---

@app.get("/")
async def health(): return {"status": "ok"}

@app.post("/register")
async def register(req: AuthRequest):
    if db.create_user(req.username, req.password): return {"status": "success"}
    raise HTTPException(400, "Kullanıcı adı alınmış.")

@app.post("/login")
async def login(req: AuthRequest):
    user = db.verify_user(req.username, req.password)
    if user: return {"user_id": user[0], "username": user[1]}
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
    
    # 2. AI Sağlayıcısını Hazırla
    p_type, m_name, api_key = db.get_ai_config(request.user_id)
    provider = AIProviderManager.get_provider({"provider_type": p_type, "model_name": m_name, "api_key": api_key})


    # 3. Statik Analiz
    static_results = {"smells": [], "stats": {"total_lines": 0, "class_name": "Analiz"}}
    if is_csharp:
        static_results = UnityAnalyzer(request.code).analyze()

    lang_instr = get_language_instr(request.language)
    final_suggestion = ""

    # 4. HİBRİT PROMPT VE ÇAĞRI MANTIĞI
    if p_type == "ollama":
        # YEREL QWEN İÇİN DÖNGÜ DEVAM (Maliyet yok, hata payı yüksek)
        policies_str = json.dumps(UNITY_POLICIES, indent=2, ensure_ascii=False)
        prompt = f"{SYSTEM_CORE.format(policies=policies_str)}\n{lang_instr}\n"
        prompt += PROMPT_ANALYZER_TEMPLATE.format(code=request.code, smells=static_results['smells'])
        
        for attempt in range(2):
            response = provider.analyze_code(prompt)
            clean_res = clean_response(response)
            is_valid, _ = ResponseValidator.validate(clean_res)
            if is_valid:
                final_suggestion = clean_res
                break
            prompt = "HATALARINI DÜZELT: Kod bloğu (```csharp) eksik!\n" + prompt
        if not final_suggestion: final_suggestion = clean_res
    else:
        # BULUT API (GEMINI) İÇİN TEK SEFERLİK TEMİZ İSTEK (KOTA DOSTU)
        # Gemini 2.0/3.0 zaten çok zeki, döngüye gerek yok.
        prompt = f"""
        Sen Senior Unity Mimarsın. {lang_instr}
        Şu Unity kodunu analiz et ve [PERF_001], [PHYS_001], [LOGIC_001] kodlarıyla hataları açıkla.
        Ardından hataların tamamen düzeltildiği TAM bir C# kodu yaz.
        
        KOD: {request.code}
        STATİK BULGULAR: {static_results['smells']}
        """
        # Sadece bir kez soruyoruz, 429 hatasını önlüyoruz
        final_suggestion = provider.analyze_code(prompt)

    # 5. Kaydet
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
    if not detail: raise HTTPException(404)
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)