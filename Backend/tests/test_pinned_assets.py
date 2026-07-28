"""Sabitlenmiş indirme kütüğünün (scripts/pinned_assets.json) kendi sözleşmesi.

Hangi arızadan doğdu: 2026-07-28 denetiminde bu depoda 13 ayrı yerden yürütülebilir
içerik indirildiği ve HİÇBİRİNDE checksum/imza/boyut kontrolü olmadığı ölçüldü
(grep: `sha256|sha512|checksum|gpg|--verify|signature|hashlib` → sıfır sonuç).
İndirilenlerin hepsi installer'a giriyor ve son kullanıcıda çalıştırılıyor.

Bu dosya kütüğün KENDİSİNİ koruyor, indirme mekaniğini değil (o
`test_fetch_omnisharp_cache.py`'de). Buradaki testlerin ortak derdi tek bir şey:
**bir doğrulama kapısının sessizce etkisiz hale gelmesi.** Bu depoda kapılar üç
kez tam da böyle kayboldu — damga doğruyken ağaç eksikti, `csproj_count` üretilip
tüketilmedi, `didOpen` gönderilip `didChange` gönderilmedi. Ortak şekil:
**birbiriyle uyuşması gereken iki yer, ve uyuşmuyorlar.**

En kritik test aşağıdaki `TestCSharpTablosuKutukleAyrisamaz`: Roslyn özetleri hem
JSON'da hem `RoslynInstaller.cs`'de yazılı (C# kodu UPM paketiyle dağıtılıyor ve
JSON'u göremiyor). İkisinin ayrışmasını hatırlamaya bağlamak, yukarıdaki arıza
sınıfını bilerek yeniden üretmek olurdu.
"""
import importlib.util
import io
import json
import os
import re
import shutil
import urllib.error
import urllib.request

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MANIFEST = os.path.join(_ROOT, "scripts", "pinned_assets.json")
_ROSLYN_CS = os.path.join(
    _ROOT, "unity-mcp", "MCPForUnity", "Editor", "Setup", "RoslynInstaller.cs"
)


@pytest.fixture(scope="module")
def pinned():
    """scripts/ bir paket değil — dosyayı yolundan yükle. Bulunamaması da bir
    bulgudur, o yüzden atlanmıyor, patlıyor."""
    path = os.path.join(_ROOT, "scripts", "pinned_assets.py")
    assert os.path.isfile(path), f"beklenen modül yok: {path}"
    spec = importlib.util.spec_from_file_location("pinned_assets", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def entries():
    with open(_MANIFEST, encoding="utf-8") as f:
        return json.load(f)["assets"]


class TestKutukKendiBicimineUyuyor:
    """Biçim kapısı. Bozuk bir girdi çalışma anında değil, burada yakalanmalı:
    build sırasında keşfedilen bir yazım hatası, CI'da tag atıldıktan sonra
    görünür ve o noktada geri dönmek pahalıdır."""

    def test_every_asset_carries_a_url_a_digest_and_a_size(self, entries):
        for key, e in entries.items():
            assert e.get("url", "").startswith("https://"), f"{key}: https URL yok"
            assert isinstance(e.get("size"), int) and e["size"] > 0, f"{key}: boyut yok"
            assert ":" in e.get("digest", ""), f"{key}: 'algo:hex' biçiminde özet yok"

    def test_every_digest_uses_a_collision_resistant_algorithm(self, entries):
        """MD5 ve SHA-1 çakışmaya karşı kırık. johnvansickle YALNIZ MD5 yayınlıyor;
        oradaki özet bilerek elle SHA-256 hesaplandı. Bu test, birinin kolaylık
        olsun diye yayınlanmış MD5'i kütüğe koymasını engelliyor."""
        for key, e in entries.items():
            algo, _, hexpart = e["digest"].partition(":")
            assert algo in ("sha256", "sha512"), f"{key}: kabul edilmeyen algoritma {algo}"
            expected_len = 64 if algo == "sha256" else 128
            assert len(hexpart) == expected_len, f"{key}: {algo} uzunluğu yanlış"
            assert re.fullmatch(r"[0-9a-f]+", hexpart), f"{key}: hex değil ya da büyük harf"

    def test_no_asset_is_pinned_to_a_moving_target(self, entries):
        """Sabitlemenin ta kendisi. `latest` içeren bir URL'in özeti sabitlenemez —
        yayıncı her yayında baytları değiştirir ve doğrulama ilk gün kırılır.
        Bu test o hatayı kütüğe girer girmez yakalıyor.

        ⚠️ `ffmpeg/win` bir istisna DEĞİL: BtbN'in `latest` tag'i her build'de
        silinip yeniden yaratılıyor, o yüzden bilerek ay-sonu autobuild tag'i
        seçildi. Bu test o seçimi bağlıyor."""
        for key, e in entries.items():
            assert "/latest/" not in e["url"], f"{key}: sabitlenmemiş 'latest' adresi"
            assert not e["url"].endswith("/latest"), f"{key}: sabitlenmemiş 'latest' adresi"

    def test_no_digest_is_left_as_a_placeholder(self, entries):
        """Yer tutucu bir özet, doğrulama kapısını açık bırakmanın en sessiz yolu."""
        for key, e in entries.items():
            assert "todo" not in e["digest"].lower(), f"{key}: doldurulmamış özet"

    def test_a_hand_computed_digest_says_so_and_carries_its_date(self, entries):
        """İki ffmpeg'de yayıncı özet YAYINLAMIYOR, yani özeti hesaplayan kişi güven
        kökü oluyor. Bunun kütükte görünür olması şart: gelecekte okuyan biri
        değerin vendor'dan geldiğini SANARSA, aslında olmayan bir garantiye
        güvenmiş olur."""
        for key, e in entries.items():
            kaynak = e.get("kaynak", "")
            assert kaynak, f"{key}: özetin kaynağı yazılmamış"
            if kaynak.startswith("yerel"):
                assert re.fullmatch(r"yerel:\d{4}-\d{2}-\d{2}", kaynak), (
                    f"{key}: elle hesaplanan özet tarihsiz — 'yerel:YYYY-AA-GG' olmalı"
                )


class TestDogrulamaIkiYondenDeCalisiyor:
    """Kapı iki yönden de sınanmalı. Bu deponun en pahalı dersi: bütün testler
    kapının çok DAR olmadığını sınıyordu, hiçbiri çok GENİŞ olmadığını
    sınamıyordu — ve üç ayrı arıza tam oradan çıktı."""

    def test_bytes_matching_the_pin_are_accepted(self, pinned, entries, monkeypatch):
        """Çok DAR olmama yönü: doğru baytlar reddedilirse ürün hiç kurulamaz."""
        data = b"tam olarak bu baytlar"
        key = "omnisharp/osx-arm64"
        sahte = dict(entries[key])
        sahte["digest"] = "sha256:" + pinned.digest_of(data, "sha256")
        sahte["size"] = len(data)
        monkeypatch.setattr(pinned, "asset", lambda k: sahte)
        pinned.verify_bytes(data, key)      # istisna atmamalı

    def test_a_single_flipped_byte_is_refused(self, pinned, entries, monkeypatch):
        """Çok GENİŞ olmama yönü, en dar hali: tek bayt değişimi bile geçmemeli."""
        data = b"tam olarak bu baytlar"
        key = "omnisharp/osx-arm64"
        sahte = dict(entries[key])
        sahte["digest"] = "sha256:" + pinned.digest_of(data, "sha256")
        sahte["size"] = len(data)
        monkeypatch.setattr(pinned, "asset", lambda k: sahte)
        with pytest.raises(pinned.IntegrityError):
            pinned.verify_bytes(data.replace(b"bu", b"su"), key)

    def test_an_unknown_key_raises_instead_of_silently_passing(self, pinned):
        """Bir kabuk betiği anahtarı yanlış yazarsa doğrulama ATLANMIŞ olurdu ve
        build yeşil kalırdı — 'sessiz no-op' sınıfının tam kendisi."""
        with pytest.raises(KeyError):
            pinned.asset("boyle/bir/anahtar/yok")

    def test_the_error_names_the_asset_and_its_source(self, pinned, entries, monkeypatch):
        """Uyuşmazlık anında teşhis edilebilirlik: mesaj hangi asset'in, hangi
        adresten geldiğini söylemezse, 19 girdilik bir kütükte arıza aramak
        gereksizce pahalı olur."""
        key = "omnisharp/osx-arm64"
        monkeypatch.setattr(pinned, "asset", lambda k: entries[key])
        with pytest.raises(pinned.IntegrityError) as hata:
            pinned.verify_bytes(b"yanlis", key)
        assert entries[key]["url"] in str(hata.value)

    def test_a_truncated_download_is_named_as_a_size_problem(
        self, pinned, entries, monkeypatch
    ):
        """Yarım inen dosyada asıl bilgi boyutta: 'iki hex uyuşmadı' demek yerine
        'X bayt bekleniyordu, Y geldi' demek teşhisi anında bitiriyor."""
        key = "omnisharp/osx-arm64"
        monkeypatch.setattr(pinned, "asset", lambda k: entries[key])
        with pytest.raises(pinned.IntegrityError, match="boyut"):
            pinned.verify_bytes(b"yarim", key)


class TestCSharpTablosuKutukleAyrisamaz:
    """Roslyn özetleri İKİ yerde yazılı ve bu kaçınılmaz: `RoslynInstaller.cs` UPM
    paketiyle son kullanıcıya gidiyor, `pinned_assets.json`'u göremiyor.

    Kaçınılmaz olan şey, denetimsiz olmak zorunda değil. Bu sınıf ayrışmayı
    hatırlamaya değil bir kapıya bağlıyor — çünkü bu depoda hatırlamaya bağlı
    hiçbir kural iki haftadan uzun yaşamadı (ölçüldü: 6 lane'in 1'inde uygulandı).
    """

    @staticmethod
    def _csharp_entries() -> dict:
        with open(_ROSLYN_CS, encoding="utf-8") as f:
            src = f.read()
        satirlar = re.findall(
            r'\(\s*"([\w.]+)"\s*,\s*"([\d.]+)"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"([^"]*)"\s*\)',
            src,
        )
        return {pid: (ver, digest) for pid, ver, digest in satirlar}

    def test_the_csharp_table_was_actually_parsed(self):
        """Kendini sınayan test: regex tutmazsa aşağıdaki testler BOŞ küme üzerinde
        koşar ve sessizce geçer — yani kapı, kırılmadan kaybolur."""
        assert len(self._csharp_entries()) == 4, (
            "RoslynInstaller.cs'deki tablo ayrıştırılamadı; tablo biçimi değiştiyse "
            "bu testin regex'i de güncellenmeli — sessizce boş geçmesin"
        )

    def test_every_csharp_digest_matches_the_manifest(self, entries):
        """Ayrışmayı yakalayan asıl satır."""
        for pid, (ver, digest) in self._csharp_entries().items():
            key = f"roslyn/{pid}"
            assert key in entries, f"C# tablosunda olan '{pid}' kütükte yok"
            beklenen = entries[key]["digest"].partition(":")[2]
            assert digest.lower() == beklenen, (
                f"{pid}: C# tablosu ile kütük ayrışmış\n"
                f"  C#    : {digest}\n"
                f"  kütük : {beklenen}"
            )

    def test_every_csharp_version_matches_the_manifest_url(self, entries):
        """Özet tutup sürüm ayrışırsa, indirilen paket beklenenden başka olur ve
        doğrulama ilk koşuda kırılır — build makinesinde değil, KULLANICININ
        Unity'sinde. O yüzden sürüm de bağlanıyor."""
        for pid, (ver, _digest) in self._csharp_entries().items():
            url = entries[f"roslyn/{pid}"]["url"]
            assert f"/{ver}/" in url, f"{pid}: C# sürümü {ver}, kütük URL'i {url}"

    def test_no_csharp_digest_is_left_as_a_placeholder(self):
        """`TODO-DIGEST` bilerek fail-loud bırakılmıştı; dolmadan sürüm çıkmasın."""
        for pid, (_ver, digest) in self._csharp_entries().items():
            assert re.fullmatch(r"[0-9a-fA-F]{64}", digest), (
                f"{pid}: özet doldurulmamış ya da 64 hanelik hex değil → {digest!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# `refresh` / `check` — tazeleme aracının kendi sözleşmesi
#
# Bu testler AĞA ÇIKMIYOR: `urllib.request.urlopen` monkeypatch'leniyor. Gerekçe
# ölçülmüş değil, yapısal — ağa çıkan bir test, yayıncı bir sürüm yayınladığı gün
# kırmızıya döner ve kırmızılığı ürünle ilgisiz olur; o noktada test susturulur
# ve kapı kaybolur. Bu depoda kapılar tam olarak böyle kayboldu.
# ─────────────────────────────────────────────────────────────────────────────

_HEX_A = "a" * 64
_HEX_B = "b" * 64

_UV_API = "https://api.github.com/repos/astral-sh/uv/releases?per_page=100"
_UV_TAR = "https://github.com/astral-sh/uv/releases/download/0.99.0/uv-aarch64-apple-darwin.tar.gz"

_BTBN_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases?per_page=100"
_BTBN_DL = "https://github.com/BtbN/FFmpeg-Builds/releases/download"
_BTBN_AY_SONU = "autobuild-2026-07-31-13-34"      # doğru seçim (~24 ay yaşar)
_BTBN_GUNLUK = "autobuild-2026-08-05-09-00"       # daha YENİ ama ~2 haftada silinir
_BTBN_ZIP = "ffmpeg-n8.2.0-10-gaaaaaaaaaa-win64-lgpl-8.2.zip"

_NUGET_INDEX = "https://api.nuget.org/v3-flatcontainer/microsoft.codeanalysis.common/index.json"


class _SahteYanit:
    """urlopen'ın döndürdüğü nesnenin bu koddaki kullanılan yüzeyi: bağlam
    yöneticisi + `read()` + `headers`. Fazlası taklit edilmiyor."""

    def __init__(self, govde: bytes, headers: dict | None = None):
        self._govde = govde
        self.status = 200
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._govde

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _sahte_ag(monkeypatch, rotalar: dict, patlayanlar: tuple = ()):
    """URL → gövde eşlemesi. Tanımlanmamış bir adres SESSİZCE boş dönmüyor,
    patlıyor: eksik rota bir test hatasıdır ve testin yanlışlıkla geçmesine
    yol açmamalı."""

    def urlopen(req, timeout=None):
        url = getattr(req, "full_url", req)
        for parca in patlayanlar:
            if parca in url:
                raise urllib.error.URLError(f"sahte ağ arızası: {parca}")
        if url not in rotalar:
            raise AssertionError(f"testte tanımsız ağ adresi: {url}")
        govde = rotalar[url]
        return _SahteYanit(govde if isinstance(govde, bytes) else json.dumps(govde).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def _uv_rotalari() -> dict:
    return {
        _UV_API: [
            # En üstteki KARARLI DEĞİL; seçilirse sürüm sabitlemesi anlamsızlaşır.
            {"tag_name": "0.99.1rc1", "draft": False, "prerelease": True, "assets": []},
            {
                "tag_name": "0.99.0", "draft": False, "prerelease": False,
                "assets": [{
                    "name": "uv-aarch64-apple-darwin.tar.gz",
                    "size": 12345,
                    "browser_download_url": _UV_TAR,
                }],
            },
        ],
        _UV_TAR + ".sha256": f"{_HEX_A}  uv-aarch64-apple-darwin.tar.gz\n".encode(),
    }


@pytest.fixture
def kutuk(pinned, tmp_path, monkeypatch):
    """Kütüğün koşuya özel kopyası. Testlerin gerçek `scripts/pinned_assets.json`
    üzerine yazması, tam da kapatmaya çalıştığımız arızayı test paketinin
    kendisiyle üretmek olurdu."""
    kopya = tmp_path / "pinned_assets.json"
    shutil.copyfile(_MANIFEST, kopya)
    monkeypatch.setattr(pinned, "MANIFEST_PATH", str(kopya))
    return kopya


class TestTazelemeKutugeIzinsizDokunmuyor:
    """`refresh`in en kritik özelliği hangi sürümü bulduğu değil, İZİNSİZ
    YAZMAMASI. Bu kütük güvenlik kapısının kendisi; sessizce üzerine yazan bir
    araç, kapıyı kapatmak için yazılmış olmasına rağmen açardı."""

    def test_a_dry_run_leaves_the_manifest_byte_identical(self, pinned, kutuk, monkeypatch):
        """Varsayılan davranış. Bir bayt bile değişirse bu test kırılmalı —
        'sadece boşluk' diye başlayan bir fark, elle incelenen diff'i boğar."""
        once = kutuk.read_bytes()
        _sahte_ag(monkeypatch, _uv_rotalari())
        sonuc = pinned.refresh(["uv/darwin-arm64"], out=io.StringIO())
        assert kutuk.read_bytes() == once, "kuru koşu kütüğe DOKUNDU"
        assert sonuc[0]["durum"] == "degisti", "değişiklik bulunmalıydı ama bulunmadı"
        assert sonuc[0]["yeni"]["url"] == _UV_TAR

    def test_a_dry_run_says_out_loud_that_nothing_was_written(self, pinned, kutuk, monkeypatch):
        """Kuru koşu sessiz kalırsa okuyan kişi yazıldığını sanar ve diff'i
        incelemez; `$aciklama`'nın verdiği talimat boşa çıkar."""
        _sahte_ag(monkeypatch, _uv_rotalari())
        cikti = io.StringIO()
        pinned.refresh(["uv/darwin-arm64"], out=cikti)
        assert "KURU KOŞU" in cikti.getvalue()
        assert "--write" in cikti.getvalue()

    def test_write_applies_the_pin_without_losing_the_prose_fields(
        self, pinned, kutuk, monkeypatch
    ):
        """`$aciklama`/`$not`/`$roslyn_notu` ölçülmüş gerekçe taşıyor. Kütüğü
        json.dump ile yeniden serileştiren bir uygulama biçimi düzleştirir ve
        diff'i okunamaz kılar — bu test yazma yolunun metin cerrahisi kalmasını
        bağlıyor."""
        _sahte_ag(monkeypatch, _uv_rotalari())
        pinned.refresh(["uv/darwin-arm64"], write=True, out=io.StringIO())

        veri = json.loads(kutuk.read_text(encoding="utf-8"))
        girdi = veri["assets"]["uv/darwin-arm64"]
        assert girdi["url"] == _UV_TAR
        assert girdi["digest"] == "sha256:" + _HEX_A
        assert girdi["size"] == 12345
        assert girdi["kaynak"] == "yayinci"

        with open(_MANIFEST, encoding="utf-8") as f:
            asil = json.load(f)
        assert veri["$aciklama"] == asil["$aciklama"], "$aciklama kayboldu/değişti"
        assert veri["$roslyn_notu"] == asil["$roslyn_notu"], "$roslyn_notu kayboldu/değişti"
        assert veri["assets"]["ffmpeg/win"]["$not"] == asil["assets"]["ffmpeg/win"]["$not"]
        assert veri["assets"]["ffmpeg/macos"]["$not"] == asil["assets"]["ffmpeg/macos"]["$not"]
        assert list(veri["assets"]) == list(asil["assets"]), "anahtar sırası bozuldu"
        assert list(girdi) == list(asil["assets"]["uv/darwin-arm64"]), "alan sırası bozuldu"

    def test_only_the_touched_entry_changes(self, pinned, kutuk, monkeypatch):
        """Yazma yolu blok sınırlarına saygılı mı: bir asset'i tazelerken
        komşusunu bozmak, 19 girdilik bir dosyada gözden kaçar."""
        with open(_MANIFEST, encoding="utf-8") as f:
            asil = json.load(f)["assets"]
        _sahte_ag(monkeypatch, _uv_rotalari())
        pinned.refresh(["uv/darwin-arm64"], write=True, out=io.StringIO())
        yeni = json.loads(kutuk.read_text(encoding="utf-8"))["assets"]
        for key in asil:
            if key != "uv/darwin-arm64":
                assert yeni[key] == asil[key], f"{key} dokunulmadan değişti"


class TestBtbNSadeceAySonuTaginiSeciyor:
    """BtbN `util/prunetags.sh` ile son 14 build + son 24 ay-sonu tag'ini tutup
    gerisini release'iyle birlikte SİLİYOR. Bu kural unutulursa `refresh` en yeni
    (günlük) tag'i seçer ve pin ~2 haftada 404 olur — üstelik sessizce, çünkü
    kırılma build gününe kadar görünmez."""

    def test_the_month_end_rule_is_computed_not_hardcoded(self, pinned):
        assert pinned._btbn_ay_sonu_mu("autobuild-2026-07-31-13-34")
        assert pinned._btbn_ay_sonu_mu("autobuild-2026-06-30-13-34")
        assert pinned._btbn_ay_sonu_mu("autobuild-2024-02-29-00-00")   # artık yıl
        assert not pinned._btbn_ay_sonu_mu("autobuild-2026-08-05-09-00")
        assert not pinned._btbn_ay_sonu_mu("autobuild-2025-02-29-00-00")  # yok olan gün
        assert not pinned._btbn_ay_sonu_mu("latest")

    def _rotalar(self) -> dict:
        def varlik(tag, ad, boyut=999):
            return {"name": ad, "size": boyut, "browser_download_url": f"{_BTBN_DL}/{tag}/{ad}"}

        adlar = [
            _BTBN_ZIP,
            "ffmpeg-n8.2.0-10-gaaaaaaaaaa-win64-lgpl-shared-8.2.zip",
            "ffmpeg-n8.2.0-10-gaaaaaaaaaa-win64-gpl-8.2.zip",
            "ffmpeg-master-latest-win64-lgpl.zip",
            "checksums.sha256",
        ]
        toplamlar = "".join(f"{_HEX_B}  {ad}\n" for ad in adlar).encode()
        return {
            _BTBN_API: [
                # Listenin başında daha YENİ ama günlük olan tag duruyor: seçim
                # "en yeni"ye göre yapılırsa test kırmızıya döner.
                {"tag_name": _BTBN_GUNLUK, "draft": False, "prerelease": False,
                 "assets": [varlik(_BTBN_GUNLUK, ad) for ad in adlar]},
                {"tag_name": _BTBN_AY_SONU, "draft": False, "prerelease": False,
                 "assets": [varlik(_BTBN_AY_SONU, ad, 144332999) for ad in adlar]},
                {"tag_name": "autobuild-2026-06-30-13-34", "draft": False, "prerelease": False,
                 "assets": [varlik("autobuild-2026-06-30-13-34", ad) for ad in adlar]},
            ],
            f"{_BTBN_DL}/{_BTBN_AY_SONU}/checksums.sha256": toplamlar,
        }

    def test_a_newer_daily_tag_is_refused_in_favour_of_the_month_end_one(
        self, pinned, kutuk, monkeypatch
    ):
        _sahte_ag(monkeypatch, self._rotalar())
        sonuc = pinned.refresh(["ffmpeg/win"], out=io.StringIO())[0]
        assert sonuc["durum"] == "degisti", sonuc
        assert _BTBN_AY_SONU in sonuc["yeni"]["url"]
        assert _BTBN_GUNLUK not in sonuc["yeni"]["url"], (
            "günlük autobuild tag'i seçildi — BtbN bunu ~2 haftada siler, pin ölür"
        )

    def test_the_shared_and_unversioned_variants_are_not_pinned(
        self, pinned, kutuk, monkeypatch
    ):
        """`shared` ayrı DLL'ler ister; `master-latest` sürümsüz, yani hareketli
        hedef — ikisi de sabitlenemez."""
        _sahte_ag(monkeypatch, self._rotalar())
        url = pinned.refresh(["ffmpeg/win"], out=io.StringIO())[0]["yeni"]["url"]
        assert url.endswith(_BTBN_ZIP)
        assert "shared" not in url and "master-latest" not in url

    def test_writing_ffmpeg_win_keeps_its_expiry_warning(self, pinned, kutuk, monkeypatch):
        """Bu girdinin `$not`'u pinin süresinin DOLACAĞINI anlatıyor; kaybolursa
        gelecekteki okuyucu 404'ün sebebini yeniden keşfetmek zorunda kalır."""
        _sahte_ag(monkeypatch, self._rotalar())
        pinned.refresh(["ffmpeg/win"], write=True, out=io.StringIO())
        girdi = json.loads(kutuk.read_text(encoding="utf-8"))["assets"]["ffmpeg/win"]
        assert _BTBN_AY_SONU in girdi["url"]
        assert girdi["digest"] == "sha256:" + _HEX_B
        assert girdi["size"] == 144332999
        assert "prunetags" in girdi["$not"], "süre-dolumu uyarısı yazma sırasında silindi"


class TestRoslynOtomatikYukseltilmiyor:
    """roslyn/* Unity Editor'ün İÇİNE yükleniyor. Sürüm yükseltmesi Unity
    uyumluluğunu kırabilir ve kırılma bizim makinemizde değil KULLANICININ
    Unity'sinde görünür — o yüzden karar otomatikleştirilemez, yalnız bildirilir.
    Ayrıca özetler `RoslynInstaller.cs` tablosunda da yazılı; kütüğü tek başına
    yükseltmek yukarıdaki `TestCSharpTablosuKutukleAyrisamaz`ı da kırardı."""

    def test_a_newer_nuget_version_is_reported_but_never_written(
        self, pinned, kutuk, monkeypatch
    ):
        once = kutuk.read_bytes()
        _sahte_ag(monkeypatch, {
            _NUGET_INDEX: {"versions": ["4.12.0", "4.14.0", "5.0.0-preview.1.25"]},
        })
        # write=True bilerek: yazma İZNİ verilse bile bu girdi değişmemeli.
        sonuc = pinned.refresh(
            ["roslyn/microsoft.codeanalysis.common"], write=True, out=io.StringIO()
        )[0]
        assert sonuc["durum"] == "bildirim", sonuc
        assert "4.14.0" in sonuc["mesaj"]
        assert kutuk.read_bytes() == once, "roslyn girdisi otomatik yükseltildi"

    def test_a_prerelease_is_not_reported_as_the_newest(self, pinned, kutuk, monkeypatch):
        """5.0.0-preview mevcut sürümden büyük görünür ama kararlı değil; onu
        bildirmek, sınanmamış bir yükseltmeyi meşru gösterirdi."""
        _sahte_ag(monkeypatch, {
            _NUGET_INDEX: {"versions": ["4.12.0", "5.0.0-preview.1.25"]},
        })
        sonuc = pinned.refresh(["roslyn/microsoft.codeanalysis.common"], out=io.StringIO())[0]
        assert sonuc["durum"] == "guncel", sonuc


class TestTekBirArizaKosuyuOldurmuyor:
    """19 asset'in 8 ayrı yayıncısı var. Birinin bakımda olması diğer 18'in
    tazelenmesini engellerse araç kullanılmaz hale gelir — ve kullanılmayan bir
    araç, var olmayan araçla aynı şeydir (bu görevi doğuran durum tam olarak
    buydu: vaat edilmiş ama olmayan `refresh`)."""

    def test_a_failing_publisher_does_not_stop_the_others(self, pinned, kutuk, monkeypatch):
        _sahte_ag(monkeypatch, _uv_rotalari(), patlayanlar=("evermeet.cx",))
        sonuclar = pinned.refresh(
            ["ffmpeg/macos", "uv/darwin-arm64"], out=io.StringIO()
        )
        durumlar = {s["key"]: s["durum"] for s in sonuclar}
        assert durumlar["ffmpeg/macos"] == "hata"
        assert durumlar["uv/darwin-arm64"] == "degisti", (
            "bir asset'in ağ hatası sonrakini de düşürdü"
        )

    def test_a_failed_asset_is_named_with_its_reason(self, pinned, kutuk, monkeypatch):
        """'bir şeyler ters gitti' teşhis ettirmiyor; hangi asset, hangi hata."""
        _sahte_ag(monkeypatch, _uv_rotalari(), patlayanlar=("evermeet.cx",))
        cikti = io.StringIO()
        pinned.refresh(["ffmpeg/macos"], out=cikti)
        metin = cikti.getvalue()
        assert "ffmpeg/macos" in metin and "HATA" in metin
        assert "sahte ağ arızası" in metin

    def test_the_cli_exit_code_reports_the_failure(self, pinned, kutuk, monkeypatch):
        """Çıkış kodu sözleşmesi (0=tamam, 1=başarısız): eksik kalan bir koşu
        CI'da yeşil sayılırsa, kapı yine sessizce etkisiz hale gelir."""
        _sahte_ag(monkeypatch, _uv_rotalari(), patlayanlar=("evermeet.cx",))
        assert pinned._main(["pinned_assets.py", "refresh", "ffmpeg/macos"]) == 1
        _sahte_ag(monkeypatch, _uv_rotalari())
        assert pinned._main(["pinned_assets.py", "refresh", "uv/darwin-arm64"]) == 0
        assert kutuk.read_bytes() == open(_MANIFEST, "rb").read(), (
            "CLI kuru koşusu kütüğe yazdı"
        )

    def test_an_unknown_key_is_refused_instead_of_silently_skipped(self, pinned, kutuk):
        with pytest.raises(KeyError):
            pinned.refresh(["boyle/bir/anahtar/yok"], out=io.StringIO())


class TestCheckOlenPinleriGoruyor:
    """İki pin'in süresi DOLACAK ve sessizce olacak: `ffmpeg/win` BtbN'in tag
    budamasıyla, `ffmpeg/linux` releases/ → old-releases/ taşınmasıyla. HEAD
    yoklaması bunu build gününden haftalar öne çekiyor."""

    def test_a_404_pin_is_reported_as_dead(self, pinned, kutuk, monkeypatch):
        olu = json.loads(kutuk.read_text(encoding="utf-8"))["assets"]["ffmpeg/win"]["url"]

        def urlopen(req, timeout=None):
            url = getattr(req, "full_url", req)
            assert req.get_method() == "HEAD", "check gövdeyi indiriyor — 1.5 GB"
            if url == olu:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            return _SahteYanit(b"")

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        sonuclar = {s["key"]: s["durum"] for s in pinned.check(out=io.StringIO())}
        assert sonuclar["ffmpeg/win"] == "olu"
        assert sonuclar["uv/win-x64"] == "ok"
        assert pinned._main(["pinned_assets.py", "check"]) == 1


class TestDotnetSurumDosyasiDogruYerdenOkunuyor:
    """Canlı koşuda ölçülmüş arıza (2026-07-28): dosyalar `release.sdk.files`
    altında, en üst düzeyde `sdk` YOK. Yanlış yol 'aday bulunamadı' hatası
    veriyordu. Ayrıca aynı rid altında .pkg/.exe/.tar.gz/.zip yan yana duruyor ve
    `name` alanı sürüm taşımıyor — yanlışını seçmek kullanıcıya çalışmayan bir
    SDK indirtirdi."""

    _URL = "https://builds.dotnet.microsoft.com/dotnet/Sdk/10.0.101"

    def _rotalar(self, pinned) -> dict:
        def dosya(rid, ad):
            return {"name": ad, "rid": rid, "url": f"{self._URL}/dotnet-sdk-10.0.101-{ad[11:]}",
                    "hash": "c" * 128}

        # Adres modülden okunuyor, kopyalanmıyor: sabiti burada tekrarlamak
        # 'uyuşması gereken iki yer' üretirdi.
        return {
            pinned._DOTNET_RELEASE_JSON: {
                "channel-version": "10.0",
                "release": {
                    "release-version": "10.0.1",
                    "sdk": {"files": [
                        dosya("osx-arm64", "dotnet-sdk-osx-arm64.pkg"),
                        dosya("osx-arm64", "dotnet-sdk-osx-arm64.tar.gz"),
                        dosya("win-x64", "dotnet-sdk-win-x64.exe"),
                        dosya("win-x64", "dotnet-sdk-win-x64.zip"),
                    ]},
                },
            },
            f"{self._URL}/dotnet-sdk-10.0.101-osx-arm64.tar.gz": b"",
        }

    def test_the_archive_is_chosen_over_the_installer_for_the_same_rid(
        self, pinned, kutuk, monkeypatch
    ):
        rotalar = self._rotalar(pinned)

        def urlopen(req, timeout=None):
            url = getattr(req, "full_url", req)
            if req.get_method() == "HEAD":
                return _SahteYanit(b"", {"Content-Length": "229999999"})
            if url not in rotalar:
                raise AssertionError(f"testte tanımsız ağ adresi: {url}")
            govde = rotalar[url]
            return _SahteYanit(govde if isinstance(govde, bytes) else json.dumps(govde).encode())

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        sonuc = pinned.refresh(["dotnet-sdk/osx-arm64"], out=io.StringIO())[0]
        assert sonuc["durum"] == "degisti", sonuc
        assert sonuc["yeni"]["url"].endswith("osx-arm64.tar.gz"), ".pkg seçildi"
        assert sonuc["yeni"]["digest"] == "sha512:" + "c" * 128, "çıplak hex sha512 sayılmadı"
        # Boyut release.json'da YOK; kütüğün sözleşmesi zorunlu tuttuğu için
        # Content-Length'ten geliyor.
        assert sonuc["yeni"]["size"] == 229999999
