<!--
  ⚠️ THIS FILE IS MAINTAINED BY HAND and goes stale easily.
  `.github/workflows/release.yml` publishes it as the BODY of the draft release
  (`body_path: RELEASE_NOTES.md`). On 2 Aug 2026 it still held v2.2.0's text; had
  the release job run, v2.3.0 would have shipped the previous version's notes.
  ▶ BEFORE cutting a release: move the top section of `CHANGELOG.md` here.

  Written in English on purpose: the release page is where a stranger lands at the
  moment they download. (This comment is invisible on GitHub.)
-->

## Gamachine v3.2.0

New models, a conversation that resumes itself when background work finishes, and
a persistent Antigravity session.

> 🍎 **macOS (Apple Silicon):** `Gamachine-3.2.0-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-3.2.0.exe`

### New models: Gemini 3.8 Flash, Gemini 3.7 Flash and GPT-6 Astra

Gemini 3.8 Flash is the recommended default now, with 3.7 Flash alongside it,
and GPT-6 Astra joins the Codex list. The reasoning-effort choices differ per
model — GPT-6 offers low through max, the new Gemini models low, medium and
high — and the picker only shows what the model you picked actually supports.

Gemini 3.7 and 3.8 need agy 1.1.25 or newer for their display names. One
limitation worth knowing before you pick it: GPT-6 cannot be used on the older
chat-completions agent loop, because its tool calling exists only on the newer
API. Choosing it there now says so instead of failing halfway through a run.

### The conversation wakes itself up when background work finishes

A run used to be tied to one open connection. If a subagent or a background
command finished after that connection closed, nothing resumed the turn — the
conversation just sat there until you typed something, and the result of the
work you were waiting for was invisible.

It now wakes itself. When background work completes, the conversation picks the
turn back up and tells you what finished. It waits if an approval card or a
prompt is on screen, so a wake never lands on top of a decision you are in the
middle of making, and it stops after three wakes in a row so a chain of tasks
cannot talk to itself indefinitely.

### Antigravity CLI keeps one session open instead of restarting every turn

The Antigravity path used to start a fresh process for every single turn and
hand it the whole conversation as a command-line argument. That capped how much
history could be carried on Windows, made each turn pay a full startup, and left
the app scraping the CLI's own transcript files to figure out what happened.

It now holds one live session per conversation and sends each turn into it. The
turn's real token usage comes back from the CLI itself rather than being
reconstructed, the Windows length limit is gone, and everything that existed to
work around the restart — the history trimming, the transcript scraping, the
polling loop that guessed whether the CLI was still alive — is gone with it.

### The usage and context panel stops going blank

The panel emptied out whenever the CLI session was busy or unavailable, and the
context section never showed anything at all. Usage readings are account-level
and stay true for a while, so the last successful reading is now kept for two
hours and shown with a "stale" badge and its age when nothing live can be
reached. Context falls back to an estimate from the stored conversation, clearly
labelled as an estimate rather than presented as a measurement.

### Removed: the token and cost readout in the message box

The small "— tok" figure next to the memory ring reported wildly wrong numbers.
It is removed rather than corrected. The memory ring and the usage button are
unchanged.

### Under the hood: secrets, approval cards and session cleanup

Everything the Antigravity CLI sends back now passes through one redaction step
on its way to the screen, including the final answer of a successful turn, which
previously bypassed it — that was the path by which a credential in a model's
own reply could reach the interface. Key names are masked as well as values, and
a deeply nested payload is trimmed rather than being allowed to kill the turn.

Approval cards are attributed to the conversation that created them, so a
pending card in one conversation no longer blocks another one from continuing.
A card that cannot be attributed still blocks, which is the safe direction.
Closing a session releases its own pending cards immediately instead of leaving
them to expire, and Stop only dismisses the cards belonging to the conversation
being stopped.
