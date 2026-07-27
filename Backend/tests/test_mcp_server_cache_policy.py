"""uvx cache politikası — 2026-07-27 saha arızasının regresyon testi.

Arıza: `start_server()` her açılışta `uvx --no-cache` kullanıyordu. Ölçüm
(2026-07-27, izole kopyayla):

    cache'li      + --offline → çalıştı, 1 sn
    --no-cache    + --offline → BAŞARISIZ
    cache'li, kaynak değişti  → belirteç görünmedi (bayat kod)
    --refresh, kaynak değişti → belirteç görünmedi (çare değil)

Yani `--no-cache` yerel bir özelliği internete bağımlı kılıyordu; kısıtlı bir
public ağda sunucu 2 dk 26 sn'de ancak ayağa kalktı ve toggle 20 dakika sarıda
kaldı. Ama bayrağı tamamen kaldırmak da olmuyor: cache kaynak değişikliğini
yakalamıyor, sunucu sessizce eski kodu çalıştırırdı.

Çözüm: karar içerik özetine bağlandı. Bu testler o kararın iki yönünü de
sabitliyor — yalnızca "değişti" yönü sınansaydı, her zaman True dönen bir
fonksiyon da testi geçerdi ve internet bağımlılığı geri gelirdi.
"""

import os

import pytest

from unity_ai_mcp.unity_mcp_manager import unity_mcp_manager


@pytest.fixture
def isolated_hash_file(tmp_path, monkeypatch):
    """Gerçek ~/.unity_architect_ai kaydına dokunmadan sınamak için."""
    marker = tmp_path / "mcp_server_src.hash"
    monkeypatch.setattr(unity_mcp_manager, "_source_hash_path", lambda: str(marker))
    return marker


def _simulate_nocache_launch(manager):
    """start_server()'ın --no-cache dalını taklit eder.

    Neden gerekli: özet artık BAŞLATMA anında yakalanıyor ve yalnız cache
    baypas edildiyse kaydediliyor. Bu adımı atlayan bir test, düzeltilen
    arızanın ta kendisini (cache'li açılışın 'güncel' damgalanması) sınamış olur.
    """
    manager._pending_source_hash = manager._compute_server_source_hash()

def test_source_hash_is_stable_across_calls():
    """Özet kararsızsa her açılış 'değişti' der ve internet bağımlılığı geri gelir."""
    first = unity_mcp_manager._compute_server_source_hash()
    assert first, "Server kaynağının özeti hesaplanamadı"
    assert first == unity_mcp_manager._compute_server_source_hash()


def test_missing_marker_counts_as_changed(isolated_hash_file):
    """İlk kurulumda cache'e güvenilemez — kayıt yoksa bayat olabilir."""
    assert not isolated_hash_file.exists()
    assert unity_mcp_manager._server_source_changed() is True


def test_recorded_hash_means_cache_is_safe(isolated_hash_file):
    _simulate_nocache_launch(unity_mcp_manager)
    unity_mcp_manager._record_server_source_hash()
    assert isolated_hash_file.exists()
    assert unity_mcp_manager._server_source_changed() is False


def test_source_edit_is_detected(isolated_hash_file):
    """Bu yön olmadan cache bayat kod çalıştırır — bayrağın var olma sebebi."""
    _simulate_nocache_launch(unity_mcp_manager)
    unity_mcp_manager._record_server_source_hash()
    assert unity_mcp_manager._server_source_changed() is False

    target = os.path.join(unity_mcp_manager.server_dir, "src", "main.py")
    original = open(target, "rb").read()
    try:
        with open(target, "ab") as fh:
            fh.write(b"\n# regression marker\n")
        assert unity_mcp_manager._server_source_changed() is True
    finally:
        with open(target, "wb") as fh:
            fh.write(original)

    # Geri alınınca yeniden cache'e güvenilebilmeli, yoksa her koşum yavaşlar.
    assert unity_mcp_manager._server_source_changed() is False


def test_unreadable_source_fails_safe(isolated_hash_file, monkeypatch):
    """Özet alınamıyorsa bayat kod çalıştırmaktansa yavaş koşum tercih edilir."""
    _simulate_nocache_launch(unity_mcp_manager)
    unity_mcp_manager._record_server_source_hash()
    monkeypatch.setattr(unity_mcp_manager, "_compute_server_source_hash", lambda: "")
    assert unity_mcp_manager._server_source_changed() is True


def test_pycache_is_ignored(isolated_hash_file, tmp_path):
    """__pycache__ her koşumda değişir; sayılsaydı cache hiç kullanılamazdı."""
    _simulate_nocache_launch(unity_mcp_manager)
    unity_mcp_manager._record_server_source_hash()
    pycache = os.path.join(unity_mcp_manager.server_dir, "src", "__pycache__")
    os.makedirs(pycache, exist_ok=True)
    probe = os.path.join(pycache, "regression_probe.pyc")
    try:
        with open(probe, "wb") as fh:
            fh.write(b"irrelevant")
        assert unity_mcp_manager._server_source_changed() is False
    finally:
        os.path.exists(probe) and os.remove(probe)


def test_cached_launch_never_stamps_the_source_as_installed(isolated_hash_file):
    """SAHA ARIZASI, 2026-07-27 — bu testin var olma sebebi.

    Özet health başarısında YENİDEN HESAPLANIYORDU. Ama başarılı bir /health,
    çalışan sürecin o kaynaktan derlendiğini kanıtlamıyor: cache'ten gelen eski
    bir build de 200 döner. Sonuç, eski build'in "güncel" damgalanması ve sonraki
    açılışların cache'e düşmesiydi — sunucu bayat kod çalıştırırken her şey
    sağlıklı görünüyordu. Ölçüldü: /mcp 404 verirken /mcp/<sır> 200 veriyordu,
    yani günün tüm güvenlik değişiklikleri sessizce devre dışıydı.

    Sözleşme: cache baypas EDİLMEDİYSE damga yazılmaz.
    """
    unity_mcp_manager._pending_source_hash = None   # cache'li açılış
    unity_mcp_manager._record_server_source_hash()
    assert not isolated_hash_file.exists(), \
        "cache'li açılış kaynağı 'kurulu' diye damgaladı"


def test_source_touched_after_launch_is_not_stamped(isolated_hash_file, monkeypatch):
    """Başlatmadan SONRA kaynağa dokunulursa o değişiklik çalışan sürece
    girmemiştir; 'kurulu' sayılmamalı. Bu yüzden özet kayıt anında yeniden
    hesaplanmıyor, başlatma anındaki değer yazılıyor."""
    _simulate_nocache_launch(unity_mcp_manager)
    launched = unity_mcp_manager._pending_source_hash
    # Başlatmadan sonra kaynak değişmiş gibi yap
    monkeypatch.setattr(unity_mcp_manager, "_compute_server_source_hash", lambda: "SONRADAN-DEGISTI")
    unity_mcp_manager._record_server_source_hash()
    assert isolated_hash_file.read_text().strip() == launched
