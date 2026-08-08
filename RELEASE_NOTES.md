<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. (This comment is invisible on GitHub.)
-->

## Gamachine v3.0.1

Three fixes on top of v3.0.0. **If you installed v3.0.0, update** — the first one
prevented Claude Code from starting at all on most Windows installs.

> 🍎 **macOS (Apple Silicon):** `Gamachine-3.0.1-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-3.0.1.exe`

### 🔧 Claude Code would not start on Windows

v3.0.0 stopped shipping a copy of the Claude Code CLI, so the app looks for the
one you installed. But `npm install -g @anthropic-ai/claude-code` puts only a
`claude.cmd` shim on PATH, and the SDK refuses to run `.cmd` files — a real
precaution, since `cmd.exe` can execute commands injected through arguments. The
result was a session that never opened, with Claude Code installed:

```
Refusing to execute batch script '...\claude.CMD'
```

The shim names its target in plain text, so the app now reads it and uses the real
executable. Nothing to install or configure.

### 🧠 The chat no longer forgets silently

When history was too long to fit into the context, the oldest messages were
dropped without a word. The model received a conversation that began in the
middle and had no way to know anything was missing — so instead of saying "I don't
have that part", it answered as if those messages never existed. On a real
conversation this was measured at 17 of 48 messages surviving: **71% of the text
gone, silently.**

Two changes:

- **The CLI's own session is resumed** where possible. It keeps the full
  transcript on disk; the app now remembers the session id and calls it back
  instead of re-sending a truncated summary. History survives closing the app.
- When a summary *is* still needed — after switching agents, or if the session is
  gone — the cut is now stated. The model is told how many earlier messages are
  missing and asked to say so rather than guess.

The session id is tied to the project folder. Open a different workspace and it is
ignored, so a resumed session can never show you another project's history.

---

**Installing:** on Windows, if you are coming from *Unity Architect AI* (v2.x),
remove it yourself first — the rename changed the application id, so it is not
replaced automatically. On macOS, if the unsigned dmg is reported as "damaged":
`xattr -cr "/Applications/Gamachine.app"`

⚠️ Only **Apple Silicon (arm64)** is published for macOS, and the builds are **not
code-signed**: Windows SmartScreen → *More info* → *Run anyway*; macOS →
right-click → *Open*.
