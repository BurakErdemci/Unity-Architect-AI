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
