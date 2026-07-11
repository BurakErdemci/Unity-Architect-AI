import os, sys, shutil, subprocess, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import providers.video_extract as ve

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _make_sample(path):
    # 2 sn, değişen test videosu (ffmpeg testsrc)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True, timeout=60)


@unittest.skipUnless(_HAS_FFMPEG, "ffmpeg PATH'te yok")
class TestExtractIntegration(unittest.TestCase):
    def test_local_path_produces_frames(self):
        with tempfile.TemporaryDirectory() as td:
            vid = os.path.join(td, "sample.mp4")
            _make_sample(vid)
            res = ve.extract({"kind": "path", "path": vid}, td, "test")
            self.assertTrue(res.frame_data_uris, "en az bir kare üretilmeli")
            self.assertTrue(all(u.startswith("data:image/jpeg;base64,")
                                for u in res.frame_data_uris))
            self.assertEqual(res.meta["frame_count"], len(res.frame_data_uris))
            # extract kendi temp'ini sildi mi
            leftover = os.path.join(td, ".unity_architect_tmp", "video")
            self.assertTrue(not os.path.isdir(leftover) or not os.listdir(leftover))

    def test_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(Exception):
                ve.extract({"kind": "path", "path": os.path.join(td, "yok.mp4")}, td, "test")


if __name__ == "__main__":
    unittest.main()
