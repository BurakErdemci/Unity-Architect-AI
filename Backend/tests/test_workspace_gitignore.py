"""Ürünün kullanıcının Unity projesine yazdığı config dosyalarının `.gitignore`'a
girdiğini koruyan testler.

Hangi ölçümden doğdu (2026-07-29, K3): ürün `.mcp.json`, `opencode.json`,
`.cursor/mcp.json` ve `.cursor/cli.json` dosyalarını KULLANICININ Unity projesine
yazıyor ve bunlar unityMCP'nin `X-API-Key`'ini düz metin taşıyor. Kullanıcının
gerçek projesinde (`MatchDayOfficial`, GitHub remote'u var) ölçüldü: `.mcp.json`
ve `opencode.json` gitignore'daydı ama satırları **kullanıcı kendi eliyle**
yazmıştı (24 Tem commit'i, `git blame`); `.cursor/mcp.json` İZLENİYORDU. Yani
ürün hiçbir yere gitignore girdisi eklemiyordu → yeni bir kullanıcıda sıfır
koruma.

Bu dosyanın ikinci yarısı (çağrı noktası testleri) birinciden ÖNEMLİ: yardımcı
doğru olsa bile bir yazım noktası onu çağırmayı unutursa o dosya kapsam dışı
kalır — bugünkü boşluk (`.cursor/mcp.json`) tam olarak öyle oluştu. Bu depoda
tekrarlayan arıza şekli "birbiriyle uyuşması gereken iki yer uyuşmuyor".
"""
import json
import logging
import os
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from providers import workspace_config  # noqa: E402
from providers.workspace_config import (  # noqa: E402
    BLOCK_BEGIN,
    BLOCK_END,
    ensure_gitignored,
    remove_gitignore_block,
)


def _git_init(path) -> None:
    """Testte gerçek git ağacı kurar — `git check-ignore` yolunu sürmek için şart.

    Saf metin karşılaştırması `*.json` gibi geniş desenleri GÖREMEZ; yardımcının
    asıl tespiti git'e dayanıyor, o yüzden testin de gerçek git'e dayanması gerek.
    """
    subprocess.run(["git", "init", "-q", str(path)], check=True,
                   capture_output=True, timeout=30)


def _read(path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────── ensure_gitignored ────────────────────────────


def test_creates_gitignore_when_missing(tmp_path):
    ensure_gitignored(str(tmp_path), [".mcp.json"])

    gi = tmp_path / ".gitignore"
    assert gi.exists(), ".gitignore yoksa oluşturulmalı"
    text = _read(gi)
    assert ".mcp.json" in text
    # Etiketli blok şart: kullanıcı `git diff`'inde ne olduğunu görsün ve tek
    # parça silebilsin (sessizce araya satır sıkıştırmak kabul edilmiyor).
    assert BLOCK_BEGIN in text and BLOCK_END in text


def test_block_goes_to_top_without_destroying_existing_content(tmp_path):
    """Blok BAŞA yazılır ve kullanıcının içeriği bozulmadan altında kalır.

    Konum kullanıcı kararı (29 Tem 2026): sona eklenen blok uzun bir
    `.gitignore`'da görünmüyor ve `git diff`'te açıklanamayan bir değişiklik
    gibi duruyor. Başta olunca "bunu ürün ekledi, silebilirim" ilk bakışta
    okunuyor. Bu test o kararı sabitler — sona dönerse kırılır.
    """
    gi = tmp_path / ".gitignore"
    original = "# kullanıcının kendi dosyası\nnode_modules/\n*.log\n"
    gi.write_text(original, encoding="utf-8")

    ensure_gitignored(str(tmp_path), ["opencode.json"])

    text = _read(gi)
    assert text.startswith(BLOCK_BEGIN), "ürün bloğu dosyanın BAŞINDA olmalı"
    assert text.endswith(original), "kullanıcının içeriği bozulmadan altta kalmalı"
    assert "opencode.json" in text


def test_second_call_is_byte_identical(tmp_path):
    _git_init(tmp_path)
    ensure_gitignored(str(tmp_path), [".mcp.json", ".cursor/mcp.json"])
    first = (tmp_path / ".gitignore").read_bytes()

    ensure_gitignored(str(tmp_path), [".mcp.json", ".cursor/mcp.json"])

    assert (tmp_path / ".gitignore").read_bytes() == first, \
        "idempotent olmalı: zaten kapsanan girdi için dosyaya DOKUNULMAMALI"


def test_broad_pattern_already_covers_entry(tmp_path):
    """`*.json` gibi geniş bir desen zaten kapsıyorsa yeni satır yazılmaz.

    Düz metin araması bu vakayı yakalayamaz; `git check-ignore` yakalar.
    """
    _git_init(tmp_path)
    gi = tmp_path / ".gitignore"
    gi.write_text("*.json\n", encoding="utf-8")
    before = gi.read_bytes()

    ensure_gitignored(str(tmp_path), [".mcp.json", "opencode.json"])

    assert gi.read_bytes() == before, "geniş desen kapsıyorsa dosya değişmemeli"


def test_works_in_non_git_directory(tmp_path):
    """git yoksa/başarısızsa satır bazlı literal karşılaştırmaya düşülmeli."""
    ensure_gitignored(str(tmp_path), [".mcp.json"])
    ensure_gitignored(str(tmp_path), [".mcp.json"])   # ikincisi eklememeli

    text = _read(tmp_path / ".gitignore")
    assert text.count(".mcp.json") == 1


@pytest.mark.baglar_gerekli


def test_symlink_escape_is_refused(tmp_path, caplog):
    """`.gitignore` workspace DIŞINA bakan bir bağsa yazma reddedilir.

    Bu depoda symlink'le config ezme ÖLÇÜLMÜŞ bir sınıf (K4: 6 yazım noktasının
    6'sı da kurbanı ezdi). Yeni bir yazım noktası aynı sınıfı açmamalı.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("KURBAN\n", encoding="utf-8")

    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink(str(victim), str(ws / ".gitignore"))

    with caplog.at_level(logging.WARNING):
        ensure_gitignored(str(ws), [".mcp.json"])

    assert victim.read_text(encoding="utf-8") == "KURBAN\n", \
        "workspace dışındaki dosya HİÇ değişmemeli"
    # Bu ikinci iddia olmadan test muhafızı ÖLÇMÜYOR: `os.replace` bağın
    # kendisini değiştirir, hedefini değil — yani muhafız kaldırılsa bile
    # kurban dosya bozulmadan kalır. Gerçek zarar iki taraflı ve ancak burada
    # görünüyor: (a) kullanıcının kasıtlı bağı sessizce yok edilir,
    # (b) workspace dışındaki içerik okunup depo içine KOPYALANIR.
    assert os.path.islink(str(ws / ".gitignore")), \
        "bağ yerinde kalmalı — yazma hiç denenmemeliydi"
    assert BLOCK_BEGIN not in victim.read_text(encoding="utf-8")


def test_missing_workspace_does_not_raise(tmp_path, caplog):
    """Çağıranın yoluna istisna sızmamalı: gitignore yazılamazsa oturum açılışı
    kırılmamalı."""
    with caplog.at_level(logging.WARNING):
        ensure_gitignored(str(tmp_path / "yok-boyle-bir-dizin"), [".mcp.json"])
    # Hiçbir şey fırlatılmadı = test geçti; ek olarak dosya da yaratılmamalı.
    assert not (tmp_path / "yok-boyle-bir-dizin").exists()


@pytest.mark.izin_bitleri_gerekli


def test_unwritable_workspace_does_not_raise(tmp_path, caplog):
    ws = tmp_path / "ro"
    ws.mkdir()
    os.chmod(str(ws), 0o500)
    try:
        with caplog.at_level(logging.WARNING):
            ensure_gitignored(str(ws), [".mcp.json"])
        assert any("gitignore" in r.message.lower() for r in caplog.records), \
            "sessizce yutma: en az bir uyarı loglanmalı"
    finally:
        os.chmod(str(ws), 0o700)


def test_warns_when_entry_is_already_tracked(tmp_path, caplog):
    """gitignore, ZATEN takip edilen bir dosyayı geri almaz — kullanıcıya söyle.

    Ürün `git rm --cached`'i KENDİLİĞİNDEN koşmamalı: kullanıcının deposunda
    sessizce index değiştirmek kabul edilemez.
    """
    _git_init(tmp_path)
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", ".mcp.json"],
                   check=True, capture_output=True, timeout=30)

    with caplog.at_level(logging.WARNING):
        ensure_gitignored(str(tmp_path), [".mcp.json"])

    joined = " ".join(r.message for r in caplog.records)
    assert ".mcp.json" in joined and "rm --cached" in joined
    # Ürün index'e DOKUNMAMALI: dosya hâlâ takip ediliyor olmalı.
    out = subprocess.run(["git", "-C", str(tmp_path), "ls-files", "--", ".mcp.json"],
                         capture_output=True, text=True, timeout=30)
    assert ".mcp.json" in out.stdout


def test_git_covered_reports_tracked_file_as_covered(tmp_path):
    """`check-ignore --no-index` ölçümünü kilitler (2026-07-29, git 2.50.1).

    `--no-index` OLMADAN git, takip edilen bir dosya için desen eşleşse bile
    rc=1 ("yok sayılmıyor") döner. Bu, kapsama tespitinin git katmanını sessizce
    yalancı yapar: `.gitignore`'da zaten yazan ama takip edilen bir dosya her
    oturumda "eksik" görünürdü. Üst katmandaki literal karşılaştırma bu hatayı
    ÖRTTÜĞÜ için, git katmanı burada doğrudan sınanıyor.
    """
    from providers.workspace_config import _git_covered

    _git_init(tmp_path)
    (tmp_path / ".gitignore").write_text("*.json\n", encoding="utf-8")
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", ".mcp.json"],
                   check=True, capture_output=True, timeout=30)

    assert _git_covered(str(tmp_path), [".mcp.json"]) == {".mcp.json"}


def test_git_covered_returns_none_outside_repo(tmp_path):
    """Ölçülemedi ile 'kapsanmıyor' ayrı sonuçlar: git yoksa None dönmeli ki
    çağıran literal karşılaştırmaya düşsün. Boş küme dönerse fark silinir."""
    from providers.workspace_config import _git_covered

    assert _git_covered(str(tmp_path), [".mcp.json"]) is None


# ───────────────────────── remove_gitignore_block ─────────────────────────


def test_remove_block_keeps_user_lines(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n*.log\n", encoding="utf-8")
    ensure_gitignored(str(tmp_path), [".mcp.json", "opencode.json"])
    assert ".mcp.json" in _read(gi)

    remove_gitignore_block(str(tmp_path))

    text = _read(gi)
    assert "node_modules/" in text and "*.log" in text
    assert ".mcp.json" not in text and "opencode.json" not in text
    assert BLOCK_BEGIN not in text and BLOCK_END not in text


def test_add_then_remove_restores_file_byte_for_byte(tmp_path):
    """Ekle → kaldır turu kullanıcının dosyasını BAYT BAYT eski hâline döndürür.

    Ayrı bir test, çünkü "blok gitti" ile "dosya eski hâline döndü" aynı şey
    değil: blok başa yazılırken araya konan nefes payı geride kalırsa her
    ekle/kaldır turunda dosyanın başında bir boş satır birikirdi ve kullanıcı
    ürünü kaldırdıktan sonra bile izini taşırdı.
    """
    gi = tmp_path / ".gitignore"
    original = "# kullanıcının kendi dosyası\nnode_modules/\n*.log\n"
    gi.write_text(original, encoding="utf-8")

    ensure_gitignored(str(tmp_path), [".mcp.json", ".cursor/mcp.json"])
    assert _read(gi) != original, "önce gerçekten değişmeli, yoksa test boş döner"

    remove_gitignore_block(str(tmp_path))

    assert _read(gi) == original


def test_remove_block_is_safe_when_nothing_to_remove(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")
    before = gi.read_bytes()

    remove_gitignore_block(str(tmp_path))          # blok yok
    remove_gitignore_block(str(tmp_path / "yok"))  # workspace yok

    assert gi.read_bytes() == before


# ──────────────────── çağrı noktaları — dört yazım yeri ────────────────────
#
# Yardımcı doğru olsa bile bağlanmayı unutan bir yazım noktası dosyayı yine
# korumasız bırakır. Aşağıdaki dördü gerçek yazım fonksiyonlarını sürüyor.


@pytest.fixture
def _no_unity_mcp(monkeypatch):
    """unityMCP kapalıymış gibi davran: `headers`/sır yolunu teste sokmadan
    config dosyalarının YAZILDIĞINI sürmek yeterli."""
    from unity_ai_mcp import unity_mcp_manager as um
    monkeypatch.setattr(um.unity_mcp_manager, "mcp_url", lambda: None)
    return um


def test_call_site_cursor_mcp_and_cli_json(tmp_path, _no_unity_mcp):
    from providers.cursor_provider import CursorProvider

    p = CursorProvider("cursor")
    p._register_mcp("/bin/true", str(tmp_path), "http://localhost:8000")

    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert (tmp_path / ".cursor" / "cli.json").exists()
    text = _read(tmp_path / ".gitignore")
    assert ".cursor/mcp.json" in text, "cursor mcp.json yazım noktası bağlanmamış"
    assert ".cursor/cli.json" in text, "cursor cli.json yazım noktası bağlanmamış"


def test_call_site_opencode_json(tmp_path, _no_unity_mcp):
    from providers.opencode_provider import OpenCodeProvider

    p = OpenCodeProvider("opencode:opencode/grok-code")
    p._register_mcp("/bin/true", str(tmp_path), "http://localhost:8000")

    assert (tmp_path / "opencode.json").exists()
    assert "opencode.json" in _read(tmp_path / ".gitignore"), \
        "opencode yazım noktası bağlanmamış"


def test_call_site_cli_base_mcp_json(tmp_path, _no_unity_mcp, monkeypatch):
    from providers.cli_base import BaseCLIProvider

    p = BaseCLIProvider("claude")
    monkeypatch.setattr(p, "_launcher_path", lambda name: "/bin/true")
    monkeypatch.setattr(BaseCLIProvider, "_ensure_exec", staticmethod(lambda path: None))

    p._write_mcp_config(str(tmp_path))

    assert (tmp_path / ".mcp.json").exists()
    assert ".mcp.json" in _read(tmp_path / ".gitignore"), \
        "cli_base .mcp.json yazım noktası bağlanmamış"


def test_call_site_agent_runner_project_mcp_json_ARTIK_YOK(tmp_path):
    """Claude SDK yolu 5. yazım noktasıydı; K8 ile KALDIRILDI (yerine temizlik geldi).

    Envanterde yerini koruyor, çünkü bu dosyanın işi yazım noktalarını saymak ve
    "beşincisi nereye gitti" sorusunun cevabı burada durmalı. Kaldırılma sebebi:
    o dosyanın okunabilmesi `setting_sources` içinde `"project"` gerektiriyordu
    ve `"project"` onay kapısını dört ayrı yoldan düşürüyordu
    (bkz. tests/test_claude_setting_sources.py). unityMCP artık SDK'ya doğrudan
    `mcp_servers` ile geçiliyor; workspace'e hiç dosya yazılmıyor.

    Yazım noktası geri gelirse burası kırmızı verir — ve o zaman gitignore
    bağının da yeniden kurulması gerektiği hatırlanır.
    """
    import inspect

    from agentic import agent_runner

    assert not hasattr(agent_runner, "_write_project_mcp_json"), (
        "Claude SDK yolunda .mcp.json yazan kod geri gelmiş — gitignore bağı ve "
        "setting_sources gerekçesi yeniden değerlendirilmeli"
    )
    # Temizlik ucu duruyor mu: yaratan adım kaldırıldıysa silen adım kalmalı.
    # ⚠️ İçerik ürünün İMZASINI taşımalı — boş bir `{}` bilerek dokunulmaz
    # bırakılıyor, çünkü bizim olduğunu kanıtlamıyor (denetim bulgusu:
    # `vacuous-server-subset`, kullanıcı verisi siliniyordu).
    # ⚠️ URL dahil: ürünün gerçek kaydı YEREL bir adres taşıyor ve sahiplik
    # imzası buna bağlı (`X-API-Key` tek başına kanıt değil — kullanıcının uzak
    # sunucusu da onu kullanabiliyor).
    (tmp_path / ".mcp.json").write_text(
        '{"mcpServers": {"unityMCP": {"url": "http://localhost:8080/mcp",'
        ' "headers": {"X-API-Key": "sir"}}}}',
        encoding="utf-8",
    )
    agent_runner._remove_project_mcp_json(str(tmp_path))
    assert not (tmp_path / ".mcp.json").exists()
    assert "_remove_project_mcp_json" in inspect.getsource(agent_runner)


# ── 30 Tem 2026 denetimi: E-a regresyonu, E-b fail-open, S4b ACL ────────────


def _depo_kur(tmp_path, takipli=True):
    subprocess.run(["git", "init", "-q", str(tmp_path)], capture_output=True, timeout=30)
    cfg = tmp_path / ".mcp.json"
    cfg.write_text('{"headers":{"X-API-Key":"KANARYA-91zQ"}}', encoding="utf-8")
    if takipli:
        subprocess.run(["git", "-C", str(tmp_path), "add", "-f", ".mcp.json"],
                       capture_output=True, timeout=30)
    return cfg


def test_takip_uyarisi_girdi_ZATEN_varken_de_atesleniyor(tmp_path, caplog):
    """E-a'nın ikinci yarısı: `if not missing: return` erken dönüşü.

    İlk çağrıda girdi `.gitignore`'a ekleniyor. İKİNCİ çağrıda `missing` boş
    kalıyor ve eski kod oracıkta dönüyordu — yani kurulu bir workspace'te
    "bu dosya git'te takipli" uyarısı bir daha ASLA ateşlenmiyordu.
    """
    _depo_kur(tmp_path)
    workspace_config.ensure_gitignored(str(tmp_path), [".mcp.json"])

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        workspace_config.ensure_gitignored(str(tmp_path), [".mcp.json"])

    assert any("ZATEN takip ediliyor" in r.message for r in caplog.records), \
        "girdi zaten varken takip uyarısı düştü"


def test_git_YOK_SAYSA_BILE_takip_uyarisi_atesleniyor(tmp_path, caplog):
    """E-a'nın birinci yarısı: sorgu `missing` ile yapılıyordu.

    `covered` girdiler — git'in ZATEN yok saydıkları — `missing`'e hiç girmiyor,
    dolayısıyla takip kontrolünden de kaçıyorlardı. Oysa asıl tehlikeli durum
    tam olarak bu: dosya hem yok sayılıyor HEM takip ediliyor, yani sır depoda.
    """
    _depo_kur(tmp_path)
    (tmp_path / ".gitignore").write_text(".mcp.json\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        workspace_config.ensure_gitignored(str(tmp_path), [".mcp.json"])

    assert any("ZATEN takip ediliyor" in r.message for r in caplog.records)


def test_tracked_olcemedigi_zaman_None_donuyor():
    """E-b: fail-OPEN idi. Her hata `[]`'e eşleniyor, çağıran "takip yok" sanıyordu.

    Kardeşi `_git_covered` ölçemediğinde `None` dönüp muhafazakâr davranıyordu —
    tek dosyada iki zıt hata felsefesi. Ayrım artık çağıranda.
    """
    assert workspace_config._tracked("/olmayan-dizin-xyz", [".mcp.json"]) is None


def test_olculemedi_uyarisi_git_deposu_YOKKEN_susuyor(tmp_path, caplog):
    """Ters yön: uyarı doğru olmalı ama gürültü de OLMAMALI.

    `.git` yoksa "takip" diye bir şey yok; her oturumda uyarmak kullanıcıyı
    uyarı körlüğüne alıştırırdı — bu dosyanın kaçındığı sınıfın aynısı.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        workspace_config.ensure_gitignored(str(tmp_path), [".mcp.json"])
    assert not any("ÖLÇÜLEMEDİ" in r.message for r in caplog.records)


def test_olculemedi_uyarisi_depo_VARKEN_atesleniyor(tmp_path, caplog, monkeypatch):
    """...ama depo varken ölçememek gerçek bir bilinmezlik ve sessiz geçilemez."""
    _depo_kur(tmp_path, takipli=False)
    monkeypatch.setattr(workspace_config, "_tracked", lambda *a, **k: None)
    with caplog.at_level(logging.WARNING):
        workspace_config.ensure_gitignored(str(tmp_path), [".mcp.json"])
    assert any("ÖLÇÜLEMEDİ" in r.message for r in caplog.records)


def test_harden_config_file_sahibe_kilitliyor(tmp_path):
    """S4b: config dosyası workspace'in ACL'ini miras alıyordu.

    Paylaşımlı ya da CI workspace'inde ana dizinde `Everyone (RX)` varsa
    `X-API-Key` makinedeki her hesap tarafından okunabiliyordu.
    """
    hedef = tmp_path / ".mcp.json"
    hedef.write_text('{"headers":{"X-API-Key":"KANARYA"}}', encoding="utf-8")

    assert workspace_config.harden_config_file(str(hedef)) is True

    if os.name == "nt":
        acl = subprocess.run(["icacls", str(hedef), "/findsid", "*S-1-1-0"],
                             capture_output=True, text=True, timeout=20)
        assert "SID Found:" not in acl.stdout, "Everyone hâlâ erişebiliyor"
    else:
        assert stat.S_IMODE(os.stat(hedef).st_mode) == 0o600


def test_ACL_kisitlanamazsa_sir_YAZILMIYOR(tmp_path, monkeypatch):
    """Doğrulama turu bulgusu: `harden_config_file`'ın dönüşü YUTULUYORDU.

    `cli_base` çağrıyı yapıp sonucu atıyordu, yani ACL kısıtlanamasa bile sır
    yine de diske yazılıyordu ve kimse bilmiyordu — hardener'ın kendi
    docstring'i "çağıran bunu yutmuyor" diyordu, oysa yutuyordu.

    Doğru taraf: sırrı korumasız yazmaktansa özelliği kaybetmek. Ürünün geri
    kalanı çalışmaya devam eder, yalnız unityMCP bağlanmaz.
    """
    import providers.cli_base as cli_base
    from providers.cli_base import BaseCLIProvider

    monkeypatch.setenv("LOCAL_APP_TOKEN", "x")
    monkeypatch.setattr(cli_base, "harden_config_file", lambda p: False, raising=False)
    monkeypatch.setattr(
        workspace_config, "harden_config_file", lambda p: False
    )

    class _SahteYonetici:
        @staticmethod
        def mcp_url():
            return "http://127.0.0.1:8080/mcp"

        @staticmethod
        def api_headers():
            return {"X-API-Key": "KANARYA-ACL"}

    import unity_ai_mcp.unity_mcp_manager as umm
    monkeypatch.setattr(umm, "unity_mcp_manager", _SahteYonetici())

    ws = tmp_path / "ws"
    ws.mkdir()
    provider = BaseCLIProvider.__new__(BaseCLIProvider)
    monkeypatch.setattr(provider, "_launcher_path", lambda name: "/bin/true", raising=False)
    monkeypatch.setattr(provider, "_ensure_exec", lambda path: None, raising=False)
    monkeypatch.setattr(provider, "_register_mcp", lambda *a, **k: None, raising=False)

    yol = provider._write_mcp_config(str(ws))
    ham = open(yol, encoding="utf-8").read()

    assert "KANARYA-ACL" not in ham, "ACL kısıtlanamadığı hâlde sır yazıldı"
    # Ürün çalışmaya devam etmeli: unityai kaydı duruyor, yalnız unityMCP düştü.
    assert json.loads(ham)["mcpServers"]["unityai"]
    assert "unityMCP" not in json.loads(ham)["mcpServers"]
