# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Unity Architect AI backend
# Kullanım: cd Backend && pyinstaller backend.spec

from PyInstaller.utils.hooks import collect_all

# claude-agent-sdk: wheel kendi CLI binary'sini ve data dosyalarını getiriyor →
# data + binary + submodule'leri topla (yoksa frozen build'de session açılmaz).
_cas_datas, _cas_binaries, _cas_hidden = collect_all('claude_agent_sdk')

a = Analysis(
    ['app/main.py'],
    pathex=['app'],
    binaries=_cas_binaries,
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
        #   backend mcp-server  → unity_ai_mcp.server.main
        #   backend unityai     → unityai_cli.main
        'unity_ai_mcp.server',
        'unity_ai_mcp.approval_bridge',
        'unity_ai_mcp.tools.file_tools',
        'unity_ai_mcp.tools.bash_tool',
        'unityai_cli',
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
