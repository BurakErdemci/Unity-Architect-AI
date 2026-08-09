<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. (This comment is invisible on GitHub.)
-->

## Gamachine v3.0.3

Compact now actually shrinks the context.

> 🍎 **macOS (Apple Silicon):** `Gamachine-3.0.3-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-3.0.3.exe`

### 🧠 Compact was summarising, not shrinking

Pressing Compact collapsed the conversation into a summary and left the model's
context exactly where it was. You could compact, then ask the CLI how much
context it was holding, and get the same number back — **773k of 1M tokens,
unchanged.** That was measured against a running session, not inferred from code.

Two faults, and the first one hid the second.

**The session was being revived.** Compact closes the live CLI session, which
used to be enough on its own. Since 3.0.1 the app also remembers each chat's CLI
session id so it can pick up where you left off — and nothing dropped that id
when you compacted. The next message resumed the old session, the CLI reloaded
its full transcript from disk, and the session that had just been closed came
back exactly as it was. On a resumed session the new summary is deliberately not
injected either, so the old context returned *and* the fresh summary never
arrived.

**Short chats skipped the reset.** Compact returned early when a chat had six
messages or fewer — the right call for summarising, the wrong one for resetting.
After a single compact the stored chat *is* short while the CLI session is still
full, so the next press reported "chat is already short" and reset nothing. That
is the state most people would actually run into.

Compact now drops the session id on both paths, so even a short chat gets a clean
CLI session. When there is nothing to summarise it says so and tells you the
context was reset anyway — and that message now comes from the dictionary, so an
English interface no longer shows a Turkish notification here.

### 🪟 The Windows installer name is fixed at the source

For three releases the installer shipped as `Gamachine.Setup.X.Y.Z.exe` while the
update feed asked for `Gamachine-Setup-X.Y.Z.exe`, and the difference was patched
by hand each time. The dots come from the installer framework's default naming
template rather than the product name, so renaming the product never helped. The
template is now pinned, and the build and the update feed agree without anyone
having to remember.

---

### 📥 Install

Download the file for your platform above. Windows removes the previous version
automatically. Updates are notify-only: Gamachine tells you a new version exists
and opens this page — it never installs anything by itself.

### ⚠️ Known limits

- **Intel Macs are not supported.** Only an Apple Silicon build is published.
- The app is unsigned, so both operating systems will warn you on first launch.
