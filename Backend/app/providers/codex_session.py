"""
Codex'i KALICI INTERAKTIF session olarak süren köprü (codex app-server, JSON-RPC).

Headless `codex exec` (tek atımlık) yerine `codex app-server`'ı tek uzun-yaşayan
süreç olarak sürer — Claude'daki ClaudeSDKClient'ın muadili:
- Sohbet başına tek canlı app-server süreci → bağlam turlar arası korunur (thread).
- NATIVE onay: server `item/commandExecution/requestApproval` /
  `item/fileChange/requestApproval` gönderir → biz command_gates üzerinden onay
  kartına çevirip {"decision":"accept"|"decline"} döneriz (can_use_tool eşdeğeri).
- Abonelik (ChatGPT) auth: API key gerekmez — codex kendi login'ini kullanır.

Protokol (codex-cli 0.139.0, ampirik doğrulandı):
- Framing: NDJSON (her mesaj tek satır UTF-8 JSON + '\n'). Content-Length YOK.
- Akış: initialize → initialized(notif) → thread/start → turn/start → (stream) →
  turn/completed. Onaylar Server→Client request (id + method) olarak gelir.
- decision enum: accept | acceptForSession | decline | cancel.

Yield edilen event'ler AgentEvent.data şekline uyar (claude_sdk_session ile aynı):
text / thinking / tool_call / tool_result / command_approval_needed / response / done / error.
"""
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from agentic.command_gates import APPROVAL_GATES, APPROVAL_RESULTS

logger = logging.getLogger(__name__)

# conversation_id → CodexSession (canlı, isteklerin ötesinde yaşar)
_SESSIONS: Dict[int, "CodexSession"] = {}

# Server→Client onay/etkileşim request method'ları (id + method ile gelir → cevaplanmalı)
_APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    # v1 legacy
    "applyPatchApproval",
    "execCommandApproval",
}


def _resolve_codex_appserver_cmd() -> List[str]:
    """`codex app-server` için spawn listesi.

    Tercih: `node <codex.js> app-server` — kalıcı stdio JSON-RPC için cmd.exe
    sarmalayıcısından daha güvenilir VE doğrudan öldürülebilir (cmd /c, node alt
    sürecini öksüz bırakıyor). codex.js, `codex` shim'inin yanındaki
    node_modules/@openai/codex/bin/codex.js'ten türetilir. Bulunamazsa cmd shim'e düşülür.
    """
    import shutil
    node = shutil.which("node")
    codex_bin = shutil.which("codex")
    if node and codex_bin:
        base = os.path.dirname(codex_bin)  # ...\npm  (codex.cmd burada)
        candidates = [
            os.path.join(base, "node_modules", "@openai", "codex", "bin", "codex.js"),
            os.path.join(base, "node_modules", "@openai", "codex", "dist", "codex.js"),
        ]
        for js in candidates:
            if os.path.isfile(js):
                return [node, js, "app-server"]
    # Fallback: .cmd shim'i cmd.exe ile sar (Windows WinError 2 fix)
    from providers.cli_base import BaseCLIProvider
    return BaseCLIProvider._resolve_exec(["codex", "app-server"])


# ── Codex skill kataloğu (Skills galerisi için) ──────────────────────────────
# codex app-server `skills/list` metodundan dolar (initialize + initialized yeter,
# thread/turn YOK → sıfır inference). Claude'un _COMMANDS_META muadili.
_CODEX_SKILLS_CACHE: List[Dict] = []
_CODEX_WARMUP_LOCK = asyncio.Lock()


def get_codex_skills_meta() -> List[Dict]:
    return list(_CODEX_SKILLS_CACHE)


def _parse_codex_skills(result: Optional[dict]) -> List[Dict]:
    """skills/list result'ını [{name, description, displayName, insert}] yapar.
    insert: galeride tıklanınca girdiye yazılacak metin (Codex skill'leri
    defaultPrompt ile çağrılır; yoksa `$<isim>`)."""
    out: List[Dict] = []
    seen = set()
    if not isinstance(result, dict):
        return out
    try:
        for group in (result.get("data") or []):
            for sk in (group.get("skills") or []):
                if not isinstance(sk, dict) or sk.get("enabled") is False:
                    continue
                name = sk.get("name")
                if not name or name in seen:
                    continue
                seen.add(name)
                iface = sk.get("interface") or {}
                desc = (iface.get("shortDescription") or sk.get("description") or "").strip()
                insert = (iface.get("defaultPrompt") or f"${name} ").strip()
                out.append({
                    "name": name,
                    "description": desc,
                    "displayName": (iface.get("displayName") or "").strip(),
                    "insert": insert,
                })
    except Exception as e:
        logger.warning(f"[_parse_codex_skills] parse hatası: {e}")
    return out


async def fetch_codex_skills(cwd: Optional[str] = None, force: bool = False) -> List[Dict]:
    """Throwaway codex app-server açıp skills/list ile skill kataloğunu çeker.
    initialize + initialized yeter (thread/turn YOK → sıfır token). Sonuç cache'lenir."""
    global _CODEX_SKILLS_CACHE
    async with _CODEX_WARMUP_LOCK:
        if _CODEX_SKILLS_CACHE and not force:
            return list(_CODEX_SKILLS_CACHE)

        spawn = _resolve_codex_appserver_cmd()
        env = {**os.environ, "NO_COLOR": "1"}
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *spawn,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=(cwd if (cwd and os.path.isdir(cwd)) else None),
            )

            req_id = 0

            async def send(method, params=None, notify=False):
                nonlocal req_id
                obj: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
                rid = None
                if not notify:
                    req_id += 1
                    rid = req_id
                    obj["id"] = rid
                if params is not None:
                    obj["params"] = params
                proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
                await proc.stdin.drain()
                return rid

            await send("initialize", {"clientInfo": {"name": "unity-architect", "version": "0.1.0"}})
            await send("initialized", notify=True)
            skills_id = await send("skills/list", {})

            result = None

            async def read_until():
                nonlocal result
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        return
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    if msg.get("id") == skills_id and ("result" in msg or "error" in msg):
                        result = msg.get("result")
                        return

            try:
                await asyncio.wait_for(read_until(), timeout=20)
            except asyncio.TimeoutError:
                logger.warning("[fetch_codex_skills] skills/list zaman aşımı")

            meta = _parse_codex_skills(result)
            if meta:
                _CODEX_SKILLS_CACHE = meta
            logger.info(f"[fetch_codex_skills] {len(meta)} Codex skill yakalandı")
            return list(_CODEX_SKILLS_CACHE)
        except Exception as e:
            logger.warning(f"[fetch_codex_skills] hata: {e}")
            return list(_CODEX_SKILLS_CACHE)
        finally:
            if proc is not None:
                try:
                    if proc.stdin and not proc.stdin.is_closing():
                        proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    # transport'ları düzgün kapat → "I/O operation on closed pipe" gürültüsü olmasın
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:
                    pass


def _describe_approval(method: str, params: dict) -> str:
    """Onay kartında gösterilecek kısa açıklama."""
    cmd = params.get("command")
    if cmd:
        return cmd if isinstance(cmd, str) else json.dumps(cmd, ensure_ascii=False)[:200]
    reason = params.get("reason")
    if reason:
        return str(reason)[:200]
    return method


class CodexSession:
    """Tek bir sohbete ait kalıcı codex app-server süreç sarmalayıcısı."""

    def __init__(
        self,
        conversation_id: int,
        *,
        model: Optional[str] = None,
        cwd: Optional[str] = None,
        approval_timeout: float = 300.0,
        auto_approve: bool = False,
    ):
        self.conversation_id = conversation_id
        self.model = model
        self.cwd = cwd
        self.approval_timeout = approval_timeout
        # Oto mod: True ise onay kartı GÖSTERİLMEZ, gelen onay isteklerine otomatik "accept".
        self.auto_approve = auto_approve

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._read_task: Optional[asyncio.Task] = None
        self._started = False
        self._turn_lock = asyncio.Lock()
        self._req_id = 0
        self._pending: Dict[int, asyncio.Future] = {}   # bizim istek id → Future
        self._out_q: Optional[asyncio.Queue] = None      # aktif tur event kuyruğu
        self._final_text = ""
        self.thread_id: Optional[str] = None
        self._current_turn_id: Optional[str] = None
        self._cancel_event: Optional[asyncio.Event] = None
        self._active_gate_ids: Set[str] = set()
        # İlk turda DB bağlam özeti enjekte edildi mi (sonraki turlarda thread hatırlıyor)
        self._ctx_injected = False

    # ── Süreç yaşam döngüsü ──────────────────────────────────────────────
    async def start(self):
        if self._started:
            return
        spawn = _resolve_codex_appserver_cmd()
        # Abonelik auth: API key env'lerini ENJEKTE ETME (codex kendi login'ini kullanır)
        env = {**os.environ, "NO_COLOR": "1"}
        self._proc = await asyncio.create_subprocess_exec(
            *spawn,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            cwd=(self.cwd if (self.cwd and os.path.isdir(self.cwd)) else None),
        )
        self._read_task = asyncio.create_task(self._read_loop())

        # 1) initialize + initialized (zorunlu)
        await self._request("initialize", {
            "clientInfo": {"name": "unity-architect", "version": "0.1.0"},
        }, timeout=30)
        await self._notify("initialized")

        # 2) thread/start — kalıcı thread. read-only sandbox + on-request → her mutasyon
        #    escalation ile native onaya gider (oto modda otomatik accept'lenir).
        params: Dict[str, Any] = {
            "cwd": self.cwd or os.getcwd(),
            "approvalPolicy": "on-request",
            "sandbox": "read-only",
        }
        if self.model:
            params["model"] = self.model
        resp = await self._request("thread/start", params, timeout=30)
        self.thread_id = (((resp or {}).get("result") or {}).get("thread") or {}).get("id")
        self._started = True
        logger.info(f"[CodexSession:{self.conversation_id}] başlatıldı (model={self.model or 'default'}, thread={self.thread_id})")

    async def close(self):
        # Önce okuma görevini durdur (kill'DEN ÖNCE — Windows Proactor'da kill + bekleyen
        # readline yarışı proc.wait()'i kilitleyebiliyor), SONRA süreci öldür.
        rt = self._read_task
        self._read_task = None
        if rt is not None:
            rt.cancel()
            try:
                await rt
            except BaseException:
                pass
        if self._proc is not None:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except Exception:
                pass
        self._proc = None
        self._started = False
        # Bekleyen istek future'larını serbest bırak (yoksa _request sonsuz bekler)
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    # ── Düşük seviye JSON-RPC (NDJSON) ───────────────────────────────────
    async def _send(self, obj: dict):
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("codex app-server süreci yok")
        self._proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _request(self, method: str, params: dict, timeout: float = 60) -> dict:
        self._req_id += 1
        rid = self._req_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def _notify(self, method: str, params: Optional[dict] = None):
        obj: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            obj["params"] = params
        await self._send(obj)

    async def _read_loop(self):
        """Tek okuma döngüsü: cevap / server-request (onay) / notification ayrımı."""
        assert self._proc and self._proc.stdout
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break  # süreç öldü / EOF
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                await self._dispatch(msg)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception(f"[CodexSession:{self.conversation_id}] read loop hatası")
        finally:
            # Süreç bittiyse aktif turu kapat
            self._started = False
            if self._out_q is not None:
                await self._out_q.put({"type": "error", "message": "Codex app-server süreci beklenmedik şekilde kapandı."})
                await self._out_q.put(None)

    async def _dispatch(self, msg: dict):
        has_id = "id" in msg
        has_method = "method" in msg
        if has_id and not has_method:
            # bizim isteğimize cevap
            fut = self._pending.get(msg["id"])
            if fut and not fut.done():
                fut.set_result(msg)
        elif has_id and has_method:
            # Server→Client request (onay / etkileşim) → arka planda işle (read loop bloklamasın)
            asyncio.create_task(self._handle_server_request(msg))
        elif has_method:
            # notification (stream)
            await self._handle_notification(msg)

    # ── Server→Client request: native onay köprüsü ───────────────────────
    async def _handle_server_request(self, msg: dict):
        rid = msg["id"]
        method = msg.get("method", "")
        params = msg.get("params", {}) or {}
        try:
            if method in _APPROVAL_METHODS:
                decision = await self._resolve_approval(method, params)
                await self._send({"id": rid, "result": {"decision": decision}})
            elif method == "item/tool/requestUserInput":
                await self._send({"id": rid, "result": {"value": ""}})
            else:
                # Bilinmeyen server-request: takılmamak için boş cevap (ör. token refresh)
                await self._send({"id": rid, "result": {}})
        except Exception as e:
            logger.warning(f"[CodexSession:{self.conversation_id}] server-request cevap hatası ({method}): {e}")

    async def _resolve_approval(self, method: str, params: dict) -> str:
        """Onay isteğini kartla/oto çöz → 'accept' | 'decline'."""
        # Oto mod: kart gösterme, otomatik onayla
        if self.auto_approve:
            return "accept"

        out_q = self._out_q
        gate_id = uuid.uuid4().hex
        ev = asyncio.Event()
        APPROVAL_GATES[gate_id] = ev           # gate'i emit'ten ÖNCE kaydet
        self._active_gate_ids.add(gate_id)
        if out_q is not None:
            await out_q.put({
                "type": "command_approval_needed",
                "gate_id": gate_id,
                "tool": method,
                "command": _describe_approval(method, params),
            })
        res = await self._wait_gate(ev, APPROVAL_GATES, APPROVAL_RESULTS, gate_id)
        return "accept" if bool(res) else "decline"

    async def _wait_gate(self, ev: asyncio.Event, gates: dict, results: dict, gate_id: str):
        try:
            await asyncio.wait_for(ev.wait(), timeout=self.approval_timeout)
            return results.pop(gate_id, None)
        except asyncio.TimeoutError:
            logger.warning(f"[CodexSession:{self.conversation_id}] onay zaman aşımı gate={gate_id}")
            return None
        finally:
            gates.pop(gate_id, None)

    # ── Notification → event dict eşlemesi ───────────────────────────────
    async def _handle_notification(self, msg: dict):
        out_q = self._out_q
        if out_q is None:
            return  # tur dışı bildirim (ör. remoteControl/status) — yok say
        method = msg.get("method", "")
        params = msg.get("params", {}) or {}

        if method == "item/agentMessage/delta":
            delta = params.get("delta", "")
            if delta:
                self._final_text += delta
                await out_q.put({"type": "text", "content": delta})

        elif method == "item/started":
            item = params.get("item", {}) or {}
            itype = item.get("type", "")
            # Metin/akıl yürütme delta ile gelir; userMessage = kullanıcının kendi mesajının
            # yankısı (araç değil) → gizle.
            if itype in ("agentMessage", "reasoning", "userMessage"):
                return
            # Araç başlangıcı (commandExecution / fileChange / mcp tool vb.)
            await out_q.put({"type": "tool_call", "tool": itype or "codex",
                             "tool_id": item.get("id"),
                             "arguments": self._item_args(item),
                             "summary": self._item_summary(item)})

        elif method == "item/completed":
            item = params.get("item", {}) or {}
            itype = item.get("type", "")
            if itype == "userMessage":
                return  # kullanıcı mesajı yankısı — gösterme
            if itype == "agentMessage":
                # Final metin zaten delta'larla akıtıldı; tekrar ekleme (çift sayım önlemi)
                txt = item.get("text", "")
                if txt and not self._final_text:
                    self._final_text = txt
                return
            if itype == "reasoning":
                txt = item.get("text", "")
                if txt:
                    await out_q.put({"type": "thinking", "text": txt})
                return
            # Araç sonucu — çıktı (komut stdout'u / değişiklik dökümü) chip'in ÇIKTI paneline
            exit_code = item.get("exitCode")
            success = (exit_code in (0, None)) and item.get("status") not in ("declined", "failed")
            await out_q.put({"type": "tool_result", "tool": itype or "codex",
                             "tool_id": item.get("id"),
                             "success": success,
                             "summary": self._item_summary(item),
                             "output": self._item_output(item)})

        elif method == "turn/completed":
            await out_q.put({"type": "response", "content": self._final_text})
            await out_q.put({"type": "done", "session_id": self.thread_id})
            await out_q.put(None)  # sentinel → stream biter

        elif method == "error":
            await out_q.put({"type": "error", "message": json.dumps(params, ensure_ascii=False)[:300]})
            await out_q.put(None)

    @staticmethod
    def _item_summary(item: dict) -> str:
        for k in ("command", "path", "title", "name"):
            v = item.get(k)
            if v:
                return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)[:160]
        return item.get("type", "")

    @staticmethod
    def _item_args(item: dict) -> dict:
        """Chip'in PARAMETRELER paneli için item'ın anlamlı girdi alanları (kırpılmış)."""
        out: Dict[str, Any] = {}
        for k in ("command", "cwd", "path", "name", "arguments", "changes", "title"):
            v = item.get(k)
            if v in (None, "", [], {}):
                continue
            if isinstance(v, str) and len(v) > 1200:
                v = v[:1200] + f"… [+{len(v) - 1200} karakter]"
            elif not isinstance(v, (str, int, float, bool)):
                v = json.dumps(v, ensure_ascii=False)[:1200]
            out[k] = v
        return out

    @staticmethod
    def _item_output(item: dict) -> str:
        """Chip'in ÇIKTI paneli için item sonucu (komut çıktısı / araç sonucu)."""
        for k in ("aggregatedOutput", "output", "stdout", "result", "error"):
            v = item.get(k)
            if not v:
                continue
            txt = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=2)
            txt = txt.strip()
            if len(txt) > 3000:
                txt = txt[:3000] + "\n… [çıktı kırpıldı]"
            return txt
        return ""

    # ── İptal (Durdur) ───────────────────────────────────────────────────
    async def cancel_turn(self):
        """Bekleyen onayları reddet + turn/interrupt. _turn_lock ALMAZ (deadlock önlemi)."""
        for gid in list(self._active_gate_ids):
            if gid in APPROVAL_GATES:
                APPROVAL_RESULTS[gid] = False
                APPROVAL_GATES[gid].set()
        try:
            if self._started and self.thread_id and self._current_turn_id:
                await self._request("turn/interrupt", {
                    "threadId": self.thread_id, "turnId": self._current_turn_id,
                }, timeout=10)
        except Exception as e:
            logger.warning(f"[CodexSession:{self.conversation_id}] interrupt hatası: {e}")
        if self._cancel_event is not None:
            self._cancel_event.set()
        logger.info(f"[CodexSession:{self.conversation_id}] tur iptal edildi (cancel_turn)")

    # ── Mesaj akışı: bir tur gönder, event dict'leri yield et ────────────
    async def usage_card_text(self) -> str:
        """`/usage` için: canlı app-server'dan account/rateLimits + account/read çekip
        /usage kartının parse ettiği formatta metin üretir (model turu YOK → sıfır token).
        Claude'un /usage'ına benzer: pencere başına 'X% used · resets <tarih>'."""
        if not self._started:
            await self.start()
        try:
            rl_resp = await self._request("account/rateLimits/read", {}, timeout=15)
        except Exception as e:
            return f"Codex kullanım bilgisi alınamadı: {e}"
        try:
            acc_resp = await self._request("account/read", {}, timeout=10)
        except Exception:
            acc_resp = {}

        rl = (((rl_resp or {}).get("result") or {}).get("rateLimits")) or {}
        acc = (((acc_resp or {}).get("result") or {}).get("account")) or {}

        acct_type = acc.get("type") or "ChatGPT"
        if acct_type.lower() == "chatgpt":
            acct_type = "ChatGPT"
        # NOT: planType (account/read='go', rateLimits='plus') tutarsız/yanlış geliyor →
        # yanlış plan göstermemek için plan adını yazmıyoruz.
        head = f"{acct_type} aboneliğiyle Codex kullanımı"
        lines = [head]

        def _fmt_window(w) -> Optional[str]:
            if not isinstance(w, dict):
                return None
            pct = w.get("usedPercent")
            if pct is None:
                return None
            mins = w.get("windowDurationMins") or 0
            if mins and mins < 1440:
                label = f"{mins // 60} saatlik pencere" if mins >= 60 else f"{mins} dakikalık pencere"
            elif mins:
                label = f"{mins // 1440} günlük pencere"
            else:
                label = "Kullanım penceresi"
            resets = w.get("resetsAt")
            reset_str = ""
            if isinstance(resets, (int, float)):
                try:
                    reset_str = " · resets " + datetime.fromtimestamp(resets).strftime("%d.%m %H:%M")
                except Exception:
                    reset_str = ""
            return f"{label}: {pct}% used{reset_str}"

        for w in (rl.get("primary"), rl.get("secondary")):
            ln = _fmt_window(w)
            if ln:
                lines.append(ln)

        credits = rl.get("credits") or {}
        if credits.get("hasCredits"):
            lines.append(f"Kredi bakiyesi: {credits.get('balance', '0')}")

        if len(lines) == 1:
            lines.append("Şu anda raporlanacak kullanım penceresi yok.")
        return "\n".join(lines)

    async def stream(self, message: str, image_paths: Optional[List[str]] = None) -> AsyncGenerator[dict, None]:
        if not self._started:
            await self.start()

        async with self._turn_lock:
            out_q: asyncio.Queue = asyncio.Queue()
            self._out_q = out_q
            self._cancel_event = asyncio.Event()
            self._active_gate_ids.clear()
            self._final_text = ""
            self._current_turn_id = None

            # Görseller app-server'a native 'localImage' input item'ı olarak gider
            # (şema: LocalImageUserInput → path). Yollar diske yazılmış temp dosyalar.
            input_items = [{"type": "text", "text": message}]
            for p in (image_paths or []):
                input_items.append({"type": "localImage", "path": p})

            try:
                resp = await self._request("turn/start", {
                    "threadId": self.thread_id,
                    "input": input_items,
                }, timeout=60)
                self._current_turn_id = (((resp or {}).get("result") or {}).get("turn") or {}).get("id")
            except Exception as e:
                logger.exception(f"[CodexSession:{self.conversation_id}] turn/start hatası")
                self._out_q = None
                yield {"type": "error", "message": f"Codex turu başlatılamadı: {e}"}
                return

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


def get_session(conversation_id: int, **kwargs) -> CodexSession:
    """conversation_id için canlı session'ı getir; yoksa oluştur."""
    sess = _SESSIONS.get(conversation_id)
    if sess is None:
        sess = CodexSession(conversation_id, **kwargs)
        _SESSIONS[conversation_id] = sess
    return sess


async def close_session(conversation_id: int):
    sess = _SESSIONS.pop(conversation_id, None)
    if sess is not None:
        await sess.close()


async def close_all_sessions():
    for cid in list(_SESSIONS.keys()):
        await close_session(cid)
