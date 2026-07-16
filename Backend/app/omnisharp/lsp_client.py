"""Minimal LSP/JSON-RPC stdio istemcisi (Content-Length framing).
OmniSharp'a özgü hiçbir şey içermez — sadece taşıma katmanı."""
import asyncio
import itertools
import json
import logging

logger = logging.getLogger("LspClient")


class LspError(Exception):
    pass


class LspClient:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._handlers: dict[str, list] = {}
        self._reader_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, cmd: list[str], cwd: str, env: dict | None = None) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,  # None → parent env aynen (mevcut davranış)
        )
        self._reader_task = asyncio.create_task(self._read_loop())

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
        if self._reader_task:
            self._reader_task.cancel()
        self._proc = None
