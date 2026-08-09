<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. (This comment is invisible on GitHub.)
-->

## Gamachine v3.0.2

The agent can now play a game it is not looking at.

> 🍎 **macOS (Apple Silicon):** `Gamachine-3.0.2-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-3.0.2.exe`

### 🎮 Input reaches the game again

`manage_input` hands your running game to the agent — it injects keyboard, mouse
and gamepad events straight into Unity's Input System, so the game receives real
input while nobody is at the keyboard. It worked in demos and failed in real use,
and the difference was never the input path.

While you are in the chat window, Unity sits fully unfocused. Two separate things
happen there, and both were measured against a live editor with the window in the
background the whole time.

**The engine stops.** Play mode enters, `timeScale` reads 1, and the game sits
frozen at frame 2. Every key we sent was correct; no frame ever processed it. The
project's own *Run In Background* setting was already on and did not help — the
runtime value is separate and starts off.

**The devices get switched off.** The Input System disables every device when the
application loses focus, the real keyboard and mouse included. The key arrives at
a device nobody is listening to.

Both are handled now, on the input path only — pressing Play by hand does not
quietly change how your editor behaves. Nothing is written to your project: the
settings we take over are handed back when play mode exits.

### 🩺 `describe` tells the truth

Ask it why input seems ignored and it used to answer by listing the members it
had resolved — saying yes while the engine was frozen. No focus flag catches
this: during the freeze Unity still reports itself as focused. It now returns a
frame counter. Call it twice; if the number does not move, the game is not
running and the input path is not your problem.

### 📄 Wording corrections

The project is **source-available**, not open-source — MIT + Commons Clause
restricts commercial use, so it does not meet the OSI definition. The licence
section always said this correctly; one summary line did not. Our own clarifying
paragraph in `LICENSE` has also moved out of the Commons Clause text so the
standard condition reads verbatim, and the `~/.unity_architect_ai` paths now
explain themselves: they hold your existing encryption key and database, and
renaming them would make already-saved API keys undecryptable.

---

**Installing:** on Windows, if you are coming from *Unity Architect AI* (v2.x),
remove it yourself first — the rename changed the application id, so it is not
replaced automatically. On macOS, if the unsigned dmg is reported as "damaged":
`xattr -cr "/Applications/Gamachine.app"`

⚠️ Only **Apple Silicon (arm64)** is published for macOS, and the builds are **not
code-signed**: Windows SmartScreen → *More info* → *Run anyway*; macOS →
right-click → *Open*.
