"""
AgentRunner — Agentic Loop motoru.

AI'a araçlar (tools) verir, AI hangisini çağıracağına karar verir,
araç sonucunu alır, tekrar AI'a gönderir. İş bitene kadar döngü devam eder.

Her adımda bir SSE event callback'i çağırılır (thinking, tool_call, response, done).
"""
import json
import time
import logging
import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from google import genai
from google.genai import types as gtypes
import anthropic
import openai

from tools.tool_registry import TOOL_DEFINITIONS, execute_tool, get_openai_tool_declarations
from prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15  # Güvenlik: Sonsuz döngü koruması


class AgentEvent:
    """SSE'ye gönderilecek bir event."""
    def __init__(self, event_type: str, data: dict):
        self.type = event_type  # thinking | tool_call | tool_result | response | error | done
        self.data = data
        self.timestamp = time.time()

    def to_sse(self) -> str:
        payload = json.dumps({"type": self.type, **self.data}, ensure_ascii=False)
        return f"data: {payload}\n\n"


class AgentRunner:
    """
    Tek bir kullanıcı isteğini agentic loop ile çalıştırır.
    Gemini'nin native function calling özelliğini kullanır.
    """

    def __init__(
        self,
        provider_type: str,
        api_key: str,
        model_name: str,
        workspace_path: str,
        language: str = "tr",
        context: str = "",
        use_thinking: bool = False,
    ):
        self.provider_type = provider_type
        self.api_key = api_key
        self.model_name = model_name
        self.workspace_path = workspace_path
        self.language = language
        self.context = context
        self.use_thinking = use_thinking

    async def run(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Agentic loop'u çalıştırır. Her adımda AgentEvent yield eder.
        """
        if self.provider_type == "google":
            async for event in self._run_gemini(user_message):
                yield event
        elif self.provider_type == "anthropic":
            async for event in self._run_anthropic(user_message):
                yield event
        elif self.provider_type in ("openai", "openrouter", "deepseek", "groq"):
            async for event in self._run_openai(user_message):
                yield event
        else:
            # Diğer provider'lar için basit fallback (function calling yok)
            async for event in self._run_simple(user_message):
                yield event

    # ═══════════════════════════════════════════════
    # GEMINI AGENTIC LOOP (Native Function Calling)
    # ═══════════════════════════════════════════════
    async def _run_gemini(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        client = genai.Client(api_key=self.api_key)

        # Tool tanımlarını Gemini formatına çevir
        tools = [gtypes.Tool(function_declarations=[
            gtypes.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in TOOL_DEFINITIONS
        ])]

        system_instruction = f"""{SYSTEM_PROMPT}

Sen Unity projesi üzerinde çalışan bir AI asistanısın. Sana verilen araçları kullanarak projeyi keşfedebilir, dosyaları okuyabilir, arama yapabilir ve kod yazabilirsin.

[ÇALIŞMA PRENSİBİ - HAYATİ KURALLAR]
1. ÖNCE projeyi keşfet (dosya oku, ara).
2. KOD YAZARKEN: KESİNLİKLE parça kod (snippet) verme. Sadece değişen yeri değil, dosyanın TAMAMINI yazmak ZORUNDASIN.
3. KOD BLOKLARI: Her kod bloğunun İSTİSNASIZ İLK SATIRINA yolu ekle:
// path: Assets/Scripts/Tam/Dosya/Yolu.cs

4. `write_file` aracını C# kodu yazmak için KULLANMA. Bunun yerine, kodu Markdown kod bloğu (```csharp ... ```) içinde ver. Kullanıcı arayüzden onaylayacaktır.
5. Kullanıcının en son verdiği teknik talimatları (örn: Update/Timer/Zırh) asla unutma, her güncellemede bunları koru.
6. Eğer tam dosyayı yazmazsan sistem çalışmaz ve kullanıcıya hatalı bilgi vermiş olursun.

[BAĞLAM]
{self.context or "Yeni sohbet."}

[DİL]
Kullanıcıyla {'Türkçe' if self.language == 'tr' else 'İngilizce'} konuş."""

        # Thinking config
        thinking_config = None
        if self.use_thinking:
            thinking_config = gtypes.ThinkingConfig(thinking_budget=4096)

        config = gtypes.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            thinking_config=thinking_config,
        )

        # İlk mesaj
        contents = [gtypes.Content(role="user", parts=[gtypes.Part(text=user_message)])]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 Agentic Loop iterasyon {iteration + 1}")

            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                yield AgentEvent("error", {"message": f"AI hatası: {str(e)}"})
                return

            if not response.candidates:
                yield AgentEvent("error", {"message": "AI yanıt üretemedi."})
                return

            candidate = response.candidates[0]
            parts = candidate.content.parts

            # Thinking varsa yield et
            for part in parts:
                if getattr(part, "thought", False) and part.text:
                    yield AgentEvent("thinking", {"text": part.text})

            # Tool call var mı kontrol et
            tool_calls = [p for p in parts if p.function_call]
            text_parts = [p for p in parts if p.text and not getattr(p, "thought", False)]

            if not tool_calls:
                # Tool call yok = AI işini bitirdi, final yanıt
                final_text = "\n".join(p.text for p in text_parts if p.text)
                yield AgentEvent("response", {"content": final_text})
                yield AgentEvent("done", {"iterations": iteration + 1})
                return

            # Tool call'ları çalıştır
            function_response_parts = []

            for part in tool_calls:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}

                yield AgentEvent("tool_call", {
                    "tool": tool_name,
                    "arguments": tool_args,
                    "iteration": iteration + 1,
                })

                # Aracı çalıştır
                result = await asyncio.to_thread(
                    execute_tool, tool_name, tool_args, self.workspace_path
                )

                # Sonucu kısalt (çok büyük olabilir)
                result_str = json.dumps(result, ensure_ascii=False)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... (kısaltıldı)"

                yield AgentEvent("tool_result", {
                    "tool": tool_name,
                    "success": result.get("success", False),
                    "summary": self._summarize_result(tool_name, result),
                })

                function_response_parts.append(
                    gtypes.Part(function_response=gtypes.FunctionResponse(
                        name=tool_name,
                        response=result,
                    ))
                )

            # Arada metin varsa (AI'ın açıklaması) yield et
            for p in text_parts:
                if p.text:
                    yield AgentEvent("text", {"content": p.text})

            # AI'ın yanıtını ve tool sonuçlarını geçmişe ekle
            contents.append(candidate.content)
            contents.append(gtypes.Content(role="user", parts=function_response_parts))

        # Max iterasyona ulaşıldı
        yield AgentEvent("response", {
            "content": "⚠️ Maksimum araç çağrısı sayısına ulaşıldı. Mevcut bulgularımla yanıt veriyorum."
        })
        yield AgentEvent("done", {"iterations": MAX_ITERATIONS, "max_reached": True})

    # ═══════════════════════════════════════════════
    # ANTHROPIC AGENTIC LOOP (Claude 3.5 Sonnet vb.)
    # ═══════════════════════════════════════════════
    async def _run_anthropic(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        
        system_instruction = f"""{SYSTEM_PROMPT}

Sen Unity projesi üzerinde çalışan bir AI asistanısın. Sana verilen araçları kullanarak projeyi keşfedebilir, dosyaları okuyabilir, arama yapabilir ve kod yazabilirsin.

[ÇALIŞMA PRENSİBİ - HAYATİ KURALLAR]
1. ÖNCE projeyi keşfet (dosya oku, ara).
2. KOD YAZARKEN: KESİNLİKLE parça kod (snippet) verme. Sadece değişen yeri değil, dosyanın TAMAMINI yazmak ZORUNDASIN.
3. KOD BLOKLARI: Her kod bloğunun İSTİSNASIZ İLK SATIRINA yolu ekle:
// path: Assets/Scripts/Tam/Dosya/Yolu.cs

4. `write_file` aracını C# kodu yazmak için KULLANMA. Bunun yerine, kodu Markdown kod bloğu (```csharp ... ```) içinde ver. Kullanıcı arayüzden onaylayacaktır.
5. Kullanıcının en son verdiği teknik talimatları asla unutma, her güncellemede bunları koru.
6. Eğer tam dosyayı yazmazsan sistem çalışmaz ve kullanıcıya hatalı bilgi vermiş olursun.

[BAĞLAM]
{self.context or "Yeni sohbet."}"""
        
        # Tool formatı
        anthropic_tools = []
        for t in TOOL_DEFINITIONS:
            # Anthropic expects input_schema instead of parameters
            anthropic_tools.append({
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"]
            })

        messages = [{"role": "user", "content": user_message}]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 Anthropic Agentic Loop iterasyon {iteration + 1}")
            
            try:
                response = await client.messages.create(
                    model=self.model_name,
                    max_tokens=4096,
                    system=system_instruction,
                    messages=messages,
                    tools=anthropic_tools
                )
            except Exception as e:
                yield AgentEvent("error", {"message": f"Claude hatası: {str(e)}"})
                return

            messages.append({"role": "assistant", "content": response.content})
            
            tool_calls = [block for block in response.content if block.type == "tool_use"]
            text_blocks = [block for block in response.content if block.type == "text"]
            
            for text_block in text_blocks:
                if text_block.text:
                    yield AgentEvent("text", {"content": text_block.text})
            
            if not tool_calls:
                # Final yanıt
                final_text = "\n".join(b.text for b in text_blocks if b.text)
                yield AgentEvent("response", {"content": final_text})
                yield AgentEvent("done", {"iterations": iteration + 1})
                return
                
            tool_results = []
            for tool_call in tool_calls:
                yield AgentEvent("tool_call", {
                    "tool": tool_call.name,
                    "arguments": tool_call.input,
                    "iteration": iteration + 1,
                })
                
                result = await asyncio.to_thread(
                    execute_tool, tool_call.name, tool_call.input, self.workspace_path
                )
                
                result_str = json.dumps(result, ensure_ascii=False)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... (kısaltıldı)"
                    
                yield AgentEvent("tool_result", {
                    "tool": tool_call.name,
                    "success": result.get("success", False),
                    "summary": self._summarize_result(tool_call.name, result),
                })
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result_str
                })
                
            messages.append({"role": "user", "content": tool_results})
            
        yield AgentEvent("response", {"content": "⚠️ Maksimum araç çağrısına ulaşıldı."})
        yield AgentEvent("done", {"iterations": MAX_ITERATIONS, "max_reached": True})

    # ═══════════════════════════════════════════════
    # OPENAI AGENTIC LOOP (OpenAI, DeepSeek, vb.)
    # ═══════════════════════════════════════════════
    async def _run_openai(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        
        # DeepSeek OpenRouter veya custom base URL'ler için:
        if self.provider_type == "openrouter":
            client.base_url = "https://openrouter.ai/api/v1"
        elif self.provider_type == "deepseek":
            client.base_url = "https://api.deepseek.com"
        elif self.provider_type == "groq":
            client.base_url = "https://api.groq.com/openai/v1"

        system_instruction = f"""{SYSTEM_PROMPT}

Sen Unity projesi üzerinde çalışan bir AI asistanısın. Sana verilen araçları kullanarak projeyi keşfedebilir, dosyaları okuyabilir, arama yapabilir ve kod yazabilirsin.

[ÇALIŞMA PRENSİBİ - HAYATİ KURALLAR]
1. ÖNCE projeyi keşfet (dosya oku, ara).
2. KOD YAZARKEN: KESİNLİKLE parça kod (snippet) verme. Sadece değişen yeri değil, dosyanın TAMAMINI yazmak ZORUNDASIN.
3. KOD BLOKLARI: Her kod bloğunun İSTİSNASIZ İLK SATIRINA yolu ekle:
// path: Assets/Scripts/Tam/Dosya/Yolu.cs

4. `write_file` aracını C# kodu yazmak için KULLANMA. Bunun yerine, kodu Markdown kod bloğu (```csharp ... ```) içinde ver. Kullanıcı arayüzden onaylayacaktır.
5. Kullanıcının en son verdiği teknik talimatları asla unutma, her güncellemede bunları koru.
6. Eğer tam dosyayı yazmazsan sistem çalışmaz ve kullanıcıya hatalı bilgi vermiş olursun.

[BAĞLAM]
{self.context or "Yeni sohbet."}"""
        
        openai_tools = get_openai_tool_declarations()
        
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_message}
        ]
        
        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 OpenAI Agentic Loop iterasyon {iteration + 1}")
            
            try:
                response = await client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto"
                )
            except Exception as e:
                yield AgentEvent("error", {"message": f"OpenAI/API hatası: {str(e)}"})
                return

            message = response.choices[0].message
            
            # API formatında mesaja ekle
            msg_dict = {"role": "assistant"}
            if message.content:
                msg_dict["content"] = message.content
            if message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    } for tc in message.tool_calls
                ]
            messages.append(msg_dict)
            
            if not message.tool_calls:
                # Final yanıt
                final_text = message.content or "Tamamlandı."
                yield AgentEvent("response", {"content": final_text})
                yield AgentEvent("done", {"iterations": iteration + 1})
                return

            if message.content:
                yield AgentEvent("text", {"content": message.content})
                
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except:
                    tool_args = {}
                    
                yield AgentEvent("tool_call", {
                    "tool": tool_name,
                    "arguments": tool_args,
                    "iteration": iteration + 1,
                })
                
                result = await asyncio.to_thread(
                    execute_tool, tool_name, tool_args, self.workspace_path
                )
                
                result_str = json.dumps(result, ensure_ascii=False)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... (kısaltıldı)"
                    
                yield AgentEvent("tool_result", {
                    "tool": tool_name,
                    "success": result.get("success", False),
                    "summary": self._summarize_result(tool_name, result),
                })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": result_str
                })
                
        yield AgentEvent("response", {"content": "⚠️ Maksimum araç çağrısına ulaşıldı."})
        yield AgentEvent("done", {"iterations": MAX_ITERATIONS, "max_reached": True})

    # ═══════════════════════════════════════════════
    # BASIT FALLBACK (Function calling olmayan provider'lar)
    # ═══════════════════════════════════════════════
    async def _run_simple(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """Function calling desteklemeyen provider'lar için basit akış."""
        from ai_providers import AIProviderManager

        yield AgentEvent("thinking", {"text": "Direkt yanıt hazırlıyorum..."})

        try:
            provider = AIProviderManager.get_provider({
                "provider_type": self.provider_type,
                "api_key": self.api_key,
                "model_name": self.model_name,
            })

            prompt = f"{SYSTEM_PROMPT}\n\n[BAĞLAM]\n{self.context}\n\n[KULLANICI]\n{user_message}"

            if self.use_thinking and hasattr(provider, "analyze_code_with_thinking"):
                text, thinking, duration = await asyncio.to_thread(
                    provider.analyze_code_with_thinking, prompt
                )
                if thinking:
                    yield AgentEvent("thinking", {"text": thinking, "duration_ms": duration})
            else:
                text = await asyncio.to_thread(provider.analyze_code, prompt)

            yield AgentEvent("response", {"content": text})
            yield AgentEvent("done", {"iterations": 1})

        except Exception as e:
            yield AgentEvent("error", {"message": str(e)})

    def _summarize_result(self, tool_name: str, result: dict) -> str:
        """Tool sonucunu kısa özetle."""
        if not result.get("success"):
            return f"❌ {result.get('error', 'Bilinmeyen hata')}"

        if tool_name == "read_file":
            lines = result.get("total_lines", 0)
            trunc = " (kısaltıldı)" if result.get("truncated") else ""
            return f"📄 {result.get('path', '?')} — {lines} satır{trunc}"
        elif tool_name == "search_in_project":
            return f"🔍 '{result.get('query', '')}' — {result.get('total_matches', 0)} eşleşme"
        elif tool_name == "find_files":
            return f"📁 '{result.get('pattern', '')}' — {result.get('count', 0)} dosya"
        elif tool_name == "list_directory":
            return f"📂 {result.get('path', '')} — {result.get('count', 0)} öğe"
        elif tool_name == "write_file":
            return f"✏️ {result.get('path', '')} yazıldı"
        return "✅ Tamamlandı"
