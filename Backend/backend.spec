# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Unity Architect AI backend
# Kullanım: cd Backend && pyinstaller backend.spec

from PyInstaller.utils.hooks import collect_all

# claude-agent-sdk: wheel kendi CLI binary'sini ve data dosyalarını getiriyor →
# data + binary + submodule'leri topla (yoksa frozen build'de session açılmaz).
_cas_datas, _cas_binaries, _cas_hidden = collect_all('claude_agent_sdk')

# Video: ffmpeg + yt-dlp binary'lerini bundle'a ekle (VARSA). Yoksa build KIRILMAZ —
# binary'ler Backend/vendor/bin/win/ altına konunca otomatik dahil olur.
# Frozen'da _internal/bin/ altına düşer → providers/video_bin.py resolver oradan bulur.
import os as _os
import sys as _sys
if _sys.platform == "win32":
    _bin_os, _video_exes = "win", ("ffmpeg.exe", "yt-dlp.exe")
elif _sys.platform == "darwin":
    _bin_os, _video_exes = "mac", ("ffmpeg", "yt-dlp")
else:
    _bin_os, _video_exes = "linux", ("ffmpeg", "yt-dlp")
_video_bins = []
for _exe in _video_exes:
    _vp = _os.path.join("vendor", "bin", _bin_os, _exe)
    if _os.path.exists(_vp):
        _video_bins.append((_vp, "bin"))

a = Analysis(
    ['app/main.py'],
    pathex=['app'],
    binaries=_cas_binaries + _video_bins,
    # NOT: Launcher scriptleri (run_mcp_server.sh, unityai) PyInstaller datas'ı ile
    # GÖMÜLMEZ — PyInstaller 6.x datas'ı _internal/ altına koyuyor, oysa scriptlerin
    # frozen 'backend' binary'sinin YANINDA (Backend kökünde) olması gerekiyor.
    # Bu yüzden electron-builder.yml extraResources ile doğrudan Backend köküne kopyalanır.
    datas=_cas_datas,
    hiddenimports=[
        # Claude Agent SDK (kalıcı interaktif session)
        'claude_agent_sdk',
        # uvicorn — otomatik bulunamayan modüller
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # pydantic v2
        'pydantic.deprecated.class_validators',
        'pydantic.v1',
        # cryptography / bcrypt
        'cryptography.fernet',
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends.openssl',
        '_cffi_backend',
        # multipart (FastAPI form desteği)
        'multipart',
        'python_multipart',
        # email (httpx/oauth)
        'email.mime.text',
        'email.mime.multipart',
        # OS keystore
        'keyring',
        'keyring.backends',
        'keyring.backends.Windows',
        'keyring.backends.macOS',
        # AI provider kütüphaneleri
        'anthropic',
        'openai',
        'ollama',
        'httpx',
        'httpcore',
        # google-generativeai + grpc
        'google.generativeai',
        'google.ai.generativelanguage',
        'grpc',
        'grpc._cython',
        'grpc._cython.cygrpc',
        # Frozen binary subcommand dispatch hedefleri (main.py bunları çağırır):
        #   backend mcp-server        → unity_ai_mcp.server.main
        #   backend unityai           → unityai_cli.main
        #   backend codex-mcp-bridge  → providers.codex_unitymcp_bridge.main
        'unity_ai_mcp.server',
        'unity_ai_mcp.approval_bridge',
        'unity_ai_mcp.tools.file_tools',
        'unity_ai_mcp.tools.bash_tool',
        'unityai_cli',
        'providers.codex_unitymcp_bridge',
        # FastMCP (MCP server transport)
        'mcp',
        'mcp.server',
        'mcp.server.fastmcp',
    ] + _cas_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Gereksiz büyük paketleri dışla
        'tkinter',
        'matplotlib',
        'numpy',
        'PIL',
        'cv2',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='backend',
)
