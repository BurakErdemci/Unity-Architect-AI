import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from schemas import ChatRequest


class TestChatRequestVideos(unittest.TestCase):
    def test_accepts_videos(self):
        r = ChatRequest(conversation_id=1, message="m", user_id=1,
                        videos=[{"kind": "path", "path": "c.mp4"},
                                {"kind": "url", "url": "http://x"}])
        self.assertEqual(r.videos[0]["kind"], "path")
        self.assertEqual(r.videos[1]["url"], "http://x")

    def test_videos_default_none(self):
        r = ChatRequest(conversation_id=1, message="m", user_id=1)
        self.assertIsNone(r.videos)


if __name__ == "__main__":
    unittest.main()
