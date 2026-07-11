import os, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import providers.video_bin as vb


class TestVideoBin(unittest.TestCase):
    def test_path_fallback_when_no_bundle(self):
        # bundle dizini yoksa PATH (shutil.which) kullanılır
        with mock.patch.object(vb, "_candidate_dirs", lambda: []), \
             mock.patch.object(vb.shutil, "which", lambda name: f"/usr/bin/{name}"):
            self.assertEqual(vb.ffmpeg_path(), "/usr/bin/ffmpeg")
            self.assertEqual(vb.ytdlp_path(), "/usr/bin/yt-dlp")

    def test_bundled_dir_wins_over_path(self):
        with tempfile.TemporaryDirectory() as td:
            bin_dir = os.path.join(td, "bin")
            os.makedirs(bin_dir)
            exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            with open(os.path.join(bin_dir, exe), "w") as f:
                f.write("x")
            with mock.patch.object(vb, "_candidate_dirs", lambda: [bin_dir]), \
                 mock.patch.object(vb.shutil, "which", lambda name: "/should/not/be/used"):
                self.assertEqual(vb.ffmpeg_path(), os.path.join(bin_dir, exe))

    def test_meipass_maps_to_bin_subdir(self):
        # _candidate_dirs, sys._MEIPASS altındaki /bin'i döndürmeli
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(vb.sys, "_MEIPASS", td, create=True):
                self.assertIn(os.path.join(td, "bin"), vb._candidate_dirs())


if __name__ == "__main__":
    unittest.main()
