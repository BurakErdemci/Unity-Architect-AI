# Contributing

> Opening issues and pull requests in Turkish is perfectly fine — that is a
> conversation, not a file in the repository. What goes *into* the repository
> is English (see below).

Thanks for looking. This is a non-commercial, one-person project, so the most
useful contributions are small, sharp and self-contained.

## Before you write code

**Open an issue first** for anything beyond a bug fix. Not bureaucracy — the
project deliberately keeps a narrow scope (see below), and it would be unfair to
let you build something that then gets declined.

## Scope

The project is in **maintenance mode**: the readily accepted changes are new AI
models and new providers, plus bug fixes.

Explicitly *not* today's scope: support for other game engines (Unreal, Godot),
and large refactors of the approval/execution core.

## Ground rules that are not obvious

These come from things that actually broke here, so they are worth reading before
your first PR:

- **A fix without a test that fails when the fix is removed is not finished.**
  Verify it by mutation: delete your fix, watch the test go red, put it back.
  Several fixes here looked complete and guarded nothing.
- **A test must not read the constant it protects.** If it imports the value it
  is asserting against, the criterion moves with the value and the test protects
  nothing.
- **"The function was called" is not "the user saw it."** Prefer asserting the
  observable result.
- **Closing the path a report names is not closing the class.** When you fix
  something, count the sibling call sites. This repo's most common failure shape
  is a fix that closes one of four paths.
- **Comments carry the reasoning, not the code.** A comment restating what the
  line does is noise; a comment recording a measurement, a constraint or an
  incident earns its place. An undocumented non-obvious decision is a defect too.
- **Everything written into the repository is in English** — code, identifiers,
  comments, docstrings, internal docs, log lines and commit messages. The one
  exception is user-facing text for the app's Turkish language option, which
  lives behind the i18n layer and is Turkish by definition.
  (This line used to ask for Turkish comments. It was reversed on 30 Aug 2026:
  a codebase whose reasoning is written in one language and whose identifiers
  are in another is harder to read in both, and the audit trail — commit
  messages, test names, findings — was already English.)
- **Do not add a dependency without asking first** in an issue.

## Running it

```bash
# Backend (Python 3.13+)
cd Backend
python -m venv venv
# Windows: venv\Scripts\activate     macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app/main.py

# Frontend (Node 20+), in another shell
cd Frontend/frontend
npm install
npm run dev
```

You do not need Unity to work on most of this, and you do not need Unity to
compile the C# side — it builds against Unity assemblies with Roslyn.

## The gates your PR has to pass

Run these before you push; CI runs the same four jobs.

```bash
# Backend tests
cd Backend && python -m pytest tests -q          # Windows: set PYTHONUTF8=1 first

# Frontend types + tests
cd Frontend/frontend && npx tsc --noEmit && npx vitest run

# unity-mcp server tests
cd unity-mcp/Server && python -m pytest -q
```

`tsc` must report **zero** errors. If a test is red before your change, say so in
the PR rather than working around it — two tests are currently red on Windows
because they assert `HOME`, which Windows does not set.

## Pull requests

- One concern per PR. Two unrelated fixes are two PRs.
- Say what you measured, not just what you changed. "Verified by mutation" is a
  sentence a reviewer can trust.
- If you left something unfinished or untested, write that down. A stated gap is
  worth more than a confident silence.

## Licence

Contributions are accepted under the project's licence: **MIT**. By submitting a
patch you agree that your contribution is released under those terms. If that does
not work for you, please don't submit a patch.
