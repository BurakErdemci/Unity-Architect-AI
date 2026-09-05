"""AUTO-WAKE: the wake queue + the `origin` contract of `/chat-stream`.

This feature has two parts and both can break silently:

  1. `wake_queue` — an in-process, bounded notice queue. If the limit or the
     chain counter breaks, the failure is INVISIBLE: the chat starts looping
     back on itself with no user present, and nobody measures it.
  2. The `origin` branch of `/chat-stream` — a wake turn's message MUST be
     stored with the `system` role. Writing `user` would make a sentence the
     user never typed appear as theirs on screen, and also enter the CLI
     handoff transcript as "USER: ...". The tests therefore check the ROLE
     that gets written, not that the call was made.

The route tests follow the pattern of `test_session_report.py`: the endpoint
function is run DIRECTLY against a fake db — a fake client never actually
runs the server's own lines.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from agentic import wake_queue
from routes.conversation_routes import create_conversation_router
from schemas import ChatRequest


@pytest.fixture(autouse=True)
def _temiz_kuyruk():
    """The queue is a MODULE-LEVEL GLOBAL and outlives a single test.

    Without cleanup, the chain counter left by the previous test wrongly opens
    the next test's "limit reached" branch — what gets measured is the leak,
    not the endpoint.
    """
    wake_queue.reset_all()
    yield
    wake_queue.reset_all()


# ── wake_queue ───────────────────────────────────────────────────────────────

def test_enqueue_then_drain_returns_notice_and_clears_queue():
    wake_queue.enqueue(7, "Task finished: build")
    assert wake_queue.drain(7) == ["Task finished: build"]
    assert wake_queue.drain(7) == []


def test_empty_text_and_invalid_id_are_not_enqueued():
    wake_queue.enqueue(7, "   ")
    wake_queue.enqueue(0, "something")
    assert wake_queue.pending(7) == 0
    assert wake_queue.pending(0) == 0


def test_n_completions_coalesce_into_one_drain():
    """Coalescing contract: N completions -> 1 wake.

    The endpoint merges the list returned by drain into a SINGLE `wake` frame;
    if the queue turned every completion into its own wake, three tasks would
    start three turns.
    """
    for ad in ("a", "b", "c"):
        wake_queue.enqueue(7, ad)
    assert wake_queue.drain(7) == ["a", "b", "c"]


def test_queue_is_bounded_and_drops_the_OLDEST():
    for i in range(wake_queue.MAX_NOTICES + 5):
        wake_queue.enqueue(7, f"n{i}")
    kalan = wake_queue.drain(7)
    assert len(kalan) == wake_queue.MAX_NOTICES
    # The newest completion is what the model needs; the oldest ones are what drops.
    assert kalan[-1] == f"n{wake_queue.MAX_NOTICES + 4}"
    assert kalan[0] == "n5"


def test_chain_counter_exhausts_at_the_limit_and_resets_on_user_message():
    assert wake_queue.chain_exhausted(7) is False
    for _ in range(wake_queue.MAX_CHAIN):
        wake_queue.bump_chain(7)
    assert wake_queue.chain_exhausted(7) is True
    wake_queue.reset_chain(7)
    assert wake_queue.chain_exhausted(7) is False


def test_wait_returns_immediately_when_a_notice_is_pending():
    async def run_it():
        wake_queue.enqueue(7, "ready")
        await asyncio.wait_for(wake_queue.wait(7), timeout=1.0)

    asyncio.run(run_it())


def test_wait_wakes_up_on_enqueue():
    async def run_it():
        bekle = asyncio.create_task(wake_queue.wait(7))
        await asyncio.sleep(0)
        wake_queue.enqueue(7, "late arrival")
        await asyncio.wait_for(bekle, timeout=1.0)

    asyncio.run(run_it())


# ── /chat-stream: origin contract ──────────────────────────────────────────

def _db():
    db = MagicMock()
    db.get_conversation_owner.return_value = 1
    db.get_ai_config.return_value = ("subscription", "claude-opus-5", "", False)
    db.get_api_key.return_value = ""
    db.get_last_workspace.return_value = ""
    db.get_memory.return_value = ""
    db.get_conversation_messages.return_value = []
    db.get_cli_session.return_value = None
    return db


def _chat_stream(db, **alanlar):
    router = create_conversation_router(db, MagicMock())
    route = next(r for r in router.routes if getattr(r, "path", "") == "/chat-stream")
    istek = ChatRequest(conversation_id=1, message="m", user_id=1, **alanlar)
    with patch("routes.conversation_routes.AgentRunner") as runner:
        runner.return_value = MagicMock()
        return asyncio.run(route.endpoint(request=istek, x_session_token="t"))


def test_wake_turn_message_is_stored_with_system_role():
    db = _db()
    _chat_stream(db, origin="wake")
    roller = [c.args[1] for c in db.add_message.call_args_list]
    assert roller == ["system"], roller


def test_user_turn_is_stored_with_user_role_and_cancels_pending_wake():
    db = _db()
    wake_queue.enqueue(1, "pending notice")
    wake_queue.bump_chain(1)
    _chat_stream(db, origin="user")
    assert db.add_message.call_args_list[0].args[1] == "user"
    # The human is back in the loop: both the pending notice and the counter drop.
    assert wake_queue.pending(1) == 0
    assert wake_queue.chain(1) == 0


def test_origin_defaults_to_user():
    db = _db()
    _chat_stream(db)
    assert db.add_message.call_args_list[0].args[1] == "user"


async def _govde(yanit) -> str:
    """Collapses a StreamingResponse body into one string (str/bytes chunks arrive mixed)."""
    parcalar = []
    async for p in yanit.body_iterator:
        parcalar.append(p if isinstance(p, str) else p.decode("utf-8"))
    return "".join(parcalar)


def test_when_chain_is_exhausted_turn_does_NOT_start_and_notice_frame_is_sent():
    db = _db()
    for _ in range(wake_queue.MAX_CHAIN):
        wake_queue.bump_chain(1)

    yanit = _chat_stream(db, origin="wake")

    govde = asyncio.run(_govde(yanit))
    assert "wake_chain_exhausted" in govde
    # Since the turn never starts, the message is ALSO never written: if it
    # were, an unexplained system row would remain in the chat.
    assert db.add_message.call_count == 0


def test_chain_increments_on_every_wake():
    db = _db()
    _chat_stream(db, origin="wake")
    assert wake_queue.chain(1) == 1
    _chat_stream(db, origin="wake")
    assert wake_queue.chain(1) == 2


# ── CLI handoff: system rows must not enter the transcript ───────────────────

def test_handoff_transcript_SKIPS_system_rows():
    """A wake text must not be carried into a new CLI as "USER: ...".

    This was the reason the "send a ready-made continuation message" idea,
    proposed as a stopgap, was rejected: an instruction that isn't the user's
    enters the history and gets copied forward on later handoffs.
    """
    from routes.conversation_routes import _build_handoff_context
    mesajlar = [
        {"role": "user", "content": "real request"},
        {"role": "system", "content": "Arka plan görevleri tamamlandı: build"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "last message (excluded)"},
    ]
    metin = _build_handoff_context("", mesajlar)
    assert "real request" in metin
    assert "Arka plan görevleri tamamlandı" not in metin


# ── /wake-stream ─────────────────────────────────────────────────────────────

def _wake_stream_route(db):
    router = create_conversation_router(db, MagicMock())
    return next(r for r in router.routes
                if getattr(r, "path", "") == "/conversations/{conv_id}/wake-stream")


def test_wake_stream_coalesces_pending_notices_into_ONE_frame():
    import json

    db = _db()
    route = _wake_stream_route(db)
    wake_queue.enqueue(1, "task A")
    wake_queue.enqueue(1, "task B")

    async def run_it():
        yanit = await route.endpoint(conv_id=1, x_session_token="t")
        return await asyncio.wait_for(_govde(yanit), timeout=5.0)

    with patch("providers.claude_sdk_session.session_busy", return_value=False),          patch("providers.claude_sdk_session.peek_session", return_value=None):
        govde = asyncio.run(run_it())

    satirlar = [l for l in govde.splitlines() if l.startswith("data: ")]
    assert len(satirlar) == 1, govde
    cerceve = json.loads(satirlar[0][6:])
    assert cerceve["type"] == "wake"
    assert cerceve["count"] == 2
    assert cerceve["notices"] == ["task A", "task B"]
    assert "task A" in cerceve["text"] and "task B" in cerceve["text"]
    assert wake_queue.pending(1) == 0


def test_wake_stream_does_NOT_fire_while_approval_pending_and_does_NOT_drop_notice():
    """Waking up while a decision card is on screen would orphan the card.

    The notice STAYING in the queue is the second half of the contract: the
    blocker is transient, so the wake is postponed — not cancelled.
    """
    from agentic.command_gates import APPROVAL_GATES

    db = _db()
    route = _wake_stream_route(db)
    wake_queue.enqueue(1, "task A")
    APPROVAL_GATES["test-gate"] = asyncio.Event()
    try:
        async def run_it():
            yanit = await route.endpoint(conv_id=1, x_session_token="t")
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(_govde(yanit), timeout=1.0)

        asyncio.run(run_it())
    finally:
        APPROVAL_GATES.pop("test-gate", None)
    assert wake_queue.pending(1) == 1
