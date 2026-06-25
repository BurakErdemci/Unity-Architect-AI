"""
AgentRunner — Agentic Loop motoru.

AI'a araçlar (tools) verir, AI hangisini çağıracağına karar verir,
araç sonucunu alır, tekrar AI'a gönderir. İş bitene kadar döngü devam eder.

Her adımda bir SSE event callback'i çağırılır (thinking, tool_call, response, done).
"""
import os
import json
import time
import uuid
import logging
import asyncio
import re
import subprocess
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from agentic.command_gates import APPROVAL_GATES as _APPROVAL_GATES, APPROVAL_RESULTS as _APPROVAL_RESULTS

# Sadece bu prefix/keyword'lerle başlayan komutlar otomatik çalışır (güvenli)
_SAFE_PREFIXES = (
    "ls", "ll", "la ", "find ", "grep ", "cat ", "head ", "tail ",
    "echo ", "pwd", "wc ", "diff ", "tree ",
    "git status", "git log", "git diff", "git show", "git branch",
    "git remote -v", "git fetch --dry", "git stash list",
)

def _is_dangerous_command(command: str) -> bool:
    """Komutun kullanıcı onayı gerektirip gerektirmediğini kontrol eder."""
    stripped = command.strip().lower()
    for safe in _SAFE_PREFIXES:
        if stripped == safe.strip() or stripped.startswith(safe):
            return False
    return True  # Whitelist dışı her komut tehlikeli sayılır


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
        thinking_level: str = "medium",
        conversation_id: Optional[int] = None,
        images: Optional[List[str]] = None,
        generation_mode: str = "auto",
        effort_level: str = "medium",
        ultracode: bool = False,
    ):
        self.provider_type = provider_type
        self.api_key = api_key
        self.model_name = model_name
        self.workspace_path = workspace_path
        self.language = language
        self.context = context
        self.thinking_level = thinking_level
        self.conversation_id = conversation_id
        self.images = images
        self.generation_mode = generation_mode  # auto | plan | step
        # Claude-only (subscription + claude-* model): effort_level → --effort,
        # ultracode → mesaja keyword enjeksiyonu. Diğer sağlayıcılarda yok sayılır.
        self.effort_level = effort_level
        self.ultracode = ultracode
        self.use_thinking = thinking_level != "off"

    def _get_architect_wisdom(self) -> str:
        """
        Proje kök dizininde ARCHITECT.md veya .claude.md varsa okur.
        Bu dosya proje kurallarını (naming convention, patterns vb.) içerir.
        """
        wisdom_paths = ["ARCHITECT.md", ".claude.md", "CLAUDE.md"]
        for p in wisdom_paths:
            full_path = os.path.join(self.workspace_path, p)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        return f"\n\n[PROJE KURALLARI (ARCHITECT.md)]\n{content}\n"
                except Exception as e:
                    logger.warning(f"Wisdom dosyası okunamadı ({p}): {e}")
        return ""

    async def _execute_tool_with_approval(
        self, tool_name: str, tool_args: dict
    ) -> tuple[dict, list]:
        """
        Tool'u çalıştırır ve (result_dict, extra_events) döndürür.

        NOT: Tehlikeli run_command onayı çağıran API yollarında (_run_gemini /
        _run_anthropic / _run_openai) ZATEN inline yapılıyor (onaylanmazsa orada
        'continue' edilir, buraya hiç gelmez). Eskiden burada İKİNCİ kez sorulması
        onaylanan komutlarda çift-onaya yol açıyordu; o yüzden bu metot artık
        yalnızca aracı çalıştırır. İmza (tuple) geriye-uyum için korunur
        (çağrılar 'result, _ = ...' biçiminde).
        """
        result = await asyncio.to_thread(
            execute_tool, tool_name, tool_args, self.workspace_path, self.conversation_id
        )
        return result, []

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
        elif self.provider_type == "subscription":
            # claude-* → kalıcı interaktif SDK session (native onay + AskUserQuestion + skill/slash).
            # codex (gpt-*) → kalıcı app-server session (native onay). agy → ephemeral CLI (ertelendi).
            _name = (self.model_name or "claude").lower()
            _is_codex = _name.startswith("gpt-")
            _is_agy = _name.startswith(("gemini", "agy-"))
            if _is_codex:
                # codex → kalıcı app-server session (native onay + bağlam sürekliliği)
                async for event in self._run_codex_session(user_message):
                    yield event
            elif _is_agy:
                # agy → şimdilik ephemeral CLI yolu (kalıcı-session ertelendi)
                async for event in self._run_cli(user_message):
                    yield event
            else:
                async for event in self._run_claude_session(user_message):
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

        # Thinking config — sadece bilinen thinking destekleyen modeller için
        _THINKING_MODELS = ("gemini-2.5", "gemini-3.", "gemini-3.0", "gemini-3.1")
        _supports_thinking = any(t in self.model_name for t in _THINKING_MODELS)
        thinking_config = None
        if self.use_thinking and _supports_thinking:
            thinking_config = gtypes.ThinkingConfig(thinking_budget=4096)

        config = gtypes.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            thinking_config=thinking_config,
        )

        # İlk mesaj
        parts = [gtypes.Part(text=user_message)]
        if self.images:
            for img_data in self.images:
                try:
                    # data:image/png;base64,.... formatını ayıkla
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        mime_type = header.split(":")[1].split(";")[0]
                        parts.append(gtypes.Part(inline_data=gtypes.Blob(mime_type=mime_type, data=base64_str)))
                    else:
                        # Fallback
                        parts.append(gtypes.Part(inline_data=gtypes.Blob(mime_type="image/jpeg", data=img_data)))
                except Exception as e:
                    logger.error(f"Gemini image parsing hatası: {e}")

        contents = [gtypes.Content(role="user", parts=parts)]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 Agentic Loop iterasyon {iteration + 1}")
            
            # Rate limit (15 RPM) için güvenli mola (her 4s bir hak doluyor, 5s garantidir)
            if iteration > 0:
                await asyncio.sleep(5.0)

            # Retry mekanizması (429 hataları için daha agresif)
            response = None
            for retry in range(3):
                try:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    )
                    break 
                except Exception as e:
                    err_msg = str(e).lower()
                    # 429 (Hız Sınırı) veya 503 (Servis Kesintisi) durumlarında bekle ve tekrar dene
                    if any(code in err_msg for code in ["429", "503", "too many requests", "service unavailable"]):
                        wait_time = (retry + 1) * 10
                        logger.warning(f"  ⚠️ Google API Hatası ({'429' if '429' in err_msg else '503'}). {wait_time}s bekleniyor... (Deneme {retry+1}/3)")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # 400 / diğer hatalar — tam hata mesajını logla
                        logger.error(f"  ❌ Gemini API hatası [{self.model_name}]: {str(e)}", exc_info=True)
                        yield AgentEvent("error", {"message": f"AI hatası: {str(e)}"})
                        return
            
            if not response:
                yield AgentEvent("error", {"message": "AI yanıt vermeyi reddetti (Rate Limit)."})
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

                # Tehlikeli komut kontrolü ve onay yield'ı
                if tool_name == "run_command":
                    command = tool_args.get("command", "")
                    if _is_dangerous_command(command):
                        # Onay event'ini HEMEN yield et
                        gate_id = uuid.uuid4().hex[:10]
                        event = asyncio.Event()
                        _APPROVAL_GATES[gate_id] = event
                        _APPROVAL_RESULTS[gate_id] = False
                        
                        yield AgentEvent("command_approval_needed", {
                            "command": command,
                            "gate_id": gate_id,
                        })
                        
                        # Şimdi onayı bekle
                        try:
                            await asyncio.wait_for(event.wait(), timeout=60.0)
                            approved = _APPROVAL_RESULTS.get(gate_id, False)
                        except asyncio.TimeoutError:
                            approved = False
                        finally:
                            _APPROVAL_GATES.pop(gate_id, None)
                            _APPROVAL_RESULTS.pop(gate_id, None)

                        if not approved:
                            result = {"success": False, "summary": "❌ Kullanıcı reddetti."}
                            # Tool result olarak ilet
                            yield AgentEvent("tool_result", {
                                "tool": tool_name,
                                "success": False,
                                "summary": "❌ Kullanıcı tarafından reddedildi.",
                            })
                            # AI'a tool sonucunu bildir (döngü devam etsin diye)
                            function_response_parts.append(
                                gtypes.Part(function_response=gtypes.FunctionResponse(
                                    name=tool_name,
                                    response=result,
                                ))
                            )
                            continue

                # Normal tool execution
                result, _ = await self._execute_tool_with_approval(tool_name, tool_args)

                screenshot_b64 = result.pop("image_base64", None)
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
                        response={"result": result_str},
                    ))
                )
                if screenshot_b64:
                    import base64 as _b64
                    raw_bytes = _b64.b64decode(screenshot_b64.split(",", 1)[1])
                    function_response_parts.append(
                        gtypes.Part(inline_data=gtypes.Blob(mime_type="image/jpeg", data=raw_bytes))
                    )

            # Arada metin varsa (AI'ın açıklaması) yield et
            for p in text_parts:
                if p.text:
                    yield AgentEvent("text", {"content": p.text})

            # AI'ın yanıtını ve tool sonuçlarını geçmişe ekle
            contents.append(candidate.content)
            contents.append(gtypes.Content(role="tool", parts=function_response_parts))

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

        # İlk mesaj içeriği
        user_parts = [{"type": "text", "text": user_message}]
        if self.images:
            for img_data in self.images:
                try:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        mime_type = header.split(":")[1].split(";")[0]
                        user_parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": base64_str
                            }
                        })
                except Exception as e:
                    logger.warning(f"Görsel işlenemedi: {e}")

        # Anthropic API: sistem talimatı messages listesine DEĞİL, create()'in
        # system= parametresine gider (aşağıda system_instruction olarak geçiliyor).
        # messages'a "system" rolü koymak API 400 döndürür.
        messages = []

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 Anthropic Agentic Loop iterasyon {iteration + 1}")
            
            # Tool formatı
            anthropic_tools = []
            for t in TOOL_DEFINITIONS:
                anthropic_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"]
                })

            # İlk mesaj içeriği
            if iteration == 0:
                user_parts = [{"type": "text", "text": user_message}]
                if self.images:
                    for img_data in self.images:
                        try:
                            if "," in img_data:
                                header, base64_str = img_data.split(",", 1)
                                mime_type = header.split(":")[1].split(";")[0]
                                user_parts.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": base64_str
                                    }
                                })
                        except Exception as e:
                            logger.error(f"Anthropic image parsing hatası: {e}")
                messages.append({"role": "user", "content": user_parts})
            
            try:
                response = await client.messages.create(
                    model=self.model_name,
                    max_tokens=4096,
                    system=system_instruction + self._get_architect_wisdom(),
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

                # Terminal Onay Katmanı
                if tool_call.name == "run_command":
                    command = tool_call.input.get("command", "")
                    if _is_dangerous_command(command):
                        gate_id = uuid.uuid4().hex[:10]
                        event = asyncio.Event()
                        _APPROVAL_GATES[gate_id] = event
                        yield AgentEvent("command_approval_needed", {"command": command, "gate_id": gate_id})
                        try:
                            await asyncio.wait_for(event.wait(), timeout=60.0)
                            approved = _APPROVAL_RESULTS.get(gate_id, False)
                        except: approved = False
                        finally: _APPROVAL_GATES.pop(gate_id, None)
                        
                        if not approved:
                            result_str = json.dumps({"success": False, "summary": "Reddedildi"})
                            tool_results.append({"type": "tool_result", "tool_use_id": tool_call.id, "content": result_str})
                            continue

                result, _ = await self._execute_tool_with_approval(tool_call.name, tool_call.input)

                screenshot_b64 = result.pop("image_base64", None)
                result_str = json.dumps(result, ensure_ascii=False)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "... (kısaltıldı)"

                yield AgentEvent("tool_result", {
                    "tool": tool_call.name,
                    "success": result.get("success", False),
                    "summary": self._summarize_result(tool_call.name, result),
                })

                if screenshot_b64:
                    content = [
                        {"type": "text", "text": result_str},
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": screenshot_b64.split(",", 1)[1],
                        }},
                    ]
                else:
                    content = result_str

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": content
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
        
        # İlk mesaj içeriği
        user_content = [{"type": "text", "text": user_message}]
        if self.images:
            for img_data in self.images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_data} # OpenAI direkt data URL kabul eder
                })

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]
        
        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 OpenAI Agentic Loop iterasyon {iteration + 1}")
            
            # Rate limit koruması için kısa mola
            if iteration > 0:
                await asyncio.sleep(5.0)

            # Retry mekanizması
            response = None
            for retry in range(3):
                try:
                    response = await client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        tools=openai_tools,
                        tool_choice="auto"
                    )
                    break
                except Exception as e:
                    err_msg = str(e).lower()
                    logger.error(f"  ❌ OpenAI/OpenRouter API hatası [{self.provider_type} / {self.model_name}]: {str(e)}", exc_info=True)
                    if any(code in err_msg for code in ["429", "503", "too many requests", "service unavailable"]):
                        wait_time = (retry + 1) * 10
                        logger.warning(f"  ⚠️ OpenAI/OpenRouter Hatası. {wait_time}s bekleniyor... (Deneme {retry+1}/3)")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        yield AgentEvent("error", {"message": f"OpenAI/API hatası: {str(e)}"})
                        return
            
            if not response:
                yield AgentEvent("error", {"message": "AI yanıt vermeyi reddetti (Rate Limit/API)."})
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

                # Terminal Onay Katmanı
                if tool_name == "run_command":
                    command = tool_args.get("command", "")
                    if _is_dangerous_command(command):
                        gate_id = uuid.uuid4().hex[:10]
                        event = asyncio.Event()
                        _APPROVAL_GATES[gate_id] = event
                        yield AgentEvent("command_approval_needed", {"command": command, "gate_id": gate_id})
                        try:
                            await asyncio.wait_for(event.wait(), timeout=60.0)
                            approved = _APPROVAL_RESULTS.get(gate_id, False)
                        except: approved = False
                        finally: _APPROVAL_GATES.pop(gate_id, None)
                        
                        if not approved:
                            messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": "Reddedildi"})
                            continue

                result, _ = await self._execute_tool_with_approval(tool_name, tool_args)

                screenshot_b64 = result.pop("image_base64", None)
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
                if screenshot_b64:
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "[Screenshot — yukarıdaki tool sonucuyla ilgili görsel]"},
                            {"type": "image_url", "image_url": {"url": screenshot_b64}},
                        ],
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
            logger.info(f"[AgentRunner] Starting simple run for provider: {self.provider_type}")
            provider = AIProviderManager.get_provider({
                "provider_type": self.provider_type,
                "api_key": self.api_key,
                "model_name": self.model_name,
            })

            prompt = f"{SYSTEM_PROMPT}\n\n[BAĞLAM]\n{self.context}\n\n[KULLANICI]\n{user_message}"

            if self.provider_type == "subscription":
                # Subscription ajanları için mod bilgisini ilet
                is_step_mode = (getattr(self, 'generation_mode', 'plan') == 'step')
                full_text = ""
                async for event in provider.analyze_code_with_thinking(prompt, thinking_level=self.thinking_level, cwd=self.workspace_path, interactive=is_step_mode):
                    if event["type"] == "tool_call":
                        yield AgentEvent("tool_call", {"tool": event["tool"], "summary": event["summary"]})
                    elif event["type"] == "thinking":
                        yield AgentEvent("thinking", {"text": event["text"]})
                    elif event["type"] == "error":
                        yield AgentEvent("error", {"message": event["content"]})
                    elif event["type"] == "final":
                        full_text = event["text"]
                
                yield AgentEvent("response", {"content": full_text})
            else:
                if self.thinking_level != "off" and hasattr(provider, "analyze_code_with_thinking"):
                    logger.info(f"[AgentRunner] Requesting thinking response (Level: {self.thinking_level}) at {self.workspace_path}")
                    text, thinking, duration = await asyncio.to_thread(
                        provider.analyze_code_with_thinking, prompt, thinking_level=self.thinking_level, cwd=self.workspace_path
                    )
                    if thinking:
                        yield AgentEvent("thinking", {"text": thinking, "duration_ms": duration})
                else:
                    logger.info(f"[AgentRunner] Requesting standard analysis from {self.provider_type} at {self.workspace_path}")
                    text = await asyncio.to_thread(provider.analyze_code, prompt, thinking_level=self.thinking_level, cwd=self.workspace_path)

                logger.info(f"[AgentRunner] Response received ({len(text) if text else 0} chars).")
                yield AgentEvent("response", {"content": text})

            yield AgentEvent("done", {"iterations": 1})

        except Exception as e:
            logger.error(f"[AgentRunner] Error in simple run: {str(e)}", exc_info=True)
            yield AgentEvent("error", {"message": str(e)})

    # ═══════════════════════════════════════════════
    # CLI PROVIDER (Claude Code, Codex — Ephemeral Snapshot)
    # ═══════════════════════════════════════════════
    async def _run_cli(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        CLIProvider'ı ephemeral snapshot modunda çalıştırır.
        CLI özgürce yazar → değişiklikler yakalanır → revert → onaya sunulur.
        Onaylanan dosyalar mevcut frontend write mekanizmasıyla uygulanır.
        """
        from ai_providers import AIProviderManager

        provider = AIProviderManager.get_provider({
            "provider_type": self.provider_type,
            "model_name": self.model_name,
            "api_key": getattr(self, "api_key", ""),
        })

        # Bağlamı prompt'a ekle
        context_block = f"\n\n[PROJE BAĞLAMI]\n{self.context}" if self.context else ""
        enriched_prompt = user_message + context_block

        final_text = ""
        ephemeral_files = []

        async for event in provider.analyze_code(
            enriched_prompt,
            thinking_level="medium" if self.use_thinking else "off",
            cwd=self.workspace_path or ".",
            interactive=True,  # Her zaman ephemeral mod
        ):
            etype = event.get("type")

            if etype == "delta":
                yield AgentEvent("text", {"content": event.get("text", "")})
            elif etype == "thinking":
                yield AgentEvent("thinking", {"text": event.get("text", "")})
            elif etype == "tool_call":
                yield AgentEvent("tool_call", {
                    "tool": event.get("tool", "CLI"),
                    "arguments": {"summary": event.get("summary", "")},
                    "iteration": 1,
                })
            elif etype == "tool_result":
                yield AgentEvent("tool_result", {
                    "tool": event.get("tool", "CLI"),
                    "success": event.get("success", True),
                    "summary": event.get("summary", ""),
                })
            elif etype == "ephemeral_changes":
                ephemeral_files = event.get("files", [])
            elif etype == "final":
                final_text = event.get("text", "")
            elif etype == "error":
                yield AgentEvent("error", {"message": event.get("content", "")})
                return

        # Ephemeral değişiklikleri encode et
        # Silinen dosyalar → pending_delete event'i olarak ayrıca gönder
        # Değiştirilen/eklenen dosyalar → // path: code block (parseGeneratedFiles yakalar)
        modified = [f for f in ephemeral_files if not f.get("deleted")]
        deleted  = [f for f in ephemeral_files if f.get("deleted")]

        response_parts = [final_text] if final_text else []
        for f in modified:
            ext  = f["path"].rsplit(".", 1)[-1] if "." in f["path"] else "cs"
            lang = "csharp" if ext == "cs" else ext
            response_parts.append(f"\n```{lang}\n// path: {f['path']}\n{f['code']}\n```")

        yield AgentEvent("response", {"content": "\n".join(response_parts)})

        # Silinen her dosya için ayrı pending_delete event'i
        for f in deleted:
            yield AgentEvent("pending_delete", {"path": f["path"]})

        yield AgentEvent("done", {"iterations": 1})

    # ═══════════════════════════════════════════════
    # CLAUDE KALICI SESSION (claude-agent-sdk, native onay)
    # ═══════════════════════════════════════════════
    async def _run_claude_session(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Claude Code'u sohbet başına KALICI interaktif session olarak sürer.
        - Bağlam turlar arası korunur (DB geçmişi prompt'a basılmaz; session hatırlar).
        - Onay native: can_use_tool → command_gates → frontend onay kartı.
        - AskUserQuestion (A/B/C) → question_needed event → frontend seçim kartı.
        """
        import json as _json
        import subprocess as _sp
        from providers.cli_base import BaseCLIProvider
        from providers.claude_sdk_session import get_session, close_session, _SESSIONS

        # MCP: SADECE unityMCP (Unity sahne kontrolü) session'a girsin. Eski 'unityai'
        # (mcp__unityai__bash/save_file + kendi onay köprüsü) ARTIK GİRMESİN — terminal/yazma
        # built-in Bash/Write üzerinden native can_use_tool onayına gitsin (Seçenek 1).
        # NOT: setting_sources=["project","user"] KORUNUR (skill + slash komutları için şart).
        try:
            from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
            mcp_servers_cfg = {}
            if unity_mcp_manager.is_running():
                mcp_servers_cfg["unityMCP"] = {"url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp"}
            # Temiz .mcp.json yaz (unityai YOK) — eski/bayat kayıtların üstüne yaz
            if self.workspace_path and os.path.isdir(self.workspace_path):
                with open(os.path.join(self.workspace_path, ".mcp.json"), "w", encoding="utf-8") as f:
                    _json.dump({"mcpServers": mcp_servers_cfg}, f, indent=2)
            # Önceki sürümlerin user-scope'a yazdığı unityai kaydını temizle
            # (_resolve_exec @staticmethod — provider örneği yaratmaya gerek yok)
            _sp.run(BaseCLIProvider._resolve_exec(["claude", "mcp", "remove", "unityai", "--scope", "user"]),
                    capture_output=True, timeout=5)
        except Exception as e:
            logger.warning(f"[ClaudeSession] MCP temizleme/yazma hatası: {e}")

        model = self.model_name if (self.model_name or "").startswith("claude-") else None

        # Max effort (Claude-only) → ClaudeAgentOptions.effort="max" (--effort max).
        # effort connect-time KİLİTLİ (SDK'da set_effort yok). Cache'li session'ın effort'u
        # farklıysa close+recreate gerekir: bu, o sohbetteki CANLI session'ı sıfırlar (DB
        # bağlam özeti aşağıda yeniden enjekte edilir). Böylece toggle gerçekten etki eder.
        desired_effort = "max" if self.effort_level == "max" else None
        _existing = _SESSIONS.get(self.conversation_id)
        if _existing is not None and _existing.effort != desired_effort:
            logger.info(f"[ClaudeSession] effort değişti ({_existing.effort}→{desired_effort}); "
                        f"session yeniden kuruluyor (canlı bağlam sıfırlanır, DB özeti korunur)")
            await close_session(self.conversation_id)

        session = get_session(
            self.conversation_id,
            model=model,
            cwd=self.workspace_path or ".",
            permission_mode="default",
            setting_sources=["project", "user"],  # skill + slash komutları için ZORUNLU
            effort=desired_effort,                 # Claude-only; None ise CLI varsayılanı
            # Savunma: eski unityai araçları bir şekilde yüklenirse bile kapalı kalsın;
            # .cs yazan onaysız unityMCP aracı da kapalı (built-in Write native onaydan geçer).
            disallowed_tools=[
                "mcp__unityMCP__manage_script",
                "mcp__unityai__bash",
                "mcp__unityai__save_file",
            ],
        )

        # Oto mod → onay sormadan otomatik izin; Adım/Plan modu → her işlemde onay kartı.
        # Session kalıcı olduğu için mod her turda güncellenir (kullanıcı ortada değiştirebilir).
        session.auto_approve = (self.generation_mode == "auto")

        # İlk turda proje bağlamını ekle; sonraki turlarda session zaten hatırlıyor.
        message = user_message
        if self.context and not session.session_id:
            message = f"{user_message}\n\n[PROJE BAĞLAMI]\n{self.context}"
        # Ultracode (Claude-only): SDK'da option YOK → tek yol mesaja keyword enjeksiyonu.
        # CLI bu kelimeyi görünce çok-ajanlı ultracode akışını tetikler (belgesiz; sürüme bağlı).
        if self.ultracode:
            message = f"{message}\n\nultracode"

        try:
            async for ev in session.stream(message):
                etype = ev.pop("type", "text")
                yield AgentEvent(etype, ev)
        except Exception as e:
            logger.exception("[ClaudeSession] stream hatası")
            yield AgentEvent("error", {"message": f"Claude session hatası: {e}"})

    # ═══════════════════════════════════════════════
    # CODEX KALICI SESSION (codex app-server, native onay)
    # ═══════════════════════════════════════════════
    async def _run_codex_session(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Codex'i sohbet başına KALICI app-server session olarak sürer (claude muadili).
        - Bağlam turlar arası korunur (thread; DB geçmişi her turda prompt'a basılmaz).
        - Onay native: item/commandExecution|fileChange/requestApproval → command_gates
          → frontend onay kartı (Claude SDK yoluyla AYNI kartlar, yeni UI yok).
        - Abonelik (ChatGPT) auth — API key gerekmez.
        """
        from providers.codex_session import get_session

        session = get_session(
            self.conversation_id,
            model=self.model_name,
            cwd=self.workspace_path or ".",
        )
        # Oto mod → onay otomatik accept; Adım/Plan modu → her mutasyonda onay kartı.
        session.auto_approve = (self.generation_mode == "auto")

        # İlk turda proje bağlamını ekle; sonraki turlarda thread zaten hatırlıyor.
        message = user_message
        if self.context and not session._ctx_injected:
            message = f"{user_message}\n\n[PROJE BAĞLAMI]\n{self.context}"
            session._ctx_injected = True

        try:
            async for ev in session.stream(message):
                etype = ev.pop("type", "text")
                yield AgentEvent(etype, ev)
        except Exception as e:
            logger.exception("[CodexSession] stream hatası")
            yield AgentEvent("error", {"message": f"Codex session hatası: {e}"})

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
