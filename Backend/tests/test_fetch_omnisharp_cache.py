"""İndirilen OmniSharp / .NET SDK ağacının "güncel" sayılma kuralını koruyan testler.

Hangi arızadan doğdu: bu repoda "damga dosyası varsa atla" deseni İKİ ayrı
denetimde arıza üretti — bir kere derleme cache'i eski build'i güncel damgalayıp
günün tüm güvenlik işini sessizce devre dışı bıraktı, bir kere de Monaco kopyası
eksik kaldığı halde güncel sayıldı. Buradaki üçüncü örnek en pahalısıydı:
`.version` damgası doğruyken gömülü .NET ağacı SDK içermiyordu ve C# hover
120 saniye asılıyordu.

Korunan kural: **damga tek başına kanıt değil; hedefin içine bakılmalı.**
Kapı iki yönden de sınanıyor — bozuk ağaç reddedilmeli AMA sağlam ağaç
gereksiz yere yeniden indirilmemeli (indirme 220-290 MB).
"""
import importlib.util
import os

import pytest

_SPEC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "fetch_omnisharp.py",
)


@pytest.fixture(scope="module")
def fetch_mod():
    """scripts/ bir paket değil — dosyayı yolundan yükle. Testin bu dosyayı
    bulamaması da bir bulgudur, o yüzden atlanmıyor, patlıyor."""
    assert os.path.isfile(_SPEC_PATH), f"beklenen script yok: {_SPEC_PATH}"
    spec = importlib.util.spec_from_file_location("fetch_omnisharp", _SPEC_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_stamp(dest: str, value: str) -> None:
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, ".version"), "w", encoding="utf-8") as f:
        f.write(value)


class TestDamgaTekBasinaYetmez:
    def test_a_correct_stamp_is_rejected_when_the_expected_files_are_missing(
        self, fetch_mod, tmp_path
    ):
        """27 Tem 2026 arızasının indirme tarafındaki yüzü: damga "10.0.100" diyor
        ama ağaçta `sdk/` yok. Eski kod bunu "zaten güncel — atlandı" diye geçiyordu,
        yani bozuk kurulum kendini onarma şansını da kaybediyordu."""
        dest = str(tmp_path / "dotnet-osx-arm64")
        _write_stamp(dest, "10.0.100")
        with open(os.path.join(dest, "dotnet"), "w") as f:
            f.write("")
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet", "sdk"]) is False

    def test_a_present_but_empty_marker_directory_is_rejected(self, fetch_mod, tmp_path):
        """Yarıda kesilen bir çıkarma boş klasör bırakabiliyor — klasörün VARLIĞI
        değil İÇERİĞİ kanıt."""
        dest = str(tmp_path / "dotnet-osx-arm64")
        _write_stamp(dest, "10.0.100")
        with open(os.path.join(dest, "dotnet"), "w") as f:
            f.write("")
        os.makedirs(os.path.join(dest, "sdk"), exist_ok=True)
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet", "sdk"]) is False

    def test_a_stale_version_stamp_is_rejected_even_when_the_tree_looks_complete(
        self, fetch_mod, tmp_path
    ):
        """Sürüm yükseltmesi kaçırılmasın: ağaç sağlam ama damga eski."""
        dest = str(tmp_path / "dotnet-osx-arm64")
        _write_stamp(dest, "10.0.10")
        with open(os.path.join(dest, "dotnet"), "w") as f:
            f.write("")
        os.makedirs(os.path.join(dest, "sdk", "10.0.100"), exist_ok=True)
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet", "sdk"]) is False

    def test_a_missing_stamp_is_rejected(self, fetch_mod, tmp_path):
        dest = str(tmp_path / "dotnet-osx-arm64")
        os.makedirs(os.path.join(dest, "sdk", "10.0.100"), exist_ok=True)
        with open(os.path.join(dest, "dotnet"), "w") as f:
            f.write("")
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet", "sdk"]) is False


class TestSaglamAgacYenidenIndirilmez:
    def test_a_matching_stamp_with_a_populated_tree_is_accepted(self, fetch_mod, tmp_path):
        """Karşıt yön: kapı çok GENİŞ olmamalı ama çok DAR da olmamalı. Her build'de
        220-290 MB yeniden indirmek, kaçırılan bir bozuk kurulum kadar gerçek bir
        arızadır — sadece daha sessizdir."""
        dest = str(tmp_path / "dotnet-osx-arm64")
        _write_stamp(dest, "10.0.100")
        with open(os.path.join(dest, "dotnet"), "w") as f:
            f.write("")
        os.makedirs(os.path.join(dest, "sdk", "10.0.100"), exist_ok=True)
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet", "sdk"]) is True


class TestPlatformaGoreIsaretler:
    def test_windows_looks_for_the_windows_host_executable(self, fetch_mod):
        assert fetch_mod.dotnet_markers("win-x64")[0] == "dotnet.exe"
        assert fetch_mod.omnisharp_marker("win-x64") == "OmniSharp.exe"

    def test_unix_platforms_look_for_the_extensionless_host(self, fetch_mod):
        assert fetch_mod.dotnet_markers("osx-arm64")[0] == "dotnet"
        assert fetch_mod.omnisharp_marker("osx-arm64") == "OmniSharp"

    def test_every_platform_requires_the_sdk_directory_not_just_the_host(self, fetch_mod):
        """Bu satır, arızanın tekrarını engelleyen tek şey: runtime paketi de host'u
        getiriyor, `sdk` işaretini istemek runtime'ı SDK'dan ayıran fark."""
        for plat in ("win-x64", "osx-arm64", "linux-x64"):
            assert "sdk" in fetch_mod.dotnet_markers(plat)

    def test_every_shipped_platform_has_an_embedded_sdk_asset(self, fetch_mod):
        """Windows eskiden bilerek dışarıda bırakılmıştı ("net472 → runtime
        gerekmez"). MSBuild açısından yanlıştı ve ürünün ANA kitlesi orada."""
        assert set(fetch_mod.DOTNET_ASSETS) == set(fetch_mod.ASSETS)

    def test_the_downloaded_dotnet_asset_is_an_sdk_and_not_a_runtime(self, fetch_mod):
        """URL'nin kendisi bir iddia: /Sdk/ yolundan indirilmeli. Biri bunu tekrar
        /Runtime/'a çevirirse C# zekası sessizce ölür ve semptom yine 120 sn asılma
        olur — o yüzden URL'nin kendisi teste bağlandı."""
        for plat, url in fetch_mod.DOTNET_ASSETS.items():
            assert "/Sdk/" in url, f"{plat}: SDK değil runtime indiriliyor → {url}"
            assert "dotnet-sdk-" in url, f"{plat}: {url}"
