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
    unity_mcp_manager._record_server_source_hash()
    assert isolated_hash_file.exists()
    assert unity_mcp_manager._server_source_changed() is False


def test_source_edit_is_detected(isolated_hash_file):
    """Bu yön olmadan cache bayat kod çalıştırır — bayrağın var olma sebebi."""
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
    unity_mcp_manager._record_server_source_hash()
    monkeypatch.setattr(unity_mcp_manager, "_compute_server_source_hash", lambda: "")
    assert unity_mcp_manager._server_source_changed() is True


def test_pycache_is_ignored(isolated_hash_file, tmp_path):
    """__pycache__ her koşumda değişir; sayılsaydı cache hiç kullanılamazdı."""
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
