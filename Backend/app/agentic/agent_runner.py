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

from tools.tool_registry import (
    TOOL_DEFINITIONS, execute_tool, get_openai_tool_declarations,
    get_gemini_tool_declarations, _all_tool_definitions,
)
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


# conversation_id → son tur'u işleyen subscription CLI'ı ('claude'|'codex'|'agy').
# CLI değişince (örn. Claude→Codex) hedef provider'ın bayat session'ı kapatılır →
# bir sonraki turda tam transcript yeniden enjekte edilir (kaldığı yerden devam).
_LAST_SUB_PROVIDER: Dict[int, str] = {}

# Yeni CLI'a geçmiş enjekte edilirken kullanılan başlık (context = tam transcript).
# Guardrail cümlesi ÖZELLİKLE agy için önemli: agy --dangerously-skip-permissions ile
# tam otonom çalışıyor ve sistem prompt append kanalı yok (Claude'daki _APP_SYSTEM_APPEND
# muadili yok). Guardrail olmadan, "kaldığımız yeri biliyor musun?" gibi belirsiz/meta
# sorularda agy bunu bir araştırma görevi sanıp dosya/web taramaya sapabiliyor (canlı
# gözlendi: alakasız bir CLI-flag konusunu araştırıp kafası karışmış "Clarification
# Required" ile bitirdi). Codex/Claude aynı bağlamla doğru yanıt verdiği için context
# içeriği sorunlu değildi — eksik olan yalnız "doğrudan bundan cevapla" talimatıydı.
_HANDOFF_HEADER = (
    "[ÖNCEKİ KONUŞMA BAĞLAMI — bu geçmiş sana YETERLİ bağlamı veriyor. Kullanıcı "
    "'kaldığımız yeri/ne yaptığımızı biliyor musun' tarzı bir şey soruyorsa, dosya "
    "okuma/tarama/web araması YAPMADAN doğrudan bu geçmişten özetleyerek yanıtla.]"
)


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
        videos: Optional[List[dict]] = None,
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
        self.videos = videos  # [{"kind":"path"|"url", ...}] → _prepare_videos ile kareye çevrilir
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

    async def _reset_session_for(self, provider: str) -> None:
        """CLI değişiminde hedef provider'ın bu sohbete ait canlı session'ını kapatır.
        Böylece bir sonraki tur 'ilk tur' sayılır ve tam transcript (self.context)
        yeniden enjekte edilir → yeni CLI aradaki turları da görüp kaldığı yerden devam eder."""
        if self.conversation_id is None:
            return
        try:
            if provider in ("cursor", "copilot", "opencode"):
                from providers.oneshot_cli import close_session as _close_oneshot
                await _close_oneshot(provider, self.conversation_id)
                logger.info(f"[handoff] {provider} session resetlendi (CLI değişimi)")
                return
            if provider == "codex":
                from providers.codex_session import close_session
            elif provider == "agy":
                from providers.agy_session import close_session
            else:
                from providers.claude_sdk_session import close_session
            await close_session(self.conversation_id)
            logger.info(f"[handoff] {provider} session resetlendi (CLI değişimi) → tam transcript yeniden enjekte edilecek")
        except Exception as e:
            logger.warning(f"[handoff] {provider} session reset hatası: {e}")

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

    def _identity_note(self) -> str:
        """Modelin kendini DOĞRU tanıması için system prompt'a eklenir. LLM'ler hangi model
        olduklarını güvenilir bilmez (ör. GLM 'ben Claude'um' diyebilir). Sadece API
        sağlayıcılarında; CLI/abonelik ve ollama'da kimlik zaten net."""
        if self.provider_type in ("subscription", "ollama"):
            return ""
        return (f"\n\n[MODEL KİMLİĞİN] Sen '{self.model_name}' modelisin ve "
                f"'{self.provider_type}' sağlayıcısı üzerinden çalışıyorsun. Kimliğin veya hangi "
                f"model olduğun sorulursa BUNU söyle; farklı bir model (Claude/GPT/Gemini vb.) "
                f"olduğunu İDDİA ETME.")

    async def _prepare_videos(self, user_message: str) -> str:
        """Videoları (yerel dosya + mesaja YAPIŞTIRILAN URL) kare data-URI'leri + transkripte
        çevirip mevcut görsel hattına enjekte eder. Kareler self.images'a katılır (sağlayıcı
        yolları DEĞİŞMEZ), transkript+bağlam bloğu user_message'ın başına eklenir. URL'ler
        ayrı UI'dan değil doğrudan mesaj metninden otomatik yakalanır. Hata YUMUŞAK."""
        from providers import video_extract
        videos = list(self.videos or [])
        for _u in video_extract.detect_video_urls(user_message):
            videos.append({"kind": "url", "url": _u})
        if not videos:
            return user_message
        blocks, all_uris = [], []
        for src in videos:
            try:
                res = await asyncio.to_thread(
                    video_extract.extract, src, self.workspace_path,
                    f"vid_conv{self.conversation_id}")
                all_uris.extend(res.frame_data_uris)
                blocks.append(video_extract.build_video_block(res.meta, res.transcript))
            except Exception as e:
                logger.warning(f"[video] çıkarım hatası: {e}")
                blocks.append(f"\n\n[VİDEO] Bir video işlenemedi ({e}). Metinle devam et.\n")
        if all_uris:
            self.images = (self.images or []) + all_uris
        return ("".join(blocks) + "\n" + user_message) if blocks else user_message

    async def run(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        Agentic loop'u çalıştırır. Her adımda AgentEvent yield eder.
        """
        user_message = await self._prepare_videos(user_message)
        if self.provider_type == "google":
            async for event in self._run_gemini(user_message):
                yield event
        elif self.provider_type == "anthropic":
            async for event in self._run_anthropic(user_message):
                yield event
        elif self.provider_type in ("openai", "openrouter", "deepseek", "groq", "moonshot", "z-ai", "nvidia"):
            async for event in self._run_openai(user_message):
                yield event
        elif self.provider_type == "subscription":
            # claude-* → kalıcı interaktif SDK session (native onay + AskUserQuestion + skill/slash).
            # codex (gpt-*) → kalıcı app-server session (native onay). agy → disk-resume CLI.
            # cursor-*/copilot-*/opencode:* → one-shot CLI + resmi resume (oneshot_cli).
            _name = (self.model_name or "claude").lower()
            if _name.startswith("cursor-"):
                _cur = "cursor"
            elif _name.startswith("copilot-"):
                _cur = "copilot"
            elif _name.startswith("opencode:"):
                _cur = "opencode"
            elif _name.startswith("gpt-"):
                _cur = "codex"
            elif _name.startswith(("gemini", "agy-")):
                _cur = "agy"
            else:
                _cur = "claude"

            # CLI'lar arası "kaldığı yerden devam": provider değiştiyse hedef CLI'ın
            # (varsa) bayat session'ını kapat → ilk-tur enjeksiyonu tetiklenir, tam
            # transcript (self.context) yeniden verilir → aradaki turları da görür.
            if self.conversation_id is not None:
                _prev = _LAST_SUB_PROVIDER.get(self.conversation_id)
                if _prev and _prev != _cur:
                    await self._reset_session_for(_cur)
                _LAST_SUB_PROVIDER[self.conversation_id] = _cur

            if _cur == "codex":
                async for event in self._run_codex_session(user_message):
                    yield event
            elif _cur == "agy":
                async for event in self._run_agy_session(user_message):
                    yield event
            elif _cur in ("cursor", "copilot", "opencode"):
                async for event in self._run_oneshot_cli_session(user_message, _cur):
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
        # Built-in + Unity MCP araçları (şema Gemini için sanitize edilir → 40+ Unity tool da gelir).
        _gemini_decls = get_gemini_tool_declarations()[0]["function_declarations"]
        tools = [gtypes.Tool(function_declarations=[
            gtypes.FunctionDeclaration(
                name=d["name"],
                description=d["description"],
                parameters=d["parameters"],
            )
            for d in _gemini_decls
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

        # Thinking config — kayıtçıdan (effort_caps): gemini-3.x → thinking_level (enum),
        # gemini-2.5 → thinking_budget (token). İkisi birlikte ASLA gönderilmez (3.x'te 400).
        # auto → None → modelin kendi varsayılanı.
        from providers.effort_caps import map_effort as _map_effort
        _eff = _map_effort("google", self.model_name,
                           self.effort_level or self.thinking_level or "auto")
        thinking_config = None
        try:
            if "gemini_thinking_level" in _eff:
                thinking_config = gtypes.ThinkingConfig(thinking_level=_eff["gemini_thinking_level"])
            elif "gemini_thinking_budget" in _eff:
                thinking_config = gtypes.ThinkingConfig(thinking_budget=_eff["gemini_thinking_budget"])
        except TypeError:
            # Eski google-genai SDK thinking_level bilmiyorsa güvenli bütçeye düş
            thinking_config = gtypes.ThinkingConfig(thinking_budget=4096)

        config = gtypes.GenerateContentConfig(
            system_instruction=system_instruction + self._identity_note(),
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

        _turn_t0 = time.time()   # footer: tur süresi + token
        _turn_in = _turn_out = 0
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

            _um = getattr(response, "usage_metadata", None)
            if _um:
                _turn_in += getattr(_um, "prompt_token_count", 0) or 0
                _turn_out += getattr(_um, "candidates_token_count", 0) or 0

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
                yield AgentEvent("turn_usage", {
                    "input_tokens": _turn_in, "output_tokens": _turn_out, "cost_usd": None,
                    "duration_ms": int((time.time() - _turn_t0) * 1000),
                })
                yield AgentEvent("response", {"content": final_text})
                yield AgentEvent("done", {"iterations": iteration + 1})
                return

            # Tool call'ları çalıştır
            function_response_parts = []
            screenshot_parts = []  # Gemini: görsel tool-role Content'e KONMAZ (400) → ayrı user-content

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
                    # Gemini tool-role Content'ine inline_data KONULAMAZ (400 INVALID_ARGUMENT).
                    # Görseli ayrı user-role Content olarak biriktir (aşağıda eklenir).
                    screenshot_parts.append(
                        gtypes.Part(inline_data=gtypes.Blob(mime_type="image/jpeg", data=raw_bytes))
                    )

            # Arada metin varsa (AI'ın açıklaması) yield et
            for p in text_parts:
                if p.text:
                    yield AgentEvent("text", {"content": p.text})

            # AI'ın yanıtını ve tool sonuçlarını geçmişe ekle
            contents.append(candidate.content)
            contents.append(gtypes.Content(role="tool", parts=function_response_parts))
            # Screenshot(lar) → AYRI user-role Content (Gemini tool-role'a görsel kabul etmez → 400)
            if screenshot_parts:
                contents.append(gtypes.Content(
                    role="user",
                    parts=[gtypes.Part(text="(capture_unity_screenshot çıktısı — ekran görüntüsü:)")] + screenshot_parts,
                ))

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
        for t in _all_tool_definitions():
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
        _turn_t0 = time.time()   # footer: tur süresi + token
        _turn_in = _turn_out = 0

        # Sistem önekini tur başında BİR kez kur (deterministik) ve cache_control ile
        # işaretle → statik system prefix 2..N. iterasyonlarda cache'ten okunur (~%90 tasarruf).
        _sys_text = system_instruction + self._get_architect_wisdom() + self._identity_note()
        _sys_blocks = [{"type": "text", "text": _sys_text,
                        "cache_control": {"type": "ephemeral"}}]

        for iteration in range(MAX_ITERATIONS):
            logger.info(f"  🔄 Anthropic Agentic Loop iterasyon {iteration + 1}")
            
            # Tool formatı
            anthropic_tools = []
            for t in _all_tool_definitions():
                anthropic_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"]
                })
            # Prompt caching: son tool'a breakpoint → tüm 'tools' prefix'i (statik ve
            # büyük ~24k tok Unity MCP şemaları) cache'lenir; tekrar turlarda ~%90 tasarruf.
            if anthropic_tools:
                anthropic_tools[-1] = {**anthropic_tools[-1],
                                       "cache_control": {"type": "ephemeral"}}

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
                # Effort: kayıtçıdan; extra_body ile geçer (output_config.effort —
                # SDK sürümü parametreyi tanımasa da httpx gövdesine girer). auto → {}.
                from providers.effort_caps import map_effort as _map_effort
                _eff_body = _map_effort("anthropic", self.model_name,
                                        self.effort_level or self.thinking_level or "auto"
                                        ).get("anthropic_extra_body")
                response = await client.messages.create(
                    model=self.model_name,
                    max_tokens=4096,
                    system=_sys_blocks,
                    messages=messages,
                    tools=anthropic_tools,
                    **({"extra_body": _eff_body} if _eff_body else {}),
                )
            except Exception as e:
                yield AgentEvent("error", {"message": f"Claude hatası: {str(e)}"})
                return

            _u = getattr(response, "usage", None)
            if _u:
                _turn_in += getattr(_u, "input_tokens", 0) or 0
                _turn_out += getattr(_u, "output_tokens", 0) or 0

            messages.append({"role": "assistant", "content": response.content})

            tool_calls = [block for block in response.content if block.type == "tool_use"]
            text_blocks = [block for block in response.content if block.type == "text"]
            
            for text_block in text_blocks:
                if text_block.text:
                    yield AgentEvent("text", {"content": text_block.text})
            
            if not tool_calls:
                # Final yanıt
                final_text = "\n".join(b.text for b in text_blocks if b.text)
                yield AgentEvent("turn_usage", {
                    "input_tokens": _turn_in, "output_tokens": _turn_out, "cost_usd": None,
                    "duration_ms": int((time.time() - _turn_t0) * 1000),
                })
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
        elif self.provider_type == "moonshot":
            client.base_url = "https://api.moonshot.cn/v1"
        elif self.provider_type == "z-ai":
            client.base_url = "https://api.z.ai/api/paas/v4"
        elif self.provider_type == "nvidia":
            # NVIDIA NIM — OpenAI-uyumlu, tek nvapi- key ile ücretsiz model havuzu
            client.base_url = "https://integrate.api.nvidia.com/v1"

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

        # Prompt caching: statik system öneki (SYSTEM_PROMPT + transcript + kimlik) tekrar
        # turlarda cache'ten okunsun. OpenRouter cache_control breakpoint'ini DESTEKLER
        # (OR→Anthropic/Gemini için explicit ZORUNLU). DeepSeek/OpenAI/Moonshot(Kimi)/z-ai(GLM)
        # zaten OTOMATİK prefix-cache yapar → düz string yeterli; bilinmeyen alanı reddedebilen
        # sağlayıcılara cache_control göndermeyerek riski sıfırlıyoruz.
        _sys = system_instruction + self._identity_note()
        if self.provider_type == "openrouter":
            system_msg = {"role": "system", "content": [
                {"type": "text", "text": _sys, "cache_control": {"type": "ephemeral"}},
            ]}
        else:
            system_msg = {"role": "system", "content": _sys}

        messages = [
            system_msg,
            {"role": "user", "content": user_content}
        ]

        _turn_t0 = time.time()   # footer: tur süresi + token
        # Reasoning/effort: kayıtçıdan (effort_caps) — auto/desteklenmeyen → hiçbir
        # parametre gitmez. request_params üst-seviye (reasoning_effort), extra_body
        # sağlayıcıya özel gövde (NIM chat_template_kwargs, deepseek/z-ai thinking).
        from providers.effort_caps import map_effort as _map_effort
        _eff = _map_effort(self.provider_type, self.model_name,
                           self.effort_level or self.thinking_level or "auto")
        _effort_params = _eff.get("request_params", {})
        _effort_extra_body = _eff.get("extra_body")

        _turn_in = _turn_out = 0
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
                        tool_choice="auto",
                        **_effort_params,
                        **({"extra_body": _effort_extra_body} if _effort_extra_body else {}),
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

            _u = getattr(response, "usage", None)
            if _u:
                _turn_in += getattr(_u, "prompt_tokens", 0) or 0
                _turn_out += getattr(_u, "completion_tokens", 0) or 0

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
                yield AgentEvent("turn_usage", {
                    "input_tokens": _turn_in, "output_tokens": _turn_out, "cost_usd": None,
                    "duration_ms": int((time.time() - _turn_t0) * 1000),
                })
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
    # AGY KALICI SESSION (disk-resume + conversation-db okuma)
    # ═══════════════════════════════════════════════
    async def _run_agy_session(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """
        agy'yi (Antigravity CLI) sohbet başına bağlamlı sürer.

        agy'nin Codex/Claude gibi canlı server'ı YOK ve KENDİ disk-resume'u
        (--conversation) agy 1.1.1'de KIRIK: resume flag'i modeli built-in
        antigravity-guide skill'ine sokup kullanıcının mesajını hiç yanıtlatmıyor
        (canlı doğrulandı). Bu yüzden:
        - Resume KULLANILMAZ. Her turda tam transcript (_build_handoff_context)
          prompt'a enjekte edilir → agy her turu "kaldığı yerden" görür.
        - Prompt STDIN değil ARG olarak verilir (agy 1.1.1 ham-metin stdin'i de bozdu);
          Windows argv limiti için context en-yeni-kısım korunacak şekilde sınırlanır.
        - Auto-approve: --dangerously-skip-permissions YERİNE settings.json
          toolPermission=always-proceed (flag skill-derail'i tetikliyordu).
        - Yanıt metni: stdout genelde çalışır (final event); boşsa bu turun
          conversation .db'sinden (step_type==15) fallback okunur.
        Ephemeral dosya-değişiklik akışı (kod blokları) korunur.
        """
        from ai_providers import AIProviderManager
        from providers.agy_session import (
            get_session, snapshot_db_names, detect_new_uuid, read_new_response,
            read_agy_tool_activity, get_max_step_idx,
        )

        provider = AIProviderManager.get_provider({
            "provider_type": self.provider_type,
            "model_name": self.model_name,
            "api_key": getattr(self, "api_key", ""),
        })

        sess = get_session(self.conversation_id)
        sess.auto_approve = (getattr(self, "generation_mode", "auto") == "auto")

        # NATIVE DISK-RESUME (2026-07-15, agy 1.1.2 canlı doğrulandı): --conversation ile
        # agy geçmişi KENDİ conversation .db'sinden yükler → normal devam mesajıyla derail
        # ETMİYOR ('analiz' framing'i yalnız transcript'e dair meta-sorularda). Böylece:
        #   • agy_uuid VARSA (bu sohbette daha önce agy koştu) → SADECE yeni mesajı yolla;
        #     context'i prompt'a BASMAYIZ → 26K kırpma yok, unutma yok, token ucuz.
        #   • agy_uuid YOKSA (ilk agy turu / app restart sonrası) → context'i enjekte et,
        #     tur sonrası beliren yeni .db'nin UUID'ini yakala + sakla (sonraki turlar resume).
        # _SESSIONS in-memory → app restart'ta agy_uuid kaybolur; ilk tur context'i yeniden
        # enjekte edip disk db'yi taze bir agy conversation'la resume eder (kabul edilebilir).
        resuming = bool(sess.agy_uuid)
        prev_idx = sess.last_step_idx if resuming else -1
        provider._resume_uuid = sess.agy_uuid if resuming else None

        enriched_prompt = user_message
        if not resuming and self.context:
            _CTX_CAP = 26000  # mcp_hint (~1.5K) + görsel + argv payı için güvenli sınır
            _ctx = self.context
            if len(_ctx) > _CTX_CAP:
                _ctx = "…[eski geçmiş kırpıldı — en yeni kısım korundu]\n" + _ctx[-_CTX_CAP:]
            enriched_prompt = f"{user_message}\n\n{_HANDOFF_HEADER}\n{_ctx}"

        # Görsel: agy'nin native görsel girişi YOK → dosyaya yaz + prompt'a yol enjekte;
        # agy kendi Read/dosya aracıyla açar (auto modda otomatik, kullanıcıdan ek iş yok).
        from providers._attachments import materialize_images, cleanup_dir
        _img_paths, _att_dir = materialize_images(
            self.images, self.workspace_path, f"agy_conv{self.conversation_id}")
        if _img_paths:
            _lines = "\n".join(f"- {p}" for p in _img_paths)
            enriched_prompt += ("\n\n[EKLİ GÖRSELLER] Kullanıcı bu turda görsel ekledi. "
                                "İncelemen için (Read/dosya aracıyla aç):\n" + _lines)

        # Resume YOKSA ilk tur yeni bir .db yaratır → UUID'i yakalamak için önceki db
        # kümesini fotoğrafla. Resume'da aynı .db'ye append edilir (yeni db yok).
        db_before = snapshot_db_names() if not resuming else set()

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
                cleanup_dir(_att_dir)
                return

        # agy subprocess bitti → ekli görsel temp klasörünü temizle (agy artık okumadı).
        cleanup_dir(_att_dir)

        # UUID: resume ise sess'te mevcut; değilse (ilk tur) yeni beliren .db'yi yakala + SAKLA
        # ki sonraki turlar native resume yapsın.
        if resuming:
            turn_uuid = sess.agy_uuid
        else:
            turn_uuid = detect_new_uuid(db_before)
            if turn_uuid:
                sess.agy_uuid = turn_uuid  # sonraki turlar --conversation ile resume eder
                logger.info(f"[AgySession] conv={self.conversation_id} agy UUID yakalandı+saklandı: {turn_uuid}")
            else:
                logger.warning(f"[AgySession] conv={self.conversation_id} yeni agy .db bulunamadı")

        # Asistan yanıt metnini .db'den oku (stdout boş kalırsa fallback). SADECE bu turun
        # yeni step'leri (prev_idx sonrası) → resume'da eski turların prose'unu tekrar
        # okumayı önler. agy 1.1.2'de stdout genelde çalışıyor; bu blok yalnız final boşsa.
        if turn_uuid and not final_text:
            prose, _ = read_new_response(turn_uuid, prev_idx)
            if not prose:
                # nadiren db flush gecikebilir → tek kısa retry
                await asyncio.sleep(0.4)
                prose, _ = read_new_response(turn_uuid, prev_idx)
            if prose:
                final_text = prose

        # Sonraki resume turu için son okunan step idx'ini güncelle (stdout yolu da dahil).
        if turn_uuid:
            sess.last_step_idx = get_max_step_idx(turn_uuid, fallback=prev_idx)

        # Ephemeral değişiklikleri encode et
        # Silinen dosyalar → pending_delete event'i olarak ayrıca gönder
        # Değiştirilen/eklenen dosyalar → // path: code block (parseGeneratedFiles yakalar)
        modified = [f for f in ephemeral_files if not f.get("deleted")]
        deleted  = [f for f in ephemeral_files if f.get("deleted")]

        # agy ne bir yanıt metni ne de dosya değişikliği ürettiyse — stdout boş kalmış
        # olabilir (uzun meshy işi tur sonunda prose yazmadan bitti; db-prose fallback'i
        # 1.1.2 şema kaymasında boş dönüyor). "yanıt üretmedi" demek yerine db'deki gerçek
        # tool aktivitesini göster ki kullanıcı agy'nin ÇALIŞTIĞINI görsün (patlamadı sansın).
        if not final_text and not modified and not deleted:
            activities = read_agy_tool_activity(turn_uuid, since_idx=prev_idx) if turn_uuid else []
            if activities:
                _acts = "\n".join(f"• {a}" for a in activities)
                final_text = (
                    "Bu turda araçları çalıştırdım ama bir metin yanıtı oluşmadı "
                    "(uzun bir işlem sürüyor olabilir). Yaptığım işlemler:\n"
                    f"{_acts}\n\nDevam etmemi mi istersin, yoksa sonucu mu sorayım?"
                )
            else:
                final_text = "⚠️ agy bu tur için bir yanıt veya değişiklik üretmedi."

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
    # CURSOR / COPILOT / OPENCODE — one-shot CLI + RESMİ resume
    # ═══════════════════════════════════════════════
    async def _run_oneshot_cli_session(self, user_message: str, cli_key: str) -> AsyncGenerator[AgentEvent, None]:
        """Cursor/Copilot/OpenCode'u tur bazlı (ephemeral subprocess) sürer.

        Bağlam, CLI'ların RESMİ resume mekanizmasıyla korunur (agy'nin aksine
        üçünde de resmi ve çalışır — 2026-07-13 canlı doğrulandı):
          cursor  → --resume <chatId>   (chatId ilk turun event'lerinden yakalanır)
          copilot → --session-id=<bizim uuid> (tur 1) / --resume=<uuid> (sonrası)
          opencode→ -s <sessionID>      (sessionID her event'te gelir)
        İlk turda (resume anahtarı yokken) tam transcript enjekte edilir;
        sonraki turlarda CLI kendi hafızasından devam eder.
        """
        import re as _re
        from ai_providers import AIProviderManager
        from providers.oneshot_cli import get_session

        def _make_provider(model_name: str):
            p = AIProviderManager.get_provider({
                "provider_type": self.provider_type,
                "model_name": model_name,
                "api_key": getattr(self, "api_key", ""),
            })
            return p

        provider = _make_provider(self.model_name)

        sess = get_session(cli_key, self.conversation_id)
        sess.auto_approve = (getattr(self, "generation_mode", "auto") == "auto")
        provider.resume_session_id = sess.session_id
        if cli_key == "copilot" and not sess.session_id:
            # Copilot'ta session UUID'ini BİZ üretiriz (--session-id) → yakalama derdi yok.
            import uuid as _uuid
            provider.fresh_session_id = str(_uuid.uuid4())
            sess.session_id = provider.fresh_session_id

        # Plan kısıtı tespiti: Cursor/Copilot free planlarda adlı modeller kapalı.
        # Hata mesajı bu kalıba uyarsa turu 'auto' modeliyle OTOMATİK tekrarlarız
        # ve öğrenilen kısıt cli_plan_caps.json'a yazılır (model seçici soluklaştırır).
        from providers.oneshot_cli import PLAN_ERROR_RE as _PLAN_ERR, set_named_models_cap
        _current_model = (self.model_name or "").lower()
        _can_fallback = (
            cli_key in ("cursor", "copilot")
            and _current_model not in (f"{cli_key}-auto",)
        )

        # İlk turda transcript enjeksiyonu (sonraki turlarda CLI resume hatırlar).
        enriched_prompt = user_message
        if self.context and not sess.ctx_injected:
            _CTX_CAP = 24000  # Windows argv sınırı (~32K) + mcp_hint payı
            _ctx = self.context
            if len(_ctx) > _CTX_CAP:
                _ctx = "…[eski geçmiş kırpıldı — en yeni kısım korundu]\n" + _ctx[-_CTX_CAP:]
            enriched_prompt = f"{user_message}\n\n{_HANDOFF_HEADER}\n{_ctx}"
        sess.ctx_injected = True

        # Görseller: dosyaya yaz + yolu prompt'a enjekte (üç CLI da read aracıyla açar).
        from providers._attachments import materialize_images, cleanup_dir
        _img_paths, _att_dir = materialize_images(
            self.images, self.workspace_path, f"{cli_key}_conv{self.conversation_id}")
        if _img_paths:
            _lines = "\n".join(f"- {p}" for p in _img_paths)
            enriched_prompt += ("\n\n[EKLİ GÖRSELLER] Kullanıcı bu turda görsel ekledi. "
                                "İncelemen için (read aracıyla aç):\n" + _lines)

        # Effort seviyesi provider'a attr olarak geçer (agy _resume_uuid deseni):
        # copilot _build_cmd --effort'a, opencode _register_mcp opencode.json'a çevirir.
        provider._effort_level = self.effort_level or self.thinking_level or "auto"

        final_text = ""
        got_error = False
        try:
            for attempt in (1, 2):
                got_error = False
                _plan_error = False
                async for event in provider.analyze_code(
                    enriched_prompt,
                    thinking_level="medium" if self.use_thinking else "off",
                    cwd=self.workspace_path or ".",
                    interactive=True,
                ):
                    etype = event.get("type")
                    if etype == "session_meta":
                        _sid = event.get("session_id")
                        if _sid and not sess.session_id:
                            sess.session_id = _sid
                            logger.info(f"[{cli_key}Session] conv={self.conversation_id} resume anahtarı: {_sid}")
                    elif etype == "delta":
                        yield AgentEvent("text", {"content": event.get("text", "")})
                    elif etype == "thinking":
                        yield AgentEvent("thinking", {"text": event.get("text", "")})
                    elif etype == "final":
                        final_text = event.get("text", "")
                    elif etype == "error":
                        _msg = event.get("content", "")
                        if attempt == 1 and _can_fallback and _PLAN_ERR.search(_msg):
                            # Plan bu modeli desteklemiyor → hatayı GÖSTERME, Auto ile tekrarla.
                            _plan_error = True
                        else:
                            got_error = True
                            from providers.oneshot_cli import QUOTA_ERROR_RE as _QRE
                            if _QRE.search(_msg):
                                _msg = (f"⏳ {cli_key.capitalize()} kullanım hakkın dolmuş görünüyor "
                                        f"(plan kotası). Kota yenilenene kadar başka bir sağlayıcı "
                                        f"seçebilirsin (örn. NVIDIA ücretsiz havuzu veya OpenCode).\n\n"
                                        + _msg[:200])
                            yield AgentEvent("error", {"message": _msg})

                if not _plan_error:
                    # Adlı model başarıyla çalıştıysa planın desteklediğini öğren
                    # (upgrade sonrası soluk modeller kendiliğinden açılır).
                    if attempt == 1 and not got_error and _can_fallback:
                        set_named_models_cap(cli_key, True)
                    break

                # ── Auto fallback (yalnız cursor/copilot, tek sefer) ──
                set_named_models_cap(cli_key, False)
                logger.info(f"[{cli_key}Session] plan kısıtı → auto fallback (model={self.model_name})")
                yield AgentEvent("thinking", {
                    "text": (f"ℹ️ Aboneliğin bu modeli desteklemiyor — **Auto** ile devam ediyorum. "
                             f"(Kalıcı çözüm: model seçiciden {cli_key.capitalize()} Auto'yu seç.)")
                })
                provider = _make_provider(f"{cli_key}-auto")
                if cli_key == "copilot":
                    # --session-id yoksa YARATIR, varsa devam eder (CLI help'inden) —
                    # ilk tur patladıysa session hiç doğmamış olabilir, --resume ölürdü.
                    provider.fresh_session_id = sess.session_id
                    provider.resume_session_id = None
                else:
                    provider.resume_session_id = sess.session_id
        finally:
            cleanup_dir(_att_dir)

        if got_error:
            return

        if not final_text:
            final_text = f"⚠️ {cli_key} bu tur için bir yanıt üretmedi."
        yield AgentEvent("response", {"content": final_text})
        yield AgentEvent("done", {"iterations": 1, "session_id": sess.session_id})

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
        from providers.claude_sdk_session import (
            get_session, close_session, _SESSIONS, SessionBusyError,
        )

        # MCP: SADECE unityMCP (Unity sahne kontrolü) session'a girsin. Eski 'unityai'
        # (mcp__unityai__bash/save_file + kendi onay köprüsü) ARTIK GİRMESİN — terminal/yazma
        # built-in Bash/Write üzerinden native can_use_tool onayına gitsin (Seçenek 1).
        # NOT: setting_sources=["project","user"] KORUNUR (skill + slash komutları için şart).
        try:
            from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager
            mcp_servers_cfg = {}
            if unity_mcp_manager.is_running():
                # "type": "http" ZORUNLU — yoksa Claude Code bunu stdio sunucu sanıp
                # 'command' arar, bulamayınca "invalid MCP server config" ile ATLAR
                # (Unity araçları manage_scene/manage_gameobject vb. görünmez).
                mcp_servers_cfg["unityMCP"] = {
                    "type": "http",
                    "url": f"http://localhost:{unity_mcp_manager.mcp_port}/mcp",
                }
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

        # Effort: kayıtçıdan (effort_caps) eşlenir — "auto" veya desteklenmeyen seviye →
        # None → SDK'ya effort GEÇMEZ, model kendi varsayılanıyla çalışır (Claude'da high).
        # effort connect-time KİLİTLİ (SDK'da set_effort yok). Cache'li session'ın effort'u
        # farklıysa close+recreate gerekir: bu, o sohbetteki CANLI session'ı sıfırlar (DB
        # bağlam özeti aşağıda yeniden enjekte edilir). Böylece seçim gerçekten etki eder.
        from providers.effort_caps import map_effort as _map_effort
        _lvl = self.effort_level or self.thinking_level or "auto"
        desired_effort = _map_effort("subscription", self.model_name or "claude-",
                                     "low" if _lvl == "off" else _lvl).get("sdk_effort")
        _existing = _SESSIONS.get(self.conversation_id)
        if _existing is not None and _existing.effort != desired_effort:
            logger.info(f"[ClaudeSession] effort değişti ({_existing.effort}→{desired_effort}); "
                        f"session yeniden kuruluyor (canlı bağlam sıfırlanır, DB özeti korunur)")
            await close_session(self.conversation_id)

        _session_kwargs = dict(
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

        # Görsel: Claude Code SDK/headless satır-içi image-block'u modele SUNMUYOR
        # (SDK ContentBlock union'ında ImageBlock yok → blok sessizce düşer). Bu yüzden
        # agy ile aynı yol: görseli temp'e yaz + mesaja yol enjekte → Claude kendi Read
        # aracıyla açar (Read görselleri görsel olarak modele sunar). Auto modda otomatik.
        from providers._attachments import materialize_images, cleanup_dir
        _img_paths, _att_dir = materialize_images(
            self.images, self.workspace_path, f"claude_conv{self.conversation_id}")
        _img_suffix = ""
        if _img_paths:
            _lines = "\n".join(f"- {p}" for p in _img_paths)
            _img_suffix = ("\n\n[EKLİ GÖRSELLER] Kullanıcı bu turda görsel ekledi. "
                           "İncelemen için Read aracıyla aç:\n" + _lines)

        # Sıkışmış/kopuk session'da bir kez otomatik reset + yeniden dene: "Durdur"
        # sonrası ya da CLI çökmesi sonrası kullanıcı mesajı asla "düşünüyor"da kalmaz.
        for _attempt in (1, 2):
            session = get_session(self.conversation_id, **_session_kwargs)

            # Oto mod → onay sormadan otomatik izin; Adım/Plan modu → her işlemde onay kartı.
            # Session kalıcı olduğu için mod her turda güncellenir (kullanıcı ortada değiştirebilir).
            session.auto_approve = (self.generation_mode == "auto")

            # İlk turda proje bağlamını ekle; sonraki turlarda session zaten hatırlıyor.
            message = user_message
            if self.context and not session.session_id:
                message = f"{user_message}\n\n{_HANDOFF_HEADER}\n{self.context}"
            # Ultracode (Claude-only): SDK'da option YOK → tek yol mesaja keyword enjeksiyonu.
            # CLI bu kelimeyi görünce çok-ajanlı ultracode akışını tetikler (belgesiz; sürüme bağlı).
            if self.ultracode:
                message = f"{message}\n\nultracode"
            # Ekli görsel yolları (varsa) mesaja eklenir → Claude Read ile açar.
            message = f"{message}{_img_suffix}"

            _yielded = 0
            try:
                async for ev in session.stream(message):
                    _yielded += 1
                    etype = ev.pop("type", "text")
                    yield AgentEvent(etype, ev)
                cleanup_dir(_att_dir)
                return
            except Exception as e:
                # Event akmadan patladıysa (busy/kopuk) güvenle resetleyip tekrar dene;
                # akış ortasında patladıysa retry çift metin basar → direkt hata göster.
                if _attempt == 1 and _yielded == 0:
                    logger.warning(f"[ClaudeSession] session sıkışmış/kopuk ({e}) → reset + retry")
                    yield AgentEvent("status", {
                        "detail": "⚠️ Claude session yanıt vermedi — yeniden başlatılıyor…",
                    })
                    try:
                        await close_session(self.conversation_id)
                    except Exception:
                        logger.exception("[ClaudeSession] reset sırasında close hatası")
                    continue
                logger.exception("[ClaudeSession] stream hatası")
                cleanup_dir(_att_dir)
                yield AgentEvent("error", {"message": f"Claude session hatası: {e}"})
                return

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
        from providers.codex_session import get_session, close_session, _SESSIONS
        from providers.effort_caps import map_effort as _map_effort

        # Effort kayıtçıdan (auto/desteklenmeyen → None → codex varsayılanı medium).
        # Launch-time config olduğundan effort DEĞİŞİNCE session yeniden kurulur
        # (Claude deseninin aynısı; thread bağlamı sıfırlanır, DB özeti yeniden gider).
        _lvl = self.effort_level or self.thinking_level or "auto"
        desired_effort = _map_effort("subscription", self.model_name or "gpt-",
                                     _lvl).get("cli_config", {}).get("model_reasoning_effort")
        _existing = _SESSIONS.get(self.conversation_id)
        if _existing is not None and getattr(_existing, "effort", None) != desired_effort:
            logger.info(f"[CodexSession] effort değişti ({_existing.effort}→{desired_effort}); "
                        f"session yeniden kuruluyor")
            await close_session(self.conversation_id)

        session = get_session(
            self.conversation_id,
            model=self.model_name,
            cwd=self.workspace_path or ".",
            effort=desired_effort,
        )
        # Oto mod → onay otomatik accept; Adım/Plan modu → her mutasyonda onay kartı.
        session.auto_approve = (self.generation_mode == "auto")

        # /usage → canlı app-server'dan kullanım kartı metni (model turu YOK → sıfır token).
        # Ham user_message'a bakılır (bağlam wrapping'inden ÖNCE).
        if user_message.strip().lower() == "/usage":
            try:
                text = await session.usage_card_text()
            except Exception as e:
                text = f"Codex kullanım bilgisi alınamadı: {e}"
            yield AgentEvent("text", {"content": text})
            yield AgentEvent("response", {"content": text})
            yield AgentEvent("done", {"session_id": session.thread_id})
            return

        # İlk turda proje bağlamını ekle; sonraki turlarda thread zaten hatırlıyor.
        message = user_message
        if self.context and not session._ctx_injected:
            message = f"{user_message}\n\n{_HANDOFF_HEADER}\n{self.context}"
            session._ctx_injected = True

        # Görseller Codex'e native 'localImage' input item'ı olarak gider → dosya yolu
        # gerekiyor. Base64'leri tura özel temp klasörüne yaz; tur sonunda temizle.
        from providers._attachments import materialize_images, cleanup_dir
        image_paths, _att_dir = materialize_images(
            self.images, self.workspace_path, f"codex_conv{self.conversation_id}")
        from providers.oneshot_cli import CODEX_PLAN_ERROR_RE, QUOTA_ERROR_RE, add_blocked_model, remove_blocked_model
        _saw_plan_error = False
        _saw_text = False
        try:
            async for ev in session.stream(message, image_paths=image_paths):
                etype = ev.pop("type", "text")
                if etype == "error":
                    _msg = str(ev.get("message", ""))
                    if CODEX_PLAN_ERROR_RE.search(_msg):
                        # Plan bu modeli desteklemiyor (canlı örnek: gpt-5.6-sol +
                        # ChatGPT hesabı) → öğren (seçici soluklaştırır) + dostane mesaj.
                        _saw_plan_error = True
                        add_blocked_model("codex", self.model_name)
                        ev["message"] = (
                            f"🔒 ChatGPT planın **{self.model_name}** modelini desteklemiyor. "
                            f"Model seçiciden başka bir Codex modeli seç (örn. GPT-5.5) — "
                            f"bu model artık listede kilitli görünecek.")
                    elif QUOTA_ERROR_RE.search(_msg):
                        ev["message"] = (
                            "⏳ Codex kullanım hakkın dolmuş görünüyor (plan kotası). "
                            "Kota yenilenene kadar başka bir sağlayıcı seçebilirsin "
                            "(örn. NVIDIA ücretsiz havuzu veya OpenCode).\n\n" + _msg[:200])
                elif etype == "text":
                    _saw_text = True
                yield AgentEvent(etype, ev)
            # Model plan hatasız yanıt üretti → varsa öğrenilmiş kilidi kaldır
            # (plan yükseltmesi sonrası ilk başarılı kullanım kilidi kendisi açar).
            if _saw_text and not _saw_plan_error:
                remove_blocked_model("codex", self.model_name)
        except Exception as e:
            logger.exception("[CodexSession] stream hatası")
            yield AgentEvent("error", {"message": f"Codex session hatası: {e}"})
        finally:
            cleanup_dir(_att_dir)

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
