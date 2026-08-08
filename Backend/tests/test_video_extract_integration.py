import json, os, sys, shutil, subprocess, tempfile, unittest
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
            leftover = os.path.join(td, ".gamachine_tmp", "video")
            self.assertTrue(not os.path.isdir(leftover) or not os.listdir(leftover))

    def test_missing_path_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(Exception):
                ve.extract({"kind": "path", "path": os.path.join(td, "yok.mp4")}, td, "test")


class TestSpawnOrtami(unittest.TestCase):
    """`_run` ffmpeg/yt-dlp'yi backend'in ortamıyla BAŞLATMAMALI.

    Dış denetim 2026-07-29: bu iki spawn `env=` almadan çalışıyordu, yani
    çocuklar `LOCAL_APP_TOKEN` (backend'in tek yetki kanıtı) ve
    `API_KEY_ENCRYPTION_KEY` (kullanıcı API anahtarlarının şifreleme anahtarı)
    dahil ebeveynin TAMAMINI görüyordu. Kapı testindeki muafiyetin gerekçesi
    "sabit argv, vendor anahtarı TÜKETMİYOR" idi; bu yanlış türden bir gerekçe —
    tüketmemek almayı engellemiyor ve yt-dlp ağa çıkan üçüncü taraf bir araç.

    Test hem sızıntıyı hem de kırılma yönünü ölçüyor: env'i fazla kısmak
    ffmpeg/yt-dlp'yi SESSİZCE bozar (PATH'siz alt-ikili bulunamaz, HOME'suz
    yt-dlp config/cache dizinini kaybeder), o yüzden PATH ve HOME'un GEÇTİĞİ de
    aynı çağrıda ölçülüyor.
    """

    _CANARY = {
        "LOCAL_APP_TOKEN": "video-canary-local-token",
        "API_KEY_ENCRYPTION_KEY": "video-canary-db-key",
        "ANTHROPIC_API_KEY": "video-canary-anthropic",
        "OPENAI_API_KEY": "video-canary-openai",
    }

    def _child_env(self) -> dict:
        """`_run`'ı gerçek bir alt süreçle sürer ve çocuğun gördüğü ortamı döner."""
        eski = {k: os.environ.get(k) for k in self._CANARY}
        os.environ.update(self._CANARY)
        try:
            r = ve._run(
                [sys.executable, "-c", "import json,os;print(json.dumps(dict(os.environ)))"],
                timeout=30)
        finally:
            for k, v in eski.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        return json.loads((r.stdout or b"").decode("utf-8", "replace"))

    def test_child_does_not_inherit_backend_secrets(self):
        child = self._child_env()
        sizan = sorted(k for k in self._CANARY if k in child)
        self.assertEqual(sizan, [], f"ffmpeg/yt-dlp çocuğuna sır sızıyor: {sizan}")

    def test_child_still_gets_the_names_the_media_binaries_need(self):
        child = self._child_env()
        # PATH: yt-dlp birleştirme için ffmpeg'i PATH'ten arıyor (ayrıca frozen
        # olmayan kurulumda ikililerin kendisi de PATH'ten çözülüyor).
        # HOME: yt-dlp'nin config/cache dizini (~/.config/yt-dlp, ~/.cache/yt-dlp).
        for ad in ("PATH", "HOME"):
            if ad in os.environ:
                self.assertIn(ad, child, f"{ad} kesilmiş — medya ikilileri sessizce bozulur")


if __name__ == "__main__":
    unittest.main()
