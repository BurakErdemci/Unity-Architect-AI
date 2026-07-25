# Third-Party Notices

Unity Architect AI incorporates or redistributes the third-party components
listed below. Each remains under its own license; nothing in this project's
LICENSE alters those terms.

Components marked **[bundled]** ship inside released installers (`.dmg` / `.exe`).
Components marked **[fetched]** are downloaded at build time and are not stored
in this repository.

---

## Source incorporated into this repository

### MCP for Unity — `unity-mcp/`
Copyright (c) 2025 CoplayDev — **MIT License**
Original license retained at `unity-mcp/LICENSE`, which continues to govern that
directory. This project contains a modified fork; modifications are documented in
the project history.

---

## Bundled runtime components

### FFmpeg — **[bundled] [fetched]** — ⚠️ GPL
Licensed under the **GNU General Public License version 3 or later (GPL-3.0-or-later)**.
The binaries used are third-party builds configured with `--enable-gpl`
`--enable-version3` and GPL components (including libx264 and libx265).

- macOS builds: https://evermeet.cx/ffmpeg/
- Linux builds: https://johnvansickle.com/ffmpeg/
- FFmpeg project and complete corresponding source: https://ffmpeg.org/download.html
- License text: https://www.gnu.org/licenses/gpl-3.0.html

FFmpeg is redistributed **unmodified**, as a standalone executable, and is invoked
by this application only as a separate process (no linking against FFmpeg
libraries). This constitutes mere aggregation; it does not place Unity Architect
AI's own code under the GPL. Recipients of a build containing FFmpeg are entitled
to the corresponding source of FFmpeg, available at the links above.

### yt-dlp — **[bundled] [fetched]**
**The Unlicense** (public domain dedication) — https://github.com/yt-dlp/yt-dlp

### OmniSharp-Roslyn — **[bundled] [fetched]**
Copyright (c) OmniSharp — **MIT License** — https://github.com/OmniSharp/omnisharp-roslyn

### .NET Runtime — **[bundled] [fetched]**
Copyright (c) .NET Foundation and Contributors — **MIT License** — https://github.com/dotnet/runtime

### Electron — **[bundled]**
Copyright (c) Electron contributors / OpenJS Foundation — **MIT License** — https://github.com/electron/electron

### Chromium / Node.js (via Electron) — **[bundled]**
Chromium: BSD-3-Clause and others. Node.js: MIT.
Full notices are included in the Electron distribution.

---

## Application dependencies

### JavaScript / TypeScript (npm)
Includes Next.js, React, Tailwind CSS, Framer Motion, Monaco Editor, xterm.js,
node-pty, electron-builder, electron-updater, axios, lucide-react and their
transitive dependencies — predominantly **MIT**, with some **Apache-2.0** and
**BSD** components. See `Frontend/frontend/package.json` and the generated
`package-lock.json` for the authoritative list and versions.

### Python (PyPI)
Includes FastAPI, Uvicorn, Pydantic, anthropic, openai, google-genai, ollama and
their transitive dependencies — predominantly **MIT**, **BSD-3-Clause** and
**Apache-2.0**. See `Backend/requirements.txt` for the authoritative list.

### uv — **[fetched]**
Copyright (c) Astral — dual licensed **MIT** or **Apache-2.0** — https://github.com/astral-sh/uv

---

## External tools (not bundled)

The application can drive AI command-line tools that the user installs and
authenticates separately. These are **not** distributed with Unity Architect AI
and remain subject to their own licenses and terms of service:

Claude Code (Anthropic), Codex CLI (OpenAI), Antigravity CLI (Google),
GitHub Copilot CLI, Cursor CLI, OpenCode, Kimi Code CLI (Moonshot AI).

---

## Reporting

If you believe an attribution is missing or incorrect, please open an issue on
the project repository.
