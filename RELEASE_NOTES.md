<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. (This comment is invisible on GitHub.)
-->

## Gamachine v3.1.0

Offline live dictation, a 3D model preview, and bundled video tools.

> 🍎 **macOS (Apple Silicon):** `Gamachine-3.1.0-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-3.1.0.exe`

### 🎙️ Dictation: speak into the chat box, and it never leaves the machine

A microphone button in the chat box transcribes live, on-device, in Turkish or English, with no audio ever uploaded.

### 🛡️ Hardened before release

An external audit found 32 issues in the dictation code; 29 were fixed, each with a regression test.

### 🧊 3D model files open in a preview instead of the code editor

FBX, glTF/GLB, Collada, OBJ, STL and PLY files now open in an orbiting, animatable preview instead of the text editor.

### 🖼️ Images open in the content area too

Textures and sprites open as pictures in the same panel the 3D preview uses, with a pixel-sharp actual-size mode.

### 🎬 Video links work without installing anything first

The tools that fetch and read video now ship with the app, YouTube Shorts links no longer fail, and a stalled or blocked download says why.

### 🗂️ The model list comes from your own account

The hand-maintained model list is gone; each provider is now asked what your account can actually reach.

### 📊 A usage and context panel, and a gauge that is always there

The context gauge is always on screen now, backed by a panel with real token counts and cost, opened without touching the conversation.

### ☑️ Questions from the assistant can take more than one answer

Multi-select, a free-text answer, and a skip option are all available now, and a fresh question no longer inherits the last one's selection.

### ⏹️ A run that stops early says why

A stalled run now stops on repeated tool calls rather than a fixed step count, and says which tool repeated; the step ceiling is a 300-step last resort.

### ⚠️ Errors say what actually went wrong

Provider outages, rate limits, and tool-support gaps are each named instead of collapsed into one generic error, and long silences report who the app is waiting on.

### 🔧 Gemini models can use tools

A long-standing bug that broke tool calls on Gemini API models is fixed.

### 📜 The chat stays where you left it

Scrolling up no longer gets dragged back to the bottom on new output, except for cards that need your answer.

### 🔗 The content area follows the file

Renaming, moving, or deleting a file now keeps the preview or editor in sync with it instead of pointing at a stale path.

### 🐳 The Docker development container actually runs

Docker mode is fixed after never having worked, and now fails fast with a clear message instead of silently.

### ⚖️ The project is now plain MIT

The Commons Clause condition is removed; the project is MIT-licensed and open source in the OSI sense.

### 🧹 Under the hood

The bundled Unity sprite tool was updated, and a long series of audited fixes on file reading, approval gates, and the Docker path each shipped with a regression test.

---

### 📥 Install

Download the file for your platform above. Windows removes the previous version
automatically. Updates are notify-only: Gamachine tells you a new version exists
and opens this page — it never installs anything by itself.

### ⚠️ Known limits

- **Intel Macs are not supported.** Only an Apple Silicon build is published.
- The app is unsigned, so both operating systems will warn you on first launch.
