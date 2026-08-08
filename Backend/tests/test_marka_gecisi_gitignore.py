"""Marka geçişi: kullanıcının `.gitignore`'undaki ESKİ blok yetim kalmamalı.

Ürün, kullanıcının Unity projesindeki `.gitignore`'a etiketli bir blok yazıyor ve
o bloğu birebir dize karşılaştırmasıyla buluyor. 8 Ağu 2026'da marka değişti
(Unity Architect AI → Gamachine), yani sahada ESKİ etiketi taşıyan `.gitignore`
dosyaları var. Yeni etiketle eşleşme aranırsa eski blok bulunamaz ve dosyaya
İKİNCİ bir blok eklenir — "tek parça silebilirsin" vaadi tam da marka temizliği
yüzünden bozulur.

⚠️ Bu testin var olma sebebi bir arıza: geçiş kodu yazıldıktan hemen sonra
otomatik yeniden adlandırma betiği `_LEGACY_*` sabitlerini de "Gamachine" yaptı,
`_LEGACY_*` ile `BLOCK_*` eşitlendi ve geçiş kendini SESSİZCE iptal etti. Koruma
kodda duruyordu, hiçbir şey korumuyordu. Bu test o eşitliği yakalar.
"""
from providers.workspace_config import (
    BLOCK_BEGIN, BLOCK_END, _LEGACY_BEGIN, _LEGACY_END, _compose,
)


def test_legacy_etiketleri_yeni_etiketlerle_AYNI_OLAMAZ():
    """En ucuz ve en çok işe yarayan iddia: eşitlerse geçiş ölü koddur."""
    assert _LEGACY_BEGIN != BLOCK_BEGIN
    assert _LEGACY_END != BLOCK_END
    # Eski etiket eski markayı taşımak ZORUNDA — yoksa sahadaki dosyalarla
    # eşleşmez. Marka adı elle yazıldı: sabitten okumak, sabit değiştiğinde
    # ölçütü de değiştirir ve test hiçbir şeyi korumaz.
    assert "Unity Architect AI" in _LEGACY_BEGIN


def test_eski_blok_KALDIRILIYOR_ve_ikinci_blok_ACILMIYOR():
    eski = (
        f"{_LEGACY_BEGIN}\n"
        "# Bu satırları Unity Architect AI ekledi\n"
        ".mcp.json\n"
        f"{_LEGACY_END}\n"
        "\n"
        "# kullanıcının kendi satırı\n"
        "Library/\n"
    )
    sonuc = _compose(eski, [".mcp.json", "opencode.json"])

    # Eski marka hiç kalmadı
    assert _LEGACY_BEGIN not in sonuc
    assert _LEGACY_END not in sonuc
    assert "Unity Architect AI" not in sonuc
    # Yeni bloktan TAM BİR tane var
    assert sonuc.count(BLOCK_BEGIN) == 1
    assert sonuc.count(BLOCK_END) == 1
    # Kullanıcının kendi satırı korundu — bu testin en pahalı arıza yönü:
    # geçiş kodu fazla kesip kullanıcının dosyasını budayabilir.
    assert "# kullanıcının kendi satırı" in sonuc
    assert "Library/" in sonuc
    # İstenen girdiler bir kez geçiyor (blok içinde), tekrarlanmıyor
    assert sonuc.count(".mcp.json") == 1
    assert sonuc.count("opencode.json") == 1


def test_eski_blok_YOKKEN_davranis_degismiyor():
    """KARŞIT YÖN: geçiş kodu, eski bloğu olmayan temiz bir dosyada hiçbir şeyi
    bozmamalı."""
    temiz = "# kullanıcı\nLibrary/\n"
    sonuc = _compose(temiz, [".mcp.json"])
    assert sonuc.count(BLOCK_BEGIN) == 1
    assert "Library/" in sonuc
    assert sonuc.count(".mcp.json") == 1
