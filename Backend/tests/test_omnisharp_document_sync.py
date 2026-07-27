"""Bir C# dosyasının OmniSharp'a bildirilme biçimini koruyan testler.

Hangi arızadan doğdu (2026-07-27): Unity'nin ürettiği .csproj bayat olduğunda —
ki harici bir IDE kurulu olmayan makinede bu KALICI haldir — açılan dosya hiçbir
projeye ait olmuyor ve hover/completion/definition sessizce boş dönüyordu.

OmniSharp'ın bu durum için "miscellaneous files" çalışma alanı var ve v1.39.15'te
her zaman AÇIK; açılacak bir ayarı yok. Ama oraya giden tek tetikleyici sunucudaki
`BufferManager.UpdateBufferAsync` ve LSP'de onu çağıran tek bildirim
`textDocument/didChange`. `didOpen` yalnızca `FileOpenService`'e gidiyor, o da
workspace'te ZATEN var olan dokümanı açıyor — yani projede olmayan bir dosya için
hiçbir şey yapmıyor.

Ölçülen kazanç (gerçek Unity dosyası, bayat csproj ile, 2026-07-27):
    hover 'PitchBuilder'  boş → class MatchOfficial.EditorTools.PitchBuilder
    hover 'RebuildPitch'  boş → void PitchBuilder.RebuildPitch()
    hover 'worldRoots'    boş → (yerel değişken) List<Transform> worldRoots
    completion            0   → 191 öğe
Ölçülen SINIR: misc proje yalnız temel .NET referanslarını alıyor, `UnityEngine.Debug`
çözülmüyor — onun için csproj tazelenmeli. İki çözüm çakışmıyor.
"""
import asyncio
import os

import pytest

from app.omnisharp import omnisharp_manager as om


class _FakeClient:
    """LspClient'ın yerine geçen kayıt cihazı — gönderilen bildirimleri saklar."""

    alive = True

    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def notify(self, method: str, params: dict) -> None:
        self.sent.append((method, params))

    async def stop(self) -> None:
        """`_stop_locked` bunu bekliyor — sunucu değişimini sınayabilmek için var."""
        self.alive = False

    @property
    def methods(self) -> list[str]:
        return [m for m, _ in self.sent]


@pytest.fixture
def mgr_with_fake_client(tmp_path):
    """Diagnostics bekleme penceresi kısa devre ediliyor: testin ölçtüğü şey
    gönderilen bildirimler, sunucunun yanıt süresi değil."""
    mgr = om.OmniSharpManager()
    fake = _FakeClient()
    mgr._client = fake
    path = str(tmp_path / "A.cs")
    with open(path, "w", encoding="utf-8") as f:
        f.write("class A {}")
    mgr._diag_ping[om._norm_key(os.path.abspath(path))] = float("inf")
    return mgr, fake, path


class TestIlkSenkron:
    def test_the_first_sync_sends_did_change_as_well_as_did_open(self, mgr_with_fake_client):
        """Bu testin koruduğu tek satır, hover'ın csproj dışı dosyalarda çalışıp
        çalışmamasını belirliyor. `didChange` "zaten didOpen gönderdik, gereksiz"
        diye silinirse ürün sessizce bozulur — hiçbir hata çıkmaz, hover boş döner."""
        mgr, fake, path = mgr_with_fake_client
        asyncio.run(mgr.sync_document(path, "class A {}"))
        assert fake.methods == ["textDocument/didOpen", "textDocument/didChange"]

    def test_the_did_change_carries_the_whole_file_and_no_range(self, mgr_with_fake_client):
        """Sunucudaki misc-files yolu tam metinli değişiklikle tetikleniyor;
        `range` içeren artımlı bir değişiklik aynı yolu izlemiyor."""
        mgr, fake, path = mgr_with_fake_client
        metin = "class A { void B() {} }"
        asyncio.run(mgr.sync_document(path, metin))
        _, params = fake.sent[1]
        degisiklikler = params["contentChanges"]
        assert degisiklikler == [{"text": metin}]
        assert "range" not in degisiklikler[0]

    def test_the_did_open_declares_the_document_as_csharp(self, mgr_with_fake_client):
        mgr, fake, path = mgr_with_fake_client
        asyncio.run(mgr.sync_document(path, "class A {}"))
        _, acilis = fake.sent[0]
        assert acilis["textDocument"]["languageId"] == "csharp"


class TestSonrakiSenkronlar:
    def test_a_reopened_file_is_not_announced_twice(self, mgr_with_fake_client):
        """Aynı dosya ikinci kez senkronlanınca `didOpen` TEKRARLANMAMALI — LSP'de
        açık bir dokümanı yeniden açmak protokol ihlali."""
        mgr, fake, path = mgr_with_fake_client
        asyncio.run(mgr.sync_document(path, "class A {}"))
        asyncio.run(mgr.sync_document(path, "class A { int x; }"))
        assert fake.methods.count("textDocument/didOpen") == 1
        assert fake.methods.count("textDocument/didChange") == 2

    def test_nothing_is_sent_when_the_server_is_not_running(self, tmp_path):
        """Karşıt yön: sunucu yokken bildirim üretmek `None` üzerinde patlardı."""
        mgr = om.OmniSharpManager()
        assert asyncio.run(mgr.sync_document(str(tmp_path / "A.cs"), "class A {}")) == []


class TestDokumanSurumu:
    """Sürüm numarası doküman başına MONOTON artan bir sayaç olmalı.

    Hangi arızadan doğdu (dış denetim, 2026-07-27): sürüm `int(time.time())` idi,
    yani çözünürlük 1 saniye. Aynı saniyedeki iki senkron AYNI sürümü üretiyor ve
    LSP sunucusu "bu sürümü zaten gördüm" diyip ikinciyi yok sayabiliyor — hover
    bayat metne bakar, hiçbir hata görünmez. Artık HER senkronda `didChange`
    gönderdiğimiz için (bkz. TestIlkSenkron) bu çarpışma sık ulaşılabilir hale
    geldi: hızlı yazan bir kullanıcı saniyede birden çok senkron üretiyor."""

    def _versions(self, fake) -> list[int]:
        return [p["textDocument"]["version"] for m, p in fake.sent
                if m == "textDocument/didChange"]

    def test_the_opening_notification_declares_version_one(self, mgr_with_fake_client):
        mgr, fake, path = mgr_with_fake_client
        asyncio.run(mgr.sync_document(path, "class A {}"))
        _, acilis = fake.sent[0]
        assert acilis["textDocument"]["version"] == 1

    def test_two_syncs_within_the_same_second_get_different_versions(
        self, mgr_with_fake_client, monkeypatch
    ):
        """Arızanın birebir kendisi: duvar saati DONDURULUYOR. Eski kod bu testte
        iki kez aynı sayıyı üretirdi; sayaç saate bağlıysa test kırmızıya döner."""
        mgr, fake, path = mgr_with_fake_client
        monkeypatch.setattr(om.time, "time", lambda: 1_800_000_000.0)
        asyncio.run(mgr.sync_document(path, "class A {}"))
        asyncio.run(mgr.sync_document(path, "class A { int x; }"))
        surumler = self._versions(fake)
        assert len(surumler) == 2
        assert surumler[0] != surumler[1]

    def test_each_change_raises_the_version_strictly_above_the_previous_one(
        self, mgr_with_fake_client, monkeypatch
    ):
        """Farklı olmak yetmez, ARTMASI gerek: LSP'de sürüm sırası dokümanın
        güncelliğini belirler, geriye giden bir sayı da yok sayılabilir."""
        mgr, fake, path = mgr_with_fake_client
        monkeypatch.setattr(om.time, "time", lambda: 1_800_000_000.0)
        for i in range(5):
            asyncio.run(mgr.sync_document(path, f"class A {{ int x{i}; }}"))
        surumler = self._versions(fake)
        assert surumler == sorted(surumler)
        assert len(set(surumler)) == len(surumler)
        # didOpen 1 gönderdi → ilk didChange ondan büyük olmalı, yoksa sunucu
        # açılış metnini daha yeni sayar.
        assert surumler[0] > 1

    def test_each_document_carries_its_own_counter(self, mgr_with_fake_client, tmp_path):
        """Karşıt yön — sayaç GLOBAL olmamalı. LSP'de sürüm doküman başına
        tanımlı; ortak bir sayaç ikinci dosyaya 1 yerine büyük bir sayıyla
        başlatır ve o dosyanın sonraki güncellemeleri yok sayılabilir."""
        mgr, fake, ilk = mgr_with_fake_client
        ikinci = str(tmp_path / "B.cs")
        with open(ikinci, "w", encoding="utf-8") as f:
            f.write("class B {}")
        mgr._diag_ping[om._norm_key(os.path.abspath(ikinci))] = float("inf")
        asyncio.run(mgr.sync_document(ilk, "class A {}"))
        asyncio.run(mgr.sync_document(ilk, "class A { int x; }"))
        asyncio.run(mgr.sync_document(ikinci, "class B {}"))
        b_didopen = [p for m, p in fake.sent
                     if m == "textDocument/didOpen"
                     and p["textDocument"]["uri"].endswith("B.cs")]
        assert b_didopen[0]["textDocument"]["version"] == 1

    def test_versions_restart_from_one_after_the_server_is_replaced(
        self, mgr_with_fake_client
    ):
        """Sunucu yeniden başlayınca `_opened` sıfırlanıyor ve dosyaya yeniden
        `didOpen` (sürüm 1) gidiyor. Sayaç eski değerinde kalırsa didChange
        sürümleri didOpen'la tutarsız olur; ikisi BİRLİKTE sıfırlanmalı."""
        mgr, fake, path = mgr_with_fake_client
        asyncio.run(mgr.sync_document(path, "class A {}"))
        asyncio.run(mgr.sync_document(path, "class A { int x; }"))
        asyncio.run(mgr._stop_locked())
        yeni = _FakeClient()
        mgr._client = yeni
        asyncio.run(mgr.sync_document(path, "class A { int y; }"))
        assert yeni.sent[0][0] == "textDocument/didOpen"
        assert yeni.sent[0][1]["textDocument"]["version"] == 1
        assert yeni.sent[1][1]["textDocument"]["version"] == 2
