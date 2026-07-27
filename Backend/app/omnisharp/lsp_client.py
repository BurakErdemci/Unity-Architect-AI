"""Minimal LSP/JSON-RPC stdio istemcisi (Content-Length framing).
OmniSharp'a özgü hiçbir şey içermez — sadece taşıma katmanı."""
import asyncio
import collections
import itertools
import json
import logging

logger = logging.getLogger("LspClient")

_STDERR_KEEP = 20        # tanı için saklanan son stderr satırı sayısı


class LspError(Exception):
    pass


class LspClient:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._handlers: dict[str, list] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stderr: collections.deque[str] = collections.deque(maxlen=_STDERR_KEEP)
        self._write_lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def stderr_tail(self) -> str:
        """Sunucunun son stderr satırları — arıza mesajına iliştirmek için."""
        return "\n".join(self._stderr)

    async def start(self, cmd: list[str], cwd: str, env: dict | None = None) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # stderr DEVNULL DEĞİL: 27 Tem 2026'da C# hover'ın 120 sn asılmasının
            # teşhisi tam üç gün bu tek satır yüzünden konulamadı. OmniSharp arızayı
            # stdout'taki LSP kanalına DEĞİL stderr'e yazıyor ("No .NET SDKs were
            # found.") ve initialize'a hiç yanıt vermiyor — stderr çöpe giderse
            # geriye yalnız sessiz bir timeout kalıyor.
            stderr=asyncio.subprocess.PIPE,
            env=env,  # None → parent env aynen (mevcut davranış)
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        """stderr'i sürekli oku: hem loga düşür hem sakla. Okunmayan bir PIPE
        dolduğunda yazan süreç bloke olur — DEVNULL'dan PIPE'a geçmenin bedeli
        bu drenajı ZORUNLU kılmak."""
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    return
                s = line.decode("utf-8", "replace").rstrip()
                if s:
                    self._stderr.append(s)
                    # DEBUG: OmniSharp sağlıklı çalışırken de stderr'e onlarca satır
                    # yazıyor ("Tried to send request … will be sent later"), WARNING'e
                    # basmak logu kullanılmaz kılıyor. Arıza anındaki asıl mesaj yine
                    # kaybolmuyor: `stderr_tail` başlatma hatasına iliştiriliyor.
                    logger.debug("OmniSharp stderr: %s", s[:500])
        except (asyncio.CancelledError, asyncio.IncompleteReadError):
            pass
        except Exception:
            logger.exception("stderr drenaj hatası")

    async def _read_loop(self) -> None:
        try:
            while self.alive:
                headers: dict[str, str] = {}
                while True:
                    line = await self._proc.stdout.readline()
                    if not line:
                        return  # process kapandı
                    s = line.decode("utf-8", "replace").strip()
                    if not s:
                        break
                    if ":" in s:
                        k, v = s.split(":", 1)
                        headers[k.strip().lower()] = v.strip()
                length = int(headers.get("content-length", 0))
                if length <= 0:
                    continue
                body = await self._proc.stdout.readexactly(length)
                self._dispatch(json.loads(body))
        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            pass
        except Exception:
            logger.exception("LSP read loop hatası")
        finally:
            # Process öldü → bekleyen istekleri boşa düşürme
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(LspError("LSP süreci kapandı"))
            self._pending.clear()

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(LspError(str(msg["error"])))
                else:
                    fut.set_result(msg.get("result"))
        elif "method" in msg:
            if "id" in msg:
                # Sunucudan gelen request (örn. workspace/configuration) → boş yanıt.
                asyncio.ensure_future(self._respond(msg["id"], None))
            for h in self._handlers.get(msg["method"], []):
                try:
                    h(msg.get("params") or {})
                except Exception:
                    logger.exception("notification handler hatası: %s", msg["method"])

    async def _respond(self, msg_id, result) -> None:
        await self._send({"jsonrpc": "2.0", "id": msg_id, "result": result})

    async def _send(self, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        frame = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        async with self._write_lock:
            self._proc.stdin.write(frame)
            await self._proc.stdin.drain()

    async def request(self, method: str, params: dict, timeout: float = 30.0):
        if not self.alive:
            raise LspError("LSP süreci çalışmıyor")
        msg_id = next(self._ids)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        await self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(msg_id, None)

    def notify(self, method: str, params: dict) -> None:
        if not self.alive:
            return
        asyncio.ensure_future(self._send({"jsonrpc": "2.0", "method": method, "params": params}))

    def on_notification(self, method: str, handler) -> None:
        self._handlers.setdefault(method, []).append(handler)

    async def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self.notify("exit", {})
            await asyncio.sleep(0.2)
        except Exception:
            pass
        if self.alive:
            self._proc.kill()
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()      # stderr drenajı da iptal edilmeli, yoksa görev sızar
        self._proc = None
