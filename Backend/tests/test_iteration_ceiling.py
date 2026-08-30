"""Iteration ceiling / progress-stall fuse of the three hand-written agentic loops.

Why this file exists: `MAX_ITERATIONS` was born in fe993c2 with no measurement
behind the number, and hitting it emitted a `done` event indistinguishable from
a normal finish. The characterization tests here were written BEFORE the fix
(they froze the old behaviour: cap 15, `max_reached` only, three different exit
texts) and were then deliberately updated with the fix.

No live provider is contacted: every client is a fake and `execute_tool` is
patched, so the loops run offline.
"""
import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import agentic.agent_runner as ar


# ── Fake provider clients ───────────────────────────────────────────────────
# Each one always answers with a tool call, so the loop can only ever end at a
# fuse (the ceiling or the stall guard) — never at "the model stopped calling
# tools". `args_for(i)` decides whether the run makes progress or repeats.


def _tool_args(i: int, repeat: bool, cycle: bool = False) -> dict:
    if cycle:
        # A/B/A/B: never two identical calls in a row, and no progress either.
        return {"file_path": "A.cs" if i % 2 == 0 else "B.cs"}
    return {"file_path": "same.cs"} if repeat else {"file_path": f"file_{i}.cs"}


class _FakeAnthropic:
    def __init__(self, repeat: bool, stop_after: int | None = None,
                 cycle: bool = False):
        self.calls = 0
        self.messages = types.SimpleNamespace(create=self._create)
        self._repeat = repeat
        self._cycle = cycle
        self._stop_after = stop_after

    async def _create(self, **kwargs):
        i = self.calls
        self.calls += 1
        usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
        if self._stop_after is not None and i >= self._stop_after:
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="bitti")],
                usage=usage,
            )
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(
                type="tool_use", id=f"t{i}", name="read_file",
                input=_tool_args(i, self._repeat, self._cycle),
            )],
            usage=usage,
        )


class _FakeOpenAI:
    def __init__(self, repeat: bool, stop_after: int | None = None,
                 cycle: bool = False):
        self.calls = 0
        self.base_url = None
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))
        self._repeat = repeat
        self._cycle = cycle
        self._stop_after = stop_after

    async def _create(self, **kwargs):
        i = self.calls
        self.calls += 1
        usage = types.SimpleNamespace(prompt_tokens=1, completion_tokens=1)
        if self._stop_after is not None and i >= self._stop_after:
            message = types.SimpleNamespace(content="bitti", tool_calls=None)
        else:
            import json as _json
            message = types.SimpleNamespace(content=None, tool_calls=[
                types.SimpleNamespace(
                    id=f"t{i}",
                    function=types.SimpleNamespace(
                        name="read_file",
                        arguments=_json.dumps(_tool_args(i, self._repeat, self._cycle)),
                    ),
                )])
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message)], usage=usage)


class _FakeGemini:
    """Gemini's loop consumes `response.candidates[0].content.parts`."""

    def __init__(self, repeat: bool, stop_after: int | None = None,
                 cycle: bool = False):
        self.calls = 0
        self.models = types.SimpleNamespace(generate_content=self._generate)
        self._repeat = repeat
        self._cycle = cycle
        self._stop_after = stop_after

    def _generate(self, **kwargs):
        i = self.calls
        self.calls += 1
        if self._stop_after is not None and i >= self._stop_after:
            parts = [types.SimpleNamespace(function_call=None, text="bitti", thought=False)]
        else:
            parts = [types.SimpleNamespace(
                function_call=types.SimpleNamespace(
                    name="read_file", args=_tool_args(i, self._repeat, self._cycle)),
                text=None, thought=False)]
        content = types.SimpleNamespace(parts=parts)
        return types.SimpleNamespace(
            candidates=[types.SimpleNamespace(content=content)],
            usage_metadata=types.SimpleNamespace(
                prompt_token_count=1, candidates_token_count=1),
        )


async def _noop_sleep(_s):
    """The Gemini/OpenAI loops pause 5s per iteration for rate limits; a
    ceiling-length run would otherwise take minutes of pure sleeping."""
    return None


def _fake_tool(name, args, workspace, conversation_id):
    return {"success": True, "summary": "ok"}


def _polling_tool():
    """A tool whose answer moves while its arguments do not — the documented
    Unity flow: `run_tests` tells the caller to poll `get_test_job(job_id)`."""
    state = {"n": 0}

    def _call(name, args, workspace, conversation_id):
        state["n"] += 1
        return {"success": True, "summary": "ok",
                "status": "complete" if state["n"] >= 8 else "pending",
                "progress": state["n"]}

    return _call


def _collect(provider_type, client, repeat=False, stop_after=None, tool_fn=None):
    """Runs one loop end to end and returns the emitted events."""
    runner = ar.AgentRunner(provider_type=provider_type, api_key="k",
                            model_name="m", workspace_path=".")
    patches = [
        mock.patch.object(ar, "execute_tool", tool_fn or _fake_tool),
        mock.patch.object(ar, "_all_tool_definitions",
                          lambda: [{"name": "read_file", "description": "d",
                                    "parameters": {"type": "object", "properties": {}}}]),
        mock.patch.object(ar, "get_openai_tool_declarations", lambda: []),
        mock.patch.object(ar, "get_gemini_tool_declarations",
                          lambda: [{"function_declarations": []}]),
        mock.patch.object(ar.asyncio, "sleep", _noop_sleep),
        mock.patch.object(ar.anthropic, "AsyncAnthropic", lambda **kw: client),
        mock.patch.object(ar.openai, "AsyncOpenAI", lambda **kw: client),
        mock.patch.object(ar.genai, "Client", lambda **kw: client),
    ]

    async def _go():
        return [e async for e in runner._run_inner("merhaba")]

    for p in patches:
        p.start()
    try:
        return asyncio.run(_go())
    finally:
        for p in reversed(patches):
            p.stop()


def _done(events):
    return next(e for e in events if e.type == "done")


_PROVIDERS = (
    ("anthropic", _FakeAnthropic),
    ("openai", _FakeOpenAI),
    ("google", _FakeGemini),
)


class TestCeiling(unittest.TestCase):
    """A run that keeps making progress may only stop at the ceiling."""

    def test_all_three_loops_stop_at_the_ceiling_with_the_same_contract(self):
        for name, factory in _PROVIDERS:
            with self.subTest(provider=name):
                ev = _collect(name, factory(repeat=False))
                d = _done(ev)
                self.assertEqual(d.data["stop_reason"], "max_iterations")
                self.assertTrue(d.data["max_reached"])
                self.assertEqual(d.data["iterations"], ar.MAX_ITERATIONS)
                # Exit text comes from one place now, and says why it stopped.
                self.assertEqual(d.data["stop_message"],
                                 ar._STOP_TEXTS["max_iterations"])
                # ...and ONLY from there. Streaming it as chat text as well put
                # the same warning on screen twice, next to the UI's own notice.
                self.assertEqual([e for e in ev if e.type == "response"
                                  and e.data.get("content") in ar._STOP_TEXTS.values()], [])

    def test_ceiling_is_well_above_the_old_fifteen(self):
        # Deliberately not importing the constant to compare against itself:
        # a test that reads the value it protects protects nothing.
        self.assertGreaterEqual(ar.MAX_ITERATIONS, 40)


class TestProgressGuard(unittest.TestCase):
    """The primary fuse: a run that stops moving ends before the ceiling."""

    def test_all_three_loops_stop_on_no_progress(self):
        for name, factory in _PROVIDERS:
            with self.subTest(provider=name):
                ev = _collect(name, factory(repeat=True))
                d = _done(ev)
                self.assertEqual(d.data["stop_reason"], "no_progress")
                self.assertTrue(d.data["max_reached"])
                self.assertEqual(d.data["iterations"], ar._STALL_LIMIT)
                self.assertEqual(len([e for e in ev if e.type == "tool_call"]),
                                 ar._STALL_LIMIT)
                self.assertEqual(d.data["stop_message"], ar._STOP_TEXTS["no_progress"])
                self.assertEqual([e for e in ev if e.type == "response"
                                  and e.data.get("content") in ar._STOP_TEXTS.values()], [])

    def test_a_poll_whose_answer_moves_is_progress(self):
        """The audit's first finding: `run_tests` documents polling
        `get_test_job`, and the earlier guard stopped the run on the third poll
        — one call before the job reported `complete`."""
        for name, factory in _PROVIDERS:
            with self.subTest(provider=name):
                ev = _collect(name, factory(repeat=True, stop_after=9),
                              tool_fn=_polling_tool())
                d = _done(ev)
                self.assertEqual(d.data["stop_reason"], "complete")

    def test_an_alternating_cycle_is_a_stall_too(self):
        """A/B/A/B makes no progress either. The first guard only recognised a
        one-node self-loop, so this ran to the ceiling."""
        for name, factory in _PROVIDERS:
            with self.subTest(provider=name):
                ev = _collect(name, factory(repeat=False, cycle=True))
                d = _done(ev)
                self.assertEqual(d.data["stop_reason"], "no_progress")
                self.assertLess(len([e for e in ev if e.type == "tool_call"]),
                                ar.MAX_ITERATIONS)

    def test_key_order_does_not_hide_a_repeat(self):
        g = ar._ProgressGuard()
        for i in range(ar._STALL_LIMIT - 1):
            g.record("read_file", {"a": 1, "b": 2} if i % 2 else {"b": 2, "a": 1}, "r")
        self.assertFalse(g.stalled)
        g.record("read_file", {"a": 1, "b": 2}, "r")
        self.assertTrue(g.stalled)

    def test_the_same_call_with_a_new_answer_is_not_a_stall(self):
        g = ar._ProgressGuard()
        for i in range(ar._STALL_LIMIT * 2):
            g.record("get_test_job", {"job_id": "j1"}, {"progress": i})
        self.assertFalse(g.stalled)

    def test_a_call_in_between_no_longer_launders_the_repetition(self):
        """Replaces an earlier test that asserted the opposite.

        That test froze the first design — a streak reset by any different
        signature — which is exactly the hole the audit walked through: a model
        interleaving one other call kept the streak at one forever. Counting
        inside a window is the fix, so an intervening call no longer hides it.
        """
        g = ar._ProgressGuard()
        for _ in range(ar._STALL_LIMIT):
            g.record("read_file", {"p": "a"}, "r")
            g.record("read_file", {"p": "b"}, "r")
        self.assertTrue(g.stalled)

    def test_repetition_outside_the_window_is_forgotten(self):
        """The window is what keeps a long, healthy run from accumulating a
        stall out of calls that are minutes apart."""
        g = ar._ProgressGuard()
        g.record("read_file", {"p": "a"}, "r")
        for i in range(ar._STALL_WINDOW):
            g.record("read_file", {"p": f"other_{i}"}, "r")
        for _ in range(ar._STALL_LIMIT - 1):
            g.record("read_file", {"p": "a"}, "r")
        self.assertFalse(g.stalled)

    def test_huge_arguments_are_hashed_not_kept(self):
        big = {"content": "x" * (ar._STALL_ARG_MAX + 500)}
        sig = ar._canonical_call("write_file", big)
        self.assertLess(len(sig), 200)
        self.assertEqual(sig, ar._canonical_call("write_file", dict(big)))
        other = {"content": "y" * (ar._STALL_ARG_MAX + 500)}
        self.assertNotEqual(sig, ar._canonical_call("write_file", other))


class TestNormalFinish(unittest.TestCase):
    def test_all_three_loops_report_complete(self):
        for name, factory in _PROVIDERS:
            with self.subTest(provider=name):
                ev = _collect(name, factory(repeat=False, stop_after=2))
                d = _done(ev)
                self.assertEqual(d.data["stop_reason"], "complete")
                self.assertFalse(d.data["max_reached"])
                self.assertEqual(d.data["iterations"], 3)


class TestExemptPathsCarryTheContract(unittest.TestCase):
    """The five CLI/SDK paths have no ceiling, but their `done` must still
    carry `stop_reason` — otherwise the reader has to guess what a missing
    field means, and the guess is exactly the bug this contract removes."""

    def test_session_done_is_normalized(self):
        e = ar._normalize_session_event("done", {"session_id": "abc"})
        self.assertEqual(e.type, "done")
        self.assertEqual(e.data["stop_reason"], "complete")
        self.assertFalse(e.data["max_reached"])
        self.assertEqual(e.data["session_id"], "abc")
        self.assertEqual(e.data["iterations"], 1)

    def test_non_done_session_events_pass_through_untouched(self):
        e = ar._normalize_session_event("text", {"content": "selam"})
        self.assertEqual(e.type, "text")
        self.assertEqual(e.data, {"content": "selam"})

    def test_every_done_in_the_module_goes_through_the_helper(self):
        """Closing the class, not one path: a new raw `AgentEvent("done", …)`
        anywhere in the runner would sidestep the contract silently."""
        src = open(ar.__file__, encoding="utf-8").read()
        raw = [ln.strip() for ln in src.splitlines()
               if 'AgentEvent("done"' in ln and not ln.strip().startswith("#")]
        # The only allowed occurrence is inside `_done_event` itself.
        self.assertEqual(raw, ['return AgentEvent("done", {'])

    def test_terminal_event_is_exactly_one(self):
        """A turn ends with `done` OR `error`, never both and never neither.

        The audit measured the earlier claim ("stop_reason on every termination
        path") against the code and found the error branches emit no `done` at
        all. Rather than wrap a failure in a `done` - which would show the same
        interruption twice, since the UI already renders `error` - the contract
        was narrowed to what the code does, and this test is what keeps the two
        from drifting apart again.
        """
        class _Boom:
            def __init__(self):
                self.messages = types.SimpleNamespace(create=self._create)

            async def _create(self, **kw):
                raise RuntimeError("saglayici patladi")

        for name, _factory in _PROVIDERS:
            with self.subTest(provider=name):
                client = _Boom()
                client.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=client._create))
                client.base_url = None
                client.models = types.SimpleNamespace(
                    generate_content=lambda **kw: (_ for _ in ()).throw(
                        RuntimeError("saglayici patladi")))
                ev = _collect(name, client)
                terminal = [e for e in ev if e.type in ("done", "error")]
                self.assertEqual(len(terminal), 1, [e.type for e in ev])
                self.assertEqual(terminal[0].type, "error")

    def test_sse_payload_carries_stop_reason(self):
        sse = ar._done_event(4, "no_progress").to_sse()
        self.assertIn('"stop_reason": "no_progress"', sse)
        self.assertIn('"max_reached": true', sse)


class TestStopMessageIsPersisted(unittest.TestCase):
    """A cut-short turn must not vanish from the conversation history.

    The loops' intermediate output goes out as `text` events and only `response`
    events are stored, so on a stop the ONLY thing worth persisting is the stop
    text — and that text is no longer streamed as chat content (the UI renders
    its own notice). Without the route layer picking it off `done`, reopening the
    conversation would show an empty assistant turn.
    """

    def _run_with(self, done_data: dict):
        from unittest.mock import MagicMock, patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.conversation_routes import create_conversation_router

        db = MagicMock()
        db.get_ai_config.return_value = ("claude", "claude-opus-5", None, None)
        db.get_api_key.return_value = ""
        db.get_last_workspace.return_value = ""
        db.get_memory.return_value = ""
        db.get_conversation_messages.return_value = []

        class _StoppingRunner:
            def __init__(self, **kwargs):
                pass

            async def run(self, message):
                yield ar.AgentEvent("text", {"content": "ara çıktı"})
                yield ar.AgentEvent("done", done_data)

        app = FastAPI()
        app.include_router(create_conversation_router(db, {}))
        with patch("routes.conversation_routes.AgentRunner", _StoppingRunner):
            with TestClient(app) as client:
                client.post("/chat-stream",
                            json={"conversation_id": 1, "message": "merhaba", "user_id": 1},
                            headers={"X-Session-Token": ""})
        return db

    def test_stop_message_reaches_the_stored_message(self):
        text = ar._STOP_TEXTS["max_iterations"]
        db = self._run_with({"iterations": 60, "stop_reason": "max_iterations",
                             "max_reached": True, "stop_message": text})
        stored = [c.args for c in db.add_message.call_args_list
                  if c.args and c.args[1] == "assistant"]
        self.assertTrue(stored, "kesilen tur hiç kaydedilmedi")
        self.assertIn(text, stored[-1][2])

    def test_normal_finish_stores_no_stop_text(self):
        db = self._run_with({"iterations": 3, "stop_reason": "complete",
                             "max_reached": False})
        for call in db.add_message.call_args_list:
            if call.args and call.args[1] == "assistant":
                for stop_text in ar._STOP_TEXTS.values():
                    self.assertNotIn(stop_text, call.args[2])


if __name__ == "__main__":
    unittest.main()
