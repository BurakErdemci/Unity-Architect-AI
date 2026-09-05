"""Persistent Antigravity stream-json sessions, one subprocess per conversation."""
import asyncio
import json
import os
from typing import AsyncGenerator, Dict, Optional

from .agy_provider import AgyProvider
from .cli_base import BaseCLIProvider, _CREATE_NO_WINDOW, build_spawn_env
from .saglayici_sahipligi import SaglayiciSahipligi, oturumu_kapat

_SESSIONS: Dict[int, "AgyStreamSession"] = {}
# Retain an init UUID even if a process dies before done can reach the disk store.
_RESUME_IDS: Dict[tuple, str] = {}
_USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens",
               "thinking_tokens", "total_tokens")


class AgyStreamSession(SaglayiciSahipligi):
    """Own the process, its stderr reader, and its serialized stdin turns."""

    def __init__(self, conversation_id: int, *, resume_id: Optional[str] = None,
                 cwd: str = "."):
        # A negative conversation ID marks a throwaway one-shot session; it is
        # never registered in _SESSIONS or the _RESUME_IDS store.
        self.conversation_id = conversation_id
        self.cwd = os.path.abspath(cwd)
        self.session_id = resume_id if conversation_id >= 0 else None
        self.model = None
        self.auto_approve = False
        self._active_process = None
        self._stderr_task = None
        self._stderr_tail = b""
        self._usage_totals = {}
        self._num_turns = 0
        self._stop_lock = asyncio.Lock()
        self._sahiplik_kur()

    @property
    def is_live(self) -> bool:
        return (not self._kapandi and self._active_process is not None
                and self._active_process.returncode is None)

    def _remember_id(self, session_id) -> None:
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id
            if self.conversation_id >= 0:
                _RESUME_IDS[(self.conversation_id, self.cwd)] = session_id

    async def _drain_stderr(self, process) -> None:
        while True:
            chunk = await process.stderr.read(4096)
            if not chunk:
                break
            self._stderr_tail = (self._stderr_tail + chunk)[-8192:]

    async def _stop_process(self, *, force: bool = False) -> None:
        # Stop and the stdout EOF path can arrive together; reap each child once.
        async with self._stop_lock:
            await self._reap_process(force=force)

    async def _reap_process(self, *, force: bool) -> None:
        process = self._active_process
        if process is None:
            return
        try:
            if force and process.returncode is None:
                process.kill()
            if process.stdin is not None:
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                if process.returncode is None:
                    process.kill()
                await asyncio.wait_for(process.wait(), timeout=3)
        except (ProcessLookupError, BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if self._stderr_task is not None:
                try:
                    await asyncio.wait_for(self._stderr_task, timeout=1)
                except (asyncio.TimeoutError, asyncio.CancelledError, OSError):
                    self._stderr_task.cancel()
                self._stderr_task = None
            self._active_process = None
            if self.active_provider is self:
                self.active_provider = None

    async def cancel_active_process(self) -> bool:
        was_live = self.is_live
        await self._stop_process(force=True)
        return was_live

    async def close(self, *, preserve_resume: bool = False) -> None:
        if self.conversation_id >= 0 and _SESSIONS.get(self.conversation_id) is self:
            _SESSIONS.pop(self.conversation_id, None)
        if not preserve_resume and self.conversation_id >= 0:
            _RESUME_IDS.pop((self.conversation_id, self.cwd), None)
        await oturumu_kapat(self)
        await self._stop_process(force=True)

    async def _start(self, model: str, cwd: str) -> str:
        if self._kapandi:
            raise RuntimeError("agy session was stopped.")
        # The process holds ~/.gemini/settings.json state for its life. Model
        # changes require closing and respawning, while retaining the UUID.
        if self._active_process is not None and (
            not self.is_live or self.model != model or self.cwd != cwd
        ):
            await self._stop_process()
        if self._kapandi:
            raise RuntimeError("agy session was stopped.")
        if self.is_live:
            return ""
        if self.cwd != cwd:
            self.session_id = (_RESUME_IDS.get((self.conversation_id, cwd))
                               if self.conversation_id >= 0 else None)
        self.cwd = cwd
        if not os.path.isdir(cwd):
            raise RuntimeError("agy workspace directory does not exist.")
        provider = AgyProvider(binary_name=model)
        provider._resume_uuid = self.session_id
        command = provider._resolve_exec(provider._build_cmd(workspace=cwd))
        # Configuration happens under the same global turn lock as execution.
        # These existing helpers are mocked by the fake-process tests.
        provider._write_mcp_config(cwd)
        provider._set_agy_model(provider._pending_agy_model, cwd)
        instructions = provider._stream_instructions()
        self._stderr_tail = b""
        self._usage_totals = {}
        self._num_turns = 0
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=cwd,
            env=build_spawn_env(family="agy", overrides={"NO_COLOR": "1"}),
            creationflags=_CREATE_NO_WINDOW,
            limit=BaseCLIProvider._CLI_STREAM_LIMIT_BYTES,
        )
        # Register before draining stdin, so Stop can reach a blocked writer.
        self._active_process = process
        self.active_provider = self
        self._stderr_task = asyncio.create_task(self._drain_stderr(process))
        self.model = model
        if self._kapandi:
            await self._stop_process(force=True)
            raise RuntimeError("agy session was stopped during startup.")
        return instructions

    def _turn_usage(self, result: dict, elapsed: float) -> dict:
        # The captured second result contains cumulative process usage. Subtract
        # the preceding result, resetting the baseline on each process start.
        totals = {key: (result.get("usage") or {}).get(key) or 0 for key in _USAGE_KEYS}
        usage = {key: max(0, value - self._usage_totals.get(key, 0))
                 for key, value in totals.items()}
        self._usage_totals = totals
        return {"type": "turn_usage", **usage, "cost_usd": None,
                "duration_ms": int(elapsed * 1000)}

    async def stream(self, message: str, *, model: str = "gemini-3.6-flash",
                     cwd: Optional[str] = None) -> AsyncGenerator[dict, None]:
        # Global serialization covers the complete turn, not the process life.
        # A queued turn rechecks the closed flag before spawning or writing.
        async with BaseCLIProvider._AGY_LOCK:
            if self._kapandi:
                yield {"type": "error", "message": "agy session was stopped."}
                return
            completed = False
            loop = asyncio.get_running_loop()
            started = loop.time()
            tool_calls = set()
            tool_results = set()
            try:
                async with asyncio.timeout(BaseCLIProvider._AGY_MAX_TOTAL):
                    instructions = await self._start(model, os.path.abspath(cwd or self.cwd))
                    process = self._active_process
                    payload = {"event": "user", "message": {"content": instructions + message}}
                    process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                    await process.stdin.drain()
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            await self._stop_process(force=True)
                            raise RuntimeError(f"agy process exited before result (rc={process.returncode}).")
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        event_type = event.get("event")
                        if event_type == "init":
                            self._remember_id(event.get("conversation_id"))
                        elif event_type == "step_update":
                            step = event.get("step_update") or {}
                            if (step.get("conversation_id") and self.session_id
                                    and step["conversation_id"] != self.session_id):
                                continue
                            self._remember_id(step.get("conversation_id"))
                            if step.get("step_type") == "agent_response":
                                if step.get("text_delta"):
                                    yield {"type": "text", "content": step["text_delta"]}
                            elif step.get("step_type") == "tool":
                                info = step.get("tool_info") or {}
                                if not info.get("name"):
                                    continue
                                key = (step.get("step_index"), info["name"])
                                if key not in tool_calls:
                                    tool_calls.add(key)
                                    parameters = info.get("parameters") or {}
                                    if isinstance(parameters, str):
                                        try:
                                            parameters = json.loads(parameters)
                                        except ValueError:
                                            parameters = {"summary": parameters}
                                    yield {"type": "tool_call", "tool": info["name"],
                                           "arguments": parameters, "iteration": 1}
                                if key not in tool_results and (
                                    step.get("state") in ("DONE", "ERROR")
                                    or info.get("output") is not None or info.get("error")
                                ):
                                    tool_results.add(key)
                                    output = info.get("error") or info.get("output") or ""
                                    if not isinstance(output, str):
                                        output = json.dumps(output, ensure_ascii=False)
                                    yield {"type": "tool_result", "tool": info["name"],
                                           "success": not bool(info.get("error")) and step.get("state") != "ERROR",
                                           "summary": output}
                        elif event_type == "result":
                            result = event.get("result") or {}
                            if (result.get("conversation_id") and self.session_id
                                    and result["conversation_id"] != self.session_id):
                                continue
                            num_turns = result.get("num_turns", self._num_turns + 1)
                            if num_turns <= self._num_turns:
                                continue
                            self._remember_id(result.get("conversation_id"))
                            self._num_turns = num_turns
                            usage = self._turn_usage(result, loop.time() - started)
                            if result.get("status") != "SUCCESS":
                                raise RuntimeError(str(result.get("error") or result.get("response")
                                                       or f"agy result status: {result.get('status')}"))
                            completed = True
                            break
                        elif event_type == "error":
                            raise RuntimeError(str(event.get("error") or event.get("message")
                                                   or "agy reported an error."))
                # The turn timer ends at result, before delivering terminal events.
                yield usage
                yield {"type": "response", "content": result.get("response") or ""}
                yield {"type": "done", "iterations": 1, "session_id": self.session_id}
            except (asyncio.CancelledError, GeneratorExit):
                if not completed:
                    await self.close(preserve_resume=True)
                raise
            except Exception as exc:
                await self.close(preserve_resume=True)
                message = (f"agy turn timed out after {BaseCLIProvider._AGY_MAX_TOTAL} seconds."
                           if isinstance(exc, asyncio.TimeoutError) else str(exc))
                tail = self._stderr_tail.decode("utf-8", errors="replace").strip()
                from secret_redaction import redact_secrets
                yield {"type": "error", "message": redact_secrets(
                    message + (f"\n{tail}" if tail else ""))}
            finally:
                if not completed and not self._kapandi:
                    await self.close(preserve_resume=True)


# Keep the public ownership type used by existing stop/lifecycle callers.
AgySession = AgyStreamSession


def get_session(conversation_id: int, *, resume_id: Optional[str] = None,
                cwd: str = ".") -> AgyStreamSession:
    if conversation_id < 0:
        return AgyStreamSession(conversation_id, cwd=cwd)
    session = _SESSIONS.get(conversation_id)
    if session is None:
        known_id = _RESUME_IDS.get((conversation_id, os.path.abspath(cwd)), resume_id)
        session = AgyStreamSession(conversation_id, resume_id=known_id, cwd=cwd)
        _SESSIONS[conversation_id] = session
    return session


def peek_session(conversation_id: int) -> Optional[AgyStreamSession]:
    if conversation_id < 0:
        return None
    return _SESSIONS.get(conversation_id)


async def close_session(conversation_id: int) -> None:
    if conversation_id < 0:
        return
    session = _SESSIONS.get(conversation_id)
    if session is not None:
        await session.close()
    for key in list(_RESUME_IDS):
        if key[0] == conversation_id:
            _RESUME_IDS.pop(key, None)


async def close_all_sessions() -> None:
    for conversation_id in list(_SESSIONS):
        await close_session(conversation_id)
    _RESUME_IDS.clear()
