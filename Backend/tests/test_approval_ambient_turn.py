"""K1 ADIM 3'ün backend yarısı: anahtar TAŞIYAMAYAN çağıran için mod sinyali.

Neden var: unityMCP onay kapısı ayrı bir süreçte koşuyor ve tek kullanımlık tur
anahtarını hiç görmüyor. O anahtar olmadan `should_auto_approve` her zaman
`False` döner, yani kapı **Auto modda da kart çıkarırdı** — kullanıcının açıkça
istemediği davranış (*"oto modda hiçbir sıkıntı yok zaten her şeyin otomatik
çalışması gerek"*).

Testler iki yönü de sabitliyor: sinyal açılması gerekende açılıyor mu, ve
KAPANMASI gerekende kapanıyor mu. İkincisi asıl olan — açık kalan bir sayaç,
tur bittikten sonra da oto-onay veren bir pencere demek.
"""

import pytest

from agentic.approval_policy import (
    ambient_auto_approve,
    ambient_turn,
    begin_opencode_turn,
    end_opencode_turn,
    should_auto_approve,
)


@pytest.fixture(autouse=True)
def temiz_sayac():
    """Her test sıfırdan başlasın — sayaçlar modül düzeyinde ve testler sızdırır."""
    import agentic.approval_policy as ap
    ap._AMBIENT_AUTO = 0
    ap._AMBIENT_TOPLAM = 0
    yield
    ap._AMBIENT_AUTO = 0
    ap._AMBIENT_TOPLAM = 0


@pytest.mark.parametrize("digerinin_modu", ["step", "plan"])
def test_ESZAMANLI_step_turu_oto_onayi_KAPATIYOR(digerinin_modu):
    """Arka plan güvenlik incelemesinin işaret ettiği fail-open, kapatıldı.

    İlk yazım "en az bir auto turu var mı" diye soruyordu. O hâliyle kullanıcı
    bir sekmede auto, başka bir sekmede step turu koşturduğunda, STEP turunun
    mutasyonları da sessizce oto-onaylanıyordu — yani adım modunun kapısı
    ilgisiz bir tur yüzünden kayboluyordu.

    Kapı ayrı süreçte olduğu için çağrının hangi turdan geldiği bilinemiyor;
    bilinemeyen bir şey hakkında güvenli varsayım "koşanlardan biri onay
    istiyorsa onay iste"dir.
    """
    with ambient_turn("/ws", "auto"):
        assert ambient_auto_approve() is True
        with ambient_turn("/ws2", digerinin_modu):
            assert ambient_auto_approve() is False, (
                f"{digerinin_modu} turu koşarken oto-onay açık kaldı"
            )
        # Diğer tur bitince auto turu yine kendi başına
        assert ambient_auto_approve() is True


def test_auto_turu_koserken_sinyal_ACIK():
    assert ambient_auto_approve() is False
    with ambient_turn("/ws", "auto"):
        assert ambient_auto_approve() is True
    assert ambient_auto_approve() is False, "tur bitti ama sinyal açık kaldı"


@pytest.mark.parametrize("mod", ["step", "plan", ""])
def test_auto_OLMAYAN_modlar_sinyali_acmiyor(mod):
    """Ters yön — yoksa kapı adım modunda da sessizce oto-onay verirdi."""
    with ambient_turn("/ws", mod):
        assert ambient_auto_approve() is False


def test_ISTISNA_da_sinyali_kapatiyor():
    """`with` seçilmesinin sebebi: erken çıkışta da teardown."""
    with pytest.raises(ValueError):
        with ambient_turn("/ws", "auto"):
            assert ambient_auto_approve() is True
            raise ValueError("tur patladı")
    assert ambient_auto_approve() is False


def test_IC_ICE_turlarda_ilk_biten_digerini_kapatmiyor():
    """Sayaç bool DEĞİL — bool olsaydı iç tur bitince dış turun sinyali düşerdi."""
    with ambient_turn("/ws", "auto"):
        with ambient_turn("/ws2", "auto"):
            assert ambient_auto_approve() is True
        assert ambient_auto_approve() is True, "iç tur dış turun sinyalini kapattı"
    assert ambient_auto_approve() is False


def test_sayac_sifirin_altina_inmiyor():
    """Fazladan bir çıkış, sonraki turların sinyalini borçlu bırakmamalı."""
    t = ambient_turn("/ws", "auto")
    t.__enter__()
    t.__exit__()
    t.__exit__()  # ikinci kez — olmamalı ama olursa
    with ambient_turn("/ws", "auto"):
        assert ambient_auto_approve() is True


def test_anahtarli_yol_ortam_turundan_BAGIMSIZ():
    """Dar yol geniş yoldan etkilenmemeli: anahtar yanlışsa ortam onu kurtarmaz.

    Bu ayrım kapının tamamı: `should_auto_approve` "bu çağrı O turdan geldi"
    diyor, ortam turu yalnızca "şu an bir auto turu var" diyor. İkincisi
    birincisinin yerine geçerse workspace eşleşmesi anlamını yitirirdi.
    """
    with ambient_turn("/ws", "auto"):
        assert should_auto_approve(None, "/ws") is False
        assert should_auto_approve("uydurma-anahtar", "/ws") is False


def test_opencode_turu_ortam_sinyalini_kendiliginden_ACMIYOR():
    """`begin_opencode_turn` anahtarlı yolu kurar; ortam sinyali ondan ayrı.

    Karıştırılırsa `end_opencode_turn` çağrılmayan bir yolda ortam sinyali
    sonsuza dek açık kalırdı.
    """
    token = begin_opencode_turn("/ws", "auto")
    try:
        assert should_auto_approve(token, "/ws") is True
        assert ambient_auto_approve() is False
    finally:
        end_opencode_turn(token)
