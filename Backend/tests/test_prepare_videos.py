import os, sys, asyncio, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from agentic.agent_runner import AgentRunner
import providers.video_extract as ve


def _runner(videos):
    return AgentRunner(provider_type="google", api_key="k", model_name="gemini",
                       workspace_path=".", videos=videos,
                       images=["data:image/png;base64,AAAA"])


class TestPrepareVideos(unittest.TestCase):
    def test_appends_frames_and_block(self):
        def fake_extract(src, ws, tag):
            return ve.ExtractResult(
                ["data:image/jpeg;base64,BBBB", "data:image/jpeg;base64,CCCC"],
                "[00:00:01] selam",
                {"name": "c.mp4", "duration_s": 5, "frame_count": 2, "dropped": 0})
        with mock.patch.object(ve, "extract", fake_extract):
            r = _runner([{"kind": "path", "path": "c.mp4"}])
            msg = asyncio.run(r._prepare_videos("orijinal mesaj"))
        self.assertEqual(len(r.images), 3)                       # 1 mevcut + 2 kare
        self.assertEqual(r.images[-1], "data:image/jpeg;base64,CCCC")
        self.assertIn("[VİDEO]", msg)
        self.assertIn("orijinal mesaj", msg)
        self.assertIn("selam", msg)

    def test_noop_without_videos(self):
        r = _runner(None)
        msg = asyncio.run(r._prepare_videos("x"))
        self.assertEqual(msg, "x")
        self.assertEqual(len(r.images), 1)

    def test_extract_error_is_soft(self):
        def boom(src, ws, tag):
            raise RuntimeError("ffmpeg patladı")
        with mock.patch.object(ve, "extract", boom):
            r = _runner([{"kind": "url", "url": "http://x"}])
            msg = asyncio.run(r._prepare_videos("devam"))
        self.assertIn("devam", msg)
        self.assertEqual(len(r.images), 1)                       # çökme yok, kare eklenmez


if __name__ == "__main__":
    unittest.main()
