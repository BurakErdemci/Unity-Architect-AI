<div align="center">

# Unity Architect AI

**An agentic development studio that unifies every coding agent and live Unity control in a single desktop app**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Unity MCP](https://img.shields.io/badge/Unity_MCP-Embedded-7B2FBE?style=for-the-badge&logo=unity&logoColor=white)](./unity-mcp)
[![License](https://img.shields.io/badge/License-MIT%20%2B%20Commons%20Clause-green?style=for-the-badge)](LICENSE)

*Claude Code, Codex, Antigravity (agy), cloud APIs and live Unity Editor control — all in the same chat window, behind the same approval system, aware of the same project.*

[Turkish README](./README.md)

<br/>

![Unity Architect AI Demo](docs/media/demo.gif)

*Develop with natural language in the code editor, then control the Unity Editor live — all from a single window.*

</div>

---

## Table of Contents

- [Under One Roof: What Does This Project Unify?](#-under-one-roof-what-does-this-project-unify)
- [Why Unity Architect AI?](#-why-unity-architect-ai)
- [Features](#-features)
- [System Architecture](#-system-architecture)
- [Supported AI Providers](#-supported-ai-providers)
- [Tool Ecosystem (MCP + Function Calling)](#-tool-ecosystem-mcp--function-calling)
- [Approval & Security Architecture](#-approval--security-architecture)
- [Installation](#-installation)
- [Packaging (dmg / exe)](#-packaging-dmg--exe)
- [Usage](#-usage)
- [Unity MCP Integration](#-unity-mcp-integration)
- [Agentic System Details](#-agentic-system-details)
- [Developer Notes: Lessons Learned](#-developer-notes-lessons-learned-and-architectural-decisions)
- [Contributing](#-contributing)

---

## 🎯 Under One Roof: What Does This Project Unify?

Today a Unity developer juggles multiple windows for different jobs: one CLI to generate code, a separate plugin to control the Editor, yet another app to chat. Each has its own approval logic, its own configuration, its own disconnected view of the project.

**Unity Architect AI brings them all into a single application** — and puts them behind *one approval gate*. You pick a model from a dropdown; whether it's the Claude Code CLI, Codex, Antigravity (agy), GitHub Copilot CLI, or a direct cloud API — they all:

- run **in the same chat window**,
- see **the same project** as their workspace,
- show **the same file/terminal approval cards** (scope below: deletes and dangerous commands are gated on every path; code writes are gated on the CLI paths and deliberately ungated on the cloud API path),
- and, when enabled, drive **the same live Unity Editor** over MCP.

### Agent × Capability Matrix

| | Chat & Analysis | Write/Edit files (approved) | Terminal (approved) | Live Unity Editor control | Auth source |
|---|:---:|:---:|:---:|:---:|---|
| **Claude Code** (CLI) | ✅ | ✅ MCP | ✅ MCP | ✅ unityMCP — **gated** | your Anthropic subscription |
| **Codex** (CLI) | ✅ | ✅ MCP | ✅ MCP | ✅ unityMCP | your OpenAI subscription |
| **Antigravity / agy** (CLI) | ✅ | ✅ `unityai` bridge | ✅ bridge | ✅ unityMCP (HTTP) | your Google subscription |
| **GitHub Copilot** (CLI) | ✅ | ✅ MCP | ✅ MCP | ✅ unityMCP | your Copilot subscription |
| **Cursor** (CLI) | ✅ | ✅ MCP | ✅ MCP | ✅ unityMCP | your Cursor subscription |
| **OpenCode** (CLI) | ✅ | ✅ MCP | ✅ MCP | ✅ unityMCP | free / your own key |
| **Kimi Code** (CLI) | ✅ | ✅ MCP | ✅ MCP | ✅ unityMCP | your Moonshot subscription |
| **Cloud API** (Claude/GPT/Gemini/…) | ✅ | ✅ function calling | ✅ function calling | ✅ function calling | your API key |
| **Ollama** (local) | ✅ | ✅ (compatible models) | ✅ | ⚠️ partial | free, offline |

What this matrix delivers is simple but rare: **the experience is identical regardless of the source.** Switching from Codex to Claude Code is one dropdown; the diff viewer, terminal approval and Unity integration you're used to stay exactly the same.

> **Important distinction:** Approval cards appear for **file deletes and dangerous terminal commands** on every path; for **file writes** on the CLI agent paths, but **not on the cloud API / Ollama function-calling path**. For **live Unity scene operations** it depends on the provider: on the Claude path, unityMCP calls that *mutate* the scene now open a card; on Codex and agy they do not. Full table and rationale: [Approval scope](#️-approval-scope-what-is-and-isnt-confirmed-an-honesty-note).

---

## 🚀 Why Unity Architect AI?

AI tools in the Unity ecosystem usually land at one of two extremes: they either just write code, or they just chat. Neither can do what a real development partner does on its own — understand the project, find the bug, fix it, test it in the terminal, and see it inside the Unity Editor.

| Traditional AI Assistants | Unity Architect AI |
|---|---|
| Locked to a single provider | 7 CLI agents (Claude Code, Codex, agy, Copilot, Cursor, OpenCode, Kimi Code), 8+ cloud APIs (incl. the free NVIDIA NIM pool), Ollama — one menu |
| Writes code, doesn't see the project | Scans every `.cs` file in the workspace, extracts an architecture map |
| Can't touch the file system | Read/write/delete files — every dangerous op behind an approval card |
| Unaware of the Unity Editor | Adds GameObjects, binds components, reads the console via MCP |
| Can't run terminal | Secure terminal layer; dangerous commands require approval |
| Every chat starts from zero | Persistent memory + project analysis keep the context |
| Setup hassle | `uv`, OmniSharp + .NET SDK, ffmpeg/yt-dlp — all **bundled into the app**, zero extra install |

---

## ✨ Features

### Many agents, one experience
- Claude Code / Codex / agy / GitHub Copilot / Cursor / OpenCode / Kimi Code CLI agents + Anthropic, Google, OpenAI, NVIDIA NIM (free pool: GLM 5.2, Qwen3 Coder 480B, Nemotron 3…), Groq, DeepSeek, Moonshot cloud APIs + local Ollama models
- When a CLI is selected, the backend writes that tool's MCP config **at call time, automatically** (`~/.claude.json`, `~/.codex/config.toml`, `~/.gemini/antigravity-cli/mcp_config.json`; Copilot gets a session-scoped `--additional-mcp-config`)
- **Transparent hot-swap**: as the Gemini CLI was being retired, the `gemini-*` model IDs were kept and the backend silently routes them to the Antigravity (`agy`) engine — the frontend never changed

### Autonomous agentic loop
- AI receives a task → thinks → calls a tool → evaluates the result → loops until done
- Infinite-loop protection at 15 iterations max
- Every step streams live (SSE): `thinking` → `tool_call` → `tool_result` → `response`
- The "Stop" button both cuts the SSE connection and rejects all pending approval gates on the backend (two-layer cancellation)

### Approval gate system
- File write → side-by-side **diff viewer** (current vs. new) — **on the CLI agent paths** (MCP / `unityai` bridge); writes are ungated on the cloud API function-calling path, rationale in [Approval scope](#️-approval-scope-what-is-and-isnt-confirmed-an-honesty-note)
- File delete → delete confirmation with content preview — **on every path**
- Terminal command → approval card showing the command (except commands considered safe) — **on every path**
- Whenever a card does appear, CLI agents and cloud APIs go through the **same** approval UI

### Live Unity Editor control (embedded, zero install)
- 46 Unity Editor tools based on [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp)
- Scene, GameObject, components, prefabs, materials, physics, animation, build settings
- **It can play the game** (`manage_input`): enters play mode, sends keyboard/mouse/gamepad input, takes a screenshot and judges the result — it actually tries what it built ([details and limits](#-the-ai-can-now-play-the-game-manage_input))
- The `uv` toolchain is **bundled into the app** (macOS arm64+x64, Windows x64) — works even if the user has no `uv` installed
- One-click toggle: turn it on while the Unity Editor is open, ready when it turns green

### Project awareness (RAG)
- All `.cs` files in the workspace are scanned, chunked, and relevant code is pulled via keyword search
- "Learn Project" → extracts classes, inheritance relationships and key methods to produce an **architecture map**, writes a user-facing summary plus a technical note to its own memory
- `/compact` lets the AI summarize long conversations, preserving context before hitting the token limit

### OmniSharp code intelligence (embedded, zero install)
- **OmniSharp LSP** sidecar — real Roslyn-based C# analysis; errors surface in the Monaco editor
- The **.NET SDK it needs is bundled into the app** (Windows, macOS, Linux) — users don't need .NET installed

> **Why the SDK and not just the runtime?** Not a preference, a measured requirement: OmniSharp resolves MSBuild from the SDK to load a project. With only the runtime bundled, `hostfxr_resolve_sdk2` fails and the sidecar returns no `initialize` response for 25 seconds; with a real SDK the same work takes **3 seconds**. The measurement is written down in `scripts/fetch_omnisharp.py`.
- Resolves the Unity project's `Assets/` and package references (the hand-made linter was removed in favor of a full LSP)

### Real effort control
- Segmented **effort selector** (Auto by default) — the selection **actually** takes effect on every provider, it's not decorative
- Provider-aware registry: `model_reasoning_effort` for Codex, `thinking_level`/`thinkingBudget` for Gemini, thinking budget for Claude — the UI only shows the levels each model supports

### Video → chat
- Drop a video link/file into the chat: bundled **ffmpeg + yt-dlp** extract frames and a transcript, which join the visual analysis pipeline
- Duration-aware frame budgeting + frame dedup keep the token cost under control

### Update notifications
- **New-release notifications** via GitHub Releases (electron-updater) — no silent download/install, the user decides

### Professional IDE interface
- **Monaco Editor** (the VS Code engine) — Unity C# syntax
- **Integrated terminal** (xterm.js + node-pty) — real PTY, system commands
- **Diff viewer**, **live thinking block** (Claude Extended Thinking / Gemini thinking stream)
- **Model selector** — instant switching across providers
- **Bilingual UI (TR/EN)** — React Context + `useLang()`, 100+ translation keys, persisted via localStorage

---

## 🏗 System Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Electron Desktop App                  │
│  ┌──────────────────────────────────────────────────┐ │
│  │  main/background.ts — LOCAL_APP_TOKEN = uuid()     │ │
│  │  ├─► Backend subprocess env                        │ │
│  │  ├─► Unity MCP subprocess env                      │ │
│  │  └─► Renderer IPC: 'app-token-get'                 │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐    │
│  │ Chat Panel  │  │Monaco Editor │  │  Terminal   │    │
│  │ (SSE stream)│  │ (OmniSharp)  │  │ (xterm.js)  │    │
│  └──────┬──────┘  └──────────────┘  └─────────────┘    │
│         │        React 18 + Next.js (TR/EN i18n)        │
└─────────┼──────────────────────────────────────────────┘
          │ HTTP / SSE   +   X-Session-Token header
          ▼
┌──────────────────────────────────────────────────────┐
│            FastAPI Backend (Python 3.13)               │
│  ┌─────────────────────────────────────────────────┐  │
│  │              AgentRunner (Agentic Loop)          │  │
│  │   Request → Think → Tool Call → Result → … → Ans │  │
│  └────────────────────┬────────────────────────────┘  │
│         ┌─────────────┼─────────────┐                  │
│         ▼             ▼             ▼                   │
│  ┌────────────┐ ┌──────────┐ ┌──────────────┐          │
│  │ToolRegistry│ │ProjectRAG│ │MemoryManager │          │
│  │read/write  │ │.cs scan  │ │/compact      │          │
│  │run_command │ │+ keyword │ │memories/*.md │          │
│  │search_proj │ │+ arch map│ └──────────────┘          │
│  └────────────┘ └──────────┘                           │
│  ┌──────────────────────────────────────────────────┐ │
│  │                  AI Providers                     │ │
│  │  Claude │ OpenAI │ Gemini │ Groq │ … │ Ollama     │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────┐ │
│  │       unityai MCP Server (FastMCP)                │ │
│  │  save_file │ read_file │ list_directory │ bash    │ │
│  │            ↑ approval_bridge → approval card       │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────┬──────────────────────┘
                                  │ MCP (stdio / HTTP) + run_command bridge
          ┌───────────────────────┼───────────────────┐
          ▼                       ▼                    ▼
   ┌─────────────┐       ┌─────────────────┐   ┌──────────────────┐
   │ Claude Code │       │   Codex CLI     │   │ Antigravity (agy)│
   │ MCP native  │       │   MCP native    │   │ run_command →    │
   │             │       │                 │   │ unityai bridge   │
   └──────┬──────┘       └────────┬────────┘   └─────────┬────────┘
          └───────────────────────┼──────────────────────┘
                                  │ MCP HTTP (127.0.0.1:8080)
                                  ▼
                         ┌─────────────────┐
                         │   Unity MCP     │
                         │ (CoplayDev)     │  ← uvx bundled
                         │   46 tools      │
                         └────────┬────────┘
                                  ▼
                         ┌─────────────────┐
                         │  Unity Editor   │
                         │  (C# Plugin)    │
                         └─────────────────┘
```

### Directory Layout

```
unityaıPython/
├── Backend/
│   ├── app/
│   │   ├── agentic/             # AgentRunner (agentic loop), approval gates
│   │   ├── providers/           # Provider layer (split)
│   │   │   ├── manager.py        #   provider selection (single entry point)
│   │   │   ├── cli_base.py       #   shared CLI logic + MCP config writing
│   │   │   ├── claude_provider.py / codex_provider.py / agy_provider.py
│   │   │   └── api_providers.py  #   Anthropic/Gemini/OpenAI/Ollama SDKs
│   │   ├── unity_ai_mcp/        # Our MCP server (FastMCP)
│   │   │   ├── tools/            #   save_file, delete_file, read_file, list_dir, bash
│   │   │   ├── approval_bridge.py#   MCP/CLI ↔ backend approval bridge
│   │   │   ├── unity_mcp_manager.py # Unity MCP subprocess + bundled uvx
│   │   │   └── server.py
│   │   ├── unityai_cli.py       # run_command bridge for agy (same approval gate)
│   │   ├── tools/               # Function-calling ToolRegistry (cloud API path)
│   │   ├── rag/                 # ProjectRAG (scan+keyword), MemoryManager
│   │   ├── routes/              # FastAPI routers (auth/chat/config/…)
│   │   ├── omnisharp/           # OmniSharp LSP sidecar (manager + client, with bundled .NET)
│   │   ├── auth_utils.py        # LOCAL_APP_TOKEN validation
│   │   └── database.py          # SQLite — single local user (id=1), Fernet
│   ├── vendor/                  # fetch_uv (uv toolchain) + fetch_video_bins (ffmpeg/yt-dlp)
│   ├── backend.spec             # PyInstaller — frozen 'backend' binary
│   └── tests/
├── Frontend/frontend/
│   ├── renderer/                # home.tsx (IDE), components/, hooks/, lib/i18n.tsx
│   └── main/background.ts       # Electron main process, LOCAL_APP_TOKEN + updater
├── scripts/fetch_omnisharp.py   # downloads OmniSharp + .NET SDK (third_party/, not in git)
├── unity-mcp/                   # CoplayDev/unity-mcp fork (Server + MCPForUnity plugin)
└── docker-compose.yml
```

---

## 🤖 Supported AI Providers

Providers fall into 3 categories based on **where the model runs**. Tool usage (MCP / function calling) is a separate layer — covered in the next section.

### 1. Subscription CLI agents (the headline)

The backend invokes the official CLI on your machine as a subprocess, using the tool's own auth (your subscription). Tool usage is via **MCP** — the backend writes the required config before each call.

| CLI Tool | Models (example) | Config file | Tool mechanism |
|---|---|---|---|
| **Claude Code** | claude-sonnet-5, claude-fable-5, claude-opus-4-8, claude-haiku-4-5 | `~/.claude.json` (user scope) | MCP native (stdio + HTTP) |
| **Codex** | gpt-5.6-sol/terra/luna, gpt-5.5, gpt-5.4 | `~/.codex/config.toml` | MCP native |
| **Antigravity (agy)** | Gemini 3.5 Flash + Claude/GPT-OSS via agy | `~/.gemini/antigravity-cli/` | `run_command` → `unityai` bridge |
| **GitHub Copilot** | copilot-auto + Claude/GPT/Gemini options | session-scoped `--additional-mcp-config` | MCP native (global config untouched) |
| **Cursor** | cursor-auto + Claude/GPT options | session-scoped | MCP native |
| **OpenCode** | free pool + your own key | `opencode.json` | MCP native |
| **Kimi Code** | kimi-k3, kimi-k2.7-code | `<workspace>/.mcp.json` | MCP native |

> ⚠️ **Kimi Code honesty note:** the provider is written and its tests pass, but the development machine has no Kimi subscription, so it has **never been exercised end to end**. If you hit unexpected behaviour on the Kimi path, that is why — an issue would be welcome.

> **Why is agy different?** agy's `--print` mode does not natively load MCP servers. So file/terminal operations go through a `unityai` CLI bridge invoked via `run_command` that **shares the exact same approval gate** as the MCP tools. Details: [Developer Notes — The agy Saga, Scene 7](#scene-7-the-fix--i-was-knocking-on-the-wrong-door).

### 2. Cloud API (direct API call)

The backend calls the provider's official SDK or the OpenRouter gateway. Tool usage is via **function calling** (the model emits a JSON tool call, the `AgentRunner` dispatches it).

| Provider | Models (example) | Notes |
|---|---|---|
| **Anthropic** | claude-sonnet-5, claude-fable-5, claude-opus-4-8, claude-haiku-4-5 | Extended Thinking, tool use |
| **Google** | gemini-3.6-flash, gemini-3.5-flash (+lite), gemini-3.1-pro, gemini-3.1-flash-lite | Thinking stream, vision |
| **OpenAI** | gpt-5.6-sol/terra/luna, gpt-5.5-pro, gpt-5.5, gpt-5.4 | Function calling, vision |
| **NVIDIA NIM** | GLM 5.2, Qwen3 Coder 480B, Nemotron 3 Ultra/Super, Mistral Large 3, Kimi K2.6… | **Free pool** with a single `nvapi-` key (40 RPM) |
| **z-ai** | glm-5.2 | Open-weight, 1M context |
| **Groq** | llama-3.3-70b-versatile | Low latency (LPU) |
| **DeepSeek** | deepseek-v4-pro, deepseek-v4-flash | Cost-effective |
| **Moonshot / Kimi** | kimi-k3, kimi-k2.7-code, kimi-k2.6 | Long context; thinking is always on for K3 |
| **OpenRouter** | all of the above via `openrouter_id` | One key, all providers (fallback path) |

### 3. Local (Ollama)

`http://localhost:11434` is polled; all installed models are listed dynamically. Zero cost, fully offline. Models that support function calling (Llama 3.3, Qwen2.5, etc.) can use tools.

---

## 🔧 Tool Ecosystem (MCP + Function Calling)

Tool usage is a layer **independent** of the provider. When a model wants to read/write a file or run a command, there are these mechanisms:

| Mechanism | Who | How |
|---|---|---|
| **Function Calling** | Cloud API + Ollama | Model emits a JSON tool call → `AgentRunner` catches it → runs it via `ToolRegistry` |
| **MCP** | Claude Code, Codex | The CLI is an MCP client → connects to MCP servers via the config the backend writes → calls tools over stdio/HTTP |
| **run_command bridge** | agy | agy calls the `unityai` CLI via `run_command` → the CLI uses the same approval gate as MCP |

### MCP servers the backend runs

1. **unityai MCP** (`Backend/app/unity_ai_mcp/server.py`) — `save_file`, `delete_file`, `read_file`, `list_directory`, `bash`/`run_terminal_command`/`execute_shell_command`. Write/delete/command operations are routed to the approval panel via `approval_bridge`.
2. **Unity MCP** (CoplayDev/unity-mcp) — 46 tools for the Unity Editor (scene, GameObject, prefab, input…), over HTTP at `127.0.0.1:8080`.

### When are MCP configs written?

| Event | Result |
|---|---|
| Cloud API / Ollama selected | No config written (function calling is used) |
| CLI model selected | Nothing happens yet |
| **A message is sent with a CLI** | The **unityai MCP** entry is written to that CLI's config file |
| **Unity MCP toggle turned on** | The Unity MCP subprocess starts; the next CLI call adds a `unityMCP` entry to the config |
| Toggle turned off | The server stops, `unityMCP` is removed from subsequent configs |

---

## 🛡 Approval & Security Architecture

A multi-layered defense to make an AI's access to the terminal and file system safe:

### 1. File system lock
- All file operations are bounded by `workspace_path`; `Path.resolve()` + prefix checks reject attempts to escape the workspace (both `_resolve` on the backend MCP side and `isAllowedWorkspacePath` on the Electron IPC side).

### 2. Approval gate (shared by all agents)

```
AI wants to change a file
          │
   Any change? (strip() comparison)
     │              │
    No → "no change"
     │
    Yes → gate opens → DiffViewer in the UI
              │
        ┌─────┴─────┐
      Approve      Reject
        │             │
      Written     "rejected" returned
```

The flow above applies to the **CLI agents** (Claude Code, Codex, Copilot, Cursor, OpenCode, Kimi Code) and the **`unityai` bridge** (agy): on those paths a file write goes through `approval_bridge` and not a byte reaches disk unapproved. On the **cloud API / Ollama function-calling path, writes are deliberately out of scope**; deletes and dangerous terminal commands are gated there too.

### ⚠️ Approval scope: what is and isn't confirmed (an honesty note)

The gate does not cover everything. The remaining deliberate trade-offs are **file writes on the cloud API path** and **live Unity scene operations on the Codex/agy paths**:

| Operation | Tool | Approval? |
|---|---|:---:|
| Create / edit a file — **CLI agents** | `save_file` (MCP) / `unityai save-file` | ✅ **Diff card appears** |
| Create / edit a file — **cloud API & Ollama** | `write_file` (function calling) | ❌ **No approval, writes directly** |
| Delete a file | `delete_file` / `unityai` / function calling | ✅ **Delete card appears** |
| Terminal command | `bash` / `run_command` | ✅ (except safe commands) |
| unityMCP call that **reads** the scene | `manage_scene action=get_hierarchy`, `read_console`… | ➖ No card (read) |
| unityMCP call that **mutates** the scene — **Claude path** | `manage_gameobject`, `manage_input`… | ✅ **Card appears** (v2.3.0) |
| unityMCP call that **mutates** the scene — **Codex / agy** | same tools | ❌ **No approval, runs directly** |

**Why is `write_file` unapproved on the cloud API path?** Writing code into the workspace is what this product is for. Asking on every write trains reflex-approval, which does not strengthen the gate — it destroys it, and then the delete card that actually matters gets approved by the same reflex. Writes are instead **confined to the workspace** by `_validate_path` (`Path.resolve()` + prefix check). Deletes are rare and irreversible, so they always show a card.

> **In practice:** with a cloud API model, **"create PlayerController.cs"** writes without asking (git can undo it). The same request through Claude Code / Codex / agy shows a diff card. If you want to see every change before it lands, **pick one of the CLI agents.**

**Why does unityMCP differ per provider?** Originally it was ungated everywhere: scene operations are undoable (Ctrl+Z) and a card on every GameObject move made the workflow unusable. v2.3.0 removed that trade-off on the Claude path — but opens a card only for calls that **mutate state**.

The read/write split is not a guess, it is a ledger: `unity-mcp/Server/src/services/registry/tool_actions.json` classifies every action of every tool, and `Backend/app/unity_tool_policy.py` reads it from the source rather than copying it — a copied list previously granted an exemption to an action that did not exist, and that line never matched anything. **If the ledger cannot be read, the policy fails closed:** no exemptions, every call shows a card.

Codex and agy do not have this gate: unityMCP is still handed to them with `default_tools_approval_mode = "approve"` (Codex) and `trust: true` (agy).

### 3. Terminal security
- Safe (read-only) commands run directly; any command outside the whitelist shows an approval card
- Attempts to write files via the terminal (`python3 -c "open().write()"`, `printf > path`, `echo > path`) are caught and routed to the DiffViewer
- CLI built-in write tools (`Write`/`Edit`, agy's `write_to_file`, etc.) are disabled via `disallowedTools`/`disabledTools` → the model is forced onto the approved channel (`save_file` / `unityai`)

### 4. Local token architecture (ephemeral)

Because this is a desktop app, the OAuth/JWT/session-DB layers were **removed**. In their place, an application-lifetime token:

```
Electron starts → generates a token with randomUUID()
   ├─► Backend subprocess env (LOCAL_APP_TOKEN)
   ├─► Unity MCP subprocess env
   └─► Exposed to the renderer via IPC ('app-token-get')

Every HTTP request carries an X-Session-Token header
   → auth_utils._check_token() compares against the env var
       mismatch → 401 · match → user_id=1 (single local user)
```

- **API key encryption**: keys are encrypted with Fernet; the key lives deterministically at `~/.unity_architect_ai/api_key_fernet.key` (file-based because an unsigned packaged binary can't reliably read the Keychain). The `api_keys` table holds only encrypted data.

---

## ⚙️ Installation

### Requirements
- Python 3.13+
- Node.js 20+
- Unity Editor (for Unity MCP, optional)

> None of these are needed for the packaged app — Python, uv, OmniSharp, the .NET SDK, and ffmpeg/yt-dlp are all bundled. These requirements are for **developing from source** only.

### Backend

```bash
cd Backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Dev server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> You enter API keys from the in-app **Settings** screen (stored encrypted), not via `.env`. If you run the backend standalone (without Electron), `LOCAL_APP_TOKEN` stays empty → token checks are skipped (dev mode).

### Frontend

```bash
cd Frontend/frontend
npm install          # postinstall builds node-pty automatically
npm run dev          # development
```

### Environment variables (optional)

```env
DB_PATH=~/.unity_architect_ai/unity_master_v3.db
HOST=127.0.0.1
PORT=8000                      # Electron picks a random free port; set this for a fixed one
API_KEY_ENCRYPTION_KEY=        # if empty, a file-based key is generated
```

---

## 📦 Packaging (dmg / exe)

A distributable app is produced in four steps (none of the bundled binaries are committed to git; they are fetched before each build):

```bash
# 1) Download the uv toolchain for Unity MCP
#    macOS: downloads both architectures (arm64 + x64)
bash Backend/vendor/fetch_uv.sh
#    Windows: pwsh Backend/vendor/fetch_uv.ps1

# 2) Download OmniSharp + the bundled .NET SDK (code intelligence; bundled on all three platforms)
python3 scripts/fetch_omnisharp.py

# 3) Download the video tools (ffmpeg + yt-dlp — the video→chat feature)
bash Backend/vendor/fetch_video_bins.sh

# 4) Compile the backend with PyInstaller, then package the Electron app
cd Backend && ./build_backend.sh        # Windows: build_backend.bat
cd Frontend/frontend && npm install && npm run build
```

Outputs land under `Frontend/frontend/build/`:
- macOS: `Unity Architect AI-<version>-arm64.dmg` (Apple Silicon)
- Windows: NSIS installer (`.exe`)

> ⚠️ **The x64 dmg trap:** electron-builder produces dmgs for both architectures, but the backend binary is only compiled for the host architecture — an x64 dmg built on Apple Silicon **won't work on Intel Macs**. Proper Intel support requires compiling the backend with an x64 Python separately.

> 🍎 **macOS quarantine note:** the dmg is unsigned; if macOS reports it as "damaged" after downloading, clear the quarantine flag with `xattr -cr "/Applications/Unity Architect AI.app"`.

The packaged app does **not** require Python or .NET — the backend is a single frozen binary; the `mcp-server` and `unityai` subcommands are invoked through that same binary. `uvx`, OmniSharp (+.NET), and ffmpeg/yt-dlp are all embedded.

---

## 💡 Usage

1. **Pick a workspace** — choose your Unity project folder; the backend scans the `.cs` files.
2. **Pick a model** — choose a provider/model in Settings. For a cloud API, enter your key (stored encrypted); for a CLI, just having it installed is enough.
3. **Talk** —

```
"Find the performance issues in PlayerController.cs"
"Create a ScriptableObject-based ItemData script for Inventory"
"NullReferenceException PlayerController.cs:47 — what's the cause, fix it"
"Add a Player capsule to the scene and attach a Rigidbody"   # when Unity MCP is on
/compact                                                      # summarize a long chat
```

4. **Approve** — when the AI requests a file/terminal operation the stream pauses and a diff/command card opens; approve or reject.

---

## 🎮 Unity MCP Integration

Unifies the [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) project, giving the AI direct control of the Unity Editor.

### Setup: fully automatic
1. Open your Unity project (the Editor must be running)
2. Click the **Unity MCP toggle** in the app
3. `unity_mcp_manager` starts the MCP server with the bundled `uvx`, installs the package, and connects to the Editor
4. When the toggle turns green (`Unity connected ✓`) it's ready

> Because `uv`/`uvx` is bundled in the packaged app, the user doesn't need to install it separately. If the Unity Editor is closed the toggle can't connect — open Unity first.

> **Approval behavior:** On the Claude path, unityMCP calls that **mutate** the scene open an approval card; calls that only **read** (hierarchy, console, search) do not. On the Codex and agy paths unityMCP still runs unapproved. See [Approval scope](#️-approval-scope-what-is-and-isnt-confirmed-an-honesty-note).

### Tools (46)

| Category | Tools |
|---|---|
| Scene | `manage_scene`, `find_gameobjects`, `manage_gameobject`, `set_active_instance` |
| Components | `manage_components`, `manage_physics`, `manage_animation` |
| **Input (new)** | **`manage_input`** — keyboard/mouse/gamepad/UI input into the running game |
| UI/Camera | `manage_ui`, `manage_camera` (incl. screenshots) |
| Prefab/Asset | `manage_prefabs`, `manage_scriptable_object`, `manage_asset`, `manage_fbx` |
| Visual | `manage_material`, `manage_shader`, `manage_texture`, `manage_graphics`, `manage_sprite`, `manage_vfx` |
| Script | `manage_script`, `script_apply_edits`, `apply_text_edits`, `create_script`, `delete_script`, `validate_script`, `get_sha`, `manage_script_capabilities`, `find_in_file`, `read_console` |
| Test & Profiling | `run_tests`, `get_test_job`, `manage_profiler` |
| Build | `manage_build`, `manage_packages`, `manage_editor`, `refresh_unity`, `manage_probuilder` |
| Discovery | `unity_docs`, `unity_reflect`, `manage_tools`, `execute_custom_tool` |
| Orchestration | `batch_execute` (up to 25 commands per call), `execute_code`, `execute_menu_item` |

### 🎮 The AI can now play the game (`manage_input`)

Entering play mode and taking screenshots already worked — what was missing was **acting**. The AI could start the game and watch it, but not play it; that was the open link in the loop.

`manage_input` queues events into Unity Input System's **virtual devices** (`QueueStateEvent`). Because the events are produced from inside the process, **no window focus is required** — the AI can play while you do something else, and your keyboard is not hijacked.

```
"Start the game, walk forward with W for 2 seconds, jump with space, then take a screenshot"
```

Actions: `describe`, `key`, `mouse_move`, `mouse_button`, `scroll`, `gamepad`, `ui_click`, `sequence`, `reset`.

> ⚠️ **A permanent limit — call `describe` first.** Only game code written against the **new Input System** sees these events. If your project uses the legacy `UnityEngine.Input` (`Input.GetKey`), virtual-device input **will not reach it**; the only thing that still works there is `ui_click`, which triggers uGUI buttons. `describe` reports the project's input backend — but it only reads the project setting, it does not measure which API the game code actually uses.

### A fork that evolves on agent feedback

The tools in this fork are continuously improved based on feedback from real overnight agent sessions (Claude, GLM):

- **Token economy** — `get_hierarchy` returns a lightweight summary by default (`detail:"full"` for everything); `find_gameobjects` results ship with a `name+path` summary (no N+1 follow-up calls)
- **Smart search** — `match_mode: exact|contains|prefix` on `find_gameobjects` ("Prop_" finds every prop)
- **Write-compile-verify in one turn** — `wait_for_compile: true` makes script writes return the compile result and console errors in the same response
- **Batch chaining** — `"$[0].data.instanceID"` references enable create→configure→parent in a single `batch_execute`
- **Honest feedback** — script changes during play mode carry a warning; a modify call that changes nothing is reported as `no_op`

### Multiple Unity instances

If more than one project is open, you can choose which instance receives commands (`set_active_instance`).

---

## 🧩 Agentic System Details

### Toolbox (function-calling ToolRegistry)

```python
read_file(file_path)                 # Read file (max 500 lines, summarized)
write_file(file_path, content)       # Write file (approval)
delete_file(file_path)               # Delete file (approval)
list_directory(dir_path)             # List a directory
search_in_project(query, exts)       # In-project search
find_files(pattern)                  # File-name pattern
run_command(command)                 # Terminal (approval if dangerous)
save_to_memory(content) / recall_memory()   # Persistent memory
capture_unity_screenshot()           # Editor screenshot (visual verification)
```

### SSE Event Stream

```
POST /chat-stream → SSE opens
event: thinking      → the AI's reasoning text
event: tool_call     → the called tool + arguments
event: tool_result   → tool output summary
event: response      → final answer (+ code blocks)
event: context_usage → context fill percentage
event: done
```

---

## 📓 Developer Notes: Lessons Learned and Architectural Decisions

This section documents the real decisions, dead ends and lessons from the project's evolution. The commit history tells you "what changed"; this section answers "why."

---

### The Beginning: the "Analysis Tool" Era

I actually started the project as a Unity code **analysis** tool. In the first version the user pasted a C# script, the system ran static analysis and returned one big JSON report. Many agents (intent classifier, orchestrator, unity expert, critic, game feel…) ran in sequence.

**The problem:** that pipeline took 45–60 seconds. Even when the user said "rename this variable," all the agents fired.

**Lesson:** an analytical architecture is the wrong paradigm for interactive development. 60 seconds is acceptable for a report; for "fix this" it's lethal.

---

### The Big Shift: From Analysis Tool to Agentic IDE

This is the project's most critical architectural decision. In the old model the user asked, a one-shot answer came back, and the chat ended — the AI couldn't see working files, read error logs, or touch the terminal.

**What pushed me to it:** the message "error: NullReferenceException at PlayerController.cs:47, fix it." Since the AI couldn't see line 47, it could only give generic advice. What would a senior do? Open the file, read the line, understand the context, fix it.

```
Old model:  User → [single LLM call] → Answer
New model:  User → [LLM] → tool call → [result] → [LLM] → … → Answer
```

`AgentRunner` and `ToolRegistry` are the products of this shift.

---

### main.py: Refactor Against the God Object

At one point `main.py` reached 2000+ lines — auth, chat, OAuth, analysis, config all in one file. I did a full route refactor:

```
Before:  main.py (2000+ lines)
After:   routes/{auth,conversation,config,analysis,…}_routes.py + main.py (~30-line bootstrap)
```

**Lesson:** "I'll just put it here for now" gets paid back sooner or later. A 2000-line file isn't just code debt, it's cognitive-load debt. (With the same discipline the `ai_providers.py` god object was later split under `providers/`.)

---

### The MCP Decision: Why a CLI Layer?

A critical choice: should the AI tools run directly through the backend, or through CLI tools (Claude Code, Codex, Gemini)?

The problem with going direct: rewriting tool calling for every new model, handling each model's different format, rebuilding security boundaries again and again.

The advantage of the CLI approach: these tools **already have** their own tool ecosystem, security layer and MCP support. Positioning as an MCP server on top of them means inheriting each CLI's power.

```
Old:  Frontend → Backend → [my own tool code] → file system
New:  Frontend → Backend → CLI (MCP client) → MCP server → file system
```

**Cost:** managing 3 different CLI config formats (JSON / TOML / JSON) and their behavioral differences.

---

### Gemini's Hidden Tool Collision

I defined a `write_file` tool over MCP. It didn't show up in the Gemini CLI: `Tool 'mcp_..._write_file' not found`. Instead of analyzing logs I asked the CLI directly:
> "Which MCP tools do you see, and is `write_file` in your built-in list?"

The answer: Gemini had a built-in tool named `write_file` and was **silently suppressing** the same-named MCP tool. Renaming it to `save_file` fixed it.

**Lesson:** when debugging CLI tools, the fastest method isn't logs — it's asking the tool itself.

---

### The Stop Button: Seemingly Simple, Actually Two Layers

On "Stop" I cut the SSE with an AbortController — but the backend CLI process kept running, polling for approval. The fix was in two parts:

```typescript
stopMessage: () => {
  abortControllerRef.current?.abort();               // cut the SSE connection
  fetch(`${API}/mcp-abort-all`, { method: 'POST' }); // reject pending approval gates
}
```

**Lesson:** cancellation semantics span multiple layers. "The frontend cancelled" ≠ "the operation cancelled." Every async boundary needs its own cancellation mechanism.

---

### I Tore Out Auth: From Web Architecture to Local Desktop

By reflex I started with web patterns: bcrypt, JWT, session DB, OAuth2 (Google+GitHub), rate limiting — ~2000 lines, 4 tables, 7 endpoints.

One day I realized: **this is an Electron app.** The user already has physical access to their device. The multi-user layer was offering fake security — an attacker can already reach `app_data/`, the API keys, the file system.

```typescript
const localAppToken = randomUUID()                 // new each launch
spawn(backend, { env: { ...process.env, LOCAL_APP_TOKEN: localAppToken } })
ipcMain.handle('app-token-get', () => localAppToken)
```

The `users` table now has a single row: `(id=1, username='local')`. The sessions/OAuth tables were dropped.

**Result:** ~2000 lines removed, 7 endpoints reduced to stubs, 4 tables gone, pytest 40% faster.

**Lesson:** architecture must fit the application's context. Copying web patterns into a local app only produces technical debt.

---

### The agy Saga: I Learned the Limits of Embedding a CLI (xD)

The project's biggest dead end. It limped along behind a **warning banner** for a while — until I found the right channel (the `run_command` bridge) and **actually solved it.**

#### Scene 1: "We have 27 days"
I learned Google would retire the Gemini CLI in 27 days; Antigravity (`agy`) was the replacement. The hot-swap looked simple: call `--print`, feed the prompt via stdin, read the output. It looked like a 3-hour job. **It took three days.**

#### Scene 2: "Where are the tool calls?"
agy returned text, but on file-write requests the MCP tools were **never called**. The agy log had a key line: `checkpoint model generated tool calls`. I asked agy and Codex: **`--print` mode blocks tool dispatch by design**, they said.

#### Scene 3: "We'll use `-i` mode!"
They suggested interactive (`-i`) mode instead of `--print`. First attempt:
```
bubbletea: could not open TTY: open /dev/tty: device not configured
```
bubbletea (agy's TUI) refused the PIPE — a real PTY was required.

#### Scene 4: The PTY and Terminal Hijack Disaster
`pty.openpty()`, `termios`, `start_new_session=True` — all by the book. I ran it: agy's TUI (sign-in, spinners, permission prompts) leaked **into the user's terminal**, and the backend could read nothing from stdout. Worse, even `--dangerously-skip-permissions` didn't bypass the native shell prompts in `-i` mode.

#### Scene 5: Research — We're Not Alone
On GitHub, `antigravity-cli` Issue #187 was exactly our problem, with no response from Google. The Gemini API docs said "Antigravity Agent: function_calling and mcp are not yet supported." All three paths were closed.

#### Scene 6: Acceptance and a Banner
I went back to `--print`. agy sometimes wrote files / ran commands — bypassing our approval bridge. The only honest solution: a dismissable yellow banner telling the user.

#### Scene 7: The Fix — "I Was Knocking on the Wrong Door"
The banner held for a few days. Then I asked again: *how does agy use unityMCP?* Because unityMCP **worked** — agy could add GameObjects to the scene. An isolated test gave the answer. agy explained it in its own words:

> "My `read_console` tool is lazily-loaded over an HTTP MCP server; so I wrote a Python script into the workspace and connected to `127.0.0.1:8080/mcp` with `streamable_http_client` to call the tool from there."

**The lightbulb moment.** agy doesn't natively load MCP under `--print` — but it's smart enough: seeing an HTTP MCP URL, it writes **its own bridge script** with `run_command` and connects. So under `--print` the **only real channel agy sees is `run_command`.** I'd been knocking on the wrong door the whole time.

**The solution — the `unityai` CLI bridge:**
1. I wrote `unityai_cli.py` + a `unityai` wrapper. This CLI **shares the same `approval_bridge`** as the MCP tools — a `unityai save-file …` call opens the approval card just like `mcp__unityai__save_file`. agy calls it via `run_command`.
2. I disabled agy's **real** built-in write tools (`write_to_file`, `replace_file_content`, `multi_replace_file_content`) via `disabledTools`. (I learned the correct names by having agy dump its own tool list — the earlier guessed names never matched.) With writes disabled, agy's only path is `run_command → unityai` → **an approval card appears.**
3. I removed the yellow banner — it was lying now. agy goes through the approval gate just like Claude Code/Codex.

**A small remaining trade-off (in the spirit of honesty):** we can't disable `run_command` (we call `unityai` through it). So agy could theoretically bypass approval via raw shell; we only deter that with prompting. Claude Code & Codex load MCP natively, so for them the ban is **absolute**; for agy it isn't. An acceptable trade-off so agy can keep using unityMCP freely for scene control.

#### Lessons
1. **Embedding a CLI is categorically different from API integration** — a CLI is designed as an interactive user tool; driving it programmatically means forcing the wrong layer.
2. **When you consult an AI agent, verify** — agy said "it falls back on PIPE," which was wrong; Codex said the same. Agents don't remember their libraries' behavior, they guess.
3. **"It doesn't work" is an answer** — clear information (even if temporary) beats a fragile hack.
4. **Check GitHub Issues early** — Issue #187 was there on day one; I'd have saved 2 days.
5. **Document the dead ends** — that's what this section is for.

---

### Practical Rules (When Contributing)

1. **Write CLI configs at global scope** — headless mode usually doesn't read project-level config.
2. **Use a `strip()` comparison in the approval gate** — a trailing-newline diff opens an unnecessary card.
3. **Compare MCP tool names against the CLI's built-in list** — name collisions are silent.
4. **Split routes early** — any route file over 500 lines should be split; this was the most expensive debt.
5. **Scan upstream Issues before spawning a CLI as a subprocess.**
6. **Verify an AI agent's claims about its own libraries with an isolated test.**

---

## 🤝 Contributing

The quality gate is three separate test suites — **~3,100 tests total**:

```bash
# Backend (~1,118 tests)
cd Backend && pytest
#   Windows: venv\Scripts\python.exe -m pytest   (env: PYTHONUTF8=1)

# unity-mcp server (~1,596 tests)
cd unity-mcp/Server && pytest

# Frontend (~396 tests) + the TypeScript gate
cd Frontend/frontend && npm test && npx tsc --noEmit
```

CI (`.github/workflows/test.yml`) runs four jobs: **Backend tests**, **unity-mcp Server tests**, **Frontend gate (tsc + vitest)** and a **PowerShell syntax check**. No release ships unless all four are green.

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Run the tests
4. Open a pull request

---

## 👤 Developer

**Burak Emre Erdemci**

An open-source portfolio and research project for developers who want to fundamentally transform Unity development with AI.

---

## 📄 License

**MIT + [Commons Clause](https://commonsclause.com/)** — see [LICENSE](LICENSE)

This project is licensed to stay **free forever**:

- ✅ **Use it** — personal, educational, research, or commercial settings
- ✅ **Study, modify and fork it**
- ✅ **Sell the games you make with it** — whatever you create is entirely yours
- ❌ **You may not sell the application itself** — forking it into a paid product or service is not permitted

For third-party component licenses, see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)
(FFmpeg, shipped in released installers, is GPL-3.0 licensed and is invoked only as a separate process.)
