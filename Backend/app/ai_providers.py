import re
import time
import subprocess
import os
import logging
import ollama
import openai
from google import genai
from google.genai import types as gtypes
from abc import ABC, abstractmethod
import asyncio
from typing import Dict, Any, Optional, Tuple, List, AsyncGenerator

logger = logging.getLogger(__name__)

# (response_text, thinking_text, thinking_duration_ms)
ThinkingResult = Tuple[str, Optional[str], Optional[int]]


class AIProvider(ABC):
    @abstractmethod
    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, cwd: Optional[str] = None) -> str:
        pass

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, thinking_level: str = "medium", cwd: Optional[str] = None) -> ThinkingResult:
        """Thinking desteklemeyen provider'lar için fallback — thinking None döner."""
        return self.analyze_code(prompt, max_tokens, images, cwd=cwd), None, None

    def _clean_response(self, text: str):
        if not text: return ""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)

        raw_name = model_name.lower() if model_name else ""
        # Google AI Studio / google-genai SDK - Mayıs 2026 (Minimum desteklenen: v2.0)
        if "3.1-pro" in raw_name:
            self.model_id = "gemini-3.1-pro"
        elif "3.1-flash-lite" in raw_name:
            self.model_id = "gemini-3.1-flash-lite"
        elif "3-flash" in raw_name or "3.0-flash" in raw_name:
            self.model_id = "gemini-3-flash"
        elif "2.5-pro" in raw_name:
            self.model_id = "gemini-2.5-pro"
        elif "2.0-flash" in raw_name:
            self.model_id = "gemini-2.0-flash"
        elif "pro" in raw_name:
            self.model_id = "gemini-3.1-pro"
        else:
            self.model_id = model_name if model_name else "gemini-3.1-pro"

    _THINKING_MODELS = ("gemini-3.1", "gemini-3.0", "gemini-2.5")

    def _supports_thinking(self) -> bool:
        return any(self.model_id.startswith(m) for m in self._THINKING_MODELS)

    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> str:
        try:
            contents = [prompt]
            if images:
                parts = [gtypes.Part(text=prompt)]
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        mime_type = header.split(":")[1].split(";")[0]
                        parts.append(gtypes.Part(inline_data=gtypes.Blob(mime_type=mime_type, data=base64_str)))
                contents = [gtypes.Content(role="user", parts=parts)]

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gtypes.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            if response and response.text:
                return response.text
            return "AI yanıt üretti ancak içerik boş döndü."
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                return "SİSTEM MESAJI: Google API ücretsiz kota sınırına ulaşıldı. Lütfen 60 saniye bekleyip tekrar deneyin veya Ollama (Yerel) moduna geçin."
            if "404" in err_str:
                return f"SİSTEM MESAJI: '{self.model_id}' modeli bulunamadı. Ayarlar'dan farklı bir Gemini modeli seçin."
            raise Exception(f"Gemini API Hatası: {err_str}")

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, thinking_level: str = "medium") -> ThinkingResult:
        if not self._supports_thinking():
            return self.analyze_code(prompt, max_tokens, images), None, None

        try:
            start = time.time()
            contents = [prompt]
            if images:
                parts = [gtypes.Part(text=prompt)]
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        mime_type = header.split(":")[1].split(";")[0]
                        parts.append(gtypes.Part(inline_data=gtypes.Blob(mime_type=mime_type, data=base64_str)))
                contents = [gtypes.Content(role="user", parts=parts)]

            # Düşünme seviyesine göre bütçe belirle
            budget_map = {"low": 4096, "medium": 16384, "high": 65536}
            budget = budget_map.get(thinking_level, 16384)

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    thinking_config=gtypes.ThinkingConfig(thinking_budget=budget),
                ),
            )
            duration_ms = int((time.time() - start) * 1000)

            thinking_text = None
            response_text = ""
            for part in response.candidates[0].content.parts:
                if getattr(part, "thought", False):
                    thinking_text = (thinking_text or "") + (part.text or "")
                else:
                    response_text += part.text or ""

            return response_text.strip() or "", thinking_text, duration_ms
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Gemini thinking] Fallback: {e}")
            return self.analyze_code(prompt, max_tokens), None, None


class OllamaProvider(AIProvider):
    def __init__(self, model_name: str = "qwen2.5-coder:7b"):
        self.model_name = model_name if model_name else "qwen2.5-coder:7b"

    def analyze_code(self, prompt: str, max_tokens: int = 4096) -> str:
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                options={'num_predict': max_tokens}
            )
            return self._clean_response(response['message']['content'])
        except Exception as e:
            raise Exception(f"Ollama Hatası: {str(e)}")


class OpenAICompatibleProvider(AIProvider):
    # OpenAI reasoning modelleri (Mayıs 2026 güncel)
    _REASONING_MODELS = ("gpt-5.5", "gpt-5.4", "o3", "o4", "o5")
    # Kimi thinking modelleri
    _KIMI_THINKING_MODELS = ("kimi-k3", "kimi-k2")
    # Kimi model name normalization
    _KIMI_ALIASES = {"kimi-k2.6": "kimi-k2.6", "kimi-k2.5": "kimi-k2.5"}

    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.base_url = base_url

    def _is_openai_reasoning(self) -> bool:
        lower_name = self.model_name.lower()
        return any(m in lower_name for m in self._REASONING_MODELS)

    def _is_kimi(self) -> bool:
        lower_name = self.model_name.lower()
        return "moonshot" in self.base_url or "moonshotai" in lower_name or "kimi-k2" in lower_name

    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> str:
        try:
            user_content = [{"type": "text", "text": prompt}]
            if images:
                for img_data in images:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img_data}
                    })

            kwargs = dict(
                model=self.model_name,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=max_tokens,
            )
            # Reasoning ve Kimi modelleri temperature parametresini desteklemiyor
            if not self._is_openai_reasoning() and not self._is_kimi():
                kwargs["temperature"] = 0.3
            response = self.client.chat.completions.create(**kwargs)
            return self._clean_response(response.choices[0].message.content)
        except Exception as e:
            raise Exception(f"API Hatası: {str(e)}")

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096) -> ThinkingResult:
        # OpenAI GPT-5.x reasoning
        if self._is_openai_reasoning():
            try:
                start = time.time()
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    reasoning={"effort": "medium"},
                )
                duration_ms = int((time.time() - start) * 1000)
                thinking = getattr(response.choices[0].message, "reasoning_content", None)
                text = self._clean_response(response.choices[0].message.content)
                return text, thinking or None, duration_ms
            except Exception:
                # reasoning parametresi desteklenmiyorsa (örn. bazı OpenRouter proxy'leri) standart call
                try:
                    start = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                    duration_ms = int((time.time() - start) * 1000)
                    text = self._clean_response(response.choices[0].message.content)
                    return text, None, duration_ms
                except Exception:
                    return self.analyze_code(prompt, max_tokens), None, None

        # Kimi K2.x thinking
        if self._is_kimi():
            try:
                start = time.time()
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"enabled": True}},
                )
                duration_ms = int((time.time() - start) * 1000)
                thinking = getattr(response.choices[0].message, "reasoning_content", None)
                text = self._clean_response(response.choices[0].message.content)
                return text, thinking or None, duration_ms
            except Exception:
                # thinking desteklenmiyorsa (K2.6 gibi yeni versiyonlar) standart call
                try:
                    start = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                    duration_ms = int((time.time() - start) * 1000)
                    text = self._clean_response(response.choices[0].message.content)
                    return text, None, duration_ms
                except Exception:
                    return self.analyze_code(prompt, max_tokens), None, None

        return self.analyze_code(prompt, max_tokens), None, None


import anthropic

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "claude-sonnet-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)

        raw_name = model_name.lower() if model_name else ""
        if "sonnet-4-6" in raw_name or "sonnet" in raw_name:
            self.model_name = "claude-4-6-sonnet"
        elif "opus-4-7" in raw_name or "opus" in raw_name:
            self.model_name = "claude-4-7-opus"
        elif "haiku-4-5" in raw_name or "haiku" in raw_name:
            self.model_name = "claude-4-5-haiku"
        else:
            self.model_name = "claude-4-6-sonnet"

    def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> str:
        try:
            if max_tokens > 16384:
                return self._stream_response(prompt, max_tokens) # Stream mode doesn't support images yet in our simple implementation

            user_content = [{"type": "text", "text": prompt}]
            if images:
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        media_type = header.split(":")[1].split(";")[0]
                        user_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_str
                            }
                        })

            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": user_content}]
            )
            text = ""
            for block in response.content:
                if block.type == "text":
                    text += block.text
            return self._clean_response(text)
        except Exception as e:
            return f"❌ Anthropic API Hatası: Sistemsel bir ret veya model hatası oluştu. Mesaj: {str(e)}"

    def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None) -> ThinkingResult:
        try:
            start = time.time()
            user_content = [{"type": "text", "text": prompt}]
            if images:
                for img_data in images:
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        media_type = header.split(":")[1].split(";")[0]
                        user_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_str
                            }
                        })

            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens + 8000,
                thinking={"type": "enabled", "budget_tokens": 8000},
                messages=[{"role": "user", "content": user_content}]
            )
            duration_ms = int((time.time() - start) * 1000)

            thinking_text = None
            response_text = ""
            for block in response.content:
                if block.type == "thinking":
                    thinking_text = block.thinking
                elif block.type == "text":
                    response_text += block.text

            return self._clean_response(response_text), thinking_text, duration_ms
        except Exception:
            return self.analyze_code(prompt, max_tokens), None, None

    def _stream_response(self, prompt: str, max_tokens: int) -> str:
        try:
            text = ""
            with self.client.messages.stream(
                model=self.model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for chunk in stream.text_stream:
                    text += chunk
            return self._clean_response(text)
        except Exception as e:
            return f"❌ Anthropic API Hatası: {str(e)}"


class CLIProvider(AIProvider):
    """
    Kullanıcının bilgisayarında yüklü olan ve abonelikle çalışan
    CLI araçlarını (Claude Code, Codex vb.) motor olarak kullanır.

    Step (interactive) modunda "Ephemeral Snapshot" mimarisi kullanılır:
    1. CLI çalışmadan önce workspace snapshot'ı alınır (dosya içerikleri)
    2. CLI özgürce çalışır (herhangi bir kısıtlama yok)
    3. CLI bittikten sonra değişen dosyalar tespit edilir
    4. Değişiklikler HEMEN geri alınır (workspace temiz kalır)
    5. Değişiklikler 'ephemeral_changes' event'i ile üst katmana iletilir
    6. Kullanıcı onaylarsa frontend mevcut write mekanizmasıyla uygular
    """

    # Snapshot'ta takip edilecek uzantılar
    _TRACKED_EXTENSIONS = ('.cs', '.shader', '.hlsl', '.glsl', '.json', '.txt', '.asset', '.asmdef')
    # Snapshot dışı bırakılacak klasörler
    _SKIP_DIRS = {'Library', 'Temp', '.git', 'Logs', 'UserSettings', 'Packages'}

    def __init__(self, binary_name: str = "claude"):
        self.binary_name = binary_name

    # ─── Snapshot Helpers ────────────────────────────────────────────────────

    def _snapshot(self, cwd: str) -> dict:
        """Assets klasörünün takip edilen dosyalarının içeriğini al."""
        snap = {}
        assets = os.path.join(cwd, "Assets")
        if not os.path.exists(assets):
            return snap
        for root, dirs, files in os.walk(assets):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
            for f in files:
                if f.endswith(self._TRACKED_EXTENSIONS):
                    full = os.path.join(root, f)
                    try:
                        with open(full, 'r', encoding='utf-8', errors='replace') as fp:
                            snap[full] = fp.read()
                    except Exception:
                        pass
        return snap

    def _get_changes(self, cwd: str, before: dict) -> list:
        """
        Snapshot'tan bu yana değişen/eklenen/silinen dosyaları döndür.
        Silinen dosyalar: code="" ve deleted=True ile işaretlenir.
        """
        changes = []
        seen_files: set = set()
        assets = os.path.join(cwd, "Assets")

        if os.path.exists(assets):
            for root, dirs, files in os.walk(assets):
                dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
                for f in files:
                    if f.endswith(self._TRACKED_EXTENSIONS):
                        full = os.path.join(root, f)
                        seen_files.add(full)
                        try:
                            with open(full, 'r', encoding='utf-8', errors='replace') as fp:
                                current = fp.read()
                            rel = os.path.relpath(full, cwd)
                            orig = before.get(full)
                            if orig is None:
                                changes.append({"path": rel, "code": current, "originalCode": "", "deleted": False})
                            elif orig != current:
                                changes.append({"path": rel, "code": current, "originalCode": orig, "deleted": False})
                        except Exception:
                            pass

        # Snapshot'ta olan ama artık olmayan dosyalar = silindi
        for full, orig_content in before.items():
            if full not in seen_files:
                rel = os.path.relpath(full, cwd)
                changes.append({"path": rel, "code": "", "originalCode": orig_content, "deleted": True})

        return changes

    def _revert(self, changes: list, cwd: str):
        """Onaylanmamış değişiklikleri geri al — workspace temiz kalır."""
        for c in changes:
            full = os.path.join(cwd, c["path"])
            try:
                if c.get("deleted"):
                    # Silinen dosyayı geri yaz
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, 'w', encoding='utf-8') as fp:
                        fp.write(c["originalCode"])
                elif c["originalCode"] == "":
                    # Yeni eklenen dosyayı sil
                    if os.path.exists(full):
                        os.remove(full)
                else:
                    # Değiştirilen dosyayı eski haline getir
                    with open(full, 'w', encoding='utf-8') as fp:
                        fp.write(c["originalCode"])
            except Exception:
                pass

    # ─── CLI Execution ────────────────────────────────────────────────────────

    # CLI'nın sorduğu onay sorusu pattern'leri (TR + EN)
    # Geniş TR kalıpları: Claude Code Türkçe yanıt verdiğinde de yakalamalı
    _APPROVAL_PATTERNS = (
        # Türkçe soru kalıpları
        "devam edeyim mi", "devam edelim mi", "emin misiniz",
        "istiyor musunuz", "ister misiniz", "yapayım mı",
        "silmemi", "silmek istiyor", "silsin mi",
        "onaylıyor musunuz", "onaylıyor musun",
        "kabul ediyor musunuz", "kabul ediyor musun",
        "yapmamı ister", "yapmamı istiyor",
        "devam mı", "devam edilsin mi",
        "değişiklikler kaybolur", "geri alınamaz",
        # İngilizce soru kalıpları
        "are you sure", "shall i proceed", "should i proceed",
        "do you want to", "would you like", "proceed?",
        "confirm", "allow this command", "continue?",
        # Evrensel
        "(y/n)", "[y/n]", "(yes/no)", "y/n",
    )

    @classmethod
    def _is_approval_question(cls, text: str) -> bool:
        lower = text.lower()
        # Pattern eşleşmesi VEYA soru işareti ile biten ve eylem fiili içeren satır
        if any(p in lower for p in cls._APPROVAL_PATTERNS):
            return True
        # "?" ile biten ve Türkçe/İngilizce eylem içeren satırlar
        if lower.strip().endswith("?"):
            action_words = ("sil", "del", "remov", "push", "commit", "reset",
                           "merge", "install", "run", "execut", "çalıştır")
            return any(w in lower for w in action_words)
        return False

    # Claude Code'un "komutu çalıştırıyorum" çıktılarından exact command'ı çıkar
    # Örn: "⎿ Bash(rm Assets/Scripts/TestScript2.cs)" → "rm Assets/Scripts/TestScript2.cs"
    import re as _re
    _CMD_EXTRACT_PATTERNS = [
        _re.compile(r'Bash\((.+?)\)', _re.IGNORECASE),
        _re.compile(r'Running:\s*`?(.+?)`?\s*$', _re.IGNORECASE),
        _re.compile(r'Executing:\s*`?(.+?)`?\s*$', _re.IGNORECASE),
        _re.compile(r'^\$\s+(.+)$'),
        _re.compile(r'`(.+?)`\s*$'),
    ]

    @classmethod
    def _extract_command_from_line(cls, text: str) -> str | None:
        """CLI çıktı satırından çalıştırılacak komutu ayıkla."""
        for pattern in cls._CMD_EXTRACT_PATTERNS:
            m = pattern.search(text)
            if m:
                cmd = m.group(1).strip()
                if len(cmd) > 2:
                    return cmd
        return None

    def _build_cmd(self, prompt: str, thinking_level: str = "medium") -> list:
        full_id = self.binary_name
        if full_id.startswith("claude-"):
            # default mod: CLI her tool çağrısında önce sorar → tam komutu görebilir + onaylayabiliriz
            return ["claude", "--model", full_id, "--permission-mode", "default", "-p", prompt]
        elif full_id.startswith("gpt-"):
            cmd = ["codex", "exec", "-m", full_id, "--sandbox", "workspace-write", prompt]
            if thinking_level != "off":
                cmd.extend(["-c", f"reasoning.effort={thinking_level}"])
            return cmd
        return [full_id, prompt]

    async def _stream_process(self, cmd: list, cwd: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        CLI'ı çalıştır, satır satır oku.

        İki aşamalı onay mantığı:
        1. CLI "Bash(rm foo.cs)" gibi bir satır yazar → komutu buffer'a al
        2. Ardından "(y/n)" / "Allow?" gibi onay sorusu yazar →
           buffer'daki EXACT KOMUT ile CommandApproval kartını göster
        3. Kullanıcı karttan onaylarsa stdin'e y, reddederse n yaz
        """
        import uuid
        from agentic.command_gates import APPROVAL_GATES, APPROVAL_RESULTS

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            env={**os.environ, "TERM": "xterm-256color"},
            cwd=cwd,
        )

        full_text = ""
        buffered_command: str | None = None  # Son görülen tool çağrısı komutu

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode('utf-8', errors='ignore')
            full_text += decoded
            clean = decoded.strip()

            # ── Adım 1: "Bash(rm foo.cs)" gibi komutu önceden yakala ────────
            extracted = self._extract_command_from_line(clean)
            if extracted:
                buffered_command = extracted
                # Komutu UI'da ToolBlock olarak göster (henüz çalışmadı, sadece bilgi)
                yield {"type": "tool_call", "tool": "Terminal",
                       "summary": f"→ {buffered_command[:120]}"}
                yield {"type": "delta", "text": decoded}
                continue

            # ── Adım 2: Onay sorusu geldi — exact komutla kartı göster ──────
            if self._is_approval_question(clean):
                # Onay kartında tam komutu göster (sözlü soru değil)
                display_cmd = buffered_command or clean
                buffered_command = None

                gate_id = uuid.uuid4().hex[:10]
                gate_event = asyncio.Event()
                APPROVAL_GATES[gate_id] = gate_event
                APPROVAL_RESULTS[gate_id] = False

                yield {
                    "type": "command_approval_needed",
                    "command": display_cmd,
                    "gate_id": gate_id,
                }

                try:
                    await asyncio.wait_for(gate_event.wait(), timeout=60.0)
                    approved = APPROVAL_RESULTS.get(gate_id, False)
                except asyncio.TimeoutError:
                    approved = False
                    logger.warning(f"[CLIProvider] Onay zaman aşımı: {display_cmd[:60]}")
                finally:
                    APPROVAL_GATES.pop(gate_id, None)
                    APPROVAL_RESULTS.pop(gate_id, None)

                if process.stdin:
                    process.stdin.write(b"y\n" if approved else b"n\n")
                    await process.stdin.drain()

                continue  # Onay satırını delta olarak gösterme

            # ── Normal satır ─────────────────────────────────────────────────
            buffered_command = None  # Alakasız satır geldi, buffer'ı temizle
            if "Thinking" in clean:
                yield {"type": "thinking", "text": clean}
            yield {"type": "delta", "text": decoded}

        await process.wait()
        if process.returncode not in (0, 1):
            stderr = (await process.stderr.read()).decode('utf-8', errors='ignore')
            yield {"type": "error", "content": f"❌ CLI Hatası (Kod {process.returncode}): {stderr}"}

        yield {"type": "final", "text": self._clean_response(full_text)}

    # ─── Public API ───────────────────────────────────────────────────────────

    async def analyze_code(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None,
                           thinking_level: str = "medium", cwd: Optional[str] = None,
                           interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            cmd = self._build_cmd(prompt, thinking_level)

            if not interactive or not cwd:
                # Direkt mod: kısıtlama yok, değişiklikler direkt uygulanır
                async for ev in self._stream_process(cmd, cwd or "."):
                    yield ev
                return

            # ── Ephemeral Snapshot Modu ──────────────────────────────────────
            yield {"type": "delta", "text": "🔬 Değişiklikler izleniyor (ephemeral mod)...\n"}
            before = await asyncio.to_thread(self._snapshot, cwd)

            final_text = ""
            async for ev in self._stream_process(cmd, cwd):
                if ev["type"] == "final":
                    final_text = ev["text"]
                else:
                    yield ev

            # Değişiklikleri tespit et
            changes = await asyncio.to_thread(self._get_changes, cwd, before)

            if changes:
                # Workspace'i HEMEN temizle — kullanıcı henüz onaylamadı
                await asyncio.to_thread(self._revert, changes, cwd)
                yield {"type": "ephemeral_changes", "files": changes}
                logger.info(f"[CLIProvider] Ephemeral: {len(changes)} değişiklik yakalandı ve geri alındı.")
            else:
                logger.info("[CLIProvider] Ephemeral: CLI hiçbir dosyayı değiştirmedi.")

            yield {"type": "final", "text": final_text}

        except Exception as e:
            yield {"type": "error", "content": f"❌ CLI Bridge Hatası: {str(e)}"}

    async def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096,
                                         images: Optional[List[str]] = None,
                                         thinking_level: str = "medium", cwd: Optional[str] = None,
                                         interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        async for ev in self.analyze_code(prompt, max_tokens, images, thinking_level, cwd, interactive):
            yield ev

    async def analyze_code_with_thinking(self, prompt: str, max_tokens: int = 4096, images: Optional[List[str]] = None, thinking_level: str = "medium", cwd: Optional[str] = None, interactive: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        async for ev in self.analyze_code(prompt, max_tokens, images, thinking_level=thinking_level, cwd=cwd, interactive=interactive):
            yield ev


class AIProviderManager:
    @staticmethod
    def get_provider(config: Dict[str, Any]) -> AIProvider:
        p_type = config.get("provider_type", "")
        m_name = config.get("model_name")
        api_key = config.get("api_key", "")

        if p_type == "anthropic" and api_key:
            return AnthropicProvider(api_key=api_key, model_name=m_name)
        elif p_type == "google" and api_key:
            return GeminiProvider(api_key=api_key, model_name=m_name)
        elif p_type == "openai" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.openai.com/v1", model_name=m_name or "gpt-5.5")
        elif p_type == "deepseek" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.deepseek.com", model_name=m_name or "deepseek-v4-pro")
        elif p_type == "groq" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.groq.com/openai/v1", model_name=m_name or "llama-3.3-70b-versatile")
        elif p_type == "openrouter" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://openrouter.ai/api/v1", model_name=m_name or "openai/gpt-5.5")
        elif p_type == "moonshot" and api_key:
            return OpenAICompatibleProvider(api_key=api_key, base_url="https://api.moonshot.cn/v1", model_name=m_name or "kimi-k3")
        elif p_type == "subscription":
            # m_name burada binary adıdır (claude, copilot vb.)
            return CLIProvider(binary_name=m_name or "claude")
        elif p_type == "ollama":
            return OllamaProvider(model_name=m_name)

        cloud_providers = ("anthropic", "google", "openai", "deepseek", "groq", "openrouter", "moonshot")
        if p_type in cloud_providers and not api_key:
            raise ValueError(
                f"⚠️ {p_type.capitalize()} için API key girilmedi. "
                f"Lütfen Ayarlar'dan API key'inizi girin."
            )

        return OllamaProvider(model_name=m_name)
