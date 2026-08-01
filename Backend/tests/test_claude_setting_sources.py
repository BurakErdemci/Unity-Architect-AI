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

    `"user"` düşerse menü 55 → 31 komuta iner (ölçüldü). Düzeltme bir güvenlik
    kazancıydı, bir yetenek kaybı değil; bu test o dengeyi de kilitliyor.
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


def test_bayat_mcp_json_siliniyor(tmp_path):
    """Sır düz metin diskteydi; düzeltme onu diskte bırakmamalı."""
    from agentic.agent_runner import _remove_project_mcp_json

    hedef = tmp_path / ".mcp.json"
    hedef.write_text('{"mcpServers": {"unityMCP": {"headers": {"X-API-Key": "sir"}}}}',
                     encoding="utf-8")

    _remove_project_mcp_json(str(tmp_path))

    assert not hedef.exists(), "bayat .mcp.json diskte kaldı — X-API-Key hâlâ okunabilir"


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
