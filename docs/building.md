# Building from source

Running the backend and frontend for development, and producing a distributable
dmg or installer. Nothing here is needed to *use* the packaged app.

---

## ⚙️ Installation

### Requirements
- Python 3.13+
- Node.js 20+
- Unity Editor (for Unity MCP, optional)

> None of these are needed for the packaged app — Python, uv, OmniSharp, the .NET SDK, and ffmpeg/yt-dlp are all bundled. These requirements are for **developing from source** only.

### Backend

```bash
cd Backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Dev server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> You enter API keys from the in-app **Settings** screen (stored encrypted), not via `.env`. If you run the backend standalone (without Electron), `LOCAL_APP_TOKEN` stays empty → token checks are skipped (dev mode).

### Frontend

```bash
cd Frontend/frontend
npm install          # postinstall builds node-pty automatically
npm run dev          # development
```

### Environment variables (optional)

```env
DB_PATH=~/.unity_architect_ai/unity_master_v3.db
HOST=127.0.0.1
PORT=8000                      # Electron picks a random free port; set this for a fixed one
API_KEY_ENCRYPTION_KEY=        # if empty, a file-based key is generated
```

---

## 📦 Packaging (dmg / exe)

A distributable app is produced in four steps (none of the bundled binaries are committed to git; they are fetched before each build):

```bash
# 1) Download the uv toolchain for Unity MCP
#    macOS: downloads both architectures (arm64 + x64)
bash Backend/vendor/fetch_uv.sh
#    Windows: pwsh Backend/vendor/fetch_uv.ps1

# 2) Download OmniSharp + the bundled .NET SDK (code intelligence; bundled on all three platforms)
python3 scripts/fetch_omnisharp.py

# 3) Download the video tools (ffmpeg + yt-dlp — the video→chat feature)
bash Backend/vendor/fetch_video_bins.sh

# 4) Compile the backend with PyInstaller, then package the Electron app
cd Backend && ./build_backend.sh        # Windows: build_backend.bat
cd Frontend/frontend && npm install && npm run build
```

Outputs land under `Frontend/frontend/build/`:
- macOS: `Gamachine-<version>-arm64.dmg` (Apple Silicon)
- Windows: NSIS installer (`.exe`)

> ⚠️ **The x64 dmg trap:** electron-builder produces dmgs for both architectures, but the backend binary is only compiled for the host architecture — an x64 dmg built on Apple Silicon **won't work on Intel Macs**. Proper Intel support requires compiling the backend with an x64 Python separately.

> 🍎 **macOS quarantine note:** the dmg is unsigned; if macOS reports it as "damaged" after downloading, clear the quarantine flag with `xattr -cr "/Applications/Gamachine.app"`.

The packaged app does **not** require Python or .NET — the backend is a single frozen binary; the `mcp-server` and `unityai` subcommands are invoked through that same binary. `uvx`, OmniSharp (+.NET), and ffmpeg/yt-dlp are all embedded.

---

---

[← Back to the README](../README.md)
