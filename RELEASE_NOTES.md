<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. Turkish notes made that page unreadable for most of the
  audience. (This comment is invisible on GitHub — it is an HTML comment.)
-->

## Gamachine v2.3.1

A small but genuinely annoying bug: **pasting a photo into the chat sometimes
killed the whole session.**

> 🍎 **macOS (Apple Silicon):** `Gamachine-2.3.1-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-2.3.1.exe`

### 🖼 A pasted image no longer kills the chat

The symptom was odd: two photos would drop the session, three would not — so the
problem was not the *count*, it was the **size**.

The cause sat at the end of a chain. The image you paste is written to disk and
the model is handed only the file *path*; when the model opens it with `Read`, the
result comes back as base64 on a single line. That line had a 1 MB ceiling, and
crossing it did not truncate anything — **it took down the entire session.** Since
base64 is roughly 4/3 of the raw size, an ordinary 750 KB photo was enough.

The fix has two layers:

- The line ceiling was raised to the value the product's other CLI path already
  used.
- **The real bound was moved to the source:** large images are downscaled before
  they are ever written to disk. That closes the crash and cuts token cost.

Transparent PNGs survive this: the alpha channel is preserved. (The first attempt
turned transparent images into a solid black square — an audit round caught it
before release.)

### 🎮 The AI can now play the game (`manage_input`)

Entering play mode and taking a screenshot already worked; what was missing was
the ability to **act**. `manage_input` sends keyboard, mouse, gamepad and UI input
to a running game, so the AI can actually try the thing it just built.

Input is pressed onto Unity Input System's virtual devices from inside the
process: **no window focus required**, so your keyboard is not hijacked while the
AI plays.

> ⚠️ **Measure the limit first:** only game code written against the new Input
> System sees these events. If your project uses the old `Input.GetKey`, the input
> will not reach it; there, the one path that works is `ui_click`, which triggers
> uGUI buttons. Run `manage_input action="describe"` to have it report your
> project's input backend.

### 📸 The screenshot tool's name was wrong

The model was being taught an action name that did not exist, so screenshot
requests sometimes went nowhere. It is now bound to the real one.

### 📖 Documentation

Both READMEs were realigned with 105 commits' worth of reality. The most important
correction was a security claim: the docs said "unityMCP never shows an approval
card", when since v2.3.0 calls that *mutate* the scene do open one on the Claude
path. It is now described per provider.

---

**Installing:** on Windows the installer removes the previous version
automatically. On macOS, if the unsigned dmg is reported as "damaged":
`xattr -cr "/Applications/Gamachine.app"`

⚠️ Only **Apple Silicon (arm64)** is published for macOS. The Intel dmg is
deliberately withheld: it gets the host architecture's backend embedded in it, and
there is no Intel Mac here to test it on.
