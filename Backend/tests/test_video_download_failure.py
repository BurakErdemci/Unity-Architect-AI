"""Video indirme: ses indirilmez, sebep kayda geçer, sebep kullanıcıya SIZMAZ.

Arıza (Burak, 30 Ağu 2026, sahada): bir YouTube Shorts linki sohbete atıldı ve
"Videonun linki indirilemedi" denip video atlandı. Mesaj sebep olarak "link
kapalı, bölgesel kısıtlı ya da ağ engelli" diyordu — ÜÇÜ DE DEĞİLDİ.

Elle yeniden üretildi: görüntü akışı sorunsuz indi, YouTube SES akışına
`HTTP Error 403: Forbidden` döndü, yt-dlp exit 1 verdi. Yani boru hattı hiç
kullanmadığı bir veriyi indirmeye çalışırken bütün videoyu kaybediyordu —
kareler görüntüden, transkript altyazıdan geliyor; sese dokunan tek satır
format seçicinin kendisiydi. `+bestaudio` düşünce iki ayrı URL'de de düzeldi.

Teşhis edilemezliğin kendisi ikinci arızaydı: `_run` stderr'i yakalayıp
atıyordu ve `CalledProcessError`'ın metni yalnız "returned non-zero exit
status 1" diyor, yani kayıtta argv'den başka bir şey yoktu. Sebep aracın
elindeydi ve çöpe gidiyordu.
"""
import os
import re
import sys
import subprocess
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import providers.video_extract as ve


def _yt_dlp_argv(monkey_calls):
    for cmd in monkey_calls:
        if "yt-dlp" in str(cmd[0]).lower():
            return cmd
    raise AssertionError(f"yt-dlp çağrısı yok: {monkey_calls}")


class TestSesIndirilmiyor(unittest.TestCase):
    """Format seçici sesi İSTEMEMELİ — 403'ü veren akış oydu ve kullanılmıyor."""

    def setUp(self):
        self.calls = []
        self._orig = ve._run

        def fake_run(cmd, timeout, check=True):
            self.calls.append(cmd)
            raise subprocess.CalledProcessError(1, cmd, output=b"", stderr=b"bitti")

        ve._run = fake_run
        self.addCleanup(lambda: setattr(ve, "_run", self._orig))

    def _format_arg(self):
        with self.assertRaises(Exception):
            ve._download_url("https://example.com/v", "/tmp/x")
        cmd = _yt_dlp_argv(self.calls)
        return cmd[cmd.index("-f") + 1]

    def test_no_audio_stream_is_requested(self):
        self.assertNotIn("bestaudio", self._format_arg())

    def test_no_merge_syntax_remains(self):
        # '+' ayrı akışları BİRLEŞTİR demek; kalırsa ses geri gelmiş demektir
        # ve ffmpeg birleştirme adımı da geri gelir.
        self.assertNotIn("+", self._format_arg())

    def test_both_orientations_still_covered(self):
        # Dikey Shorts height=1920/width=1080; yatay video height<=1080.
        # Biri düşerse o yönelim tamamen indirilemez hale gelir.
        f = self._format_arg()
        self.assertIn("height<=1080", f)
        self.assertIn("width<=1080", f)

    def test_a_last_resort_fallback_remains(self):
        # Yalnız video-akışı sunmayan siteler var; zincirin sonunda çıplak
        # 'best' kalmazsa onlar hiç indirilemez.
        self.assertTrue(self._format_arg().endswith("best"))


class TestSebepKaydaGeciyor(unittest.TestCase):
    def test_the_tools_own_stderr_reaches_the_detail(self):
        e = subprocess.CalledProcessError(
            1, ["yt-dlp"], stderr=b"[download] 50%\nERROR: unable to download video data: "
                                  b"HTTP Error 403: Forbidden\n")
        d = ve._tool_error_detail(e)
        self.assertIn("403", d)
        self.assertIn("CalledProcessError", d)

    def test_only_the_tail_is_kept(self):
        # yt-dlp parça başına bir ilerleme satırı basıyor; tamamı kayda
        # girerse sebep binlerce satırın içinde kaybolur.
        gurultu = b"\n".join(b"[download] %d%%" % i for i in range(500))
        e = subprocess.CalledProcessError(1, ["yt-dlp"], stderr=gurultu + b"\nERROR: son sebep")
        d = ve._tool_error_detail(e)
        self.assertIn("son sebep", d)
        self.assertLess(len(d), 900)

    def test_an_exception_without_stderr_adds_nothing(self):
        d = ve._tool_error_detail(ValueError("kötü url"))
        self.assertIn("ValueError", d)
        self.assertNotIn("stderr", d)

    def test_bytes_and_str_stderr_behave_the_same(self):
        a = subprocess.CalledProcessError(1, ["x"], stderr=b"ERROR: ayni")
        b = subprocess.CalledProcessError(1, ["x"], stderr="ERROR: ayni")
        self.assertIn("ayni", ve._tool_error_detail(a))
        self.assertIn("ayni", ve._tool_error_detail(b))


class TestSebepKullaniciyaSizmiyor(unittest.TestCase):
    """KAPI: stderr kayda serbest, kullanıcıya YASAK.

    yt-dlp stderr'ine hedef URL'yi (query string'iyle — bir paylaşım linkindeki
    erişim jetonu dahil), çıktı şablonunu ve dolayısıyla çalışma alanı yolunu
    basıyor. `detail` artık bunu taşıyor, yani `client_detail`'in filtresi
    ilk kez GERÇEK bir sırrın önünde duruyor; önce yalnız argv'yi kesiyordu.
    """

    def _client_detail(self, stderr: bytes) -> str:
        e = subprocess.CalledProcessError(1, ["yt-dlp"], stderr=stderr)
        err = ve.VideoPipelineError("video_download_failed", "mesaj",
                                    stage="indirme", detail=ve._tool_error_detail(e))
        return err.client_detail

    def test_the_url_in_stderr_does_not_reach_the_client(self):
        cd = self._client_detail(b"ERROR: https://x.com/v?token=GIZLI reddedildi")
        self.assertNotIn("GIZLI", cd)
        self.assertNotIn("x.com", cd)

    def test_the_home_directory_in_stderr_does_not_reach_the_client(self):
        cd = self._client_detail(rb"ERROR: C:\Users\burcu\gizli\dl.mp4 yazilamadi")
        self.assertNotIn("burcu", cd)

    def test_the_client_still_learns_stage_and_kind(self):
        # Kapı, mesajı boşaltarak "güvenli" olmamalı: kullanıcı hangi aşamada
        # ne tür bir hata olduğunu görmeye devam etmeli.
        cd = self._client_detail(b"ERROR: HTTP Error 403: Forbidden")
        self.assertIn("indirme", cd)
        self.assertIn("CalledProcessError", cd)


class TestSebebeGoreMesaj(unittest.TestCase):
    def test_a_refusal_is_named_a_refusal(self):
        m = ve.download_failure_message("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        self.assertIn("403", m)
        # Eski mesaj bunu "link kapalı" sanıyordu; yanlış tavsiye veriyordu.
        self.assertNotIn("link kapalı", m)

    def test_a_private_video_is_named(self):
        self.assertIn("özel", ve.download_failure_message("ERROR: Private video. Sign in..."))

    def test_a_geo_block_is_named(self):
        m = ve.download_failure_message("ERROR: The uploader has not made this video available in your country")
        self.assertIn("ülkeden", m)

    def test_an_unknown_reason_keeps_the_honest_vague_message(self):
        # Sebep bilinmiyorsa uydurma: yanlış bir kesin sebep, dürüst bir
        # belirsizlikten kötü.
        m = ve.download_failure_message("ERROR: bilinmeyen bir sey oldu")
        self.assertIn("link kapalı", m)

    def test_empty_stderr_is_not_read_as_a_reason(self):
        self.assertEqual(ve.download_failure_message(""),
                         ve.download_failure_message("baska bir sey"))

    def test_every_message_says_the_chat_continues(self):
        # Ürün sözü: video düşse bile sohbet ölmüyor. Mesajlardan biri bunu
        # söylemezse kullanıcı turun bittiğini sanır.
        for s in ["403 Forbidden", "Private video", "not available in your country", "?"]:
            self.assertIn("sohbet metinle sürüyor", ve.download_failure_message(s))


class TestBaglanti(unittest.TestCase):
    """Yol gerçekten bu fonksiyonlardan geçiyor mu — birim testler tek başına
    'kod var' der, 'kod çağrılıyor' demez."""

    def test_a_403_download_produces_the_refusal_message_end_to_end(self):
        orig = ve._run

        def fake_run(cmd, timeout, check=True):
            raise subprocess.CalledProcessError(
                1, cmd, stderr=b"ERROR: unable to download video data: HTTP Error 403: Forbidden")

        ve._run = fake_run
        self.addCleanup(lambda: setattr(ve, "_run", orig))
        with self.assertRaises(ve.VideoPipelineError) as ctx:
            ve.extract({"kind": "url", "url": "https://www.youtube.com/shorts/abc"}, ".", "tag")
        err = ctx.exception
        self.assertEqual(err.code, "video_download_failed")
        self.assertIn("403", err.message)
        self.assertIn("403", err.detail)          # kayıt sebebi görüyor
        self.assertNotIn("403", err.client_detail)  # kullanıcı ham metni görmüyor


if __name__ == "__main__":
    unittest.main()
