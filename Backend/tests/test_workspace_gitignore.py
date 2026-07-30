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
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

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


def test_call_site_agent_runner_project_mcp_json(tmp_path):
    from agentic.agent_runner import _write_project_mcp_json

    _write_project_mcp_json(str(tmp_path), {"unityMCP": {"type": "http"}})

    written = json.loads(_read(tmp_path / ".mcp.json"))
    assert "unityMCP" in written["mcpServers"]
    assert ".mcp.json" in _read(tmp_path / ".gitignore"), \
        "Claude SDK yolundaki .mcp.json yazım noktası bağlanmamış"
