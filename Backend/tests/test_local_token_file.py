"""Backend bearer token'ının dosya üzerinden aktarımı — 2026-07-27 C grubu.

Bulgu: token `workspace/.mcp.json` içine düz metin yazılıyordu (modelin kendi
okuyabildiği yer) ve `codex mcp add --env LOCAL_APP_TOKEN=...` argv'sinde
geçiyordu (`ps` ile aynı-kullanıcı her sürece görünür). Aktarım artık 0600
izinli tek bir dosyadan geçiyor.

Testler hem aktarımın ÇALIŞTIĞINI hem de sırrın SIZMADIĞINI sabitliyor; ikincisi
olmadan sızıntıyı geri getiren bir değişiklik testlerden geçerdi.
"""

import json
import os
import stat

import pytest

import local_token_file


@pytest.fixture
def isolated_token(tmp_path, monkeypatch):
    """Gerçek ~/.unity_architect_ai kaydına dokunmadan sınamak için."""
    target = tmp_path / "local-app-token"
    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(tmp_path))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(target))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)
    return target


@pytest.mark.izin_bitleri_gerekli


def test_token_file_is_owner_only(isolated_token):
    """0600 olmazsa aynı makinedeki başka kullanıcılar sırrı okur."""
    assert local_token_file.write_local_app_token("s3cret")
    mode = stat.S_IMODE(os.stat(isolated_token).st_mode)
    assert mode == 0o600, f"beklenen 0600, bulunan {oct(mode)}"


def test_written_token_is_readable_back(isolated_token):
    """Bu yön olmadan düzeltme sırrı gizler ama MCP sunucusunu kilitler."""
    local_token_file.write_local_app_token("s3cret")
    assert local_token_file.read_local_app_token() == "s3cret"


def test_environment_wins_over_file(isolated_token, monkeypatch):
    """Backend kendi sürecinde ortamdaki değeri kullanmalı — dosya bayat olabilir."""
    local_token_file.write_local_app_token("eski")
    monkeypatch.setenv("LOCAL_APP_TOKEN", "yeni")
    assert local_token_file.read_local_app_token() == "yeni"


def test_empty_token_removes_the_file(isolated_token):
    """Token'sız (dev) başlatmada önceki oturumun GEÇERLİ sırrı diskte kalmamalı."""
    local_token_file.write_local_app_token("s3cret")
    assert isolated_token.exists()
    local_token_file.write_local_app_token("")
    assert not isolated_token.exists()
    assert local_token_file.read_local_app_token() == ""


def test_missing_file_reads_as_empty_not_error(isolated_token):
    assert local_token_file.read_local_app_token() == ""


def test_mcp_config_written_to_workspace_carries_no_token(tmp_path, monkeypatch):
    """Asıl bulgu: `.mcp.json` modelin okuyabildiği yerde ve token oradaydı.

    Sağlayıcıyı import etmeden, üretim fonksiyonunun yazdığı dosyayı sınıyoruz;
    dosyanın HERHANGİ bir yerinde token görünürse test kırılır.
    """
    monkeypatch.setenv("LOCAL_APP_TOKEN", "KANARYA-TOKEN")
    from providers.cli_base import BaseCLIProvider

    workspace = tmp_path / "ws"
    workspace.mkdir()

    provider = BaseCLIProvider.__new__(BaseCLIProvider)
    monkeypatch.setattr(provider, "_launcher_path", lambda name: "/bin/true", raising=False)
    monkeypatch.setattr(provider, "_ensure_exec", lambda path: None, raising=False)
    monkeypatch.setattr(provider, "_register_mcp", lambda *a, **k: None, raising=False)

    config_path = provider._write_mcp_config(str(workspace))
    raw = open(config_path, encoding="utf-8").read()

    assert "KANARYA-TOKEN" not in raw, ".mcp.json bearer token içeriyor"
    # Yapı bozulmasın: dosya hâlâ geçerli ve unityai sunucusunu tanımlıyor olmalı.
    assert json.loads(raw)["mcpServers"]["unityai"]


# ── Bağ yönlendirmesi sınıfı (30 Tem 2026 denetimi) ──────────────────────────
#
# Sınıfın kökü: `os.path.islink()` ve `O_NOFOLLOW` *"bu yol sandığım dosya mı"*
# sorusunu CEVAPLAMIYOR. Ölçüldü (ayrıcalıksız, IsUserAnAdmin=0):
#
#     os.symlink → RED (1314) · os.link → OK · mklink /J → OK
#     os.path.islink(junction) → False
#
# Yani sırrı yönlendirmenin ayrıcalıksız iki yolu vardı ve mevcut kontrol
# ikisini de görmüyordu. Bu testler `junction_gerekli` / `sabit_bag_gerekli`
# kapılarına bağlı ve bu makinede GERÇEKTEN koşuyorlar — sembolik bağ kapısına
# bağlansalardı sessizce atlanırlardı ki koruma ölü demek olurdu.


def _junction_kur(bag, hedef):
    import subprocess

    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(bag), str(hedef)],
        capture_output=True, text=True, timeout=20,
    )
    assert r.returncode == 0, r.stderr or r.stdout


@pytest.mark.junction_gerekli
def test_junction_ana_dizin_sahte_tokeni_KABUL_ETMIYOR(tmp_path, monkeypatch):
    """Saldırganın yerleştirdiği token ürüne kabul ettiriliyordu."""
    saldirgan = tmp_path / "saldirgan"
    saldirgan.mkdir()
    (saldirgan / "local-app-token").write_text("SALDIRGAN-TOKENI", encoding="utf-8")
    token_dir = tmp_path / "token-home"
    _junction_kur(token_dir, saldirgan)

    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(token_dir))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(token_dir / "local-app-token"))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)

    assert local_token_file.read_local_app_token() == ""


@pytest.mark.junction_gerekli
def test_junction_ana_dizin_sirri_DISARI_YAZMIYOR(tmp_path, monkeypatch):
    """Yazma yolu saldırganın seçtiği dosyaya sırrı taşıyordu."""
    saldirgan = tmp_path / "saldirgan"
    saldirgan.mkdir()
    hedef = saldirgan / "local-app-token"
    hedef.write_text("ONCEKI-ICERIK", encoding="utf-8")
    token_dir = tmp_path / "token-home"
    _junction_kur(token_dir, saldirgan)

    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(token_dir))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(token_dir / "local-app-token"))

    assert local_token_file.write_local_app_token("URUN-SIRRI") is False
    # O_TRUNC açılıştan çıkarıldığı için hedef dosya KESİLMİYOR da.
    assert hedef.read_text(encoding="utf-8") == "ONCEKI-ICERIK"


@pytest.mark.sabit_bag_gerekli
def test_sabit_bag_ile_ikinci_ad_REDDEDILIYOR(tmp_path, monkeypatch):
    """Sabit bağ bir bağ değil, ikinci bir ADdır — `islink` onu görmüyor.

    Sır dosyasının ikinci bir adı varsa, sır o addan da okunabilir. `O_NOFOLLOW`
    bunu reddetmiyor çünkü takip edilecek bir bağ yok.
    """
    token = tmp_path / "local-app-token"
    token.write_text("SIR", encoding="utf-8")
    ikinci_ad = tmp_path / "saldirganin-adi"
    os.link(token, ikinci_ad)
    assert not os.path.islink(ikinci_ad), "ön koşul: islink sabit bağı görmemeli"

    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(tmp_path))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(token))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)

    assert local_token_file.read_local_app_token() == ""
    assert local_token_file.write_local_app_token("YENI-SIR") is False


@pytest.mark.junction_gerekli
def test_yonlendirme_YOKKEN_normal_calisiyor(tmp_path, monkeypatch):
    """TERS YÖN — bu olmadan yukarıdakiler "her şeyi reddet" ile de geçerdi.

    Kimlik doğrulaması yanlış kurulursa (ör. `\\\\?\\` öneki normalize edilmezse)
    ürün token'ı hiç yazamaz ve backend açılmaz. O arıza bu testle görünür.
    """
    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(tmp_path))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(tmp_path / "local-app-token"))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)

    assert local_token_file.write_local_app_token("GERCEK-SIR") is True
    assert local_token_file.read_local_app_token() == "GERCEK-SIR"


@pytest.mark.junction_gerekli
def test_ARA_dizin_junctioni_da_yakalaniyor(tmp_path, monkeypatch):
    """İki-varyant: yönlendirme token dizininin KENDİSİNDE değil, ÜSTÜNDE.

    Bulgu S1a token dizininin kendisini junction yapıyordu. Aynı sınıfın başka
    bir yazımı, yolun herhangi bir üst bileşenini yönlendirmek. Tam yol
    karşılaştırması bunu da kapsıyor — ama kapsadığı ÖLÇÜLMEDEN iddia edilemez.
    """
    saldirgan = tmp_path / "saldirgan"
    (saldirgan / "uai").mkdir(parents=True)
    (saldirgan / "uai" / "local-app-token").write_text("SALDIRGAN", encoding="utf-8")
    ara = tmp_path / "ara"
    _junction_kur(ara, saldirgan)

    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(ara / "uai"))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(ara / "uai" / "local-app-token"))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)

    assert local_token_file.read_local_app_token() == ""
    assert local_token_file.write_local_app_token("SIR") is False


@pytest.mark.junction_gerekli
@pytest.mark.sabit_bag_gerekli
def test_junction_ve_sabit_bag_BIRLIKTE_kullanilinca(tmp_path, monkeypatch):
    """İki-varyant: iki mekanizmanın birleşimi.

    Tek tek kapatılan iki yazım birlikte kullanıldığında kontrollerden birinin
    diğerini gölgelemediğini ölçüyor — sınıf kapatmalarında sık görülen boşluk.
    """
    gercek = tmp_path / "gercek"
    gercek.mkdir()
    token = gercek / "local-app-token"
    token.write_text("SIR", encoding="utf-8")
    os.link(token, gercek / "ikinci-ad")
    gorunen = tmp_path / "gorunen"
    _junction_kur(gorunen, gercek)

    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(gorunen))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(gorunen / "local-app-token"))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)

    assert local_token_file.read_local_app_token() == ""


@pytest.mark.baglar_gerekli
def test_POSIX_ara_dizin_sembolik_bagi_reddediliyor(tmp_path, monkeypatch):
    """POSIX dalının karşılığı — bu makinede ATLANIYOR, bilerek burada.

    Windows'ta tanıtıcının gerçek yolu `GetFinalPathNameByHandleW` ile
    sorulabiliyor; POSIX'te taşınabilir bir karşılığı yok ve kod `realpath`
    karşılaştırmasına düşüyor. O dal bu makinede ÖLÇÜLEMİYOR (sembolik bağ
    kurmak winerror 1314 veriyor), ama dalı yakalayacak test yazılı: CI Linux'ta
    koştuğunda gerçek bir iddia taşıyor.
    """
    saldirgan = tmp_path / "saldirgan"
    saldirgan.mkdir()
    (saldirgan / "local-app-token").write_text("SALDIRGAN", encoding="utf-8")
    token_dir = tmp_path / "token-home"
    os.symlink(str(saldirgan), str(token_dir), target_is_directory=True)

    monkeypatch.setattr(local_token_file, "_TOKEN_DIR", str(token_dir))
    monkeypatch.setattr(local_token_file, "_TOKEN_PATH", str(token_dir / "local-app-token"))
    monkeypatch.delenv("LOCAL_APP_TOKEN", raising=False)

    assert local_token_file.read_local_app_token() == ""
