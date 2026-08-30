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

    def test_missing_binaries_names_what_is_missing(self):
        # `_resolve` falling back to the bare name made "found" and "not found"
        # indistinguishable; `missing_binaries` is exactly that distinction.
        with mock.patch.object(vb, "_candidate_dirs", lambda: []), \
             mock.patch.object(vb.shutil, "which", lambda name: None):
            self.assertEqual(vb.missing_binaries(need_ytdlp=True), ["ffmpeg", "yt-dlp"])
            self.assertEqual(vb.missing_binaries(need_ytdlp=False), ["ffmpeg"])

    def test_missing_binaries_empty_when_all_resolve(self):
        with mock.patch.object(vb, "_candidate_dirs", lambda: []), \
             mock.patch.object(vb.shutil, "which", lambda name: f"/usr/bin/{name}"):
            self.assertEqual(vb.missing_binaries(need_ytdlp=True), [])

    def test_extract_names_the_missing_binary_instead_of_dying_in_subprocess(self):
        import providers.video_extract as ve
        with mock.patch.object(ve, "missing_binaries", lambda need_ytdlp: ["yt-dlp"]):
            with self.assertRaises(ve.VideoPipelineError) as cm:
                ve.extract({"kind": "url", "url": "https://youtu.be/x"}, None, "t")
        self.assertEqual(cm.exception.code, "video_binary_missing")
        self.assertIn("yt-dlp", cm.exception.message)

    def test_meipass_maps_to_bin_subdir(self):
        # _candidate_dirs, sys._MEIPASS altındaki /bin'i döndürmeli
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(vb.sys, "_MEIPASS", td, create=True):
                self.assertIn(os.path.join(td, "bin"), vb._candidate_dirs())


if __name__ == "__main__":
    unittest.main()
