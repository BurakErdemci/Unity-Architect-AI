import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import providers.video_extract as ve


class TestBudgetFps(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(ve.budget_fps(10), (1.0, 60))
        self.assertEqual(ve.budget_fps(120), (0.5, 60))
        self.assertEqual(ve.budget_fps(400), (0.2, 60))
        fps, cap = ve.budget_fps(6000)
        self.assertEqual(cap, 60)
        self.assertTrue(0.0 < fps <= 0.05 + 1e-9)


class TestParseVtt(unittest.TestCase):
    def test_basic(self):
        vtt = ("WEBVTT\n\n"
               "00:00:01.000 --> 00:00:03.000\n"
               "Merhaba dünya\n\n"
               "00:00:03.000 --> 00:00:05.000\n"
               "<c>Merhaba dünya</c>\n\n"   # duplike + tag → temizlenip elenmeli
               "00:00:05.000 --> 00:00:07.000\n"
               "İkinci cümle\n")
        out = ve.parse_vtt(vtt)
        self.assertIn("[00:00:01] Merhaba dünya", out)
        self.assertIn("[00:00:05] İkinci cümle", out)
        self.assertEqual(out.count("Merhaba dünya"), 1)   # duplike elendi

    def test_empty(self):
        self.assertEqual(ve.parse_vtt(""), "")


class TestDedup(unittest.TestCase):
    def test_drops_near_duplicates(self):
        a = bytes([10] * 256)
        a2 = bytes([11] * 256)   # a'ya çok yakın (MAD=1 < 2) → düşer
        b = bytes([200] * 256)   # farklı → tutulur
        self.assertEqual(ve.dedup_indices([a, a2, b], threshold=2.0), [0, 2])


class TestEncodeAndBlock(unittest.TestCase):
    def test_frames_to_data_uris(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "f.jpg")
            with open(p, "wb") as f:
                f.write(b"\xff\xd8\xff\xe0jpeg-bytes")
            uris = ve.frames_to_data_uris([p, os.path.join(td, "yok.jpg")])
            self.assertEqual(len(uris), 1)
            self.assertTrue(uris[0].startswith("data:image/jpeg;base64,"))

    def test_build_video_block(self):
        block = ve.build_video_block(
            {"name": "clip.mp4", "duration_s": 42, "frame_count": 12, "dropped": 3},
            "[00:00:01] merhaba")
        self.assertIn("[VİDEO]", block)
        self.assertIn("clip.mp4", block)
        self.assertIn("12 kare", block)
        self.assertIn("3", block)
        self.assertIn("[VİDEO TRANSKRİPTİ]", block)
        self.assertIn("merhaba", block)


class TestDetectVideoUrls(unittest.TestCase):
    def test_finds_youtube_shorts(self):
        urls = ve.detect_video_urls("şu videoya bak https://www.youtube.com/shorts/8b5ZrNGAntc süper")
        self.assertEqual(urls, ["https://www.youtube.com/shorts/8b5ZrNGAntc"])

    def test_ignores_non_video_hosts(self):
        self.assertEqual(ve.detect_video_urls("bak https://github.com/foo/bar dokümanı"), [])

    def test_youtu_be_and_dedup(self):
        urls = ve.detect_video_urls("https://youtu.be/abc123 ve yine https://youtu.be/abc123.")
        self.assertEqual(urls, ["https://youtu.be/abc123"])

    def test_empty(self):
        self.assertEqual(ve.detect_video_urls(""), [])


if __name__ == "__main__":
    unittest.main()
