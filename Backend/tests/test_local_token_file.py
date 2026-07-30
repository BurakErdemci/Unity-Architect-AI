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
