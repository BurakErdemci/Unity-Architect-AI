"""Video ikilileri UYGULAMAYLA gelir — çözümleyici depo vendor'ını da görür.

Arıza (Burak, 30 Ağu 2026, sahada): YouTube linki gönderildi, video sessizce
atlandı, mesaj "yt-dlp bu bilgisayarda bulunamadı" dedi. Ölçüldü: yt-dlp
makinede kuruluydu (`~/bin/yt-dlp`) ama o dizin **Windows PATH'inde değildi**,
yani mesaj DOĞRUYDU — eksik olan ikilinin uygulamayla gelmesiydi.

Kökü daha derin ve tamamen sessizdi: indirme script'leri 30 Tem 2026'dan beri
yazılıydı, `backend.spec` onların bıraktığı ikilileri pakete koyuyordu,
`.gitignore` yorumu onları adıyla anıyordu — ama hiçbir şey onları ÇAĞIRMIYORDU
ve çözümleyici de `Backend/vendor/bin/` klasörüne hiç bakmıyordu. Üç parça
hazır, zincir kopuk.

Testler iki şeyi sabitliyor: vendor dizini aday listesinde VAR, ve platform
adı `backend.spec`'in beklediği adla aynı (`win` / `mac` / `linux`). İkincisi
mac desteği için kritik: ad kayarsa paketleme sessizce boş bundle üretir.
"""
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from providers import video_bin


def test_the_repo_vendor_dir_is_among_the_candidates():
    adaylar = [os.path.normpath(d) for d in video_bin._candidate_dirs()]
    assert os.path.normpath(video_bin._vendor_dir()) in adaylar


def test_the_bundle_wins_over_the_repo_vendor_dir():
    """Paketlenmiş kopyanın kendi ikilisi önce gelmeli.

    Sıra bozulursa frozen bir uygulama, geliştirme makinesinde kalmış bir
    ikiliyi tercih edebilirdi — sürümü bilinmeyen bir ffmpeg.
    """
    with mock.patch.object(video_bin.sys, "_MEIPASS", "/tmp/meipass", create=True):
        adaylar = video_bin._candidate_dirs()
    assert adaylar[0] == os.path.join("/tmp/meipass", "bin")
    assert os.path.normpath(adaylar[-1]) == os.path.normpath(video_bin._vendor_dir())


@pytest.mark.parametrize("platform,beklenen", [
    ("win32", "win"),
    ("darwin", "mac"),
    ("linux", "linux"),
])
def test_the_platform_folder_matches_what_the_spec_expects(platform, beklenen):
    # `backend.spec` tam bu adları arıyor. Kayarsa paketleme sessizce boş çıkar.
    with mock.patch.object(video_bin.sys, "platform", platform):
        assert os.path.basename(video_bin._vendor_dir()) == beklenen


def test_the_vendor_dir_sits_under_backend():
    yol = video_bin._vendor_dir().replace("\\", "/")
    assert "/Backend/vendor/bin/" in yol


def test_a_binary_in_the_vendor_dir_is_found_without_touching_PATH(tmp_path):
    """Asıl iddia: PATH boş olsa bile vendor'daki ikili bulunuyor."""
    sahte = tmp_path / "yt-dlp.exe"
    sahte.write_bytes(b"x")
    with mock.patch.object(video_bin, "_candidate_dirs", lambda: [str(tmp_path)]), \
         mock.patch.object(video_bin.shutil, "which", lambda _n: None):
        assert video_bin._find("yt-dlp", "yt-dlp.exe") == str(sahte)
        assert video_bin.missing_binaries(need_ytdlp=True) == ["ffmpeg"]


def test_a_missing_binary_is_still_reported_as_missing(tmp_path):
    # Kapının ters yönü: bulunamayan gerçekten bulunamadı denmeli, yoksa
    # yukarıdaki test bir şey ölçmüyor olurdu.
    with mock.patch.object(video_bin, "_candidate_dirs", lambda: [str(tmp_path)]), \
         mock.patch.object(video_bin.shutil, "which", lambda _n: None):
        assert set(video_bin.missing_binaries(need_ytdlp=True)) == {"ffmpeg", "yt-dlp"}
