# Security Policy

> Türkçe rapor göndermek tamamen normaldir — bu dosya İngilizce yazıldı çünkü
> hedef kitlesi dışarıdaki güvenlik araştırmacıları.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use one of these instead:

1. **GitHub private vulnerability reporting** — the *Security* tab of this
   repository → *Report a vulnerability*. Preferred, because it keeps the
   discussion attached to the code.
2. **Email** — `erdemciburakemre@gmail.com`, with `SECURITY` in the subject.

Please include: what you did, what happened, what you expected, and the version
you tested (`Help → About`, or the release tag). A minimal reproduction is worth
more than a long description.

This is a one-person, non-commercial project. There is no bounty and no
guaranteed response window. Realistically you should expect a first reply within
a few days.

## What is in scope

This application drives AI coding agents and can read, write and execute things
on the user's machine, so its security properties are mostly about **containment
and consent**. In-scope examples:

- Bypassing the approval gate — getting a file write, a file delete, a terminal
  command or a Unity scene mutation to happen **without** the user's card being
  shown and accepted.
- Escaping the selected workspace: reading or writing outside it, or writing a
  `.cs` file outside `Assets/Scripts/`.
- Leaking secrets: API keys, session tokens or the local MCP token appearing in
  logs, in the chat transcript, in process arguments visible to other processes,
  or in a file readable by another user.
- Getting the renderer to navigate to, or execute, remote content.
- Anything that lets a *prompt* — a chat message, a file's contents, a web page
  the agent fetched — cause an unapproved side effect.

## What is out of scope

- **Unsigned installers.** Windows SmartScreen and macOS Gatekeeper warnings are
  expected: the builds are not code-signed yet. Known, documented, not a report.
- **Third-party AI CLIs and their credentials.** Claude Code, Codex, Antigravity,
  Copilot, Cursor, OpenCode and Kimi are installed and authenticated by the user;
  report issues in their own trackers. What *is* in scope is how this application
  passes data to them.
- **What the user explicitly approved.** If a card was shown and accepted, the
  resulting action is intended behaviour, however destructive.
- **Auto-approve mode doing what it says.** Choosing it is a decision to skip
  cards.
- Reports produced only by a scanner, with no demonstrated impact.

## Known and accepted limitations

Stated up front so nobody spends time rediscovering them:

- Builds are **not code-signed or notarized** on either platform.
- API keys are encrypted at rest, but the encryption key sits next to the
  database in the user's home directory. This protects against casual reading,
  **not** against anyone who can already read that directory.
- The Windows installer is per-user, so its install directory is writable by the
  user's own processes.
- Cloud-API function calling does not gate file writes; the CLI agent paths do.
  This asymmetry is documented in the README.

If you think one of these is worse than described, that itself is a valid report.
