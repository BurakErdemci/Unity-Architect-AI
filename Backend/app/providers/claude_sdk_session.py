"""
Claude Code'u KALICI INTERAKTIF session olarak süren köprü (claude-agent-sdk).

Headless `claude -p` (stateless, onay kanalı yok) yerine ClaudeSDKClient kullanır:
- Sohbet başına tek canlı session → bağlam turlar arası korunur.
- can_use_tool → native onay; Write/Edit/Bash/MCP araçları kullanıcı onayından geçer.
- AskUserQuestion (Opus'un A/B/C sorması) → yapısal soru event'i; frontend chip'lerle
  gösterir, cevabı geri akıtırız.
- Abonelik auth (ANTHROPIC_API_KEY gerekmez — SDK kurulu CLI login'ini miras alır).

Yield edilen event'ler AgentEvent.data şekline uyar (type + alanlar): AgentRunner bunları
AgentEvent'e sarıp SSE'ye basar. Onay/soru beklemeleri command_gates üzerinden yürür.
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from agentic.command_gates import (
    APPROVAL_GATES, APPROVAL_RESULTS,
    QUESTION_GATES, QUESTION_RESULTS,
)

logger = logging.getLogger(__name__)

# conversation_id → ClaudeSDKSession (canlı, isteklerin ötesinde yaşar)
_SESSIONS: Dict[int, "ClaudeSDKSession"] = {}

# system/init'ten gelen slash komutları (chat'te '/' autocomplete için). Bir session
# başlayınca dolar; backend süreci boyunca kalır. Frontend GET /slash-commands ile okur.
_SLASH_COMMANDS_CACHE: List[str] = []
# Aktif skill isimleri (slash_commands'ın alt kümesi; frontend'de "skill" rozeti için).
_SKILLS_CACHE: List[str] = []
# Komut meta'sı: [{name, description, argumentHint}] — Skills galerisi (açıklamalı katalog)
# için. get_server_info().commands'tan warmup'ta dolar; isim-listesinden FARKLI olarak
# açıklama da taşır (system/init yalnızca isim verir, açıklama vermez).
_COMMANDS_META: List[Dict] = []
# Eşzamanlı /slash-commands isteklerinde tek warmup subprocess'i aç (çift spawn önleme).
_WARMUP_LOCK = asyncio.Lock()


def get_slash_commands() -> List[str]:
    return list(_SLASH_COMMANDS_CACHE)


def get_skills() -> List[str]:
    return list(_SKILLS_CACHE)


def get_commands_meta() -> List[Dict]:
    return list(_COMMANDS_META)


async def warmup_slash_commands(cwd: Optional[str] = None,
                                setting_sources: Optional[List[str]] = None) -> List[str]:
    """İlk mesaj atılmadan kurulu TÜM slash komut + skill'leri yakala (cold-start fix).

    ClaudeSDKClient.get_server_info() connect anındaki 'initialize' handshake'inden
    komutları SIFIR inference (token) ile verir — bu bir kullanıcı turu değildir.
    Throwaway client kullanılır (conversation _SESSIONS'a DOKUNULMAZ); mcp_servers /
    can_use_tool VERİLMEZ (hızlı + yan etkisiz). Sonuç global cache'lere yazılır.
    """
    global _SLASH_COMMANDS_CACHE, _SKILLS_CACHE, _COMMANDS_META
    async with _WARMUP_LOCK:
        if _SLASH_COMMANDS_CACHE:
            return list(_SLASH_COMMANDS_CACHE)  # başka bir istek doldurmuş

        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

        ws = cwd if (cwd and os.path.isdir(cwd)) else None  # silinmiş/taşınmış ws → None
        opts = ClaudeAgentOptions(
            setting_sources=setting_sources or ["project", "user"],
            cwd=ws,
        )
        client = ClaudeSDKClient(options=opts)
        cmds: List[str] = []
        meta: List[Dict] = []
        try:
            await client.__aenter__()
            info = await client.get_server_info() or {}
            # get_server_info → komutlar 'commands' anahtarında (dict listesi: name +
            # description + argumentHint). system/init'teki 'slash_commands' (string
            # listesi) anahtarından FARKLI ve AÇIKLAMA taşır → Skills galerisi bundan beslenir.
            # NOT: get_server_info'da 'skills' anahtarı YOK (yalnızca 'agents' = subagent
            # tipleri var; bunlar skill değil). Gerçek skill listesi canlı session'ın
            # system/init mesajından gelir → _SKILLS_CACHE'i burada DOLDURMUYORUZ.
            for c in (info.get("commands") or []):
                if isinstance(c, dict) and c.get("name"):
                    cmds.append(c["name"])
                    meta.append({
                        "name": c["name"],
                        "description": (c.get("description") or "").strip(),
                        "argumentHint": (c.get("argumentHint") or "").strip(),
                    })
                elif isinstance(c, str):  # eski CLI string verebilir
                    cmds.append(c)
                    meta.append({"name": c, "description": "", "argumentHint": ""})
        except Exception as e:
            logger.warning(f"[warmup_slash_commands] hata: {e}")
        finally:
            try:
                await client.__aexit__(None, None, None)  # subprocess sızıntısı önlemi
            except Exception:
                pass

        if cmds:
            _SLASH_COMMANDS_CACHE = cmds
        if meta:
            _COMMANDS_META = meta
        logger.info(f"[warmup_slash_commands] {len(cmds)} komut yakalandı (skill'ler ilk mesajda dolar)")
        return list(_SLASH_COMMANDS_CACHE)


_FILE_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# Salt-okunur / yan-etkisiz araçlar → onay sormadan otomatik izin (gürültü azaltma).
# MUTASYON araçları (Bash, Write/Edit, manage_gameobject/components/ui/material,
# execute_menu_item, run_tests, manage_build vb.) bilerek DIŞARIDA → onayda kalır.
_AUTO_ALLOW_TOOLS = {
    "Read", "Glob", "Grep", "LS", "NotebookRead",
    "TodoWrite", "ToolSearch", "WebFetch", "WebSearch",
}

# Chat'te gösterilmeyecek düşük-değerli iç araçlar (görünürlük; onay akışını etkilemez).
_NOISE_TOOLS = {"ToolSearch", "Skill", "Task"}
# Plan/todo araçları → ham döküm yerine tek "plan yapıyor" sinyali.
_PLAN_TOOLS = {"TodoWrite", "TaskCreate", "TaskUpdate"}


def _path_in_workspace(path: str, workspace: str) -> bool:
    """path, workspace kökünün altında mı? (path-traversal koruması)."""
    if not workspace:
        return True  # workspace tanımsızsa kısıtlama yok
    try:
        ap = os.path.abspath(path)
        ws = os.path.abspath(workspace)
        return os.path.commonpath([ap, ws]) == ws
    except Exception:
        return False


def _describe_tool(tool_name: str, inp: dict) -> str:
    """Onay kartında gösterilecek kısa, insan-okunur açıklama."""
    try:
        if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            return f"{tool_name} → {inp.get('file_path', inp.get('path', '?'))}"
        if tool_name == "Bash":
            return inp.get("command", "")
        if tool_name.startswith("mcp__"):
            return f"{tool_name} {json.dumps(inp, ensure_ascii=False)[:160]}"
        return f"{tool_name} {json.dumps(inp, ensure_ascii=False)[:160]}"
    except Exception:
        return tool_name


class ClaudeSDKSession:
    """Tek bir sohbete ait kalıcı ClaudeSDKClient sarmalayıcısı."""

    def __init__(
        self,
        conversation_id: int,
        *,
        model: Optional[str] = None,
        cwd: Optional[str] = None,
        permission_mode: str = "default",
        setting_sources: Optional[List[str]] = None,
        mcp_servers: Optional[dict] = None,
        disallowed_tools: Optional[List[str]] = None,
        approval_timeout: float = 300.0,
        auto_approve: bool = False,
        effort: Optional[str] = None,
    ):
        self.conversation_id = conversation_id
        self.model = model
        self.cwd = cwd
        self.permission_mode = permission_mode
        # Reasoning effort (Claude-only): "low"|"medium"|"high"|"xhigh"|"max".
        # connect-time'da --effort olarak verilir; oturum ortasında DEĞİŞTİRİLEMEZ.
        self.effort = effort
        # Oto mod: True ise araç onayı kartı GÖSTERİLMEZ, otomatik izin verilir
        # (path-traversal koruması yine uygulanır). Adım modunda False → her işlemde kart.
        self.auto_approve = auto_approve
        self.setting_sources = setting_sources if setting_sources is not None else ["project", "user"]
        self.mcp_servers = mcp_servers or {}
        self.disallowed_tools = disallowed_tools or []
        self.approval_timeout = approval_timeout

        self._client = None
        self._started = False
        self._turn_lock = asyncio.Lock()
        self._out_q: Optional[asyncio.Queue] = None
        self.session_id: Optional[str] = None
        # İptal (Durdur) için: aktif tur boyunca bekleyen gate'ler + iptal sinyali
        self._cancel_event: Optional[asyncio.Event] = None
        self._active_gate_ids: Set[str] = set()

    async def start(self):
        if self._started:
            return
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

        opts_kwargs: Dict[str, Any] = dict(
            permission_mode=self.permission_mode,
            setting_sources=self.setting_sources,
            can_use_tool=self._can_use_tool,
            cwd=self.cwd,
        )
        if self.model:
            opts_kwargs["model"] = self.model
        if self.effort:
            opts_kwargs["effort"] = self.effort  # ClaudeAgentOptions.effort → --effort
        if self.mcp_servers:
            opts_kwargs["mcp_servers"] = self.mcp_servers
        if self.disallowed_tools:
            opts_kwargs["disallowed_tools"] = self.disallowed_tools

        self._client = ClaudeSDKClient(options=ClaudeAgentOptions(**opts_kwargs))
        await self._client.__aenter__()
        self._started = True
        logger.info(f"[ClaudeSDKSession:{self.conversation_id}] başlatıldı (model={self.model}, effort={self.effort or '-'})")

    async def close(self):
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] kapatma hatası: {e}")
        self._client = None
        self._started = False

    # ── can_use_tool: native onay + AskUserQuestion köprüsü ──────────────
    async def _can_use_tool(self, tool_name: str, input_data: dict, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        out_q = self._out_q
        gate_id = uuid.uuid4().hex

        # Salt-okunur araçlar → onay sormadan otomatik izin (gürültü azaltma)
        if tool_name in _AUTO_ALLOW_TOOLS:
            return PermissionResultAllow(updated_input=input_data)
        # unityMCP salt-okuma sorguları (sahneyi DEĞİŞTİRMEZ) → otomatik izin
        if tool_name == "mcp__unityMCP__manage_scene" and \
                input_data.get("action") in {"get_hierarchy", "get_active", "get_info"}:
            return PermissionResultAllow(updated_input=input_data)
        if tool_name == "mcp__unityMCP__read_console":
            return PermissionResultAllow(updated_input=input_data)

        # AskUserQuestion → A/B/C seçim kartı
        if tool_name == "AskUserQuestion":
            ev = asyncio.Event()
            QUESTION_GATES[gate_id] = ev   # gate'i emit'ten ÖNCE kaydet (yarış önleme)
            self._active_gate_ids.add(gate_id)
            if out_q is not None:
                await out_q.put({"type": "question_needed", "gate_id": gate_id,
                                 "questions": input_data.get("questions", [])})
            answers = await self._wait_gate(ev, QUESTION_GATES, QUESTION_RESULTS, gate_id, "soru")
            if answers is None:
                return PermissionResultDeny(message="Kullanıcı soruyu yanıtlamadı (zaman aşımı).")
            return PermissionResultAllow(updated_input={**input_data, "answers": answers})

        # Path güvenliği: workspace dışına yazımı kullanıcıya sormadan reddet
        if tool_name in _FILE_WRITE_TOOLS:
            fp = input_data.get("file_path", input_data.get("path", ""))
            if fp and not _path_in_workspace(fp, self.cwd or ""):
                logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] workspace dışı yazım reddedildi: {fp}")
                if out_q is not None:
                    await out_q.put({"type": "tool_result", "tool": tool_name, "success": False,
                                     "summary": f"🚫 Workspace dışı yazım engellendi: {fp}"})
                return PermissionResultDeny(message=f"'{fp}' workspace dışında — güvenlik nedeniyle reddedildi.")

        # Oto mod: onay kartı gösterme, otomatik izin ver (path güvenliği yukarıda uygulandı)
        if self.auto_approve:
            return PermissionResultAllow(updated_input=input_data)

        # Normal araç → onay kartı (adım modu)
        ev = asyncio.Event()
        APPROVAL_GATES[gate_id] = ev       # gate'i emit'ten ÖNCE kaydet
        self._active_gate_ids.add(gate_id)
        if out_q is not None:
            await out_q.put({
                "type": "command_approval_needed",
                "gate_id": gate_id,
                "tool": tool_name,
                "title": getattr(context, "title", None) or getattr(context, "display_name", None),
                "command": _describe_tool(tool_name, input_data),
            })
        res = await self._wait_gate(ev, APPROVAL_GATES, APPROVAL_RESULTS, gate_id, "onay")
        if bool(res):
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(message="Kullanıcı işlemi reddetti.")

    async def _wait_gate(self, ev: asyncio.Event, gates: dict, results: dict,
                         gate_id: str, label: str):
        """Frontend cevabını bekler; sonucu (bool veya answers dict) döndürür, yoksa None."""
        try:
            await asyncio.wait_for(ev.wait(), timeout=self.approval_timeout)
            return results.pop(gate_id, None)
        except asyncio.TimeoutError:
            logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] {label} zaman aşımı gate={gate_id}")
            return None
        finally:
            gates.pop(gate_id, None)

    async def cancel_turn(self):
        """Kullanıcı 'Durdur' dediğinde aktif turu iptal eder.
        ÖNCE bekleyen onay/soru gate'lerini 'reddedildi' ile çözer (yoksa can_use_tool
        300sn bloklu kalır), SONRA SDK turunu interrupt() ile durdurur. _turn_lock ALMAZ
        (deadlock önlemi — cancel ayrı bir request task'ından gelir)."""
        for gid in list(self._active_gate_ids):
            if gid in APPROVAL_GATES:
                APPROVAL_RESULTS[gid] = False
                APPROVAL_GATES[gid].set()
            if gid in QUESTION_GATES:
                QUESTION_RESULTS[gid] = None
                QUESTION_GATES[gid].set()
        try:
            if self._client is not None:
                await self._client.interrupt()
        except Exception as e:
            logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] interrupt hatası: {e}")
        if self._cancel_event is not None:
            self._cancel_event.set()
        logger.info(f"[ClaudeSDKSession:{self.conversation_id}] tur iptal edildi (cancel_turn)")

    # ── Mesaj akışı: bir tur gönder, event dict'leri yield et ────────────
    async def stream(self, message: str) -> AsyncGenerator[dict, None]:
        if not self._started:
            await self.start()

        async with self._turn_lock:
            out_q: asyncio.Queue = asyncio.Queue()
            self._out_q = out_q
            self._cancel_event = asyncio.Event()
            self._active_gate_ids.clear()

            async def pump():
                from claude_agent_sdk import (
                    AssistantMessage, ResultMessage, SystemMessage,
                    TextBlock, ThinkingBlock, ToolUseBlock,
                )
                final_text = ""
                try:
                    await self._client.query(message)
                    async for msg in self._client.receive_response():
                        if isinstance(msg, SystemMessage):
                            data = getattr(msg, "data", None) or {}
                            if getattr(msg, "subtype", None) == "init" and isinstance(data, dict):
                                self.session_id = data.get("session_id") or self.session_id
                                # Slash komutlarını + skill'leri cache'le ('/' autocomplete için).
                                # Canlı session daha günceldir → warmup değerinin üzerine yazar.
                                global _SLASH_COMMANDS_CACHE, _SKILLS_CACHE
                                sc = data.get("slash_commands")
                                if isinstance(sc, list) and sc:
                                    _SLASH_COMMANDS_CACHE = sc
                                sk = data.get("skills")
                                if isinstance(sk, list) and sk:
                                    _SKILLS_CACHE = list(sk)
                        elif isinstance(msg, AssistantMessage):
                            for b in msg.content:
                                if isinstance(b, TextBlock):
                                    final_text += b.text
                                    await out_q.put({"type": "text", "content": b.text})
                                elif isinstance(b, ThinkingBlock):
                                    await out_q.put({"type": "thinking", "text": b.thinking})
                                elif isinstance(b, ToolUseBlock):
                                    if b.name in _PLAN_TOOLS:
                                        # Plan/todo: ham döküm yerine tek "plan yapıyor" sinyali
                                        await out_q.put({"type": "tool_call", "tool": "TodoWrite", "summary": ""})
                                    elif b.name in _NOISE_TOOLS:
                                        continue  # düşük-değerli iç araçları gizle
                                    else:
                                        await out_q.put({"type": "tool_call", "tool": b.name,
                                                         "summary": _describe_tool(b.name, b.input or {})})
                        elif isinstance(msg, ResultMessage):
                            result = getattr(msg, "result", "") or final_text
                            await out_q.put({"type": "response", "content": result})
                            await out_q.put({"type": "done", "session_id": self.session_id})
                except Exception as e:
                    logger.exception(f"[ClaudeSDKSession:{self.conversation_id}] pump hatası")
                    await out_q.put({"type": "error", "message": f"Claude session hatası: {e}"})
                finally:
                    await out_q.put(None)  # sentinel

            task = asyncio.create_task(pump())
            try:
                while True:
                    ev = await out_q.get()
                    if ev is None:
                        break
                    yield ev
            finally:
                self._out_q = None
                self._cancel_event = None
                self._active_gate_ids.clear()
                await task


def get_session(conversation_id: int, **kwargs) -> ClaudeSDKSession:
    """conversation_id için canlı session'ı getir; yoksa oluştur."""
    sess = _SESSIONS.get(conversation_id)
    if sess is None:
        sess = ClaudeSDKSession(conversation_id, **kwargs)
        _SESSIONS[conversation_id] = sess
    return sess


async def close_session(conversation_id: int):
    sess = _SESSIONS.pop(conversation_id, None)
    if sess is not None:
        await sess.close()


async def close_all_sessions():
    for cid in list(_SESSIONS.keys()):
        await close_session(cid)
