"""C# zekasının çalışma zamanı ortamını koruyan testler.

Hangi arızadan doğdu (2026-07-27): C# hover isteği ~120 saniye asılıp tarayıcıda
"Failed to fetch" ile düşüyordu. Kök neden, gömülü yükün .NET **SDK** değil
.NET **runtime** olmasıydı: OmniSharp proje yüklemek için MSBuild'i SDK'dan
çözüyor, çözemeyince `initialize` isteğine NE result NE error frame'i gönderiyor
ve süreci de kapatmıyor — yani tek geri bildirim uzun bir sessizlik oluyordu.

Bu dosya iki yüzeyi birlikte koruyor:
  1. Gömülü .NET ağacının SDK olduğunun doğrulanması (host'un varlığı yetmez),
  2. O ortam kurulamadığında ürünün ASILMADAN, sebebini söyleyerek düşmesi.

Kapı iki yönden de sınanıyor: eksik SDK reddedilmeli AMA sağlam kurulum
kabul edilmeli, ve sistemde .NET varken ürün "yok" diye erken pes etmemeli.
Bu projede kapıların yalnız "çok dar değil" yönü sınandığı için üç ayrı arıza
üretildi; buradaki her testin karşıt yönü de yazılı.
"""
import asyncio
import os

import pytest

from app.omnisharp import omnisharp_manager as om


def _make_dotnet_tree(root: str, plat: str, *, with_sdk: bool, sdk_empty: bool = False) -> str:
    """Gömülü .NET ağacının taklidi. `with_sdk=False` tam olarak 27 Tem 2026'daki
    bozuk kurulumu üretir: `dotnet` host'u var, `sdk/` yok."""
    dest = os.path.join(root, f"dotnet-{plat}")
    os.makedirs(dest, exist_ok=True)
    exe = "dotnet.exe" if plat.startswith("win") else "dotnet"
    with open(os.path.join(dest, exe), "w") as f:
        f.write("")
    if with_sdk:
        sdk = os.path.join(dest, "sdk")
        os.makedirs(sdk, exist_ok=True)
        if not sdk_empty:
            os.makedirs(os.path.join(sdk, "10.0.100"), exist_ok=True)
    return dest


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """`_omnisharp_roots` yerine tek geçici kök koy — gerçek third_party ağacı
    testin sonucunu belirlemesin (makinede SDK varsa testler yalancı yeşil olur)."""
    root = str(tmp_path)
    monkeypatch.setattr(om, "_omnisharp_roots", lambda: [root])
    return root


class TestGomuluSdkDogrulamasi:
    def test_a_runtime_only_tree_is_rejected_even_though_the_dotnet_host_exists(
        self, fake_root, monkeypatch
    ):
        """27 Tem 2026 arızasının birebir kendisi: .NET runtime paketi de `dotnet`
        host'unu getiriyor, yani host'un varlığı SDK olduğunu KANITLAMIYOR. Bu test
        kırılırsa 120 saniyelik asılma geri gelmiş demektir."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        _make_dotnet_tree(fake_root, "osx-arm64", with_sdk=False)
        assert om._embedded_dotnet_root() is None

    def test_a_tree_with_a_populated_sdk_directory_is_accepted(self, fake_root, monkeypatch):
        """Karşıt yön: kapı çok GENİŞ olmamalı ama çok DAR da olmamalı — sağlam
        kurulum reddedilirse C# zekası hiç çalışmaz."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        expected = _make_dotnet_tree(fake_root, "osx-arm64", with_sdk=True)
        assert om._embedded_dotnet_root() == expected

    def test_an_sdk_directory_that_exists_but_is_empty_is_rejected(self, fake_root, monkeypatch):
        """Yarıda kesilmiş bir çıkarma boş `sdk/` bırakabiliyor; klasörün VARLIĞI
        değil İÇERİĞİ kanıt."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        _make_dotnet_tree(fake_root, "osx-arm64", with_sdk=True, sdk_empty=True)
        assert om._embedded_dotnet_root() is None

    def test_windows_resolves_the_embedded_sdk_through_the_same_code_path_as_macos(
        self, fake_root, monkeypatch
    ):
        """Windows eskiden `_spawn_env` içinde erkenden `None` dönüp bu mekanizmayı
        tamamen atlıyordu ("net472 → runtime gerekmez"); bu .NET Framework için
        doğru ama MSBuild için yanlıştı. Windows ürünün ANA kitlesi ve macOS'tan
        sınanamıyor — tek yol iki platformu aynı kod yolunda tutmak."""
        monkeypatch.setattr(om, "_platform_key", lambda: "win-x64")
        expected = _make_dotnet_tree(fake_root, "win-x64", with_sdk=True)
        assert om._embedded_dotnet_root() == expected


class TestSpawnOrtami:
    def test_the_spawn_environment_pins_dotnet_root_and_puts_it_on_path(
        self, fake_root, monkeypatch
    ):
        """DOTNET_ROOT tek başına yetmiyor: OmniSharp MSBuild'i Microsoft.Build.Locator
        ile çözerken `dotnet` komutunu ÇALIŞTIRIYOR, o da PATH'ten aranıyor."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        root = _make_dotnet_tree(fake_root, "osx-arm64", with_sdk=True)
        env = om._spawn_env()
        assert env is not None
        assert env["DOTNET_ROOT"] == root
        assert env["DOTNET_ROLL_FORWARD"] == "Major"
        assert env["PATH"].split(os.pathsep)[0] == root

    def test_without_an_embedded_sdk_the_environment_is_left_untouched(
        self, fake_root, monkeypatch
    ):
        """Gömülü SDK yoksa sistemdeki .NET'i BOZMA: kendi (eksik) kökümüzü
        dayatmak, makinede çalışan bir kurulumu da çalışmaz hale getirirdi."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        assert om._spawn_env() is None


class TestSdkYokkenDavranis:
    def test_a_machine_with_no_dotnet_at_all_gets_a_reason_instead_of_a_long_hang(
        self, fake_root, monkeypatch
    ):
        """Ön kontrolün varlık sebebi: SDK yokken OmniSharp `initialize`'a hiç yanıt
        vermiyor, yani tek geri bildirim timeout oluyor. Anında ve sebebiyle düşmek
        şart; mesaj kullanıcıya ne yapacağını söylemeli."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        monkeypatch.setattr(om.shutil, "which", lambda _name: None)
        reason = om._dotnet_missing_reason()
        assert reason is not None
        assert ".NET SDK" in reason

    def test_a_system_dotnet_is_enough_to_stop_us_from_refusing_early(
        self, fake_root, monkeypatch
    ):
        """Karşıt yön: gömülü SDK yok ama makinede .NET varsa denemeden pes etme —
        aksi halde geliştirici makinelerinde çalışan kurulum reddedilirdi."""
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        monkeypatch.setattr(om.shutil, "which", lambda _name: "/usr/local/bin/dotnet")
        assert om._dotnet_missing_reason() is None

    def test_an_embedded_sdk_makes_the_preflight_pass_without_consulting_the_system(
        self, fake_root, monkeypatch
    ):
        monkeypatch.setattr(om, "_platform_key", lambda: "osx-arm64")
        _make_dotnet_tree(fake_root, "osx-arm64", with_sdk=True)
        monkeypatch.setattr(om.shutil, "which", lambda _name: None)
        assert om._dotnet_missing_reason() is None


class TestSunucuYokkenUcNoktalar:
    """OmniSharp hiç başlamadığında `_client` None kalıyor. Bu üç uç eskiden
    doğrudan `self._client.request(...)` çağırıyordu → `AttributeError` handler'dan
    dışarı çıkıyor, CORSMiddleware'in ALTINDAKİ katmanda 500'e dönüşüyor ve o
    yanıtta Access-Control-Allow-Origin olmadığı için tarayıcı "Failed to fetch"
    gösteriyordu. Yani kullanıcının gördüğü mesaj gerçek sebebi tamamen gizliyordu."""

    def test_hover_returns_nothing_instead_of_raising_when_the_server_never_started(self):
        mgr = om.OmniSharpManager()
        assert asyncio.run(mgr.hover("/x/A.cs", "class A {}", 1, 1)) is None

    def test_completion_returns_an_empty_list_instead_of_raising(self):
        mgr = om.OmniSharpManager()
        assert asyncio.run(mgr.completion("/x/A.cs", "class A {}", 1, 1)) == []

    def test_definition_returns_nothing_instead_of_raising(self):
        mgr = om.OmniSharpManager()
        assert asyncio.run(mgr.definition("/x/A.cs", "class A {}", 1, 1)) is None


class TestBasarisizBaslatmaninTekrari:
    def test_a_failed_start_is_not_retried_on_every_single_request(self, monkeypatch):
        """Monaco hover/completion her imleç hareketinde istek üretiyor ve hepsi
        `ensure_started`'ın kilidinden geçiyor. Başarısız başlatma her istekte
        tekrarlanırsa kuyruk büyüyor ve editör tümden donuyor — soğuma penceresi
        tam olarak bunu engelliyor."""
        mgr = om.OmniSharpManager()
        calls = []
        monkeypatch.setattr(om, "_resolve_binary", lambda: (calls.append(1), "/bin/false")[1])
        monkeypatch.setattr(om, "_dotnet_missing_reason", lambda: "SDK yok")

        async def run_twice():
            await mgr.ensure_started("/ws")
            await mgr.ensure_started("/ws")

        asyncio.run(run_twice())
        assert len(calls) == 1, "başarısız başlatma her istekte yeniden denendi"
        assert mgr.status["state"] == "error"
        assert mgr.status["detail"] == "SDK yok"

    def test_a_different_workspace_still_gets_a_fresh_attempt_during_the_cooldown(
        self, monkeypatch
    ):
        """Karşıt yön: soğuma penceresi çok GENİŞ olmamalı. Kullanıcı başka bir
        projeye geçtiğinde eski arızanın onu 30 saniye rehin alması yanlış olurdu."""
        mgr = om.OmniSharpManager()
        calls = []
        monkeypatch.setattr(om, "_resolve_binary", lambda: (calls.append(1), "/bin/false")[1])
        monkeypatch.setattr(om, "_dotnet_missing_reason", lambda: "SDK yok")

        async def run_two_workspaces():
            await mgr.ensure_started("/ws-a")
            await mgr.ensure_started("/ws-b")

        asyncio.run(run_two_workspaces())
        assert len(calls) == 2
