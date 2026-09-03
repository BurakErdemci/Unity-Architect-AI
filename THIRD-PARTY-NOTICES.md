# Third-Party Notices

Gamachine incorporates or redistributes the third-party components
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

### FFmpeg — **[bundled] [fetched]** — ⚠️ the license differs per platform
The bundled FFmpeg build is **not under the same license on every platform**. The
exact builds are pinned in `scripts/pinned_assets.json`; the table reflects those
pins. Do not collapse these rows into a single claim — each platform ships a
different binary, and pointing a recipient at the wrong license also points them
at the wrong corresponding source.

| Platform | Pinned build | License |
|---|---|---|
| Windows | BtbN `ffmpeg-n8.1.2-…-win64-**lgpl**-8.1.zip` | **LGPL-3.0-or-later** |
| macOS | evermeet.cx `ffmpeg-8.1.2` | **GPL-3.0-or-later** |
| Linux | johnvansickle `ffmpeg-7.0.2-amd64-static` | **GPL-3.0-or-later** |

The Windows binary carries `--enable-version3` **without** `--enable-gpl`, which is
why it is LGPL rather than GPL (verified 2026-08-08 by reading the configuration
string out of the shipped `ffmpeg.exe`). The macOS and Linux rows reflect the
upstream publishers' stated build configuration (`--enable-gpl --enable-version3`,
including libx264/libx265); those two binaries were **not** re-verified from a
packaged artifact on this machine.

- Windows builds: https://github.com/BtbN/FFmpeg-Builds/releases
- macOS builds: https://evermeet.cx/ffmpeg/
- Linux builds: https://johnvansickle.com/ffmpeg/
- FFmpeg project and complete corresponding source: https://ffmpeg.org/download.html
- License texts: https://www.gnu.org/licenses/gpl-3.0.html and
  https://www.gnu.org/licenses/lgpl-3.0.html

FFmpeg is redistributed **unmodified**, as a standalone executable, and is invoked
by this application only as a separate process (no linking against FFmpeg
libraries). This constitutes mere aggregation; it does not place Gamachine's
own code under the GPL or LGPL. Recipients of a build containing FFmpeg are
entitled to the corresponding source of FFmpeg for **their** platform's build,
available at the links above.

⚠️ This reasoning depends on all three conditions holding — unmodified, standalone,
separate process. Linking against the `libav*` libraries would break it and place
this project's own code under the FFmpeg build's license.

### yt-dlp — **[bundled] [fetched]**
**The Unlicense** (public domain dedication) — https://github.com/yt-dlp/yt-dlp

### Vosk (vosk-api) — **[bundled] [fetched]**
Copyright (c) Alpha Cephei Inc — **Apache-2.0** — https://github.com/alphacep/vosk-api

Where that license line comes from: the installed wheel's
`vosk-0.3.45.dist-info/METADATA` carries
`Classifier: License :: OSI Approved :: Apache Software License` and
`Home-page: https://github.com/alphacep/vosk-api`. ⚠️ The same METADATA also says
`License: UNKNOWN`, and the wheel ships **no LICENSE file at all** (measured
2026-09-03: `grep -i "licen|copying|notice" vosk-0.3.45.dist-info/RECORD` → no rows).
The Apache-2.0 claim therefore rests on the classifier plus the upstream repository,
not on a license text inside the distributed artifact.

The `vosk` package is embedded into the frozen backend via `collect_all('vosk')`
(`Backend/backend.spec`), so these four DLLs ship inside the installer:

| File | Size (bytes) | License |
|---|---|---|
| `libvosk.dll` | 26,447,872 | **Apache-2.0** (the vosk-api build itself) |
| `libstdc++-6.dll` | 26,619,146 | ⚠️ **unverified** — see below |
| `libgcc_s_seh-1.dll` | 606,425 | ⚠️ **unverified** — see below |
| `libwinpthread-1.dll` | 366,907 | ⚠️ **unverified** — see below |

⚠️ **Unverified rows.** No license statement for the three runtime DLLs was found in
the wheel; the file listing above is the only evidence the wheel provides (measured
2026-09-03 from `Backend/venv/Lib/site-packages/vosk/`). By their names they are the
**MinGW-w64 runtime (GPL with runtime exception)** — GCC's libstdc++/libgcc under
GPL-3.0 with the GCC Runtime Library Exception, and libwinpthread under MinGW-w64's
own permissive terms — but that identification is **inferred from the filenames, not
read from any license text shipped with them**, and it is recorded here as unverified
rather than asserted. Resolving it means obtaining the statements from the MinGW-w64
build these were produced by; the alphacephei model/download pages do not carry them
either (checked 2026-09-03).

### Vosk speech models — **[bundled] [fetched]**
Copyright 2020 Alpha Cephei Inc — **Apache 2.0**

| Model | Pinned archive | License |
|---|---|---|
| Turkish | `vosk-model-small-tr-0.3.zip` | **Apache 2.0** |
| US English | `vosk-model-small-en-us-0.15.zip` | **Apache 2.0** |

Where those license lines come from: the model index at
https://alphacephei.com/vosk/models has a **License** column, and it reads
`Apache 2.0` on both rows (fetched 2026-09-03). That page publishes **no checksum**
for any model, which is why `scripts/pinned_assets.json` records these two digests as
`kaynak: yerel:2026-09-03` — hand-computed, with this project as the root of trust
rather than the publisher. The copyright line is quoted from the `README` inside
`vosk-model-small-en-us-0.15` ("Copyright 2020 Alpha Cephei Inc"); the Turkish
model's `README` carries only the line "Turkish model" and no copyright or license
text of its own, so its row rests on the models page alone.

The models are **not** embedded in the frozen backend; `electron-builder.yml` copies
them to `resources/vosk/` in the installed application. They are data used only for
on-device speech recognition — no audio leaves the machine.

### OmniSharp-Roslyn — **[bundled] [fetched]**
Copyright (c) OmniSharp — **MIT License** — https://github.com/OmniSharp/omnisharp-roslyn

### .NET SDK — **[bundled] [fetched]** — ⚠️ Microsoft proprietary terms, not MIT
OmniSharp needs a .NET toolchain, and what ships is the **SDK**, not merely the
runtime — measured 2026-08-08: `third_party/omnisharp/dotnet-win-x64/sdk/10.0.100/`.
Its root `LICENSE.txt` reads **"MICROSOFT SOFTWARE LICENSE TERMS — MICROSOFT .NET
LIBRARY"**. That is *not* the MIT license under which the `dotnet/runtime` **source**
is published, and this entry previously claimed MIT in error.

The license text ships alongside the binary at
`resources/omnisharp/dotnet-win-x64/LICENSE.txt`. Individual SDK components remain
under their own licenses (many of them MIT).

- Applicable terms: the bundled `LICENSE.txt`
- Source repository (MIT — covers the source, not these binaries):
  https://github.com/dotnet/runtime

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
authenticates separately. These are **not** distributed with Gamachine
and remain subject to their own licenses and terms of service:

Claude Code (Anthropic), Codex CLI (OpenAI), Antigravity CLI (Google),
GitHub Copilot CLI, Cursor CLI, OpenCode, Kimi Code CLI (Moonshot AI).

---

## Reporting

If you believe an attribution is missing or incorrect, please open an issue on
the project repository.
