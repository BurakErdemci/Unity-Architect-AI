"""Codex onay hakemi SABİTLENİYOR — ürünün kapısı bir dış ayarla devre dışı kalmıyor.

Sahada üretilen arıza (2 Ağu 2026): kullanıcı "Adım Adım" modunda Codex'in
çalışma klasöründe dosya oluşturduğunu ve HİÇBİR onay kartı çıkmadığını gördü.

Kök sebep: ürün Codex thread'ini başlatırken `approvalsReviewer` alanını hiç
göndermiyordu. Codex bu durumda reviewer'ı kullanıcının KENDİ
`~/.codex/config.toml` dosyasından okuyor; orada `approvals_reviewer =
"auto_review"` yazıyordu ve onay isteği ürünün kapısına gelmek yerine bir LLM
alt-ajanına ("guardian") gitti. O `{"outcome":"allow"}` dedi.

⭐ Sınıfın şekli: ürünün güvenlik vaadi, ürünün KONTROL ETMEDİĞİ bir dış ayara
bağlıydı. Protokolün varsayılanı `user` olmasına GÜVENMEK yetmiyor — config
varsayılanı sessizce eziyor.

⚠️ Bu testler bayrağın GÖNDERİLDİĞİNİ doğruluyor; ISIRDIĞINI değil. Isırdığı
canlı ölçüldü (Codex 0.146.0, 3 tur: alan yokken yanıt `auto_review`, alan
varken `user`), ama o ölçüm burada tekrarlanamaz. Isırma tarafının ürün içindeki
karşılığı `CodexSession.start()`'taki yanıt doğrulaması ve o da aşağıda
sınanıyor — bayrağı gönderip yanıtı kontrol etmemek, bu deponun tekrar tekrar
ödediği bedeldi.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest


def _mock_unity_mcp(running=False):
    """`_build_cmd` unity_mcp_manager'a bakıyor; testin Unity'ye ihtiyacı yok."""
    m = MagicMock()
    m.unity_mcp_manager.is_running.return_value = running
    m.unity_mcp_manager.mcp_port = 8080
    return patch.dict(sys.modules, {
        "unity_ai_mcp": MagicMock(unity_mcp_manager=m.unity_mcp_manager),
        "unity_ai_mcp.unity_mcp_manager": m,
    })


class TestCodexExecYolu:
    """Eski `codex exec` yolu — argv üzerinden `-c` override."""

    def _cmd(self, unity_running=False):
        from providers.codex_provider import CodexProvider
        p = CodexProvider("gpt-5.6-sol")
        with _mock_unity_mcp(running=unity_running):
            return [str(x) for x in p._build_cmd("merhaba", workspace="C:/ws")]

    @pytest.mark.parametrize("unity_running", [False, True])
    def test_onay_hakemi_argvde_sabitleniyor(self, unity_running):
        # Unity'nin AÇIK ve KAPALI hâli ayrı ayrı: `unity_running` dalı argv'ye
        # başka `-c` override'ları ekliyor ve hakem satırının o dala bağlı
        # olmadığını göstermek gerekiyor.
        cmd = self._cmd(unity_running)
        assert 'approvals_reviewer="user"' in cmd, (
            "codex exec yolu onay hakemini sabitlemiyor; kullanıcının "
            "config.toml'undaki auto_review devreye girer."
        )

    def test_hakem_bir_c_override_olarak_geciyor(self):
        # Dizginin argv'de bulunması yetmez: `-c` ile eşleşmezse Codex onu
        # yapılandırma override'ı olarak okumaz ve ayar sessizce düşer.
        cmd = self._cmd()
        i = cmd.index('approvals_reviewer="user"')
        assert cmd[i - 1] == "-c"


class TestAppServerYolu:
    """Kalıcı app-server yolu — `thread/start` params'ı ve yanıt doğrulaması."""

    def test_thread_start_params_hakemi_iceriyor(self):
        # Kaynak düzeyinde nöbetçi. `start()` canlı bir Codex süreci gerektirdiği
        # için burada koşturulamıyor; ölçülebilir tek biçim bu. Alan çağrı
        # yerinden düşerse test kırılır, sessizce ölmez.
        from pathlib import Path
        import providers.codex_session as cs
        src = Path(cs.__file__).read_text(encoding="utf-8")
        assert '"approvalsReviewer": "user"' in src

    @pytest.mark.parametrize("hakem", ["auto_review", "guardian_subagent"])
    def test_hakem_user_DEGILSE_yakalaniyor(self, hakem):
        # İKİ değeri de yakalamak şart: ikisi de kararı kullanıcıdan alıp bir
        # modele veriyor. Yalnız `auto_review`'u tanıyan bir muhafız, eski
        # `guardian_subagent` adıyla sessizce atlatılırdı.
        from providers.codex_session import bul_onay_hakemi
        assert bul_onay_hakemi({"thread": {"id": "t1"}, "approvalsReviewer": hakem}) == hakem

    def test_user_bulunuyor(self):
        # Ters yön: her şeyi `None` döndüren bir mutant yukarıdaki testi geçer
        # ama ürünü kullanılamaz yapardı.
        from providers.codex_session import bul_onay_hakemi
        assert bul_onay_hakemi({"thread": {"id": "t1"}, "approvalsReviewer": "user"}) == "user"

    @pytest.mark.parametrize("govde", [
        {"thread": {"id": "t1", "approvals_reviewer": "auto_review"}},
        {"thread": {"id": "t1", "config": {"approvalsReviewer": "auto_review"}}},
        {"config": {"nested": {"approvals-reviewer": "auto_review"}}},
        {"items": [{"approvalsReviewer": "auto_review"}]},
    ])
    def test_BASKA_SEKILLERDE_gelen_hakem_de_bulunuyor(self, govde):
        # ⚠️ Bu testlerin sebebi doğrudan bir dış denetim bulgusu
        # (`fail-open-validation`, probe ile üretildi): arama iki SABİT ADRESE
        # bakıyordu, snake_case ya da bir düzey derin gelen `auto_review`
        # bulunamıyordu ve "bulamadım" dalı bilerek geçirgen olduğu için oturum
        # SESSİZCE başlıyordu. Yani gerçekte model onaylıyorken ürün hiçbir şey
        # fark etmiyordu.
        from providers.codex_session import bul_onay_hakemi
        assert bul_onay_hakemi(govde) == "auto_review"

    def test_alan_gercekten_YOKSA_None(self):
        # "Bulamadım" ile "yok" ayrımı: yalnız bu durumda `start()` uyarı basıp
        # devam ediyor. Derin arama bunu bir kaçış yolu olmaktan çıkardı.
        from providers.codex_session import bul_onay_hakemi
        assert bul_onay_hakemi({"thread": {"id": "t1"}}) is None
        assert bul_onay_hakemi({}) is None

    def test_dongusel_govde_asmiyor(self):
        # Derinlik sınırı olmasa kötü biçimli bir yanıt aramayı kilitlerdi.
        #
        # ⚠️ SÖZLEŞME DEĞİŞTİ (doğrulama turu, 2 Ağu 2026). Bu test eskiden
        # `is None` bekliyordu — yani sınırın ötesinde kalan bir `auto_review`
        # "alan yok" sayılıyor ve geçirgen dala düşüyordu. Testin kendisi bir
        # fail-open'ı SÖZLEŞME olarak kaydediyordu. Arama eksik kaldıysa yokluk
        # iddia edilemez: artık `HAKEM_BELIRSIZ` dönüyor ve çağıran turu kesiyor.
        from providers.codex_session import HAKEM_BELIRSIZ, bul_onay_hakemi
        derin = {"a": {}}
        d = derin["a"]
        for _ in range(20):
            d["a"] = {}
            d = d["a"]
        d["approvalsReviewer"] = "auto_review"
        assert bul_onay_hakemi(derin) == HAKEM_BELIRSIZ  # asmıyor, ve susmuyor

    # ⚠️ Aşağıdakiler ürünün GERÇEK doğrulama gövdesini çağırıyor. Öncesinde
    # testler yerel bir KOPYAYI çağırıyordu (dış denetim bulgusu
    # `test-double-divergence`): blok silinse ya da koşulu tersine dönse
    # dosyadaki hiçbir test kırılmıyordu. Mantığın `start()` içinden ayrı bir
    # gövdeye çıkarılmasının tek sebebi bu — kopyalanabilir bir mantık er ya da
    # geç kopyasından ayrışıyor.

    @pytest.mark.parametrize("hakem", ["auto_review", "guardian_subagent"])
    def test_GERCEK_govde_user_olmayani_REDDEDIYOR(self, hakem):
        from providers.codex_session import dogrula_onay_hakemi
        with pytest.raises(RuntimeError, match="onay hakemi"):
            dogrula_onay_hakemi({"thread": {"id": "t1"}, "approvalsReviewer": hakem})

    def test_GERCEK_govde_snake_case_i_de_REDDEDIYOR(self):
        # Derin aramanın fail-closed dalına bağlandığını ölçüyor: probe bu
        # şeklin sessizce GEÇTİĞİNİ göstermişti.
        from providers.codex_session import dogrula_onay_hakemi
        with pytest.raises(RuntimeError, match="onay hakemi"):
            dogrula_onay_hakemi({"thread": {"id": "t1", "approvals_reviewer": "auto_review"}})

    def test_GERCEK_govde_user_a_izin_veriyor(self):
        # Ters yön: her şeyi reddeden bir mutant ürünü kullanılamaz yapardı.
        from providers.codex_session import dogrula_onay_hakemi
        assert dogrula_onay_hakemi({"approvalsReviewer": "user"}) == "user"

    def test_GERCEK_govde_alan_yokken_kirmiyor_ama_UYARIYOR(self, caplog):
        import logging
        from providers.codex_session import dogrula_onay_hakemi
        with caplog.at_level(logging.WARNING):
            assert dogrula_onay_hakemi({"thread": {"id": "t1"}}) is None
        assert any("DOĞRULANAMADI" in r.message for r in caplog.records)

    def test_start_bu_govdeyi_CAGIRIYOR(self):
        # Gövde doğru olsa bile `start()` onu çağırmazsa muhafız yoktur.
        from pathlib import Path
        import providers.codex_session as cs
        src = Path(cs.__file__).read_text(encoding="utf-8")
        govde = src.split("async def start(")[1].split("\n    async def ")[0]
        assert "dogrula_onay_hakemi(" in govde


class TestHakemBelirsiz:
    """Doğrulama turu bulgusu `deep-reviewer-search-still-fail-open-on-non-string-values`.

    Ölçüt "adres" yerine "anahtar adı" olduktan sonra bile arama iki kenardan
    sessizce ``None`` dönüyordu: anahtar bulunup DEĞERİ dizge olmadığında ve
    arama derinlik sınırında kesildiğinde. ``None`` dalı bilerek geçirgen olduğu
    için ikisi de "alan yok" sayılıyor, oturum başlıyordu — yani kapatıldığı
    söylenen fail-open sınıfı hâlâ açıktı.

    Bu depoda kayıtlı ders: "bulamadım" ile "yok" aynı şey değildir.
    """

    def test_NESNE_degerli_hakem_BELIRSIZ_sayiliyor(self):
        from providers.codex_session import HAKEM_BELIRSIZ, bul_onay_hakemi
        govde = {"approvalsReviewer": {"name": "auto_review", "model": "gpt-5"}}
        assert bul_onay_hakemi(govde) == HAKEM_BELIRSIZ

    def test_NESNE_degerli_hakem_TURU_BASLATMIYOR(self):
        from providers.codex_session import dogrula_onay_hakemi
        with pytest.raises(RuntimeError, match="okunamadı"):
            dogrula_onay_hakemi({"approvalsReviewer": {"name": "auto_review"}})

    def test_derinlik_sinirinda_KESILEN_arama_BELIRSIZ(self):
        # Arama tamamlanamadıysa YOKLUK iddia edilemez.
        from providers.codex_session import HAKEM_BELIRSIZ, bul_onay_hakemi
        govde = {}
        dugum = govde
        for _ in range(20):
            dugum["a"] = {}
            dugum = dugum["a"]
        dugum["approvalsReviewer"] = "auto_review"
        assert bul_onay_hakemi(govde) == HAKEM_BELIRSIZ

    def test_kesilme_YOKSA_alan_yoklugu_hala_gecirgen(self):
        # Ters yön: her belirsizliği reddeden bir mutant, alanı hiç döndürmeyen
        # eski Codex sürümlerinde ürünü tamamen kullanılamaz yapardı. O dalın
        # geçirgen kalması BİLİNÇLİ bir karar.
        from providers.codex_session import bul_onay_hakemi
        assert bul_onay_hakemi({"thread": {"id": "t1", "model": "gpt-5"}}) is None

    def test_makul_derinlikte_hakem_HALA_bulunuyor(self):
        # Ters yön: sınırı daraltan bir mutant burada düşer.
        from providers.codex_session import bul_onay_hakemi
        govde = {"result": {"thread": {"config": {"approvals_reviewer": "auto_review"}}}}
        assert bul_onay_hakemi(govde) == "auto_review"
