"""
Claude Code'u KALICI INTERAKTIF session olarak süren köprü (claude-agent-sdk).

Headless `claude -p` (stateless, onay kanalı yok) yerine ClaudeSDKClient kullanır:
- Sohbet başına tek canlı session → bağlam turlar arası korunur.
- can_use_tool → native onay; Write/Edit/Bash/MCP araçları kullanıcı onayından geçer.
- AskUserQuestion (Opus'un A/B/C sorması) → yapısal soru event'i; frontend chip'lerle
  gösterir, cevabı geri akıtırız.
- Abonelik auth (ANTHROPIC_API_KEY gerekmez — SDK kurulu CLI login'ini miras alır).

MİMARİ (tek sürekli reader):
CLI'dan mesajları session ömrü boyunca TEK reader task okur (`_reader_loop`).
Tur aktifken event'ler `_out_q`'ya (SSE'ye) akar; tur yokken / SSE koptuğunda
biten turun metni DB'ye kaydedilir (set_db_saver ile takılan callback).
Bu tasarım üç kritik bug'ı çözer:
1. DURDUR sonrası kilitlenme: tur kilidi artık pump'ı sonsuz beklemez; interrupt
   işlemezse session zorla resetlenir (sonraki mesaj temiz session'la başlar).
2. Arka plan subagent kaybı: SDK'nın task_started/progress/notification/updated
   sistem mesajları (SystemMessage alt sınıfları — eski kod bunları sessizce
   YUTUYORDU) artık canlı aktivite + görev kartı olarak akar. ResultMessage
   geldiğinde arka plan görevleri sürüyorsa tur SSE'de AÇIK TUTULUR; görevler
   bitince CLI'ın otonom devamı akar, gelmezse kısa bir dürtme (nudge) gönderilir
   → "proaktif uyanma".
3. Görünmezlik: include_partial_messages ile canlı thinking/text delta'ları +
   token sayacı (status event) akar — kullanıcı Claude'un çalıştığını GÖRÜR.

Yield edilen event'ler AgentEvent.data şekline uyar (type + alanlar): AgentRunner bunları
AgentEvent'e sarıp SSE'ye basar. Onay/soru beklemeleri command_gates üzerinden yürür.
"""
import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

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

# SSE koptuktan sonra biten turların asistan metnini DB'ye yazan callback
# (conversation_routes kayıt eder: lambda cid, text: db.add_message(cid, "assistant", text)).
# Provider katmanından DB'ye doğrudan import etmemek için köprü.
_DB_SAVE_CB: Optional[Callable[[int, str], None]] = None


def set_db_saver(cb: Callable[[int, str], None]) -> None:
    global _DB_SAVE_CB
    _DB_SAVE_CB = cb


class SessionBusyError(RuntimeError):
    """Önceki tur kilidi bırakmadı (sıkışmış session). AgentRunner yakalayıp resetler."""


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
# NOT: "Task" artık BURADA DEĞİL — subagent çağrıları "Subagent" chip'i olarak görünür.
_NOISE_TOOLS = {"ToolSearch", "Skill"}
# Plan/todo araçları → ham döküm yerine tek "plan yapıyor" sinyali.
_PLAN_TOOLS = {"TodoWrite", "TaskCreate", "TaskUpdate"}

# Uygulama ortamını Claude'a tanıtan system prompt eki (claude_code preset'ine append —
# skill/slash komutları BOZULMAZ). "Bekleme moduna geçme" sapmasını ve gereksiz
# subagent token yakımını hedefler.
_APP_SYSTEM_APPEND = (
    "[ORTAM] Unity Architect AI masaüstü uygulamasının sohbet arayüzü içinden "
    "kullanılıyorsun (Unity odaklı). Arka plan görevleri (background subagent/Bash) "
    "desteklenir: bir arka plan görevi bittiğinde sistem seni OTOMATİK uyandırır ve "
    "kaldığın yerden devam edersin. Bu yüzden kendini 'bekleme moduna' alma, bekleme "
    "döngüsü kurma ya da görev bitti mi diye tekrar tekrar yoklama. Kullanıcının "
    "abonelik kotasını korumak için: küçük/orta işleri subagent açmadan doğrudan kendin "
    "yap; subagent'ları yalnızca gerçekten paralellik gerektiren büyük işlerde kullan."
)

# Metin/thinking delta'ları bu boyuta ulaşınca SSE'ye basılır (event spam azaltma).
_DELTA_FLUSH_CHARS = 48
# Arka plan görevleri bitince CLI kendiliğinden devam etmezse bu süre sonra dürtülür.
_TASKS_DONE_GRACE_S = 20.0
# Nudge sonrası devam turu hiç gelmezse turu bitirme emniyeti.
_NUDGE_FALLBACK_S = 180.0
# Result geldi + görevler sürüyor: görevler hiç bitmezse turu bitirme emniyeti.
_TASKS_WATCHDOG_S = 900.0
_NUDGE_MESSAGE = (
    "[Sistem] Arka plan görevlerin tamamlandı. Sonuçlarını değerlendirip kaldığın "
    "yerden kısaca devam et ve işi sonuçlandır."
)


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
    """Onay kartında / chip başlığında gösterilecek kısa, insan-okunur açıklama."""
    try:
        if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            return f"{tool_name} → {inp.get('file_path', inp.get('path', '?'))}"
        if tool_name == "Bash":
            return inp.get("command", "")
        if tool_name == "Read":
            return inp.get("file_path", "")
        if tool_name in ("Glob", "Grep"):
            return inp.get("pattern", "")
        if tool_name == "WebFetch":
            return inp.get("url", "")
        if tool_name == "WebSearch":
            return inp.get("query", "")
        if tool_name.startswith("mcp__"):
            return f"{tool_name} {json.dumps(inp, ensure_ascii=False)[:160]}"
        return f"{tool_name} {json.dumps(inp, ensure_ascii=False)[:160]}"
    except Exception:
        return tool_name


def _trim_args(inp: dict, cap: int = 1200) -> dict:
    """Tool girdisini chip'in 'PARAMETRELER' panelinde göstermek için kırpar
    (örn. Write'ın dosya içeriği devasa olabilir — SSE'yi şişirmesin)."""
    out: Dict[str, Any] = {}
    try:
        for k, v in (inp or {}).items():
            if isinstance(v, str) and len(v) > cap:
                out[k] = v[:cap] + f"… [+{len(v) - cap} karakter]"
            else:
                out[k] = v
    except Exception:
        return inp or {}
    return out


def _tool_result_text(block) -> str:
    """ToolResultBlock.content → düz metin (str | [{'type':'text',...}] | TextBlock listesi)."""
    c = getattr(block, "content", None)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for item in c:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                parts.append(getattr(item, "text") or "")
        return "\n".join(p for p in parts if p)
    return ""


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
        self._broken = False          # reader/transport öldü → get_session taze kurar
        self._turn_lock = asyncio.Lock()
        self._out_q: Optional[asyncio.Queue] = None
        self.session_id: Optional[str] = None
        # İptal (Durdur) için: aktif tur boyunca bekleyen gate'ler + iptal sinyali
        self._cancel_event: Optional[asyncio.Event] = None
        self._active_gate_ids: Set[str] = set()

        # ── Sürekli reader + tur durum makinesi ──────────────────────────
        self._reader_task: Optional[asyncio.Task] = None
        self._turn_active = False
        self._final_text = ""          # tur boyunca biriken asistan metni (TextBlock'lardan)
        self._last_result_text = ""    # son ResultMessage.result (slash komut çıktıları için)
        self._saw_text_delta = False   # partial delta geldiyse blok metnini tekrar basma
        self._saw_thinking_delta = False
        self._txt_buf = ""             # delta birleştirme tamponları (SSE spam azaltma)
        self._think_buf = ""
        self._turn_tokens = 0          # tur boyunca üretilen output token (canlı sayaç)
        self._msg_tokens_seen = 0      # aktif API mesajının son bilinen output_tokens'ı
        # Arka plan görevleri (session ömürlü — görev turlar arası sürebilir).
        self._active_tasks: Dict[str, str] = {}   # task_id → açıklama
        self._result_pending = False   # Result geldi ama arka plan görevleri sürüyor
        self._nudges = 0               # görevler bitince gönderilen dürtme sayısı (tur başına)
        self._turn_started_at = 0.0
        self._cancel_requested = False
        self._grace_task: Optional[asyncio.Task] = None
        self._usage_event: Optional[dict] = None
        # tool_use_id → araç adı: ToolResultBlock geldiğinde çıktıyı doğru chip'e
        # bağlamak için (frontend tool_id ile eşleştirir). pop-on-use → küçük kalır.
        self._tool_names: Dict[str, str] = {}
        # API stall teşhisi: CLI'dan son mesajın geldiği an + son bilinen limit durumu.
        # Heartbeat bunlarla "neden bekliyoruz"u kullanıcıya SÖYLER (kör bekleme yerine).
        self._last_cli_msg_at: float = time.time()
        # Son İÇERİK ilerlemesi (ping/keepalive HARİÇ). Fable derin düşünürken dakikalarca
        # içerik gelmez ama ping akar → iki zaman ayrışınca "derin düşünme" teşhisi konur.
        self._last_progress_at: float = time.time()
        self._rate_limit: Optional[Dict[str, Any]] = None

    # ── Yaşam döngüsü ────────────────────────────────────────────────────
    async def start(self):
        if self._started:
            return
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

        opts_kwargs: Dict[str, Any] = dict(
            permission_mode=self.permission_mode,
            setting_sources=self.setting_sources,
            can_use_tool=self._can_use_tool,
            cwd=self.cwd,
            # Canlı thinking/text delta'ları + token sayacı için şart.
            include_partial_messages=True,
            # claude_code preset'i korunur (skill/slash bozulmaz); ortam bilgisi eklenir.
            system_prompt={"type": "preset", "preset": "claude_code",
                           "append": _APP_SYSTEM_APPEND},
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
        self._broken = False
        self._reader_task = asyncio.create_task(self._reader_loop())
        logger.info(f"[ClaudeSDKSession:{self.conversation_id}] başlatıldı (model={self.model}, effort={self.effort or '-'})")

    async def close(self):
        # Önce reader'ı durdur (transport kapanırken yarım okuma gürültüsü olmasın),
        # sonra client'ı kapat. Reader'ın KENDİ içinden çağrılırsa kendini iptal etmez.
        self._cancel_grace()
        rt = self._reader_task
        self._reader_task = None
        if rt is not None and rt is not asyncio.current_task():
            rt.cancel()
            try:
                await rt
            except BaseException:
                pass
        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.__aexit__(None, None, None), timeout=10)
            except Exception as e:
                logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] kapatma hatası: {e}")
        self._client = None
        self._started = False
        self._turn_active = False

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

    # ── İptal (Durdur) ───────────────────────────────────────────────────
    async def cancel_turn(self):
        """Kullanıcı 'Durdur' dediğinde aktif turu iptal eder.
        1) Bekleyen onay/soru gate'lerini 'reddedildi' ile çözer (yoksa can_use_tool
           300sn bloklu kalır). 2) SDK turunu interrupt() eder. 3) Tur makul sürede
           bitmezse session'ı ZORLA resetler — böylece sonraki mesaj asla eski kilide
           takılmaz. _turn_lock ALMAZ (deadlock önlemi — cancel ayrı request task'ından gelir)."""
        self._cancel_requested = True
        self._cancel_grace()
        for gid in list(self._active_gate_ids):
            if gid in APPROVAL_GATES:
                APPROVAL_RESULTS[gid] = False
                APPROVAL_GATES[gid].set()
            if gid in QUESTION_GATES:
                QUESTION_RESULTS[gid] = None
                QUESTION_GATES[gid].set()
        if self._cancel_event is not None:
            self._cancel_event.set()

        interrupted = False
        try:
            if self._client is not None:
                await asyncio.wait_for(self._client.interrupt(), timeout=8.0)
                interrupted = True
        except Exception as e:
            logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] interrupt hatası: {e}")

        if interrupted:
            # Interrupt kabul edildi → CLI kısa sürede Result üretip turu bitirmeli.
            for _ in range(40):  # ≤10 sn
                if not self._turn_active:
                    logger.info(f"[ClaudeSDKSession:{self.conversation_id}] tur iptal edildi (interrupt)")
                    return
                await asyncio.sleep(0.25)

        # Interrupt başarısız ya da tur hâlâ aktif → sert reset. Sonraki mesaj taze
        # session açar (session_id None → DB transcript'i yeniden enjekte edilir).
        logger.warning(f"[ClaudeSDKSession:{self.conversation_id}] interrupt işlemedi → session zorla resetleniyor")
        await self._finish_turn(error="⏹ Tur durduruldu (session resetlendi).")
        if _SESSIONS.get(self.conversation_id) is self:
            _SESSIONS.pop(self.conversation_id, None)
        await self.close()

    # ── Sürekli reader: CLI'dan gelen HER mesajı işler ───────────────────
    async def _reader_loop(self):
        try:
            async for msg in self._client.receive_messages():
                await self._on_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"[ClaudeSDKSession:{self.conversation_id}] reader koptu")
            self._broken = True
            await self._finish_turn(error=f"Claude session koptu: {e}")
            if _SESSIONS.get(self.conversation_id) is self:
                _SESSIONS.pop(self.conversation_id, None)
            # Kendi içinden tam close çağrılmaz (kendini iptal etmesin) — subprocess
            # zaten ölmüş; artıkları arka plan task'ı temizler (close, current_task
            # kontrolü sayesinde reader'ı kendi kendine iptal ettirmez).
            asyncio.create_task(self.close())

    async def _emit(self, ev: dict):
        """Aktif tur SSE'sine bas; SSE yoksa sessizce düş (metin zaten _final_text'te
        birikiyor; tur bitince DB'ye kaydedilir)."""
        q = self._out_q
        if q is not None:
            await q.put(ev)

    def _begin_turn(self):
        self._turn_active = True
        self._final_text = ""
        self._last_result_text = ""
        self._saw_text_delta = False
        self._saw_thinking_delta = False
        self._txt_buf = ""
        self._think_buf = ""
        self._turn_tokens = 0
        self._msg_tokens_seen = 0
        self._result_pending = False
        self._nudges = 0
        self._turn_started_at = time.time()
        self._cancel_requested = False
        self._usage_event = None
        self._cancel_grace()

    async def _flush_deltas(self):
        if self._think_buf:
            t, self._think_buf = self._think_buf, ""
            await self._emit({"type": "thinking", "text": t})
        if self._txt_buf:
            t, self._txt_buf = self._txt_buf, ""
            await self._emit({"type": "text", "content": t})

    async def _finish_turn(self, error: Optional[str] = None):
        """Turu kapat: usage + response + done + sentinel. SSE koptuysa metni DB'ye yaz."""
        if not self._turn_active:
            return
        self._turn_active = False
        self._result_pending = False
        self._cancel_grace()
        await self._flush_deltas()
        final = self._final_text or self._last_result_text
        q = self._out_q
        if q is not None:
            if self._usage_event:
                await q.put(self._usage_event)
            if error:
                await q.put({"type": "error", "message": error})
            await q.put({"type": "response", "content": final})
            await q.put({"type": "done", "session_id": self.session_id})
            await q.put(None)  # sentinel → stream() biter
        elif final and not error:
            # SSE kapalıyken biten tur (Durdur/kopma sonrası otonom devam) → kaybolmasın.
            if _DB_SAVE_CB is not None:
                try:
                    _DB_SAVE_CB(self.conversation_id, final)
                    logger.info(f"[ClaudeSDKSession:{self.conversation_id}] otonom tur yanıtı DB'ye kaydedildi ({len(final)} kr)")
                except Exception:
                    logger.exception("[ClaudeSDKSession] otonom yanıt DB kaydı başarısız")

    # ── Grace/nudge zamanlayıcıları (arka plan görev orkestrasyonu) ──────
    def _cancel_grace(self):
        gt = self._grace_task
        self._grace_task = None
        if gt is not None and not gt.done():
            gt.cancel()

    def _schedule_grace(self, delay: float, action: str):
        """action: 'nudge' → görevler bitti, CLI kendiliğinden devam etmezse dürt;
        'finish' → emniyet: turu bitir."""
        self._cancel_grace()
        self._grace_task = asyncio.create_task(self._grace_fire(delay, action))

    async def _grace_fire(self, delay: float, action: str):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if action != "nudge" and not self._turn_active:
            return  # 'finish' yalnızca aktif turda anlamlı; nudge tur kapandıktan sonra da
                    # çalışabilir (görev geç bitti → devam turu tetiklenir, yanıt DB'ye düşer)
        if action == "nudge" and (self._turn_active and not self._result_pending):
            return  # bu arada yeni bir kullanıcı turu başlamış → nudge araya girmesin
        if action == "nudge" and self._nudges < 1 and not self._cancel_requested and not self._broken:
            self._nudges += 1
            logger.info(f"[ClaudeSDKSession:{self.conversation_id}] görevler bitti, otonom devam gelmedi → nudge")
            await self._emit({"type": "status", "detail": "🔔 Arka plan görevleri bitti — devam ettiriliyor…",
                              "tokens": self._turn_tokens})
            try:
                await self._client.query(_NUDGE_MESSAGE)
                self._result_pending = False
                self._schedule_grace(_NUDGE_FALLBACK_S, "finish")
            except Exception:
                logger.exception("[ClaudeSDKSession] nudge gönderilemedi")
                await self._finish_turn()
        else:
            await self._finish_turn()

    async def _maybe_tasks_drained(self):
        """Aktif arka plan görevi kalmadıysa: kısa bir süre CLI'ın otonom devam turunu
        bekle; gelmezse nudge ile devam ettir (proaktif uyanma). Tur watchdog'la
        kapanmış olsa bile çalışır — geç biten görevin sonucu kaybolmaz (hayalet tur
        + DB kaydı)."""
        if self._active_tasks or self._cancel_requested:
            return
        if (self._turn_active and self._result_pending) or not self._turn_active:
            self._schedule_grace(_TASKS_DONE_GRACE_S, "nudge")

    # ── Mesaj çevirici + tur durum makinesi ──────────────────────────────
    async def _on_message(self, msg):
        from claude_agent_sdk import (
            AssistantMessage, RateLimitEvent, ResultMessage, StreamEvent, SystemMessage,
            TaskNotificationMessage, TaskProgressMessage, TaskStartedMessage,
            TaskUpdatedMessage, TERMINAL_TASK_STATUSES,
            TextBlock, ThinkingBlock, ToolResultBlock, ToolUseBlock, UserMessage,
        )

        self._last_cli_msg_at = time.time()
        # ping/keepalive stream-event'leri ilerleme SAYILMAZ (Fable düşünürken sırf ping akar)
        if not (isinstance(msg, StreamEvent) and (msg.event or {}).get("type") == "ping"):
            self._last_progress_at = time.time()

        # Kullanım limiti sinyali — eskiden sessizce düşüyordu; kullanıcı limit
        # yüzünden bekleyen turu "dondu" sanıyordu. Artık açıkça gösterilir.
        if isinstance(msg, RateLimitEvent):
            info = msg.rate_limit_info
            self._rate_limit = {"status": info.status, "resets_at": info.resets_at,
                                "type": info.rate_limit_type, "utilization": info.utilization}
            if info.status == "rejected":
                when = ""
                if info.resets_at:
                    try:
                        from datetime import datetime as _dt
                        when = " — " + _dt.fromtimestamp(info.resets_at).strftime("%H:%M") + "'de sıfırlanır"
                    except Exception:
                        pass
                await self._emit({"type": "status",
                                  "detail": (
                                      "🚦 Claude bu isteği kullanım penceresi sinyaliyle "
                                      f"bekletiyor ({info.rate_limit_type or 'pencere'}){when}. "
                                      "Bu, hesabındaki tüm Claude erişiminin kapandığı anlamına "
                                      "gelmeyebilir; CLI otomatik yeniden deniyor. Durdur ile "
                                      "başka modele geçebilirsin."
                                  ),
                                  "tokens": self._turn_tokens})
            elif info.status == "allowed_warning":
                pct = f" (%{int(info.utilization * 100)})" if isinstance(info.utilization, (int, float)) else ""
                await self._emit({"type": "status",
                                  "detail": f"⚠️ Claude kullanım limitine yaklaşılıyor{pct}",
                                  "tokens": self._turn_tokens, "heartbeat": True})
            return

        # Task yaşam döngüsü — SystemMessage ALT SINIFLARI, önce bunlar kontrol edilir.
        if isinstance(msg, TaskStartedMessage):
            desc = msg.description or "arka plan görevi"
            self._active_tasks[msg.task_id] = desc
            await self._emit({"type": "status", "scope": "subagent",
                              "detail": f"🤖 Görev başladı: {desc}",
                              "tokens": self._turn_tokens})
            return
        if isinstance(msg, TaskProgressMessage):
            u = msg.usage or {}
            detail = f"🤖 {msg.description or 'Görev sürüyor'}"
            if msg.last_tool_name:
                detail += f" · {msg.last_tool_name}"
            await self._emit({"type": "status", "scope": "subagent", "detail": detail,
                              "tokens": u.get("total_tokens") or self._turn_tokens})
            return
        if isinstance(msg, TaskNotificationMessage):
            desc = self._active_tasks.pop(msg.task_id, None) or "Görev"
            ok = msg.status == "completed"
            icon = "✅" if ok else ("🛑" if msg.status == "stopped" else "❌")
            await self._emit({"type": "tool_result", "tool": "Subagent", "success": ok,
                              "summary": f"{icon} {desc}: {(msg.summary or msg.status)[:200]}"})
            await self._emit({"type": "status",
                              "detail": f"{icon} Görev bitti: {desc}",
                              "tokens": self._turn_tokens})
            await self._maybe_tasks_drained()
            return
        if isinstance(msg, TaskUpdatedMessage):
            if msg.status in TERMINAL_TASK_STATUSES and msg.task_id in self._active_tasks:
                desc = self._active_tasks.pop(msg.task_id, "Görev")
                ok = msg.status == "completed"
                await self._emit({"type": "tool_result", "tool": "Subagent", "success": ok,
                                  "summary": f"{'✅' if ok else '❌'} {desc}: {msg.status}"})
                await self._maybe_tasks_drained()
            return

        if isinstance(msg, StreamEvent):
            await self._on_stream_event(msg)
            return

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
            return

        if isinstance(msg, AssistantMessage):
            if getattr(msg, "parent_tool_use_id", None):
                return  # subagent iç trafiği ana transcript'e karışmasın
            _api_err = getattr(msg, "error", None)
            if _api_err:
                _err_tr = {
                    "rate_limit": "kullanım limiti", "server_error": "sunucu hatası (Anthropic)",
                    "billing_error": "faturalama sorunu", "authentication_failed": "oturum/auth hatası",
                    "invalid_request": "geçersiz istek",
                }.get(_api_err, _api_err)
                await self._emit({"type": "status",
                                  "detail": f"⚠️ Claude API: {_err_tr} — CLI otomatik yeniden deniyor…",
                                  "tokens": self._turn_tokens})
            if not self._turn_active:
                # Tur kapandıktan SONRA gelen asistan mesajı = otonom devam turu
                # (watchdog/stop sonrası geciken task bitişi). "Hayalet tur" aç ki
                # Result geldiğinde metni DB'ye kaydedilsin — hiçbir yanıt kaybolmasın.
                self._begin_turn()
            self._cancel_grace()  # asistan aktif → otonom devam başladı, bitirme sayacı dursun
            for b in msg.content:
                if isinstance(b, TextBlock):
                    self._final_text += b.text
                    if not self._saw_text_delta:
                        await self._emit({"type": "text", "content": b.text})
                elif isinstance(b, ThinkingBlock):
                    if not self._saw_thinking_delta and b.thinking:
                        await self._emit({"type": "thinking", "text": b.thinking})
                elif isinstance(b, ToolUseBlock):
                    await self._flush_deltas()  # sıra korunumu: metin → araç
                    inp = b.input or {}
                    tool_id = getattr(b, "id", None)
                    if tool_id:
                        self._tool_names[tool_id] = b.name
                    if b.name in ("Task", "Agent"):
                        desc = inp.get("description") or inp.get("prompt", "")[:80] or "subagent"
                        await self._emit({"type": "tool_call", "tool": "Subagent",
                                          "tool_id": tool_id,
                                          "arguments": _trim_args(inp),
                                          "summary": f"🤖 {desc}"})
                        await self._emit({"type": "status",
                                          "detail": f"🤖 Subagent çalışıyor: {desc}",
                                          "tokens": self._turn_tokens})
                    elif b.name in _PLAN_TOOLS:
                        # Plan/todo: ham döküm yerine tek "plan yapıyor" sinyali
                        await self._emit({"type": "tool_call", "tool": "TodoWrite", "summary": ""})
                    elif b.name in _NOISE_TOOLS:
                        continue  # düşük-değerli iç araçları gizle
                    else:
                        await self._emit({"type": "tool_call", "tool": b.name,
                                          "tool_id": tool_id,
                                          "arguments": _trim_args(inp),
                                          "summary": _describe_tool(b.name, inp)})
            return

        if isinstance(msg, UserMessage):
            # Araç SONUÇLARI user-mesajı olarak döner (ToolResultBlock) → chip'in
            # "ÇIKTI" paneli buradan dolar. Subagent iç trafiği yine dışarıda.
            if getattr(msg, "parent_tool_use_id", None):
                return
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                return
            for b in content:
                if not isinstance(b, ToolResultBlock):
                    continue
                name = self._tool_names.pop(getattr(b, "tool_use_id", ""), None)
                if not name or name in _NOISE_TOOLS or name in _PLAN_TOOLS:
                    continue
                txt = (_tool_result_text(b) or "").strip()
                if len(txt) > 3000:
                    txt = txt[:3000] + "\n… [çıktı kırpıldı]"
                ok = not bool(getattr(b, "is_error", False))
                first_line = txt.splitlines()[0][:120] if txt else ("tamam" if ok else "hata")
                await self._emit({
                    "type": "tool_result",
                    "tool": "Subagent" if name in ("Task", "Agent") else name,
                    "tool_id": getattr(b, "tool_use_id", None),
                    "success": ok,
                    "summary": first_line,
                    "output": txt,
                })
            return

        if isinstance(msg, ResultMessage):
            self._last_result_text = getattr(msg, "result", "") or ""
            self._usage_event = self._build_usage_event(msg)
            if getattr(msg, "is_error", False) or self._cancel_requested or not self._active_tasks:
                await self._finish_turn()
            else:
                # Arka plan görevleri sürüyor → turu (SSE'yi) AÇIK tut; kullanıcı
                # süreci canlı izler, görevler bitince devam otomatik akar.
                self._result_pending = True
                names = ", ".join(list(self._active_tasks.values())[:3])
                await self._flush_deltas()
                await self._emit({"type": "status",
                                  "detail": f"⏳ {len(self._active_tasks)} arka plan görevi sürüyor ({names}) — bitince devam edilecek",
                                  "tokens": self._turn_tokens})
                self._schedule_grace(_TASKS_WATCHDOG_S, "finish")
            return

    async def _on_stream_event(self, msg):
        """Partial (canlı) akış: thinking/text delta'ları + token sayacı."""
        if getattr(msg, "parent_tool_use_id", None):
            return  # subagent delta'ları ana akışa karışmasın (TaskProgress zaten raporlar)
        e = msg.event or {}
        et = e.get("type")
        if et == "content_block_delta":
            d = e.get("delta") or {}
            dt = d.get("type")
            if dt == "thinking_delta":
                self._saw_thinking_delta = True
                self._think_buf += d.get("thinking", "")
                if len(self._think_buf) >= _DELTA_FLUSH_CHARS:
                    t, self._think_buf = self._think_buf, ""
                    await self._emit({"type": "thinking", "text": t})
            elif dt == "text_delta":
                self._saw_text_delta = True
                self._txt_buf += d.get("text", "")
                if len(self._txt_buf) >= _DELTA_FLUSH_CHARS:
                    t, self._txt_buf = self._txt_buf, ""
                    await self._emit({"type": "text", "content": t})
        elif et in ("content_block_stop", "message_stop"):
            await self._flush_deltas()
        elif et == "message_start":
            self._msg_tokens_seen = 0
            self._cancel_grace()  # yeni model mesajı başladı → otonom devam geldi
        elif et == "message_delta":
            out = ((e.get("usage") or {}).get("output_tokens"))
            if isinstance(out, int) and out > 0:
                self._turn_tokens += max(0, out - self._msg_tokens_seen)
                self._msg_tokens_seen = out
                await self._emit({"type": "status", "tokens": self._turn_tokens,
                                  "heartbeat": True})

    def _build_usage_event(self, msg) -> dict:
        u = getattr(msg, "usage", None) or {}
        inp = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) \
            + (u.get("cache_read_input_tokens") or 0)
        return {
            "type": "turn_usage",
            "input_tokens": inp,
            "output_tokens": u.get("output_tokens") or self._turn_tokens or 0,
            "cost_usd": getattr(msg, "total_cost_usd", None),
            "duration_ms": getattr(msg, "duration_ms", None)
                           or int((time.time() - self._turn_started_at) * 1000),
        }

    # ── Mesaj akışı: bir tur gönder, event dict'leri yield et ────────────
    async def stream(self, message: str) -> AsyncGenerator[dict, None]:
        if not self._started:
            await self.start()
        if self._broken:
            raise SessionBusyError("Claude session kopmuş (reader ölü).")

        # Kilidi SINIRLI bekle: önceki tur sıkıştıysa sonsuza dek "düşünüyor"da
        # kalınmaz — SessionBusyError fırlar, AgentRunner session'ı resetleyip dener.
        try:
            await asyncio.wait_for(self._turn_lock.acquire(), timeout=10.0)
        except asyncio.TimeoutError:
            raise SessionBusyError("Önceki tur kilidi bırakmadı.")

        try:
            out_q: asyncio.Queue = asyncio.Queue()
            self._out_q = out_q
            self._cancel_event = asyncio.Event()
            self._active_gate_ids.clear()
            self._begin_turn()
            await self._client.query(message)
            while True:
                try:
                    ev = await asyncio.wait_for(out_q.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    # Kalp atışı: SSE'yi canlı tut + kullanıcıya NEDEN beklediğini söyle.
                    hb: Dict[str, Any] = {"type": "status", "heartbeat": True,
                                          "tokens": self._turn_tokens}
                    stall = int(time.time() - self._last_cli_msg_at)
                    if self._rate_limit and self._rate_limit.get("status") == "rejected":
                        hb["detail"] = (
                            "🚦 Claude isteği kullanım penceresi nedeniyle bekliyor — "
                            "bu tüm hesap erişiminin kapandığı anlamına gelmeyebilir "
                            "(Durdur ile başka modele geçebilirsin)"
                        )
                    elif stall >= 90:
                        # CLI'dan uzun süredir hiç mesaj yok → model düşünüyor olabilir ama
                        # limit/yoğunluk backoff'u da olabilir. Kör "düşünüyor" yerine dürüst bilgi.
                        hb["detail"] = (f"⏳ Claude API {stall // 60} dk {stall % 60} sn'dir sessiz — "
                                        "uzun düşünme ya da limit/yoğunluk (otomatik yeniden deneniyor)")
                    elif self._active_tasks:
                        hb["detail"] = f"⏳ {len(self._active_tasks)} arka plan görevi sürüyor"
                    yield hb
                    continue
                if ev is None:
                    break
                yield ev
        finally:
            # NOT: reader'ı BEKLEMEYİZ/iptal etmeyiz (eski 'await task' kilidi burdaydı).
            # SSE koptuysa tur CLI'da sürer; reader biten turun metnini DB'ye kaydeder.
            self._out_q = None
            self._cancel_event = None
            self._active_gate_ids.clear()
            self._turn_lock.release()


def get_session(conversation_id: int, **kwargs) -> ClaudeSDKSession:
    """conversation_id için canlı session'ı getir; yoksa (veya kopmuşsa) oluştur."""
    sess = _SESSIONS.get(conversation_id)
    if sess is not None and sess._broken:
        _SESSIONS.pop(conversation_id, None)
        asyncio.create_task(sess.close())  # artıkları arka planda temizle
        sess = None
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
