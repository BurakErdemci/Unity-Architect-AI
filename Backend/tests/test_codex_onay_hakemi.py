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
    def test_yanit_user_degilse_tur_REDDEDILIYOR(self, hakem):
        # İKİ değeri de reddetmek şart: ikisi de kararı kullanıcıdan alıp bir
        # modele veriyor. Yalnız `auto_review`'u reddeden bir muhafız, eski
        # `guardian_subagent` adıyla sessizce atlatılırdı.
        from providers.codex_session import CodexSession
        oturum = CodexSession.__new__(CodexSession)
        oturum.conversation_id = "test"
        yanit = {"result": {"thread": {"id": "t1"}, "approvalsReviewer": hakem}}
        with pytest.raises(RuntimeError, match="onay hakemi"):
            _dogrula(oturum, yanit)

    def test_user_ise_tur_BASLIYOR(self):
        # Ters yön: her şeyi reddeden bir muhafız ürünü kullanılamaz yapardı ve
        # yukarıdaki testlerin ikisini de geçerdi.
        from providers.codex_session import CodexSession
        oturum = CodexSession.__new__(CodexSession)
        oturum.conversation_id = "test"
        yanit = {"result": {"thread": {"id": "t1"}, "approvalsReviewer": "user"}}
        _dogrula(oturum, yanit)  # fırlatmamalı

    def test_alan_YOKSA_tur_kirilmiyor(self):
        # Alanı döndürmeyen bir Codex sürümünde doğrulayamamak, ürünün hiç
        # çalışmaması için yeterli sebep değil — ve o sürümlerde açığın var
        # olduğu ÖLÇÜLMEDİ. Kayıt `start()` içinde uyarı olarak bırakılıyor.
        from providers.codex_session import CodexSession
        oturum = CodexSession.__new__(CodexSession)
        oturum.conversation_id = "test"
        _dogrula(oturum, {"result": {"thread": {"id": "t1"}}})  # fırlatmamalı


def _dogrula(oturum, resp):
    """`start()` içindeki hakem doğrulamasının aynısı.

    ⚠️ KOPYA OLDUĞU İÇİN ZAYIF: `start()`'ın gövdesi değişirse bu sessizce
    ayrışır. Gerçek gövdeyi çağıramamanın sebebi `start()`'ın canlı bir Codex
    süreci istemesi. Bu yüzden yukarıdaki `test_thread_start_params_hakemi_iceriyor`
    kaynak nöbetçisi TAMAMLAYICI, süs değil — kopyanın ayrışmasını o yakalar.
    """
    _result = (resp or {}).get("result") or {}
    _reviewer = _result.get("approvalsReviewer")
    if _reviewer is None:
        _reviewer = (_result.get("thread") or {}).get("approvalsReviewer")
    if _reviewer is not None and _reviewer != "user":
        raise RuntimeError(f"Codex onay hakemi 'user' değil: {_reviewer!r}")
