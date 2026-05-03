import logging
import asyncio
from typing import Any, Dict, List, Optional
from app.pipelines.agents.intent_classifier import IntentClassifierAgent
from app.pipelines.single_agent_pipeline import SingleAgentPipeline
from app.pipelines.single_agent_code_generation import SingleAgentCodeGenerationPipeline
from app.pipelines.quick_fix_pipeline import QuickFixPipeline
from app.pipelines.multi_agent_pipeline import MultiAgentPipeline
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class PartnerOrchestrator:
    """
    Unity Architect AI'ın ana beyni.
    Kullanıcı mesajını analiz eder, doğru alt ajanı/pipeline'ı seçer ve yönetir.
    """
    def __init__(self, db, provider, provider_type: str):
        self.db = db
        self.provider = provider
        self.provider_type = provider_type
        self.classifier = IntentClassifierAgent(provider)

    async def handle_message(self, conversation_id: int, message: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mesajı işler ve uygun pipeline'ı çalıştırır.
        """
        # 1. Niyet tespiti
        intent = await self.classifier.classify_async(message)
        logger.info(f"🧠 [Orchestrator] Tespit edilen niyet: {intent}")

        # 2. Bağlamı hazırla (Hafıza + Son mesajlar)
        history = self.db.get_conversation_messages(conversation_id)
        memory = self.db.get_memory(conversation_id)
        
        context = ""
        if memory:
            context += f"[ÖNCEKİ SOHBET HAFIZASI]\n{memory}\n\n"
        
        # Son 5 mesajı context'e ekle
        recent = history[-5:]
        for msg in recent:
            context += f"{'Kullanıcı' if msg['role'] == 'user' else 'AI'}: {msg['content'][:500]}\n"

        # 3. Dallanma (Routing)
        
        # A) SADECE SOHBET / BAĞLAM KURMA
        if intent in ["CHAT", "GREETING"]:
            return await self._handle_chat(conversation_id, message, context)

        # B) KOD ÜRETİMİ
        if intent == "GENERATION":
            return await self._handle_generation(conversation_id, message, context, config)

        # C) KOD ANALİZİ VE DÜZELTME
        if intent in ["ANALYSIS", "FIX"]:
            return await self._handle_analysis(conversation_id, message, context, config)

        # Fallback to chat
        return await self._handle_chat(conversation_id, message, context)

    async def _handle_chat(self, conversation_id: int, message: str, context: str) -> Dict[str, Any]:
        prompt = f"{SYSTEM_PROMPT}\n\n[BAĞLAM]\n{context}\n\n[KULLANICI]\n{message}"
        response = await asyncio.to_thread(self.provider.analyze_code, prompt)
        
        return {
            "role": "assistant",
            "content": response,
            "intent": "CHAT",
            "static_results": {"smells": []},
            "pipeline": None
        }

    async def _handle_generation(self, conversation_id: int, message: str, context: str, config: Dict[str, Any]) -> Dict[str, Any]:
        # Burada SingleAgentCodeGenerationPipeline çağrılacak
        pipeline = SingleAgentCodeGenerationPipeline(
            prompt=message,
            provider=self.provider,
            language=config.get("language", "tr"),
            context=context,
            provider_type=self.provider_type,
            progress_callback=config.get("progress_callback")
        )
        result = await pipeline.run()
        return {
            "role": "assistant",
            "content": result.combined_response,
            "intent": "GENERATION",
            "static_results": {"smells": []},
            "pipeline": None
        }

    async def _handle_analysis(self, conversation_id: int, message: str, context: str, config: Dict[str, Any]) -> Dict[str, Any]:
        # Burada SingleAgentPipeline çağrılacak
        pipeline = SingleAgentPipeline(
            code=message, # Kod mesajın kendisindeyse
            provider=self.provider,
            language=config.get("language", "tr"),
            context=context,
            user_message=message,
            provider_type=self.provider_type,
            progress_callback=config.get("progress_callback")
        )
        result = await pipeline.run()
        return {
            "role": "assistant",
            "content": result.combined_response,
            "intent": "ANALYSIS",
            "static_results": {"smells": result.step1_static.output.get("smells", []) if result.step1_static else []},
            "pipeline": None
        }
