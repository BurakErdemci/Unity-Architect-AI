"""Stopping a chat must actually stop the video extraction it started.

External audit, 30 Aug 2026. `_prepare_videos` hands extraction to
`asyncio.to_thread`, and cancelling the awaiting coroutine does NOT reach the
pool thread: the caller got its `CancelledError` immediately while the worker
stayed parked inside `subprocess.run`, still downloading, with its per-video
directory under `<workspace>/.gamachine_tmp/video` still live — until yt-dlp's
own 600-second timeout expired. Repeated cancelled turns therefore piled up
executor threads, bandwidth and workspace disk with nothing to bound them.

The fix has two halves and BOTH are measured here, because either one alone is
worthless: the caller drops the abandoned temp directory, and it kills the live
child process. A cancellation that returns while an orphaned yt-dlp keeps
downloading has moved the leak, not closed it.

`_run` was rewritten from `subprocess.run` to `Popen` for the second half
(`run` hides the handle there is nothing to kill), so its ordinary contract —
timeout, `check`, the returned object — is re-measured here too.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from agentic.agent_runner import AgentRunner
import providers.video_extract as ve


class TestCancelStopsTheWorker(unittest.IsolatedAsyncioTestCase):
    async def test_cancelling_the_turn_drops_the_per_video_temp_directory(self):
        started, release = threading.Event(), threading.Event()

        def blocking_run(cmd, timeout, check=True):
            started.set()
            release.wait(10)
            raise RuntimeError("test blocker released")

        with tempfile.TemporaryDirectory() as workspace:
            runner = AgentRunner(
                provider_type="google", api_key="k", model_name="gemini",
                workspace_path=workspace, conversation_id=7,
                videos=[{"kind": "url", "url": "https://youtube.com/watch?v=cancel"}])
            original_run, original_missing = ve._run, ve.missing_binaries
            ve._run = blocking_run
            ve.missing_binaries = lambda need_ytdlp: []
            task = asyncio.create_task(runner._prepare_videos("devam"))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 5),
                                "extraction never reached its subprocess boundary")
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

                temp_root = os.path.join(workspace, ".gamachine_tmp", "video")
                leftover = os.listdir(temp_root) if os.path.isdir(temp_root) else []
                self.assertEqual(leftover, [],
                                 "the abandoned per-video directory is still live")
            finally:
                release.set()
                ve._run, ve.missing_binaries = original_run, original_missing

    async def test_a_cancel_does_not_swallow_the_cancellation(self):
        # The turn must still end. A handler that ate `CancelledError` to do its
        # cleanup would leave the caller believing the video is on its way.
        cancel = ve.ExtractionCancel()
        self.assertFalse(cancel.cancelled)
        cancel.cancel()
        self.assertTrue(cancel.cancelled)
        with self.assertRaises(ve.ExtractionCancelled):
            cancel.raise_if_cancelled("test")


class TestCancelKillsTheChildProcess(unittest.TestCase):
    """The half that a temp-directory check cannot see."""

    def test_the_live_subprocess_is_killed_and_the_worker_unwinds(self):
        cancel = ve.ExtractionCancel()
        token = ve._CANCEL.set(cancel)
        result = {}
        # A child that would outlive the turn by a wide margin if nobody killed
        # it; the worker's own timeout is 600 s in production.
        child = [sys.executable, "-c", "import time; time.sleep(60)"]

        def worker():
            ve._CANCEL.set(cancel)
            try:
                ve._run(child, timeout=120)
            except BaseException as e:                # noqa: BLE001 — recorded
                result["error"] = e

        try:
            t = threading.Thread(target=worker)
            t.start()
            for _ in range(500):                      # wait for the child to exist
                with cancel._lock:
                    procs = list(cancel._procs)
                if procs:
                    break
                threading.Event().wait(0.01)
            self.assertTrue(procs, "the child was never registered on the handle")
            proc = procs[0]
            cancel.cancel()
            t.join(20)
            self.assertFalse(t.is_alive(), "the worker stayed blocked after cancel")
            self.assertIsNotNone(proc.poll(), "the child process was left orphaned")
            self.assertIsInstance(result.get("error"), ve.ExtractionCancelled)
        finally:
            ve._CANCEL.reset(token)

    def test_a_kill_is_not_reported_as_a_download_failure(self):
        # Before, a killed yt-dlp would surface as "the link could not be
        # downloaded" — blaming the site for the user's own stop.
        cancel = ve.ExtractionCancel()
        cancel.cancel()
        with tempfile.TemporaryDirectory() as workspace:
            token = ve._CANCEL.set(cancel)
            original = ve.missing_binaries
            ve.missing_binaries = lambda need_ytdlp: []
            try:
                with self.assertRaises(ve.ExtractionCancelled):
                    ve.extract({"kind": "url", "url": "https://youtube.com/watch?v=x"},
                               workspace, "tag", cancel)
            finally:
                ve.missing_binaries = original
                ve._CANCEL.reset(token)


class TestRunStillBehavesLikeSubprocessRun(unittest.TestCase):
    """The Popen rewrite must not change `_run`'s contract."""

    def test_stdout_comes_back(self):
        r = ve._run([sys.executable, "-c", "print('merhaba')"], timeout=60)
        self.assertIn(b"merhaba", r.stdout)
        self.assertEqual(r.returncode, 0)

    def test_a_nonzero_exit_raises_when_checked(self):
        with self.assertRaises(subprocess.CalledProcessError) as ctx:
            ve._run([sys.executable, "-c", "import sys; sys.stderr.write('bok'); "
                                           "sys.exit(3)"], timeout=60)
        self.assertEqual(ctx.exception.returncode, 3)
        self.assertIn(b"bok", ctx.exception.stderr)

    def test_a_nonzero_exit_is_tolerated_when_check_is_off(self):
        # The subtitle call relies on this: its failure must not drop the video.
        r = ve._run([sys.executable, "-c", "import sys; sys.exit(4)"],
                    timeout=60, check=False)
        self.assertEqual(r.returncode, 4)

    def test_a_timeout_kills_the_child_and_raises(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            ve._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)


if __name__ == "__main__":
    unittest.main()
