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
import glob
import importlib.util
import io
import os
import tarfile
import time
import zipfile

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


def _sdk_zip(host_body: str) -> bytes:
    """Gerçek .NET SDK zip'inin minik taklidi: host + dolu bir `sdk/` klasörü, yani
    `_intact` gözünde sağlam bir ağaç. `host_body` hangi koşunun kurduğunu ayırt
    etmek için — testler ağın 290 MB'ını değil, KURULUM MEKANİĞİNİ sınıyor."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dotnet.exe", host_body)
        zf.writestr("sdk/10.0.100/Sdk.props", "")
    return buf.getvalue()


def _read(*parts: str) -> str:
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


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


class TestEszamanliKoşularBirbiriniBozmaz:
    """Aynı checkout'ta iki build aynı anda koşabiliyor (CI matrisi, elle başlatılan
    ikinci bir `npm run build`). Sabit `dest + ".staging"` bunu tek bir paylaşılan
    dizine yığıyordu."""

    def test_each_install_run_gets_a_staging_directory_of_its_own(
        self, fetch_mod, tmp_path, monkeypatch
    ):
        """Garantinin kendisi: iki kurulum aynı staging yolunu ASLA paylaşmaz.
        Paylaşırlarsa biri diğerinin ağacını `rmtree` ile siler; bu test o yolu
        adıyla yakalıyor, çünkü ayıklanması en kolay hali bu."""
        dest = str(tmp_path / "dotnet-win-x64")
        seen: list[str] = []
        real_extract = fetch_mod._extract

        def spy(data, url, staging):
            seen.append(staging)
            real_extract(data, url, staging)

        monkeypatch.setattr(fetch_mod, "_extract", spy)
        fetch_mod._install(_sdk_zip("A"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
        fetch_mod._install(_sdk_zip("B"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
        assert seen[0] != seen[1], f"iki koşu aynı staging'i paylaştı: {seen[0]}"
        assert dest + ".staging" not in seen, "sabit staging adı geri gelmiş"

    def test_a_second_install_started_mid_extraction_does_not_destroy_the_first(
        self, fetch_mod, tmp_path, monkeypatch
    ):
        """Çakışmanın canlandırılmış hali: dıştaki koşu tam çıkarmayı bitirmişken
        içerde ikinci bir kurulum baştan sona koşuyor. Eski kodda içteki koşu
        dıştakinin staging'ini siliyordu ve dıştaki `os.replace` FileNotFoundError
        ile patlıyordu; hedefte de içtekinin ağacı kalıyordu."""
        dest = str(tmp_path / "dotnet-win-x64")
        real_extract = fetch_mod._extract
        nested_ran: list[str] = []

        def extract_then_reenter(data, url, staging):
            real_extract(data, url, staging)
            if nested_ran:
                return
            nested_ran.append(staging)
            fetch_mod._install(_sdk_zip("B"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
            assert os.path.isfile(os.path.join(staging, "dotnet.exe")), (
                "ikinci koşu birincinin staging'ini götürdü"
            )

        monkeypatch.setattr(fetch_mod, "_extract", extract_then_reenter)
        fetch_mod._install(_sdk_zip("A"), "x.zip", dest, "10.0.100", ["dotnet.exe"])

        assert nested_ran, "iç içe koşu hiç çalışmadı — test kendini sınamıyor"
        # Son yazan kazanır; kabul edilen budur. Kabul EDİLMEYEN, iki ağacın
        # birbirine karışması ya da kurulumun patlaması.
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet.exe", "sdk"]) is True
        assert _read(dest, "dotnet.exe") == "A"


class TestBasarisizKurulumIzBirakmaz:
    def test_a_failed_install_cleans_up_its_own_staging_directory(
        self, fetch_mod, tmp_path
    ):
        """Ölmüş/patlamış koşunun kalıntısı diskte kalmamalı: dotnet ağacı ~290 MB
        ve eski kod her başarısız çıkarmada bir tane bırakıyordu."""
        dest = str(tmp_path / "dotnet-win-x64")
        with pytest.raises(Exception):
            fetch_mod._install(b"bu bir zip degil", "x.zip", dest, "10.0.100", ["dotnet.exe"])
        assert glob.glob(dest + ".staging*") == []
        assert glob.glob(dest + ".old*") == []

    def test_a_failed_install_leaves_the_previous_working_tree_in_place(
        self, fetch_mod, tmp_path
    ):
        """Bozuk bir indirme çalışan kurulumu götürmemeli. Eski kod hedefi
        `rmtree` ile silip sonra takas ediyordu; bu testin koruduğu şey, silmenin
        artık BAŞARILI takastan sonraya alınmış olması."""
        dest = str(tmp_path / "dotnet-win-x64")
        fetch_mod._install(_sdk_zip("iyi"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
        with pytest.raises(Exception):
            fetch_mod._install(b"bu bir zip degil", "x.zip", dest, "10.0.100", ["dotnet.exe"])
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet.exe", "sdk"]) is True
        assert _read(dest, "dotnet.exe") == "iyi"

    def test_a_swap_that_fails_halfway_puts_the_previous_installation_back(
        self, fetch_mod, tmp_path, monkeypatch
    ):
        """Eski sırada (`rmtree(dest)` → `os.replace`) arada ne eski ne yeni ağacın
        olduğu bir pencere vardı; orada ölen süreç `.version` damgasıyla birlikte
        ÇALIŞAN kurulumu da götürüyordu. Takas artık silme değil rename olduğu için
        geri alınabiliyor. Bu testin `os.replace`'i patlatması, o pencereyi süreç
        öldürmeden gözlemlemenin tek ucuz yolu."""
        dest = str(tmp_path / "dotnet-win-x64")
        fetch_mod._install(_sdk_zip("iyi"), "x.zip", dest, "10.0.100", ["dotnet.exe"])

        def boom(src, dst):
            raise OSError("takas tutmadı")

        monkeypatch.setattr(fetch_mod.os, "replace", boom)
        with pytest.raises(OSError):
            fetch_mod._install(_sdk_zip("yeni"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
        monkeypatch.undo()
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet.exe", "sdk"]) is True
        assert _read(dest, "dotnet.exe") == "iyi"

    def test_a_stale_leftover_is_pruned_but_a_fresh_neighbour_is_left_alone(
        self, fetch_mod, tmp_path
    ):
        """Kalıntı süpürme iki yönlü: eski çöp gitmeli AMA taze bir dizin ŞU AN
        koşan komşu build'in staging'i olabilir — ona dokunmak, düzeltilen arızanın
        ta kendisi olurdu."""
        dest = str(tmp_path / "dotnet-win-x64")
        stale = dest + ".staging-1234-deadbeef"
        fresh = dest + ".staging-5678-cafebabe"
        for d in (stale, fresh):
            os.makedirs(d)
        old = time.time() - fetch_mod._STALE_LEFTOVER_SECONDS - 60
        os.utime(stale, (old, old))

        fetch_mod._install(_sdk_zip("A"), "x.zip", dest, "10.0.100", ["dotnet.exe"])

        assert not os.path.exists(stale), "bayat kalıntı süpürülmedi"
        assert os.path.isdir(fresh), "canlı komşunun staging'i silinmiş"


class TestKurulumSonrasiAgacGuncelSayilir:
    """Düzeltmenin bozmaması gereken yön: `_install` biter bitmez `_intact` "güncel"
    demeli. Demezse her build 220-290 MB'ı yeniden indirir — kaçırılan bozuk kurulum
    kadar gerçek, sadece daha sessiz bir arıza."""

    def test_a_freshly_installed_tree_is_immediately_considered_current(
        self, fetch_mod, tmp_path
    ):
        dest = str(tmp_path / "dotnet-win-x64")
        fetch_mod._install(_sdk_zip("A"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
        assert fetch_mod._intact(dest, "10.0.100", ["dotnet.exe", "sdk"]) is True

    def test_the_version_stamp_ends_up_inside_the_target_and_not_beside_it(
        self, fetch_mod, tmp_path
    ):
        """Damganın yeri dünkü arızanın düzeltmesiydi: hedefin İÇİNDE olmalı, çünkü
        `_intact` oraya bakıyor ve hedefle birlikte atomik takas edilmesi gereken de o."""
        dest = str(tmp_path / "dotnet-win-x64")
        fetch_mod._install(_sdk_zip("A"), "x.zip", dest, "10.0.100", ["dotnet.exe"])
        assert _read(dest, ".version") == "10.0.100"
        assert not os.path.exists(dest + ".version")

    def test_a_sound_installation_is_not_downloaded_a_second_time(
        self, fetch_mod, tmp_path, monkeypatch
    ):
        """Uçtan uca kapı testi: `fetch_dotnet` iki kez koşuyor, indirme BİR kez
        olmalı. Buradaki asıl konu maliyet — win-x64 SDK'sı 290 MB."""
        monkeypatch.setattr(fetch_mod, "DEST", str(tmp_path))
        calls: list[str] = []

        def fake_download(url):
            calls.append(url)
            return _sdk_zip("A")

        monkeypatch.setattr(fetch_mod, "_download", fake_download)
        fetch_mod.fetch_dotnet("win-x64")       # .zip asset'i → ağ yok, bellekten
        fetch_mod.fetch_dotnet("win-x64")
        assert len(calls) == 1, f"ikinci koşu yeniden indirdi: {calls}"
        assert fetch_mod._intact(
            str(tmp_path / "dotnet-win-x64"), fetch_mod.DOTNET_VERSION,
            fetch_mod.dotnet_markers("win-x64"),
        ) is True

class TestArsivHedefinDisinaYazamaz:
    """Arşiv çıkarmanın içerme garantisi.

    Hangi arızadan doğdu (dış denetim, 2026-07-28): `_extract` içinde
    `except TypeError: tf.extractall(staging)` diye bir yedek dal vardı, `filter`
    parametresini tanımayan eski Python'lar için. O dal HİÇBİR içerme kontrolü
    yapmıyordu — gerçek 3.9.6 ile ölçüldü: `../ESCAPED.txt` hedefin dışına yazıldı,
    sembolik bağ + üstüne yazma iki aşamada dışarı çıktı, dizin ve FIFO de öyle.
    Teorik bir yol da değildi: prebuild `python … || python3 …` diyor ve Homebrew
    Python'ı olmayan makinede `python3` stok macOS'un 3.9.6'sı oluyor.

    Kapı iki yönden de sınanıyor: kaçan üye reddedilmeli AMA normal arşiv sorunsuz
    açılmalı — çıkarmayı bozmak 220-290 MB'lık yükü tümden kullanılamaz kılardı.
    """

    @staticmethod
    def _tar_with(members) -> bytes:
        """members: (TarInfo, veri|None) çiftleri."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            for info, data in members:
                tf.addfile(info, io.BytesIO(data) if data is not None else None)
        return buf.getvalue()

    @staticmethod
    def _regular(name: str, data: bytes = b"x"):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        return info, data

    @staticmethod
    def _symlink(name: str, target: str):
        info = tarfile.TarInfo(name)
        info.type = tarfile.SYMTYPE
        info.linkname = target
        return info, None

    def test_a_member_whose_name_climbs_out_of_the_target_is_refused(
        self, fetch_mod, tmp_path
    ):
        """Arızanın birebir kendisi. Bu test kırılırsa build makinesinde hedef
        klasörün dışına yazılabiliyor demektir."""
        staging = tmp_path / "staging"
        staging.mkdir()
        data = self._tar_with([self._regular("../KACAN.txt")])
        with pytest.raises(Exception):
            fetch_mod._extract(data, "x.tar.gz", str(staging))
        assert not (tmp_path / "KACAN.txt").exists()

    def test_a_symlink_pointing_outside_the_target_is_refused(self, fetch_mod, tmp_path):
        """Tek başına zararsız görünen bağ, ikinci aşamada üstüne yazmak için
        kullanılıyordu — ölçümde iki aşamalı yazma başarılı olmuştu."""
        staging = tmp_path / "staging"
        staging.mkdir()
        data = self._tar_with([self._symlink("kotu", "../DISARIDA")])
        with pytest.raises(Exception):
            fetch_mod._extract(data, "x.tar.gz", str(staging))

    def test_an_ordinary_archive_still_extracts(self, fetch_mod, tmp_path):
        """Karşıt yön: kapı çok DAR olmamalı, yoksa gömülü SDK hiç kurulamaz."""
        staging = tmp_path / "staging"
        staging.mkdir()
        data = self._tar_with([self._regular("alt/dosya.txt", b"merhaba")])
        fetch_mod._extract(data, "x.tar.gz", str(staging))
        assert (staging / "alt" / "dosya.txt").read_bytes() == b"merhaba"

    def test_extraction_refuses_to_run_at_all_without_filter_support(
        self, fetch_mod, tmp_path, monkeypatch
    ):
        """Eski Python'da SESSİZCE korumasız çıkarmak yerine gürültülü hata.
        Bu bir build script'i; kırılmak, korumasız yazmaktan iyidir."""
        staging = tmp_path / "staging"
        staging.mkdir()
        monkeypatch.setattr(fetch_mod, "_TAR_FILTER_SUPPORTED", False)
        data = self._tar_with([self._regular("zararsiz.txt")])
        with pytest.raises(RuntimeError, match="filter"):
            fetch_mod._extract(data, "x.tar.gz", str(staging))

    def test_a_symlink_named_like_the_executable_is_refused_before_chmod(
        self, fetch_mod, tmp_path, monkeypatch
    ):
        """`os.chmod` bağ takip ediyor: arşivde `OmniSharp` ADINDA bir bağ varsa
        hedefin DIŞINDAKİ dosyanın modu değişiyordu (ölçüldü: 0600 → 0755)."""
        dest = tmp_path / "osx-arm64"
        kurban = tmp_path / "kurban.txt"
        kurban.write_text("gizli")
        os.chmod(kurban, 0o600)

        def _sahte_extract(_data, _url, staging):
            os.symlink(str(kurban), os.path.join(staging, "OmniSharp"))

        monkeypatch.setattr(fetch_mod, "_extract", _sahte_extract)
        with pytest.raises(RuntimeError, match="sembolik bağ"):
            fetch_mod._install(b"", "x.tar.gz", str(dest), "v1", ["OmniSharp"])
        assert oct(os.stat(kurban).st_mode)[-3:] == "600"

class TestSembolikBagKuruluSayilmaz:
    """Sembolik bağ üzerinden kalıcı kod çalıştırma zincirini kapatan testler.

    Hangi arızadan doğdu (dış denetim, 2026-07-28, ikinci model ailesi): tek
    seferlik bir yazma, kalıcı kod çalıştırmaya dönüşebiliyordu. Zincir:
    `third_party/omnisharp/<plat>/OmniSharp` yerine dışarıyı gösteren bir bağ
    konur → `_intact()` bunu "sağlam kurulum" sayıp indirmeyi ATLAR → ürün
    `_resolve_binary()` ile o bağı bulur ve ÇALIŞTIRIR. Ölçüldü: `_intact()`
    dışarıdaki bir binary için True döndü.

    Sebep her üç yerde de aynı: `os.path.exists` ve `os.chmod` bağ TAKİP EDİYOR.
    """

    def test_a_symlinked_marker_is_not_a_healthy_installation(self, fetch_mod, tmp_path):
        """Zincirin ilk halkası. Bu test kırılırsa indirme atlanmaya ve dışarıdaki
        bir binary 'kurulu OmniSharp' sayılmaya geri döner."""
        disarida = tmp_path / "DISARIDAKI"
        disarida.write_text("#!/bin/sh\n")
        dest = tmp_path / "osx-arm64"
        dest.mkdir()
        os.symlink(str(disarida), str(dest / "OmniSharp"))
        (dest / ".version").write_text("v1")
        assert fetch_mod._intact(str(dest), "v1", ["OmniSharp"]) is False

    def test_a_real_marker_file_is_still_accepted(self, fetch_mod, tmp_path):
        """Karşıt yön: gerçek dosya reddedilirse her build yeniden indirir."""
        dest = tmp_path / "osx-arm64"
        dest.mkdir()
        (dest / "OmniSharp").write_text("")
        (dest / ".version").write_text("v1")
        assert fetch_mod._intact(str(dest), "v1", ["OmniSharp"]) is True

    def test_a_symlink_named_like_the_stamp_is_refused(self, fetch_mod, tmp_path, monkeypatch):
        """Damga yazımı da bağ takip ediyordu — yazma hedefin dışına gidiyordu."""
        dest = tmp_path / "osx-arm64"
        kurban = tmp_path / "kurban.txt"
        kurban.write_text("dokunulmamis")

        def _sahte_extract(_data, _url, staging):
            os.symlink(str(kurban), os.path.join(staging, ".version"))

        monkeypatch.setattr(fetch_mod, "_extract", _sahte_extract)
        with pytest.raises(RuntimeError, match="sembolik bağ"):
            fetch_mod._install(b"", "x.tar.gz", str(dest), "v1", [])
        assert kurban.read_text() == "dokunulmamis"

