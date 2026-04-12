# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Unity Architect AI backend
# Kullanım: cd Backend && pyinstaller backend.spec

a = Analysis(
    ['app/main.py'],
    pathex=['app'],
    binaries=[],
    datas=[
        ('app/knowledge/unity_kb.json', 'knowledge'),
    ],
    hiddenimports=[
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
    ],
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
