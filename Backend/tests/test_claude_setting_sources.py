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


_SIR_KAYDI = {"type": "http", "headers": {"X-API-Key": "SIR-BURADA"}}

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
    assert "SIR-BURADA" not in kalan, f"{ad}: X-API-Key hâlâ diskte"
    if korunacak:
        assert korunacak in kalan, f"{ad}: kullanıcının verisi ({korunacak}) yok edildi"


def test_cok_buyuk_dosya_bellege_alinmiyor(tmp_path):
    """Güvensiz projeden gelen dev bir dosya turu bloke etmemeli."""
    from agentic.agent_runner import _MCP_JSON_AZAMI_BAYT, _remove_project_mcp_json

    hedef = tmp_path / ".mcp.json"
    dolgu = "x" * (_MCP_JSON_AZAMI_BAYT + 1024)
    hedef.write_text(json.dumps({"mcpServers": {}, "dolgu": dolgu}), encoding="utf-8")

    _remove_project_mcp_json(str(tmp_path))

    assert hedef.exists(), "boyut sınırı aşılmışken dosyaya dokunulmamalıydı"


def test_unityMCP_kaydi_degisince_oturum_yeniden_kuruluyor():
    """Unity MCP sonradan açılınca araçlar gelmeli — bayat oturum kilitlenmemeli.

    `mcp_servers` connect-time kilitli olduğu için karşılaştırma listesinde
    olmazsa, MCP kapalıyken açılan bir sohbet MCP açıldıktan sonra da araçsız
    kalırdı. Egzotik değil, en sıradan akış: kullanıcı önce uygulamayı, sonra
    Unity'yi açıyor.
    """
    import inspect

    from agentic import agent_runner

    kaynak = inspect.getsource(agent_runner.AgentRunner._run_claude_session)
    assert "_existing.mcp_servers" in kaynak, (
        "oturum yeniden kurma ölçütü unityMCP kaydını görmüyor"
    )


def test_sse_hata_metni_redaksiyondan_geciyor():
    """Tarayıcıya giden hata metni sırrı taşımamalı.

    Log tarafı global filtreyle korunuyor ama o filtre bu olay nesnesine
    uğramıyordu — koruma sanılan yerde yoktu.
    """
    import inspect

    from agentic import agent_runner

    kaynak = inspect.getsource(agent_runner.AgentRunner._run_claude_session)
    assert "Claude session hatası: {_redact(str(e))}" in kaynak, (
        "SSE hata metni ham istisna taşıyor; redact_secrets uygulanmalı"
    )


def test_ad_tek_basina_sahiplik_kaniti_degil():
    """`unityMCP` adı ürünün malı olduğunu KANITLAMAZ; imza aranır."""
    from agentic.agent_runner import _urunun_kaydi_mi

    assert _urunun_kaydi_mi("unityMCP", _SIR_KAYDI)
    assert _urunun_kaydi_mi("unityai", {"command": r"C:\Users\x\.unity_architect_ai\launcher"})
    assert not _urunun_kaydi_mi("unityMCP", {"command": "kullanicinin-kendi-seyi"})
    assert not _urunun_kaydi_mi("baskaSunucu", _SIR_KAYDI)
    assert not _urunun_kaydi_mi("unityMCP", "dize-bile-degil")


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
