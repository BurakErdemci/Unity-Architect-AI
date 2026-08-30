"""One pasted URL must not be able to spend unbounded disk, memory or context.

External audit, 30 Aug 2026, two findings on the same surface. The only input
to this pipeline is a URL the user pastes into the chat, and the host behind
that URL is the side that chooses how many bytes come back.

  1. The yt-dlp download was bounded ONLY by a 600-second wall clock. No
     `--max-filesize`, and no application-side size check before or during the
     write, so a host that keeps streaming video fills the disk for ten minutes
     and the temp directory is cleaned only afterwards.

  2. The best-effort subtitle file was read with `f.read()` and parsed with no
     cap. A 2 MiB WebVTT was measured going straight into `ExtractResult.
     transcript`, i.e. into the model prompt: one URL paid for the file, the
     decoded string, the `splitlines()` intermediates AND the enlarged request.

Frame count was already capped; these two paths were the ones that were not.
"""
import os
import sys
import builtins
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import providers.video_extract as ve


class _FakeYtDlp:
    """Stands in for `_run`: records argv and writes what a host would send."""

    def __init__(self, video_bytes=b"video", subtitle_text=""):
        self.calls = []
        self.video_bytes = video_bytes
        self.subtitle_text = subtitle_text

    def __call__(self, cmd, timeout, check=True):
        self.calls.append(list(cmd))
        out_tmpl = cmd[cmd.index("-o") + 1]
        if len(self.calls) == 1:
            with open(out_tmpl.replace("%(ext)s", "mp4"), "wb") as f:
                f.write(self.video_bytes)
        elif self.subtitle_text:
            path = os.path.join(os.path.dirname(out_tmpl), "dl.en.vtt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n")
                f.write(self.subtitle_text)
                f.write("\n")
        return SimpleNamespace(stdout=b"", stderr=b"")


def _download(fake):
    with mock.patch.object(ve, "_run", fake), \
            tempfile.TemporaryDirectory() as td:
        return ve._download_url("https://youtube.com/watch?v=bound", td)


class TestDownloadHasAByteBound(unittest.TestCase):
    def test_the_download_command_carries_a_byte_bound(self):
        fake = _FakeYtDlp()
        _download(fake)
        argv = fake.calls[0]
        self.assertIn("--max-filesize", argv)
        self.assertEqual(argv[argv.index("--max-filesize") + 1],
                         str(ve._MAX_DOWNLOAD_BYTES))

    def test_the_bound_is_also_checked_on_our_side(self):
        # `--max-filesize` needs a size the stream announced. A response with no
        # Content-Length gives yt-dlp nothing to compare, which is exactly the
        # shape of the abuse; so the bytes on disk are measured here too.
        fake = _FakeYtDlp(video_bytes=b"x" * 64)
        with mock.patch.object(ve, "_MAX_DOWNLOAD_BYTES", 8):
            with self.assertRaises(RuntimeError) as ctx:
                _download(fake)
        self.assertIn("boyut", str(ctx.exception))

    def test_a_download_inside_the_bound_still_succeeds(self):
        # A cap that also refuses ordinary videos would be a worse bug than the
        # one it fixes.
        video, _transcript, _name = _download(_FakeYtDlp(video_bytes=b"x" * 64))
        self.assertTrue(video.endswith(".mp4"))


class TestSubtitleIsBounded(unittest.TestCase):
    """The read itself must be finite, not just the string that survives it."""

    def _download_with_subtitle(self, text):
        read_sizes = []

        class _Recorder:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def __enter__(self):
                self.wrapped.__enter__()
                return self

            def __exit__(self, *a):
                return self.wrapped.__exit__(*a)

            def read(self, size=-1):
                read_sizes.append(size)
                return self.wrapped.read(size)

        def recording_open(file, mode="r", *a, **kw):
            handle = builtins.open(file, mode, *a, **kw)
            if str(file).endswith(".vtt") and "r" in mode:
                return _Recorder(handle)
            return handle

        fake = _FakeYtDlp(subtitle_text=text)
        had_open = "open" in ve.__dict__
        original = ve.__dict__.get("open")
        ve.open = recording_open
        try:
            _v, transcript, _n = _download(fake)
        finally:
            if had_open:
                ve.open = original
            else:
                ve.__dict__.pop("open", None)
        self.assertTrue(read_sizes, "subtitle read path was not exercised")
        return read_sizes, transcript

    def test_the_subtitle_file_is_never_read_whole(self):
        read_sizes, _ = self._download_with_subtitle("S" * (2 * 1024 * 1024))
        self.assertNotIn(-1, read_sizes)
        self.assertTrue(all(0 < n <= ve._SUBTITLE_CHAR_CAP for n in read_sizes),
                        f"unbounded read size: {read_sizes}")

    def test_the_transcript_that_reaches_the_prompt_is_bounded(self):
        _, transcript = self._download_with_subtitle("S" * (2 * 1024 * 1024))
        self.assertLessEqual(len(transcript), ve._TRANSCRIPT_CHAR_CAP)

    def test_an_ordinary_subtitle_survives_intact(self):
        # The cap must not quietly truncate real transcripts — that would trade
        # a resource bug for a silent quality bug.
        _, transcript = self._download_with_subtitle("merhaba dünya")
        self.assertIn("merhaba dünya", transcript)

    def test_the_two_caps_are_separate_budgets(self):
        # File read protects memory; transcript length protects the model's
        # context. Collapsing them into one number loses one of the two.
        self.assertLess(ve._TRANSCRIPT_CHAR_CAP, ve._SUBTITLE_CHAR_CAP)


if __name__ == "__main__":
    unittest.main()
