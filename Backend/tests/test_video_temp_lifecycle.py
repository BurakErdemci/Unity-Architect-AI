"""Where the per-video temp directory lives, and who removes it after a crash.

External audit, 30 Aug 2026, two findings about the same directory.

  · Cleanup lived ONLY in `extract()`'s `finally`. A crash, a `kill`, or a power
    loss walks straight past that block, and nothing ever swept
    `<workspace>/.gamachine_tmp/video`, so every abnormal exit left a directory
    with whatever media had been written into it — forever. Reproduced by
    killing a child interpreter mid-extraction.

  · `_attach_root` fell back to the literal `"."` whenever the saved workspace
    was empty, missing, or no longer a directory. The temp tree then landed
    next to the RUNNING APP: unwritable in a packaged install (so the video path
    failed for a reason no message named), and littering the source tree in
    development. Either way the user's request was silently redirected.

Two answers, and this file measures both: the directory is created as late as
possible so a crash before the first byte leaves nothing at all, and whatever
an earlier run did leave is swept by the next extraction.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import providers.video_extract as ve

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))

# Crashes mid-extraction, the way a `kill` or a power loss does: `os._exit`
# runs no `finally` block and no `atexit` hook.
_CRASH_CHILD = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
import providers.video_extract as ve
ve.missing_binaries = lambda need_ytdlp: []
ve._download_url = lambda url, out_dir: os._exit(17)
ve.extract({"kind": "url", "url": "https://youtube.com/watch?v=crash"}, sys.argv[2], "crash")
"""


class TestACrashLeavesNothingToLeak(unittest.TestCase):
    def test_a_hard_kill_before_the_first_write_leaves_no_directory(self):
        with tempfile.TemporaryDirectory() as workspace:
            r = subprocess.run([sys.executable, "-c", _CRASH_CHILD, _APP_DIR, workspace],
                               capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 17, "the child did not crash as intended")
            root = os.path.join(workspace, ".gamachine_tmp", "video")
            leftover = os.listdir(root) if os.path.isdir(root) else []
            self.assertEqual(leftover, [], f"crash left {leftover} behind")

    def test_a_directory_left_by_an_earlier_crash_is_swept(self):
        # The half a late `mkdir` cannot cover: a process killed AFTER the first
        # byte still leaves a tree, and only a later run can collect it.
        with tempfile.TemporaryDirectory() as workspace:
            root = os.path.join(workspace, ".gamachine_tmp", "video")
            stale = os.path.join(root, "vid_conv1_deadbeef")
            os.makedirs(stale)
            with open(os.path.join(stale, "dl.mp4"), "wb") as f:
                f.write(b"half a download")
            old = time.time() - (ve._STALE_TEMP_AGE_S + 60)
            os.utime(stale, (old, old))

            self.assertEqual(ve.sweep_stale_temp(workspace), 1)
            self.assertFalse(os.path.exists(stale))

    def test_a_live_extraction_is_not_swept_out_from_under_itself(self):
        # A second backend process, or a parallel turn, may be mid-download.
        # Deleting its directory to reclaim a few megabytes would break a live
        # turn, so the sweep is age-gated rather than unconditional.
        with tempfile.TemporaryDirectory() as workspace:
            live = os.path.join(workspace, ".gamachine_tmp", "video", "vid_conv2_feed")
            os.makedirs(live)
            self.assertEqual(ve.sweep_stale_temp(workspace), 0)
            self.assertTrue(os.path.isdir(live))

    def test_the_sweep_is_quiet_when_there_is_nothing_to_sweep(self):
        with tempfile.TemporaryDirectory() as workspace:
            self.assertEqual(ve.sweep_stale_temp(workspace), 0)

    def test_an_extraction_sweeps_before_it_starts(self):
        # "The function exists" is not "the function is called".
        with tempfile.TemporaryDirectory() as workspace:
            stale = os.path.join(workspace, ".gamachine_tmp", "video", "vid_conv3_old")
            os.makedirs(stale)
            old = time.time() - (ve._STALE_TEMP_AGE_S + 60)
            os.utime(stale, (old, old))
            original = ve.missing_binaries
            ve.missing_binaries = lambda need_ytdlp: []
            try:
                with self.assertRaises(ve.VideoPipelineError):
                    ve.extract({"kind": "bilinmeyen"}, workspace, "tag")
            finally:
                ve.missing_binaries = original
            self.assertFalse(os.path.exists(stale))


class TestTempFilesGoWhereTheCallerAsked(unittest.TestCase):
    def test_a_real_workspace_is_used(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = ve._attach_root(workspace)
            self.assertTrue(os.path.abspath(root).startswith(os.path.abspath(workspace)))

    def test_a_missing_workspace_does_not_fall_back_to_the_process_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            missing = os.path.join(parent, "gone")
            root = os.path.abspath(ve._attach_root(missing))
            cwd = os.path.abspath(os.getcwd()) + os.sep
            self.assertFalse(root.startswith(cwd),
                             f"temp files land next to the running app: {root}")

    def test_the_fallback_is_the_os_temp_directory(self):
        for workspace in (None, "", os.path.join(tempfile.gettempdir(), "yok-boyle-bir-yer")):
            root = os.path.abspath(ve._attach_root(workspace))
            self.assertTrue(root.startswith(os.path.abspath(tempfile.gettempdir())),
                            f"unexpected fallback for {workspace!r}: {root}")

    def test_a_file_that_is_not_a_directory_is_rejected_too(self):
        # The finding's exact shape: a saved workspace path that still exists
        # but is no longer a directory.
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            root = os.path.abspath(ve._attach_root(path))
            self.assertFalse(root.startswith(os.path.abspath(path)))
            self.assertTrue(root.startswith(os.path.abspath(tempfile.gettempdir())))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
