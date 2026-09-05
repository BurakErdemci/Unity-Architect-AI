"""Replay the genuine two-turn fixture; tool/failure cases are synthetic.

No CLI, config writer, external service, or filesystem scratch is used here.
"""
import asyncio
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from providers import agy_session
from providers.agy_provider import AgyProvider
from providers.cli_base import BaseCLIProvider


FIXTURE = Path(__file__).parent / "fixtures/agy_stream_json_sample.ndjson"
EVENTS = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]
SESSION_ID = EVENTS[0]["conversation_id"]
TURNS = []
pending = []
for event in EVENTS:
    pending.append(event)
    if event["event"] == "result":
        TURNS.append(pending)
        pending = []


class FakeStdin:
    def __init__(self, process):
        self.process = process
        self.lines = []
        self.closed = False
        self.drains = 0

    def write(self, data):
        if self.closed:
            raise BrokenPipeError("fake closed stdin")
        self.lines.append(data)

    async def drain(self):
        self.drains += 1
        self.process.written.set()
        if self.process.release is not None:
            await self.process.release.wait()
        await asyncio.sleep(0)
        index = self.drains - 1
        if index < len(self.process.turns):
            for event in self.process.turns[index]:
                self.process.stdout.feed_data((json.dumps(event) + "\n").encode("utf-8"))
        if self.process.crash:
            self.process.stderr.feed_data(b"fake agy stderr: process crashed mid-turn\n")
            self.process.finish(27)

    def close(self):
        self.closed = True
        self.process.finish(0)


class FakeProcess:
    def __init__(self, turns=None, *, crash=False, release=None):
        self.turns = copy.deepcopy(TURNS if turns is None else turns)
        self.crash = crash
        self.release = release
        self.returncode = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stdin = FakeStdin(self)
        self.written = asyncio.Event()
        self.exited = asyncio.Event()
        self.killed = False

    def finish(self, code):
        if self.returncode is None:
            self.returncode = code
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self.exited.set()

    def kill(self):
        self.killed = True
        self.finish(-9)

    async def wait(self):
        await self.exited.wait()
        return self.returncode


class TestAgyStreamSession(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        agy_session._SESSIONS.clear()
        agy_session._RESUME_IDS.clear()
        self.processes = []
        self.spawns = []
        self.plans = []
        self.patches = [
            patch.object(BaseCLIProvider, "_AGY_LOCK", asyncio.Lock()),
            patch.object(AgyProvider, "_agy_binary", return_value="fake-agy"),
            patch.object(AgyProvider, "_resolve_exec", side_effect=lambda command: command),
            patch.object(AgyProvider, "_write_mcp_config", return_value=""),
            patch.object(AgyProvider, "_set_agy_model"),
            patch.object(AgyProvider, "_stream_instructions", return_value=""),
            patch.object(agy_session.asyncio, "create_subprocess_exec", side_effect=self.spawn),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self):
        await agy_session.close_all_sessions()
        for item in reversed(self.patches):
            item.stop()

    async def spawn(self, *argv, **kwargs):
        self.spawns.append((argv, kwargs))
        process = FakeProcess(**(self.plans.pop(0) if self.plans else {}))
        self.processes.append(process)
        return process

    async def collect(self, session=None, message="hello", **kwargs):
        session = session or agy_session.get_session(11)
        return [event async for event in session.stream(message, **kwargs)]

    async def test_two_turns_share_process_conversation_and_keep_stdin_open(self):
        session = agy_session.get_session(11)
        first = await self.collect(session)
        second = await self.collect(session, "second turn")
        self.assertEqual(len(self.processes), 1)
        self.assertEqual([first[-1]["session_id"], second[-1]["session_id"]], [SESSION_ID] * 2)
        self.assertIs(agy_session.peek_session(11), session)
        self.assertTrue(session.is_live)
        self.assertFalse(self.processes[0].stdin.closed)
        self.assertEqual(self.processes[0].stdin.drains, 2)
        self.assertNotIn("--conversation", self.spawns[0][0])
        self.assertEqual([e["content"] for e in first if e["type"] == "text"], ["OK\n"])

    async def test_utf8_long_multiline_prompt_only_on_stdin(self):
        message = "private prompt: şİ🙂\n" * 4000
        await self.collect(message=message)
        argv, kwargs = self.spawns[0]
        self.assertFalse(any("private prompt" in argument for argument in argv))
        self.assertIn("-p=", argv)
        self.assertNotIn("-p", argv)
        self.assertEqual(argv[argv.index("--input-format") + 1], "stream-json")
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
        self.assertEqual(kwargs["stdin"], asyncio.subprocess.PIPE)
        self.assertEqual(kwargs["stdout"], asyncio.subprocess.PIPE)
        data = self.processes[0].stdin.lines[0]
        self.assertEqual(data.count(b"\n"), 1)
        self.assertEqual(json.loads(data.decode("utf-8")),
                         {"event": "user", "message": {"content": message}})

    async def test_result_usage_is_per_turn_including_cached_and_thinking_tokens(self):
        session = agy_session.get_session(11)
        first = await self.collect(session)
        second = await self.collect(session)
        first_usage = next(e for e in first if e["type"] == "turn_usage")
        second_usage = next(e for e in second if e["type"] == "turn_usage")
        for key in agy_session._USAGE_KEYS:
            self.assertEqual(first_usage[key], TURNS[0][-1]["result"]["usage"][key])
            self.assertEqual(second_usage[key], TURNS[1][-1]["result"]["usage"][key]
                             - TURNS[0][-1]["result"]["usage"][key])
        self.assertEqual(second_usage["input_tokens"], 6512)
        self.assertEqual(second_usage["thinking_tokens"], 127)
        self.assertEqual(second_usage["total_tokens"], 6640)
        self.assertIsNone(second_usage["cost_usd"])

    async def test_synthetic_tool_steps_are_ordered_and_deduplicated(self):
        # Trivial live prompts produced no tools: these tool_info cases are synthetic.
        tool = {"event": "step_update", "step_update": {
            "conversation_id": SESSION_ID, "step_index": 9, "state": "RUNNING",
            "step_type": "tool", "tool_info": {"name": "view_file", "parameters": {"path": "a.cs"}},
        }}
        tool_done = copy.deepcopy(tool)
        tool_done["step_update"].update(state="DONE")
        tool_done["step_update"]["tool_info"]["output"] = "file contents"
        turn = [TURNS[0][0], TURNS[0][2], tool, tool, tool_done, tool_done,
                TURNS[0][2], TURNS[0][-1]]
        self.plans = [{"turns": [turn]}]
        events = await self.collect()
        self.assertEqual([e["type"] for e in events],
                         ["text", "tool_call", "tool_result", "text", "turn_usage", "response", "done"])
        self.assertEqual(events[1]["arguments"], {"path": "a.cs"})
        self.assertEqual(events[2]["summary"], "file contents")
        self.assertTrue(events[2]["success"])

    async def test_synthetic_tool_error_is_reported(self):
        tool = {"event": "step_update", "step_update": {
            "conversation_id": SESSION_ID, "step_index": 7, "state": "DONE",
            "step_type": "tool", "tool_info": {
                "name": "view_file", "parameters": '{"path":"missing.cs"}', "error": "missing",
            },
        }}
        self.plans = [{"turns": [[TURNS[0][0], tool, TURNS[0][-1]]]}]
        events = await self.collect()
        self.assertEqual(events[0]["arguments"], {"path": "missing.cs"})
        self.assertFalse(events[1]["success"])
        self.assertEqual(events[1]["summary"], "missing")

    async def test_process_death_emits_stderr_drops_registry_and_respawns_with_resume(self):
        self.plans = [{"turns": [[TURNS[0][0], TURNS[0][2]]], "crash": True}, {}]
        old = agy_session.get_session(11)
        events = await self.collect(old)
        self.assertEqual([e["type"] for e in events], ["text", "error"])
        self.assertIn("process crashed mid-turn", events[-1]["message"])
        self.assertIsNone(agy_session.peek_session(11))
        self.assertFalse(old.is_live)
        new = agy_session.get_session(11)
        self.assertIsNot(new, old)
        next_events = await self.collect(new)
        self.assertEqual(next_events[-1]["type"], "done")
        argv = self.spawns[1][0]
        self.assertEqual(argv[argv.index("--conversation") + 1], SESSION_ID)

    async def test_model_change_respawns_and_preserves_uuid(self):
        session = agy_session.get_session(11)
        await self.collect(session, model="gemini-3.6-flash")
        first = self.processes[0]
        await self.collect(session, model="gemini-3.8-flash")
        self.assertEqual(len(self.processes), 2)
        self.assertIsNotNone(first.returncode)
        self.assertEqual(session.model, "gemini-3.8-flash")
        argv = self.spawns[1][0]
        self.assertEqual(argv[argv.index("--conversation") + 1], SESSION_ID)
        self.assertEqual(AgyProvider._set_agy_model.call_args.args[0], "Gemini 3.8 Flash (High)")

    async def test_restart_uses_uuid_from_existing_disk_store_interface(self):
        session = agy_session.get_session(11, resume_id=SESSION_ID)
        await self.collect(session)
        argv = self.spawns[0][0]
        self.assertEqual(argv[argv.index("--conversation") + 1], SESSION_ID)
        await self.collect(session)
        self.assertEqual(len(self.spawns), 1)

    async def test_timeout_closes_process_and_emits_one_error(self):
        self.plans = [{"turns": [[TURNS[0][0]]]}]
        with patch.object(BaseCLIProvider, "_AGY_MAX_TOTAL", 0.02):
            events = await self.collect()
        self.assertEqual([e["type"] for e in events], ["error"])
        self.assertIn("timed out", events[0]["message"])
        self.assertIsNotNone(self.processes[0].returncode)
        self.assertTrue(self.processes[0].killed)
        self.assertIsNone(agy_session.peek_session(11))

    async def test_stop_and_stdout_eof_can_close_concurrently(self):
        self.plans = [{"turns": [[TURNS[0][0]]]}]
        session = agy_session.get_session(11)
        task = asyncio.create_task(self.collect(session))
        while not self.processes:
            await asyncio.sleep(0)
        await self.processes[0].written.wait()
        await agy_session.close_session(11)
        events = await asyncio.wait_for(task, timeout=1)
        self.assertEqual(events[-1]["type"], "error")
        self.assertTrue(self.processes[0].killed)
        self.assertIsNone(session._stderr_task)
        self.assertIsNone(agy_session.peek_session(11))

    async def test_global_lock_covers_turn_but_not_idle_process_lifetime(self):
        release = asyncio.Event()
        self.plans = [{"release": release}, {}]
        first = asyncio.create_task(self.collect(agy_session.get_session(11)))
        while not self.processes:
            await asyncio.sleep(0)
        await self.processes[0].written.wait()
        second = asyncio.create_task(self.collect(agy_session.get_session(12)))
        await asyncio.sleep(0)
        self.assertEqual(len(self.spawns), 1)
        self.assertTrue(BaseCLIProvider._AGY_LOCK.locked())
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
        self.assertEqual(len(self.spawns), 2)
        self.assertIsNone(self.processes[0].returncode)
        self.assertFalse(BaseCLIProvider._AGY_LOCK.locked())

    async def test_cancel_while_stdin_drain_is_blocked_closes_process(self):
        self.plans = [{"release": asyncio.Event()}]
        session = agy_session.get_session(11)
        task = asyncio.create_task(self.collect(session))
        while not self.processes:
            await asyncio.sleep(0)
        await self.processes[0].written.wait()
        self.assertIn(session, session.iptal_edilecekler())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNotNone(self.processes[0].returncode)
        self.assertIsNone(agy_session.peek_session(11))
        self.assertIsNone(session.active_provider)

    async def test_closed_queued_session_cannot_spawn(self):
        session = agy_session.get_session(11)
        await BaseCLIProvider._AGY_LOCK.acquire()
        task = asyncio.create_task(self.collect(session))
        await asyncio.sleep(0)
        await agy_session.close_session(11)
        BaseCLIProvider._AGY_LOCK.release()
        events = await task
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(self.spawns, [])

    async def test_early_generator_close_cleans_up(self):
        session = agy_session.get_session(11)
        stream = session.stream("hello")
        self.assertEqual((await anext(stream))["type"], "text")
        await stream.aclose()
        self.assertIsNotNone(self.processes[0].returncode)
        self.assertIsNone(agy_session.peek_session(11))
        self.assertFalse(BaseCLIProvider._AGY_LOCK.locked())

    async def test_runner_emits_native_text_usage_and_done_without_context_injection(self):
        from agentic.agent_runner import AgentRunner
        runner = AgentRunner(provider_type="subscription", api_key="", model_name="gemini-3.8-flash",
                             conversation_id=11, workspace_path=".", context="old history" * 10000)
        events = [event async for event in runner._run_agy_session("new user turn")]
        self.assertEqual([e.type for e in events], ["text", "turn_usage", "response", "done"])
        self.assertEqual(events[1].data["input_tokens"], 6335)
        self.assertEqual(events[-1].data["session_id"], SESSION_ID)
        self.assertEqual(events[-1].data["stop_reason"], "complete")
        self.assertEqual(json.loads(self.processes[0].stdin.lines[0])["message"]["content"], "new user turn")

    async def test_empty_success_response_is_not_replaced_with_fallback(self):
        result = copy.deepcopy(TURNS[0][-1])
        result["result"]["response"] = ""
        self.plans = [{"turns": [[TURNS[0][0], result]]}]
        events = await self.collect()
        self.assertEqual(events[-2], {"type": "response", "content": ""})
        self.assertEqual(events[-1]["type"], "done")

    async def test_closing_runner_iterator_after_done_keeps_process_for_next_turn(self):
        from agentic.agent_runner import AgentRunner
        runner = AgentRunner(provider_type="subscription", api_key="", model_name="gemini-3.8-flash",
                             conversation_id=11, workspace_path=".")
        stream = runner._run_agy_session("hello")
        async for event in stream:
            if event.type == "done":
                break
        await stream.aclose()
        self.assertTrue(agy_session.peek_session(11).is_live)
        events = [event async for event in runner._run_agy_session("second turn")]
        self.assertEqual(events[-1].type, "done")
        self.assertEqual(len(self.spawns), 1)

    async def test_unrelated_or_stale_results_do_not_end_current_turn(self):
        wrong = copy.deepcopy(TURNS[0][-1])
        wrong["result"]["conversation_id"] = "unrelated-conversation"
        self.plans = [{"turns": [TURNS[0], [wrong, TURNS[0][-1]] + TURNS[1]]}]
        session = agy_session.get_session(11)
        await self.collect(session)
        second = await self.collect(session)
        self.assertEqual(next(e for e in second if e["type"] == "turn_usage")["total_tokens"], 6640)

    async def test_failed_result_emits_only_error_terminal(self):
        result = copy.deepcopy(TURNS[0][-1])
        result["result"].update(status="ERROR", response="upstream failed")
        self.plans = [{"turns": [[TURNS[0][0], result]]}]
        events = await self.collect()
        self.assertEqual([e["type"] for e in events], ["error"])
        self.assertIn("upstream failed", events[0]["message"])
        self.assertIsNone(agy_session.peek_session(11))


class TestAnalyzeCodeOneShot:
    """AgyProvider.analyze_code runs one throwaway session turn and closes it.

    Callers without a conversation (analysis routes, compact summary, security
    check) used cli_base's generic one-shot spawn before the stream-json
    migration; that branch is gone, so this is the only path left for them.
    """

    def test_maps_session_events_and_closes(self, monkeypatch):
        import asyncio
        from providers import agy_session
        from providers.agy_provider import AgyProvider

        closed = []

        async def fake_stream(self, message, *, model="x", cwd=None):
            assert message == "summarize"
            assert model == "gemini-3.8-flash"
            yield {"type": "text", "content": "hel"}
            yield {"type": "text", "content": "lo"}
            yield {"type": "response", "content": "hello"}
            yield {"type": "done", "iterations": 1, "session_id": "s"}

        async def fake_close(self, *, preserve_resume=False):
            closed.append(self.conversation_id)

        monkeypatch.setattr(agy_session.AgyStreamSession, "stream", fake_stream)
        monkeypatch.setattr(agy_session.AgyStreamSession, "close", fake_close)

        async def run():
            provider = AgyProvider(binary_name="gemini-3.8-flash")
            return [ev async for ev in provider.analyze_code("summarize", cwd=".")]

        events = asyncio.run(run())
        assert [e["type"] for e in events] == ["delta", "delta", "final"]
        assert events[-1]["text"] == "hello"
        assert len(closed) == 1 and closed[0] < 0

    def test_error_event_is_forwarded_and_session_closed(self, monkeypatch):
        import asyncio
        from providers import agy_session
        from providers.agy_provider import AgyProvider

        closed = []

        async def fake_stream(self, message, *, model="x", cwd=None):
            yield {"type": "error", "message": "boom"}

        async def fake_close(self, *, preserve_resume=False):
            closed.append(True)

        monkeypatch.setattr(agy_session.AgyStreamSession, "stream", fake_stream)
        monkeypatch.setattr(agy_session.AgyStreamSession, "close", fake_close)

        async def run():
            provider = AgyProvider(binary_name="gemini-3.8-flash")
            return [ev async for ev in provider.analyze_code("x", cwd=".")]

        events = asyncio.run(run())
        assert events == [{"type": "error", "content": "boom"}]
        assert closed == [True]
