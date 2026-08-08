<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. (This comment is invisible on GitHub.)
-->

## Gamachine v3.0.0

**Unity Architect AI is now Gamachine.** A major version because this is not an
upgrade you install over the old one — and because two things about how the app
behaves have changed on purpose.

> 🍎 **macOS (Apple Silicon):** `Gamachine-3.0.0-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-3.0.0.exe`

### ⚠️ Read this before installing

**The old version is not removed automatically.** The application id changed with
the rename, so Windows treats this as a separate product: uninstall *Unity
Architect AI* yourself, or you will have both. For the same reason, an installed
v2.3.1 will not offer you this update — this is the only place it is announced.

**Your data is kept.** Chat history, API keys and settings live in
`~/.unity_architect_ai` and that path deliberately did **not** change: it holds the
key your API keys are encrypted with, and renaming it would have made them
permanently unreadable. It is an invisible folder; the old name there costs you
nothing.

### 🔌 Bring your own AI — we no longer ship one

Earlier builds silently included a full copy of the Claude Code CLI. Nobody chose
that: the SDK vendors it, and the packaging step swept it in. It also defeated the
point — the bundled copy took priority over the CLI you had installed yourself, so
your own Claude Code was never used.

It is gone. You connect what you already use: an API key, or a CLI agent on your
machine. **We do not install a third-party AI tool on your computer without telling
you.**

The installer is **253 MB smaller** as a result (roughly 45%).

### 🔒 The chat stays locked until a provider is connected

Picking a model was never the same as having the thing behind it. A cloud provider
needs a key; a CLI agent needs to be installed. Previously the app let you send a
message anyway, and the first reply could be a raw Python traceback.

Now the composer is disabled until the selected provider is actually usable, and it
tells you which of the three things is missing: a key, an installation, or a
sign-in.

### 🌍 English, properly

The interface followed a hard-coded Turkish default even for users who had never
seen Turkish — and that same value was sent to the model, so a question asked in
English came back in Turkish. The starting language now follows your operating
system.

The dictionary grew from 157 to 373 entries and the entire renderer goes through
it: toasts, tool blocks, approval cards, the terminal panel, the export dialog.

> Still Turkish: the operating-system dialogs the desktop shell opens (folder
> authorisation, update prompt) and backend error messages. Both need work beyond
> translation and are not done yet.

### ⚖️ Licensing and privacy

- **The installer now actually contains the licences it is required to ship.**
  Previously `LICENSE` and `THIRD-PARTY-NOTICES.md` were never copied into the
  package, while FFmpeg — which requires its licence text to travel with the binary
  — was shipped.
- **The FFmpeg notice was wrong.** It declared GPL everywhere; the Windows build is
  LGPL, and no Windows source link was given at all. Now stated per platform.
- **The bundled .NET was declared as MIT.** What ships is the .NET **SDK** under
  Microsoft's proprietary terms. Corrected.
- **Third-party telemetry is off.** The MCP server inherited from the upstream fork
  reported to an external endpoint on startup, enabled by default, with nothing in
  this product telling you so. Disabled at the source.

### 🐛 Fixes

- The Codex error path sent raw exception text to the interface without redaction —
  the same text can carry the local MCP key. The Claude path already redacted it;
  the sibling path did not.
- The chat input's placeholder read *"Ask zap a question…"*, left over from a
  template.
- Dead screens were removed, which let the content-security policy drop its last
  remote image source.

---

**Installing:** on Windows, remove *Unity Architect AI* first (see above). On
macOS, if the unsigned dmg is reported as "damaged":
`xattr -cr "/Applications/Gamachine.app"`

⚠️ Only **Apple Silicon (arm64)** is published for macOS. The Intel dmg gets the
host architecture's backend embedded in it and there is no Intel Mac here to test
it on, so it is deliberately withheld rather than shipped untested.

⚠️ The builds are **not code-signed**. Windows SmartScreen → *More info* → *Run
anyway*; macOS → right-click → *Open*.
