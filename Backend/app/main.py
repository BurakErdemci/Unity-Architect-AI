from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import ollama
import logging

# Modüler sınıflarımızı içeri alıyoruz
from analyzer import UnityAnalyzer, CodeProcessor
from prompts import (
    SYSTEM_BASE, PROMPT_GREETING, PROMPT_OUT_OF_SCOPE, 
    PROMPT_ANALYZER_TEMPLATE, get_language_instr
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unity Architect AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    code: str
    language: str = "tr"

@app.post("/analyze")
async def analyze_code(request: AnalysisRequest):
    logger.info(f"Yeni İstek Alındı. Dil: {request.language}")

    # 1. ADIM: Niyet ve Kod Kontrolü (Logic analyzer.py'da)
    intent = CodeProcessor.detect_intent(request.code)
    is_code = CodeProcessor.is_actually_code(request.code)

    # Eğer niyet analiz olsa bile içerik kod değilse sohbet moduna çek
    if intent == "ANALYSIS" and not is_code:
        intent = "GREETING"

    # 2. ADIM: Statik Analiz (Sadece niyet ANALYSIS ise)
    static_results = {"smells": [], "stats": {"total_lines": 0}}
    if intent == "ANALYSIS":
        analyzer = UnityAnalyzer(request.code)
        static_results = analyzer.analyze()

    # 3. ADIM: Prompt Hazırlama (prompts.py'dan)
    lang_instr = get_language_instr(request.language)
    
    if intent == "GREETING":
        final_prompt = f"{SYSTEM_BASE}\n{lang_instr}\n{PROMPT_GREETING}\nKullanıcı: {request.code}"
    elif intent == "OUT_OF_SCOPE":
        final_prompt = f"{SYSTEM_BASE}\n{lang_instr}\n{PROMPT_OUT_OF_SCOPE}"
    else:
        final_prompt = f"{SYSTEM_BASE}\n{lang_instr}\n" + PROMPT_ANALYZER_TEMPLATE.format(
            code=request.code, 
            smells=static_results['smells']
        )

    # 4. ADIM: AI (Ollama) Çağrısı
    try:
        response = ollama.chat(
            model='llama3.1', 
            messages=[{'role': 'user', 'content': final_prompt}],
            options={'num_predict': 2500, 'temperature': 0.1, 'top_p': 0.4,'repeat_penalty': 1.2}
        )
        
        return {
            "intent": intent,
            "static_results": static_results,
            "ai_suggestion": response['message']['content'],
            "status": "success"
        }
    except Exception as e:
        logger.error(f"AI Hatası: {e}")
        return {"error": str(e), "status": "error", "static_results": static_results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)