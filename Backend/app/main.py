import logging
import uvicorn
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ollama

# Sadece olanları import ediyoruz
from analyzer import UnityAnalyzer, CodeProcessor
from prompts import (
    SYSTEM_BASE, PROMPT_OUT_OF_SCOPE, 
    PROMPT_ANALYZER_TEMPLATE, get_language_instr
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unity Architect AI")

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

def clean_deepseek_response(text: str):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

@app.post("/analyze")
async def analyze_code(request: AnalysisRequest):
    logger.info(f"İstek: {request.language}")

    intent = CodeProcessor.detect_intent(request.code)
    is_code = CodeProcessor.is_actually_code(request.code)

    if intent == "ANALYSIS" and not is_code:
        intent = "OUT_OF_SCOPE"

    if intent == "GREETING":
        return {
            "intent": "GREETING",
            "static_results": {"smells": []},
            "ai_suggestion": "Selam kral! Ben Unity asistanınım. Kodunu gönder, düzeltelim! 🚀",
            "status": "success"
        }

    static_results = {"smells": [], "stats": {"total_lines": 0}}
    if intent == "ANALYSIS":
        try:
            analyzer = UnityAnalyzer(request.code)
            static_results = analyzer.analyze()
        except Exception as e:
            logger.error(f"Statik analiz hatası: {e}")

    lang_instr = get_language_instr(request.language)
    
    if intent == "OUT_OF_SCOPE":
        final_prompt = f"{lang_instr} {PROMPT_OUT_OF_SCOPE}"
    else:
        final_prompt = f"{SYSTEM_BASE}\n{lang_instr}\n" + PROMPT_ANALYZER_TEMPLATE.format(
            code=request.code, 
            smells=static_results['smells']
        )

    try:
        response = ollama.chat(
            model='qwen2.5-coder:7b', 
            messages=[{'role': 'user', 'content': final_prompt}],
            options={
                'num_predict': 2500,  
                'temperature': 0.3,   
                'top_p': 0.9,         
                'repeat_penalty': 1.1 
            }
        )
        
        final_answer = clean_deepseek_response(response['message']['content'])
        
        return {
            "intent": intent,
            "static_results": static_results,
            "ai_suggestion": final_answer,
            "status": "success"
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)