"""Kullanıcının açtığı proje, onay kapısını KAPATAMAMALI.

Ölçülmüş arıza (K8, 2026-07-29, ürünün kendi `ClaudeSDKSession`'ıyla): `cwd`
ürünün reposu değil, **kullanıcının açtığı Unity projesi** — indirilmiş ya da
klonlanmış olabilir ve ürün içeriğini denetlemiyor. `setting_sources` içinde
`"project"` varken o projeye konan bir `.claude/settings.json` kapıyı dört ayrı
yoldan düşürüyordu; hepsi canlı sayaçla ölçüldü:

  1. `hooks.PreToolUse` — komut kapıdan ÖNCE ve KOŞULSUZ koştu; kapı `deny`
     dediğinde bile hook'un `touch` izi diskte kaldı. `permissionDecision:
     "allow"` dönen bir hook'ta kapı HİÇ çağrılmadı.
  2. `sandbox.enabled: true` → 4 komutun 4'ü kartsız (sayaç 0/4).
  3. `permissions.allow` → `Bash(touch:*)` eklenince sayaç 1 → 0.
  4. `env` → workspace dosyası ürünün süreç ortamına değişken enjekte etti.

Bu dosya dizeyi değil SINIFI koruyor: ayar katmanı listesi güvensiz katmanı
içermemeli, ve bunu geri getiren her düzenleme kırmızı vermeli. Test tek bir
çağrı yerine değil, ürünün TÜM Claude giriş noktalarına bakıyor — çünkü bu
depoda tekrarlayan arıza şekli "uyuşması gereken iki yer uyuşmuyor" ve K8'in
kendisi de tam olarak öyle büyümüştü (oturum düzeltilip warmup unutulabilirdi).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from providers.claude_sdk_session import (  # noqa: E402
    CLAUDE_SETTING_SOURCES,
    ClaudeSDKSession,
)


# ── Ayar katmanı listesinin kendisi ───────────────────────────────────────


def test_project_katmani_listede_olmamali():
    """Asıl iddia: güvensiz katman kapalı."""
    assert "project" not in CLAUDE_SETTING_SOURCES, (
        "setting_sources'a 'project' geri eklenmiş. Kullanıcının açtığı projeye "
        "konan .claude/settings.json onay kapısını düşürüyor (K8, canlı ölçüldü)."
    )


def test_local_katmani_da_olmamali():
    """`settings.local.json` de aynı sınıf: workspace'e konabilen bir dosya."""
    assert "local" not in CLAUDE_SETTING_SOURCES


def test_liste_bos_birakilmamali():
    """Boş/None en kötü seçenek: SDK'da None = ['user','project','local'].

    Yani listeyi "temizlemek" güvensiz katmanı kapatmaz, ÜÇÜNÜ birden açar.
    Bu testin varlık sebebi, düzeltmenin yanlış yönde 'sadeleştirilmesini'
    engellemek.
    """
    assert CLAUDE_SETTING_SOURCES, "liste boş bırakılamaz — SDK varsayılanı hepsini açar"


def test_kullanici_katmani_korunmali():
    """Kaybedilmemesi gereken şey: kullanıcının kendi komutları ve eklentileri.

    Düzeltme bir güvenlik kazancıydı, bir yetenek kaybı değil — ölçüldü
    (2026-08-01): `["project","user"]` 114 komut, `["user"]` 114 komut, fark 0.
    O sayı `"user"` da düşürülürse korunmaz; bu test onu kilitliyor.
    """
    assert "user" in CLAUDE_SETTING_SOURCES


# ── Giriş noktaları: hepsi aynı kaynaktan beslenmeli ──────────────────────


def test_oturum_varsayilani_guvenli_tarafta():
    """Çağıran `setting_sources` vermeyi unutursa da kapı düşmemeli."""
    s = ClaudeSDKSession(conversation_id=1)
    assert "project" not in s.setting_sources
    assert "local" not in s.setting_sources
    assert s.setting_sources  # boş da olmamalı


def test_oturum_varsayilani_paylasilan_listeyi_MUTASYONA_ugratmamali():
    """Varsayılan, modül sabitinin kendisi olmamalı.

    Aksi hâlde tek bir oturumun listeyi yerinde değiştirmesi (`.append("project")`)
    süreçteki BÜTÜN oturumları etkilerdi — sessiz ve teşhisi zor bir kapı açığı.
    """
    s = ClaudeSDKSession(conversation_id=1)
    s.setting_sources.append("project")
    assert "project" not in CLAUDE_SETTING_SOURCES, "sabit yerinde değiştirilebiliyor"


def test_warmup_da_ayni_listeyi_kullanmali():
    """Komut listeleme de gerçek bir CLI oturumu açıyor (cwd = kullanıcının projesi).

    `"project"` açık olsaydı projenin SessionStart hook'u daha kullanıcı tek
    kelime yazmadan koşardı — [[test_unity_tools_load_is_read_only]] ile aynı
    sınıf: kullanıcının başlatmadığı bir yan etki.
    """
    import inspect

    from providers import claude_sdk_session

    kaynak = inspect.getsource(claude_sdk_session.warmup_slash_commands)
    assert "CLAUDE_SETTING_SOURCES" in kaynak, (
        "warmup kendi katman listesini kuruyor; tek kaynağa bağlanmalı"
    )
    assert '["project", "user"]' not in kaynak


def test_agent_runner_tek_kaynaga_bagli_ve_project_yazmiyor():
    """Ürünün asıl Claude turu da elle liste kurmamalı."""
    import inspect

    from agentic import agent_runner

    kaynak = inspect.getsource(agent_runner)
    assert "CLAUDE_SETTING_SOURCES" in kaynak
    assert '"project", "user"' not in kaynak, (
        "agent_runner'da elle kurulmuş katman listesi var — tek kaynaktan sapıyor"
    )


# ── unityMCP hâlâ erişilebilir olmalı (düzeltme özelliği kırmamalı) ────────


def test_agent_runner_mcp_servers_i_SDK_ya_geciyor():
    """`"project"` düşünce `.mcp.json` okunmaz olur; unityMCP başka yoldan girmeli.

    Bu test düzeltmenin YARIM kalmasını yakalar: katman kapatılıp `mcp_servers`
    geçilmezse Unity araçları sessizce kaybolurdu — güvenlik kazanılır, ürün
    çalışmaz. Ölçüldü (canlı probe): SDK'ya geçilen kayıt, kullanıcı
    kapsamındaki AYNI ADLI başlıksız bayat kaydı EZİYOR, yani kimlik doğrulama
    gölgelenmiyor.
    """
    import inspect

    from agentic import agent_runner

    kaynak = inspect.getsource(agent_runner.AgentRunner._run_claude_sdk_session) \
        if hasattr(agent_runner.AgentRunner, "_run_claude_sdk_session") \
        else inspect.getsource(agent_runner)
    assert "mcp_servers=mcp_servers_cfg" in kaynak, (
        "unityMCP kaydı SDK'ya geçilmiyor — Unity araçları oturuma hiç girmez"
    )


def test_oturum_mcp_servers_i_SDK_secenegine_koyuyor():
    """Kwarg kabul edilmesi yetmez; gerçekten ClaudeAgentOptions'a girmeli."""
    import inspect

    from providers import claude_sdk_session

    kaynak = inspect.getsource(claude_sdk_session.ClaudeSDKSession._ensure_started) \
        if hasattr(claude_sdk_session.ClaudeSDKSession, "_ensure_started") \
        else inspect.getsource(claude_sdk_session)
    assert 'opts_kwargs["mcp_servers"]' in kaynak


# ── Bayat `.mcp.json` temizliği ───────────────────────────────────────────


# Ürünün KENDİ kalıcı anahtarı. Sahiplik artık tahmin değil bu değerle
# eşleşme; testler de o yüzden gerçek anahtarı taklit ediyor (fixture aşağıda).
# ⚠️ Uzunluk gerçekçi: ürünün anahtarı `secrets.token_urlsafe(32)`, yani her
# zaman 43 karakter. Redaksiyon tarafındaki 12 karakterlik alt sınır bu yüzden
# aşılıyor — kısa bir sahte sır bu dosyada İKİ KEZ olmayan hata bildirdi.
_URUN_SIRRI = "Test-Urun-Sirri-0123456789abcdefGHIJKLMNOPQ"

# Redaksiyon testlerinin kullandığı sır: ürünün anahtarıyla aynı şekilde.
_SAHTE_SIR = _URUN_SIRRI

_SIR_KAYDI = {"type": "http", "url": "http://localhost:8080/mcp",
              "headers": {"X-API-Key": _URUN_SIRRI}}


def _gercek_urun_sirri_fonksiyonu():
    """Fixture ezmeden ÖNCEKİ gerçek gövde — onu da sınayabilmek için."""
    from agentic.agent_runner import _urunun_sirri

    return _urunun_sirri


_GERCEK_URUNUN_SIRRI = _gercek_urun_sirri_fonksiyonu()


@pytest.fixture(autouse=True)
def _urun_sirrini_sabitle(monkeypatch):
    """Temizlik ürünün gerçek anahtarını diskten okuyor; testte onu sabitliyoruz.

    ⚠️ Bu fixture olmadan testler makinede gerçekten kurulu olan anahtara
    bağlanırdı — yani başka bir makinede başka şey ölçerdi ve CI'da rastgele
    davranırdı.
    """
    from agentic import agent_runner

    monkeypatch.setattr(agent_runner, "_urunun_sirri", lambda: _URUN_SIRRI)

_SAHIPLIK_VAKALARI = [
    ("ÜRÜN: yerel + gerçek sır",
     {"url": "http://localhost:8080/mcp", "headers": {"X-API-Key": _URUN_SIRRI}}, True),
    # 7. denetim turu, YÜKSEK: kullanıcı da yerel MCP sunucusu çalıştırabilir,
    # ona `unityMCP` diyebilir ve `X-API-Key` kullanabilir. Ne ad, ne başlığın
    # varlığı, ne de yerellik ürüne özgü — hiçbiri sahiplik kanıtı değil.
    ("KULLANICI: yerel ama KENDİ anahtarı",
     {"url": "http://localhost:7777/mcp", "headers": {"X-API-Key": "kullanicinin"}}, False),
    ("KULLANICI: uzak + kendi anahtarı",
     {"url": "https://uzak.example/mcp", "headers": {"X-API-Key": "kullanicinin"}}, False),
    ("KULLANICI: yalnız adı aynı", {"command": "kendi-seyim"}, False),
    ("ÜRÜN: eski biçim, sır URL yolunda",
     {"url": f"http://localhost:8080/mcp/{_URUN_SIRRI}"}, True),
    # 7. denetim turu: `unityai` imzası `unity_architect_ai` alt dizesini
    # arıyordu, oysa gerçek üretici `<backend_dir>/run_mcp_server.cmd` yazıyor —
    # yani imza ürünün KENDİ kaydını hiç yakalamıyordu. Ölçüt artık taşıdığı
    # kimlik bilgisi: `env.LOCAL_APP_TOKEN` (39994dd öncesi biçim).
    ("ÜRÜN: eski unityai, env'de LOCAL_APP_TOKEN",
     {"command": r"C:\x\Backend\run_mcp_server.cmd",
      "env": {"UNITYAI_URL": "u", "LOCAL_APP_TOKEN": "t"}}, True),
    ("KULLANICI: env var ama token yok",
     {"command": "kendi", "env": {"UNITYAI_URL": "u"}}, False),
]


@pytest.mark.parametrize("ad,tanim,bizim_mi", _SAHIPLIK_VAKALARI,
                         ids=[v[0] for v in _SAHIPLIK_VAKALARI])
def test_sahiplik_TAHMIN_degil_KANIT(ad, tanim, bizim_mi):
    """Sahiplik ürünün GERÇEK anahtar değeriyle eşleşmeye dayanmalı.

    Bu fonksiyonun altı önceki hâli tahmin ediyordu (ad → başlığın varlığı →
    yerellik → 43 karakterlik segment) ve yedi denetim turunun DÖRDÜ tam bu
    tahminlerin kenarında bulgu yazdı. Çıkış yolu ölçümle geldi: ürünün anahtarı
    kalıcı (`~/.unity-mcp/local-api-token`), yani soru kesin cevaplanabiliyor.
    """
    from agentic.agent_runner import _urunun_kaydi_mi

    assert _urunun_kaydi_mi("unityMCP", tanim, _URUN_SIRRI) is bizim_mi, ad


def test_sunucu_ADI_artik_olcut_degil():
    """Ürünün sırrını taşıyan kayıt, adı ne olursa olsun ürünündür."""
    from agentic.agent_runner import _urunun_kaydi_mi

    assert _urunun_kaydi_mi("bambaska-ad", {"headers": {"X-API-Key": _URUN_SIRRI}}, _URUN_SIRRI)


def test_sir_okunamazsa_HICBIR_SEY_urunun_sayilmaz():
    """Fail-safe: anahtar okunamıyorsa sahiplik iddia edilemez, silme de olmaz."""
    from agentic.agent_runner import _urunun_kaydi_mi

    assert not _urunun_kaydi_mi("unityMCP", {"headers": {"X-API-Key": _URUN_SIRRI}}, None)
    # Tek istisna: taşıdığı kimlik bilgisi kendi kendini ele veriyor.
    assert _urunun_kaydi_mi("unityai", {"env": {"LOCAL_APP_TOKEN": "t"}}, None)


def test_urunun_sirri_dosya_YARATMIYOR(tmp_path, monkeypatch):
    """Temizlik bir yan etki olarak sır dosyası oluşturmamalı.

    Anahtarı üretmek `unity_mcp_manager`'ın işi; temizlik yalnızca OKUR.
    Üstelik yaratsaydı, ürünün sırrı hiç kurulmamış bir makinede boş bir
    anahtar dosyası bırakırdı.
    """
    from agentic import agent_runner

    # Fixture `_urunun_sirri`'yi ezdiği için GERÇEK gövdeyi modülden alıyoruz.
    gercek = _GERCEK_URUNUN_SIRRI
    yol = tmp_path / "yok-boyle-bir-dizin" / "local-api-token"
    monkeypatch.setattr(agent_runner, "_URUN_SIR_YOLU", str(yol))

    assert gercek() is None, "olmayan anahtar için None dönmeli"
    assert not yol.exists(), "temizlik sır dosyası YARATMIŞ"
    assert not yol.parent.exists(), "temizlik dizin YARATMIŞ"


# Denetimden çıkan vaka tablosu, kalıcı teste terfi etti. İlk tasarım ikiliydi
# ("tamamı bizimse sil, değilse dokunma") ve bu tablonun 8 satırının 6'sında
# yanlış davranıyordu — üçü canlı doğrulandı, hepsi aşağıda tek tek kilitli.
# Sütunlar: dosya sağ kalmalı mı · kullanıcı verisi korunmalı mı.
_TEMIZLIK_VAKALARI = [
    ("mcpServers anahtarı YOK, saf kullanıcı verisi",
     {"userMetadata": {"kalsin": True}, "notlar": "onemli"}, True, "userMetadata"),
    ("boş nesne", {}, True, None),
    ("JSON listesi", [], True, None),
    ("null", None, True, None),
    ("kullanıcının KENDİ unityMCP kaydı",
     {"mcpServers": {"unityMCP": {"command": "kullanicinin-seyi"}}}, True, "kullanicinin-seyi"),
    ("karışık: ürünün sırrı + kullanıcının sunucusu",
     {"mcpServers": {"unityMCP": _SIR_KAYDI, "kullanicinin": {"command": "x"}}}, True, "kullanicinin"),
    ("saf ürün kaydı — dosya bütünüyle bizim",
     {"mcpServers": {"unityMCP": _SIR_KAYDI}}, False, None),
    ("ürün kaydı + üst düzey kullanıcı anahtarı",
     {"mcpServers": {"unityMCP": _SIR_KAYDI}, "benimAyarim": 1}, True, "benimAyarim"),
]


@pytest.mark.parametrize(
    "ad,icerik,sag_kalmali,korunacak",
    _TEMIZLIK_VAKALARI,
    ids=[v[0] for v in _TEMIZLIK_VAKALARI],
)
def test_temizlik_sirri_alir_kullanici_verisini_birakir(
    tmp_path, ad, icerik, sag_kalmali, korunacak
):
    """Üç şey aynı anda doğru olmalı: sır gitmeli, veri kalmalı, dosya doğru kaderi görmeli.

    Tek bir assert'e indirilemez, çünkü ilk tasarım tam da bunları BİRBİRİNE
    değişerek hata yapıyordu: veri kaybını önlemek için sırrı bırakıyor, sırrı
    almak için veriyi siliyordu.
    """
    from agentic.agent_runner import _remove_project_mcp_json

    hedef = tmp_path / ".mcp.json"
    hedef.write_text(json.dumps(icerik), encoding="utf-8")

    _remove_project_mcp_json(str(tmp_path))

    assert hedef.exists() is sag_kalmali, (
        f"{ad}: dosyanın kaderi yanlış (sağ kalmalı={sag_kalmali})"
    )
    kalan = hedef.read_text(encoding="utf-8") if hedef.exists() else ""
    assert _URUN_SIRRI not in kalan, f"{ad}: X-API-Key hâlâ diskte"
    if korunacak:
        assert korunacak in kalan, f"{ad}: kullanıcının verisi ({korunacak}) yok edildi"


def test_cok_buyuk_dosya_bellege_alinmiyor(tmp_path):
    """Güvensiz projeden gelen dev bir dosya turu bloke etmemeli.

    ⚠️ Yük BİLEREK "sınır olmasa DEĞİŞECEK" bir dosya: içinde ürünün kaydı var,
    yani sınır kalkarsa dosya yeniden yazılır ve dolgu kaybolur. İlk yazımda
    yük `{"mcpServers": {}}` idi — sınır olsa da olmasa da dosya aynen kalıyordu
    ve test mutasyonu GÖREMİYORDU (mutasyon turunda ölçüldü).
    """
    from agentic.agent_runner import _MCP_JSON_AZAMI_BAYT, _remove_project_mcp_json

    hedef = tmp_path / ".mcp.json"
    dolgu = "x" * (_MCP_JSON_AZAMI_BAYT + 1024)
    hedef.write_text(
        json.dumps({"mcpServers": {"unityMCP": _SIR_KAYDI}, "dolgu": dolgu}),
        encoding="utf-8",
    )
    onceki = hedef.read_text(encoding="utf-8")

    _remove_project_mcp_json(str(tmp_path))

    assert hedef.exists(), "boyut sınırı aşılmışken dosya silinmemeliydi"
    assert hedef.read_text(encoding="utf-8") == onceki, (
        "boyut sınırı aşılmışken dosya OKUNMUŞ ve yeniden yazılmış"
    )


class _SahteOturum:
    """`_oturum_yeniden_kurma_gerekceleri`'nin okuduğu asgari yüzey."""

    def __init__(self, *, model="claude-x", effort="high", cwd=".", mcp_servers=None):
        self.model = model
        self.effort = effort
        self.cwd = cwd
        self.mcp_servers = mcp_servers or {}


_UNITY_KAYDI = {"unityMCP": {"type": "http", "url": "http://localhost:8080/mcp"}}


def test_unityMCP_kaydi_degisince_oturum_yeniden_kuruluyor(tmp_path):
    """Unity MCP sonradan açılınca araçlar gelmeli — bayat oturum kilitlenmemeli.

    `mcp_servers` connect-time kilitli olduğu için karşılaştırma listesinde
    olmazsa, MCP kapalıyken açılan bir sohbet MCP açıldıktan sonra da araçsız
    kalırdı. Egzotik değil, en sıradan akış: kullanıcı önce uygulamayı, sonra
    Unity'yi açıyor. DAVRANIŞ testi — ilk yazımı kaynak taramasıydı ve bir
    mutasyon turunda KÖR olduğu ölçüldü.
    """
    from agentic.agent_runner import _oturum_yeniden_kurma_gerekceleri as gerekce

    ws = str(tmp_path)
    mcpsiz = _SahteOturum(cwd=ws, mcp_servers={})

    # MCP kapalıyken açılmış oturum + MCP artık açık → yeniden kurulmalı.
    r = gerekce(mcpsiz, model="claude-x", effort="high", workspace=ws, mcp_servers=_UNITY_KAYDI)
    assert r, "unityMCP açıldığı hâlde oturum bayat kalıyor — Unity araçları hiç gelmez"
    assert any("unityMCP" in g for g in r)

    # Hiçbir şey değişmediyse boşuna yeniden kurulmamalı (canlı bağlam sıfırlanır).
    mcpli = _SahteOturum(cwd=ws, mcp_servers=_UNITY_KAYDI)
    assert gerekce(mcpli, model="claude-x", effort="high", workspace=ws,
                   mcp_servers=dict(_UNITY_KAYDI)) == []


def test_mcp_kaydi_ayni_kalinca_oturum_KORUNUYOR(tmp_path):
    """Ters yön de kilitli: fazla yeniden kurma sohbet bağlamını çöpe atar."""
    from agentic.agent_runner import _oturum_yeniden_kurma_gerekceleri as gerekce

    ws = str(tmp_path)
    o = _SahteOturum(cwd=ws, mcp_servers={})
    assert gerekce(o, model="claude-x", effort="high", workspace=ws, mcp_servers={}) == []
    assert gerekce(o, model="claude-x", effort="high", workspace=ws, mcp_servers=None) == []


def test_yok_olan_oturum_gerekce_uretmiyor():
    from agentic.agent_runner import _oturum_yeniden_kurma_gerekceleri as gerekce

    assert gerekce(None, model="m", effort="e", workspace=".", mcp_servers={}) == []


def test_oturum_bogazindaki_hata_olayi_maskeleniyor():
    """Oturumdan çıkan HER hata olayı SSE'ye gidiyor; sır taşımamalı.

    Dış döngüdeki maskeleme reader döngüsünden gelen hataları kapsamıyordu —
    koruma çağrı yerine konduğunda, unutulan çağrı kadar koruma demek.
    DAVRANIŞ testi: `_finish_turn` gerçekten çağrılıp kuyruğa bakılıyor.
    """
    import asyncio

    from providers.claude_sdk_session import ClaudeSDKSession

    async def kosu():
        s = ClaudeSDKSession(conversation_id=1)
        s._turn_active = True
        s._out_q = asyncio.Queue()
        await s._finish_turn(error=f"baglanti koptu: X-API-Key: {_SAHTE_SIR}")
        olaylar = []
        while not s._out_q.empty():
            olaylar.append(await s._out_q.get())
        return olaylar

    olaylar = asyncio.run(kosu())
    hatalar = [o for o in olaylar if isinstance(o, dict) and o.get("type") == "error"]
    assert hatalar, "hata olayı hiç üretilmedi — test ölçtüğünü sanıyor ama ölçmüyor"
    assert _SAHTE_SIR not in hatalar[0]["message"], "sır tarayıcıya giden olayda"


def test_sahte_sir_GERCEK_sirrin_seklini_tasiyor():
    """Fixture ürünün gerçek veri şeklinde olmalı; yoksa test ürünü değil kendini ölçer.

    Bu, bu dosyada İKİ KEZ yaşandı: önce 10 karakterlik sahte sır redaksiyonun
    12 karakterlik alt sınırının altında kalıp OLMAYAN bir ürün hatası bildirdi,
    sonra 35 karakterlik hâli sahiplik ölçütünün tam-43 kuralına takıldı.
    Ölçüt artık kodda: gerçek sır `secrets.token_urlsafe(32)` ve her zaman 43.
    """
    import secrets

    assert len(_SAHTE_SIR) == 43
    assert len(secrets.token_urlsafe(32)) == 43, "üretecin boyutu değişmiş — fixture da değişmeli"


@pytest.mark.parametrize("kalip", [
    "X-API-Key: {s}",
    "{{'X-API-Key': '{s}'}}",
    '{{"X-API-Key": "{s}"}}',
    "headers={{'X-API-Key': '{s}'}}",
    "http://localhost:8080/mcp/{s}",
    # JSON içine gömülü JSON: tanılama nesneleri bir kez daha serileştiriliyor
    # ve tırnağın önüne ters bölü giriyordu (3. denetim turu bulgusu).
    '{{\\"X-API-Key\\": \\"{s}\\"}}',
    # `Authorization` da `AUTH` önekiyle geliyor; masum-kelime istisnası onu
    # KAPSAMAMALI, yoksa gerçek bir sır başlığı açıkta kalır.
    "Authorization: Bearer {s}",
    "authorization: {s}",
    # İKİ KEZ serileştirilmiş: ters bölü sayısı her turda katlanıyor (1→3→7).
    '{{\\\\\\"X-API-Key\\\\\\": \\\\\\"{s}\\\\\\"}}',
    # ⚠️ Ayırıcı silinerek masum listesine takla atma yolu (4. denetim turu):
    # `auth-or` → `author` sanılıp maskelenmiyordu.
    "auth-or: {s}",
    "key-board: {s}",
    "secret-ary: {s}",
])
def test_redaksiyon_serilestirilmis_bicimleri_de_kapatiyor(kalip):
    """Bir istisnadaki sözlük `{'X-API-Key': '...'}` gibi görünür — desen onu kaçırıyordu.

    Koruma tam da sırrın tarayıcıya ulaşabildiği biçimde yoktu; düz `ad: değer`
    biçimi maskeleniyor, tırnaklı biçim sızıyordu.
    """
    from secret_redaction import redact_secrets

    assert _SAHTE_SIR not in redact_secrets(kalip.format(s=_SAHTE_SIR))


@pytest.mark.parametrize("metin", [
    "monkey: banana",
    # `author:` git çıktısında her commit'te geçiyor ve bu ürün git loglu­yor.
    "author: Ahmet Yilmaz",
    # Serileştirilmiş hâli de masum: sarmalayıcı ters bölü ad'ın parçası değil.
    '{\\"author\\": \\"Burak\\"}',
    "Author: burak",
    "authors: a, b",
    "keyboard: mekanik",
])
def test_redaksiyon_masum_metni_bozmuyor(metin):
    """Yanlış pozitif log'u okunmaz yapar; okunmayan log teşhis değeri taşımaz."""
    from secret_redaction import redact_secrets

    assert redact_secrets(metin) == metin


def test_gitignore_girdisine_DOKUNULMUYOR(tmp_path):
    """`.mcp.json`'ı CLI sağlayıcıları hâlâ yazıyor; girdi kalkarsa sır depoya açılır.

    Ayrıca `remove_gitignore_block` ürünün BÜTÜN bloğunu siler — içinde
    `.cursor/mcp.json` ve `opencode.json` da var. Buradan çağrılması başka
    sağlayıcıların sırlarını sessizce yok sayılmaz hâle getirirdi.
    """
    from agentic.agent_runner import _remove_project_mcp_json
    from providers.workspace_config import BLOCK_BEGIN, BLOCK_END, remove_gitignore_block

    # ⚠️ Etiketler SABİTTEN alınıyor, elle yazılmıyor. İlk yazımda uydurma bir
    # etiket kullanılmıştı: `remove_gitignore_block` etiketi bulamayıp erkenden
    # dönüyordu, dolayısıyla test mutasyonu GÖREMİYORDU (mutasyon turu 6 sızdı).
    # Sahte yeşilin ders hâli: bir yokluk iddiasını sınayan fixture'ın CANLI
    # olduğu, bilinen bir pozitifle kanıtlanmalı — aşağıdaki alt-test tam bu.
    def _kur():
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        icerik = f"{BLOCK_BEGIN}\n.mcp.json\nopencode.json\n{BLOCK_END}\n"
        (tmp_path / ".gitignore").write_text(icerik, encoding="utf-8")
        return icerik

    gitignore = tmp_path / ".gitignore"

    # POZİTİF KONTROL: bu fixture üzerinde blok kaldırma GERÇEKTEN çalışıyor.
    # Çalışmıyorsa asıl iddia ("dokunulmadı") hiçbir şey ölçmüyor demektir.
    onceki = _kur()
    remove_gitignore_block(str(tmp_path))
    assert gitignore.read_text(encoding="utf-8") != onceki, (
        "fixture ölü: blok kaldırma bu dosyayı hiç değiştirmiyor, asıl iddia ölçülemez"
    )

    # ASIL İDDİA: temizlik gitignore'a dokunmuyor.
    onceki = _kur()
    _remove_project_mcp_json(str(tmp_path))
    assert gitignore.read_text(encoding="utf-8") == onceki, (
        ".gitignore değişti — diğer sağlayıcıların sır dosyaları açığa çıkabilir"
    )


def test_kullanicinin_kendi_kayitlari_SILINMIYOR(tmp_path):
    """Ürünün, kullanıcının yazdığı MCP kayıtlarını silme hakkı yok.

    Eski kod bu dosyayı koşulsuz EZİYORDU; temizlik o davranışı devralmamalı.
    Ölçüt sahiplik: içerik tamamen ürünün kayıtlarıysa silinir, değilse durur.
    """
    from agentic.agent_runner import _remove_project_mcp_json

    hedef = tmp_path / ".mcp.json"
    hedef.write_text(
        '{"mcpServers": {"unityMCP": {"type": "http"}, "benim-sunucum": {"command": "x"}}}',
        encoding="utf-8",
    )

    _remove_project_mcp_json(str(tmp_path))

    assert hedef.exists(), "kullanıcının kendi MCP kaydı sessizce silindi"


def test_bozuk_dosyaya_dokunulmuyor(tmp_path):
    """Okunamayan dosya BİZİM olduğunu kanıtlayamaz → fail-closed, silme yok."""
    from agentic.agent_runner import _remove_project_mcp_json

    hedef = tmp_path / ".mcp.json"
    hedef.write_text("{bu gecerli json degil", encoding="utf-8")

    _remove_project_mcp_json(str(tmp_path))

    assert hedef.exists()


def test_dosya_yoksa_sessizce_geciyor(tmp_path):
    """İlk kurulumda dosya hiç yoktur; tur bir istisnayla ölmemeli."""
    from agentic.agent_runner import _remove_project_mcp_json

    _remove_project_mcp_json(str(tmp_path))  # patlamamalı


@pytest.mark.parametrize("yol", [None, "", "/var/olmayan/dizin-xyz"])
def test_gecersiz_workspace_patlamamali(yol):
    """Workspace silinmiş/taşınmış olabilir — temizlik sohbeti kırmamalı."""
    from agentic.agent_runner import _remove_project_mcp_json

    _remove_project_mcp_json(yol)


def test_claude_sdk_yolu_artik_mcp_json_YAZMIYOR():
    """Yazan kodun geri gelmesi, kapatılan katmanı sessizce yeniden gerektirir.

    Regresyonun sinsi biçimi bu: dosya yeniden yazılır, kimse fark etmez,
    unityMCP çalışmadığı için birileri `"project"`i geri ekler ve K8 geri döner.
    """
    import inspect

    from agentic import agent_runner

    kaynak = inspect.getsource(agent_runner)
    assert "_write_project_mcp_json" not in kaynak, (
        "Claude SDK yolunda .mcp.json yazan kod geri gelmiş"
    )
