<div align="center">

# Unity Architect AI

**Autonomous, Secure & Agentic Software Studio for Unity Developers**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Unity MCP](https://img.shields.io/badge/Unity_MCP-Active-7B2FBE?style=for-the-badge&logo=unity&logoColor=white)](./unity-mcp)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

*Unity Architect AI is not just a code assistant. It is an autonomous development partner that understands your entire project, manages the terminal, issues direct commands to the Unity Editor, and does all of this behind a layered security system.*

[Turkish README](./README.md)

</div>

---

## Table of Contents

- [Why Unity Architect AI?](#-why-unity-architect-ai)
- [Features](#-features)
- [System Architecture](#-system-architecture)
- [Supported AI Providers](#-supported-ai-providers)
- [Tool Ecosystem (MCP + Function Calling)](#tool-ecosystem-mcp--function-calling)
- [Security Architecture](#️-security-architecture)
- [Installation](#-installation)
- [Usage](#-usage)
- [Unity MCP Integration](#-unity-mcp-integration)
- [Agentic System Details](#-agentic-system-details)
- [API Reference](#-api-reference)
- [Developer Notes: Lessons Learned](#developer-notes-lessons-learned-and-architectural-decisions)
- [Contributing](#-contributing)

---

## Why Unity Architect AI?

AI tools in the Unity ecosystem fall into one of two categories: they either just write code, or they just chat. Neither can do what a real development partner should — understand the project, find the bug, fix it, test it, and see it inside the Unity Editor.

Unity Architect AI closes this gap:

| Traditional AI Assistants | Unity Architect AI |
|---|---|
| Writes code, sees no context | Reads and indexes all `.cs` files in your project |
| Cannot access files | File read/write/delete (with approval gate) |
| Unaware of Unity Editor | Adds GameObjects to scenes, edits Inspector values via MCP |
| Cannot run terminal | Executes commands through a secure terminal layer |
| Every conversation starts from zero | Remembers the project with persistent memory and RAG |
| Single provider only | Claude, GPT-4, Gemini, Codex, Ollama support |

---

## Features

### Autonomous Agentic Loop
- When given a task, the AI thinks, calls tools, evaluates results, and loops until complete
- Maximum 15 iterations to protect against infinite loops
- Every step is streamed live to the user (SSE): `thinking` → `tool_call` → `tool_result` → `response`
- User can cancel at any time via the "Stop" button; all pending approval gates are automatically rejected

### Broad Provider Coverage
- **Cloud API**: Anthropic, OpenAI, Google, Groq, DeepSeek, Moonshot/Kimi (+ all of them via OpenRouter fallback)
- **Subscription CLI**: Claude Code, Codex CLI, Antigravity CLI (agy) — runs on the user's own Anthropic/OpenAI/Google subscription
- **Local**: Ollama (`http://localhost:11434`) — all installed models discovered dynamically
- When a CLI is selected, the backend writes its MCP config files on the first message (`~/.claude.json`, `~/.codex/config.toml`, `~/.gemini/antigravity-cli/mcp_config.json`)

### Semantic RAG Engine
- All `.cs` files are scanned, chunked into 1000-character segments, and indexed as vectors
- When the AI works on a file, it automatically pulls relevant scripts, inheritance relationships, and dependencies
- `/compact` command summarizes long conversations before context token limit is reached

### Real-time C# Linter
- Integrated Mono `csc` compiler — compiles in the background as you write
- Errors shown as red squiggly lines in the Monaco editor
- Recognizes package references in both `Assets/` and `Library/PackageCache/` (URP, HDRP, etc.)

### Unity MCP Integration
- Based on [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) with 40+ Unity Editor tools
- Scene management: GameObject creation/deletion/editing, component attachment, Inspector values
- Script management: creation, editing, compiler error retrieval
- Prefab, material, physics, animation, and build settings control
- Multi-instance support: route commands to the correct project among multiple open Unity editors

### Approval Gate System
- Every dangerous operation (file write, delete, terminal command) requires user confirmation
- File write: side-by-side diff viewer comparing current vs. new content
- File delete: confirmation with content preview
- Terminal commands: approval card showing command and context
- AI cannot change a single byte without approval

### Memory and Persistence
- Conversation compaction: `POST /conversations/{id}/compact` triggers AI to summarize before approaching the context limit; result is written to `conversations.memory_summary`
- Project memory: stored as markdown files under `app_data/memories/`
- RAG index: updated after every analysis
- API key storage: Fernet encryption + OS keystore (Keychain/Credential Manager) — the `api_keys` table only stores encrypted data

### User Interface
- **Monaco Editor** — The VS Code editor engine with Unity C# syntax support
- **Integrated Terminal** — xterm.js-based, for system commands and Unity logs
- **Diff Viewer** — Inspect file changes side-by-side before approving
- **Thinking Block** — Watch the AI think in real-time (Claude Extended Thinking, Gemini thinking stream)
- **Model Selector** — Instantly switch between all providers; CLI groups expand/collapse
- **File Explorer** — Navigate project hierarchy visually
- **Bilingual UI (TR/EN)** — Custom React Context + `useLang()` hook, language preference persisted in localStorage, 100+ translation keys

---

## System Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Electron Desktop App                │
│  ┌──────────────────────────────────────────────────┐ │
│  │  main/background.ts — LOCAL_APP_TOKEN = uuid()    │ │
│  │  ├─► Backend subprocess env                        │ │
│  │  ├─► MCP subprocess env                            │ │
│  │  └─► Renderer IPC: 'app-token-get'                 │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Chat Panel  │  │Monaco Editor │  │  Terminal   │ │
│  │ (SSE stream)│  │ (C# linter)  │  │ (xterm.js)  │ │
│  └──────┬──────┘  └──────────────┘  └─────────────┘ │
│         │       React 18 + Next.js 14 (TR/EN i18n)    │
└─────────┼────────────────────────────────────────────┘
          │ HTTP / SSE   +   X-Session-Token header
          ▼
┌──────────────────────────────────────────────────────┐
│                 FastAPI Backend (Python 3.13)          │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │              AgentRunner (Agentic Loop)          │  │
│  │   User Request → Think → Tool Call → Result → …  │  │
│  └────────────────────┬────────────────────────────┘  │
│                       │                                │
│         ┌─────────────┼─────────────┐                 │
│         ▼             ▼             ▼                  │
│  ┌────────────┐ ┌──────────┐ ┌──────────────┐         │
│  │ToolRegistry│ │ProjectRAG│ │MemoryManager │         │
│  │read_file   │ │FAISS idx │ │/compact      │         │
│  │write_file  │ │.cs chunks│ │memories/*.md │         │
│  │run_command │ └──────────┘ └──────────────┘         │
│  │search_proj │                                        │
│  └────────────┘                                        │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │                  AI Providers                     │ │
│  │  Claude API │ OpenAI API │ Gemini API │ Ollama    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │             MCP Server (FastMCP)                  │ │
│  │  save_file │ read_file │ list_directory │ bash    │ │
│  └──────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────┘
                                  │ MCP (stdio / HTTP)
          ┌───────────────────────┼───────────────────┐
          ▼                       ▼                    ▼
   ┌─────────────┐       ┌─────────────────┐   ┌──────────────────┐
   │ Claude Code │       │   Codex CLI     │   │ Antigravity CLI  │
   │  (CLI)      │       │   (CLI)         │   │ (agy) — hot-swap │
   └─────────────┘       └─────────────────┘   │ ← gemini-cli-*   │
                                                └──────────────────┘
          │                                            │
          └──────────────────┬─────────────────────────┘
                             │ MCP HTTP (localhost:8080)
                             ▼
                    ┌─────────────────┐
                    │   Unity MCP     │
                    │ (CoplayDev/     │
                    │  unity-mcp)     │
                    │  40+ tools      │
                    └────────┬────────┘
                             │ WebSocket
                             ▼
                    ┌─────────────────┐
                    │  Unity Editor   │
                    │  (C# Plugin)    │
                    └─────────────────┘
```

### Directory Structure

```
unityaıPython/
├── Backend/
│   ├── app/
│   │   ├── agentic/            # AgentRunner, approval gates, agent loop
│   │   ├── unity_ai_mcp/       # MCP server (FastMCP) + Unity MCP manager
│   │   │   ├── tools/          # save_file, delete_file, read_file, list_directory, bash
│   │   │   ├── approval_bridge.py  # Backend ↔ MCP approval bridge
│   │   │   └── server.py
│   │   ├── tools/              # Legacy ToolRegistry (for direct-API agentic)
│   │   ├── rag/                # ProjectRAG (FAISS), MemoryManager
│   │   ├── knowledge/          # Offline Unity knowledge base
│   │   ├── routes/             # FastAPI routers
│   │   │   ├── auth_routes.py            # Local token validation (stub /login, /me)
│   │   │   ├── conversation_routes.py    # Chat stream + approval endpoints
│   │   │   ├── config_routes.py          # AI config, model list
│   │   │   ├── analysis_routes.py        # Project analysis, memory
│   │   │   ├── lint_routes.py            # C# Roslyn linter
│   │   │   ├── mcp_routes.py             # Unity MCP toggle/status
│   │   │   └── workspace_routes.py       # Workspace management
│   │   ├── ai_providers.py     # Multi-provider + CLI management (agy hot-swap included)
│   │   ├── auth_utils.py       # LOCAL_APP_TOKEN validation (env var)
│   │   ├── database.py         # SQLite — local user seed (id=1)
│   │   ├── linter.py           # Resolves Roslyn path from Unity Hub
│   │   └── prompts.py          # System prompts, intent classifier
│   ├── tests/                  # pytest test suite
│   ├── requirements.txt
│   └── Dockerfile
├── Frontend/
│   └── frontend/
│       ├── renderer/
│       │   ├── pages/          # home.tsx (main IDE), _app.tsx
│       │   ├── components/     # 25+ components
│       │   │   ├── home/       # ChatPanel, DiffViewer, approval UIs, editor
│       │   │   └── ui/         # Reusable UI components
│       │   ├── hooks/          # useChat, useAuth, useAIConfig, useMCPApproval
│       │   └── lib/
│       │       └── i18n.tsx    # TR/EN translation context, useLang hook
│       └── main/
│           ├── background.ts   # Electron main process, LOCAL_APP_TOKEN generator
│           └── helpers/        # IPC whitelist, preload
├── unity-mcp/                  # CoplayDev/unity-mcp (submodule)
│   ├── Server/                 # Python MCP server
│   └── MCPForUnity/            # C# Unity Editor plugin
├── LICENSE
└── docker-compose.yml
```

---

## Supported AI Providers

Providers fall into 3 main categories. These categories define **where the model runs** — tool usage (MCP / function calling) is a separate layer, explained in the *Tool Ecosystem* section below.

### 1. Cloud API (Direct API call)

The backend issues requests via the provider's official SDK or through the OpenRouter gateway. Tool usage happens via **function calling** (the model emits a tool call in JSON, the backend dispatches it).

| Provider | Example Models | Notes |
|---|---|---|
| **Anthropic** | claude-fable-5, claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5, claude-opus-4-6 | Extended Thinking, tool use |
| **Google** | gemini-3.1-pro-preview, gemini-3-flash-preview, gemini-3.1-flash-lite-preview, gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite | Thinking stream, tool use |
| **OpenAI** | gpt-5.5-pro, gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.4-nano | Function calling, vision |
| **Groq** | llama-3.3-70b-versatile | Low-latency inference (LPU) |
| **DeepSeek** | deepseek-chat (V3) | Affordable general-purpose |
| **Moonshot / Kimi** | kimi-k2.6, kimi-k2.5 | Long context (200K+) |
| **OpenRouter** | All of the above via `openrouter_id` | Single API key, all providers (fallback path) |

### 2. Subscription CLI Agents

The backend invokes the official CLI binary on the user's machine as a subprocess. The CLI uses its own auth (Anthropic / OpenAI / Google subscription). Tool usage happens via **MCP (Model Context Protocol)** — before each call, the backend writes the `mcp_config.json` that the CLI will read.

| CLI Tool | Models | Config File |
|---|---|---|
| **Claude Code** | claude-fable-5, claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5 | `~/.claude.json` |
| **Codex CLI** | gpt-5.5, gpt-5.4, gpt-5.4-mini | `~/.codex/config.toml` |
| **Antigravity CLI (agy)** | Gemini 3.5 Flash, Gemini 3.1 Pro, Gemini 3 Flash, Gemini 2.5 Pro/Flash + Claude/GPT-OSS via agy | `~/.gemini/antigravity-cli/mcp_config.json` |

**Transparent Hot-Swap (Gemini CLI → agy):** The frontend keeps the `gemini-cli-*` model IDs; the backend catches them (`_AGY_MODEL_MAP`) and routes them to the agy binary. Since agy's `--print` mode doesn't load MCP tools natively (unlike Claude Code/Codex), file/terminal operations go through a `unityai` CLI bridge invoked via `run_command` — the bridge uses the same approval gate as the MCP tools, so agy shows the approval card too (see *Developer Notes — The agy Adventure, Scene 7*).

### 3. Local (Ollama)

The backend polls the Ollama API (`http://localhost:11434`) and lists all installed models dynamically. Zero API cost, fully offline. Models that support function calling (e.g. Llama 3.3, Qwen2.5) can use tools.

---

## Tool Ecosystem (MCP + Function Calling)

Tool usage is **independent of the provider**. When a model wants to read a file, write a file, or run a terminal command, two distinct mechanisms exist:

| Mechanism | Which Providers | How It Works |
|---|---|---|
| **Function Calling** | Cloud API + Ollama (compatible models) | The model emits a tool call in JSON, the backend's `AgentRunner` catches it and dispatches via `ToolRegistry` |
| **MCP (Model Context Protocol)** | Subscription CLI agents | The CLI acts as an MCP client, connects to MCP servers via the `mcp_config.json` the backend writes, and invokes tools over stdio or HTTP |

### MCP Servers (Authored by Us)

The backend runs two MCP servers:

1. **Antigravity MCP** (`Backend/app/unity_ai_mcp/server.py`) — `save_file`, `delete_file`, `read_file`, `list_directory`, `bash`. File writes and shell commands are routed through the approval bridge to the user's approval panel
2. **Unity MCP** (CoplayDev/unity-mcp, submodule) — 40+ tools for Unity Editor (scene, GameObject, prefab, etc.)

### When Are MCP Configs Written?

| Event | Effect |
|---|---|
| Cloud API / Ollama model selected | No MCP config is written (not needed — function calling is used) |
| CLI model selected | Nothing happens (config is written only on invocation) |
| **CLI model is sent a message** | `_write_mcp_config()` / `_register_agy_mcp()` runs → the **Antigravity MCP** server entry is written to the CLI's config file |
| **Unity MCP toggle turned on** | `unity_mcp_manager.start_server()` starts the Unity MCP subprocess. On the next CLI invocation, the `unityMCP` entry is added to config files as well |
| Unity MCP toggle turned off | Server stops, the `unityMCP` entry is removed from subsequent CLI configs |

**Key point:** Unity MCP **itself** is started/stopped by the toggle. CLI selection only writes config files — so for a CLI to access Unity MCP, both (a) the Unity MCP toggle must be on, and (b) a message must have been sent through that CLI.

### MCP Bridge on the Function Calling Side

Currently Cloud API and Ollama models use their own `ToolRegistry`; they don't have direct access to the MCP servers. This is a deliberate architectural boundary — bridging API-model tool lists dynamically from MCP servers requires a translation layer. Not yet implemented.

---

## Security Architecture

Unity Architect AI uses a multi-layered defense architecture to safely grant an AI access to the terminal and file system:

### 1. File System Lock
- All file operations are restricted to `workspace_path`
- `Path.resolve()` + prefix check guards against absolute path attacks
- Attempts to escape the workspace are rejected with `PermissionError`

### 2. Approval Gate Layer

```
AI wants to modify a file
           │
           ▼
   Is there a change?
   (strip() comparison)
      │           │
     Yes          No → Returns "No change"
      │
      ▼
  Approval gate opens
  DiffViewer shown in UI
      │
  ┌───┴───┐
  │       │
Approve  Reject
  │       │
Writes  Returns "Rejected"
```

### 3. Terminal Security
- Dangerous commands are blacklisted: `rm -rf`, `sudo`, `curl | bash`, etc.
- Commands not on the blacklist still show an approval card
- File-write attempts via terminal (`python3 -c "open().write()"`, `printf > path`) are intercepted and redirected to DiffViewer
- TOML policy for CLI tools: built-in tools like `run_shell_command` and `replace` are denied

### 4. Local Token Architecture (Ephemeral Session)

Since this is a desktop app, the OAuth/JWT/session-DB layers were **removed**. They were replaced with an **application-lifetime token** (LOCAL_APP_TOKEN):

```
Electron starts → generates token via randomUUID()
        │
        ├─► Passed to backend subprocess via env var
        ├─► Passed to MCP server subprocess via env var
        └─► Exposed to renderer via IPC handler (`app-token-get`)

Each HTTP request includes X-Session-Token header
        │
        ▼
Backend `auth_utils._check_token()` compares against env var
        │
    Mismatch → 401
    Match    → user_id=1 (single local user)
```

- **Single-user model**: `users` table contains only a seed row `id=1, username=local`
- **Token scope**: Valid only for that application session; cleared when app closes
- **API key encryption**: Fernet + OS keystore (Keychain/Credential Manager) — this layer was preserved

### 5. Legacy Web Security (Why Removed)

The old architecture had bcrypt, JWT, OAuth2, rate limiting, and a session DB. All removed because:
- This is a desktop application, not exposed to the internet
- The user already has physical access to the device
- The multi-user layer was **fake security** — an attacker would already have file system access
- 7 endpoints + 4 DB tables + 3 OAuth provider layers were generating pure technical debt

Result: ~2000 lines of auth code removed, the system became simpler and more secure.

### 6. MCP Security (CLI Providers)

```toml
# Auto-generated TOML policy (Gemini CLI)
[[rule]]
toolName = "run_shell_command"
decision = "deny"

[[rule]]
toolName = "replace"
decision = "deny"
```

---

## Installation

### Requirements

- Python 3.13+
- Node.js 20+
- Mono (optional, for C# linter)
- Unity Editor (optional, for Unity MCP)

### Backend Setup

```bash
cd Backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Edit .env (Google/GitHub OAuth keys, etc.)

# Start server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend Setup

```bash
cd Frontend/frontend

# Install dependencies
npm install

# Start in development mode
npm run dev

# Build production release
npm run build
```

### Docker Setup

```bash
# Start all services
docker-compose up -d

# Backend only
docker build -t unity-architect-backend ./Backend
docker run -p 8000:8000 unity-architect-backend
```

### Environment Variables

```env
# Database
DB_PATH=~/.unity_architect_ai/unity_master_v3.db

# Server (Electron picks a random free port; set this for a fixed port)
HOST=127.0.0.1
PORT=8000

# API key encryption (uses OS keystore if empty)
API_KEY_ENCRYPTION_KEY=
```

> **Note — LOCAL_APP_TOKEN**: The backend validates `X-Session-Token` header against the `LOCAL_APP_TOKEN` env var on every request. This value is **generated by Electron at every app launch via `randomUUID()`** and passed to subprocesses automatically — you don't need to set it manually. If you run the backend standalone (without Electron), you can either set it explicitly or leave it empty (empty disables token check, dev mode).

---

## Usage

### 1. Select Workspace
After launching the app, select your Unity project folder as the workspace. The backend will scan it and index all `.cs` files.

### 2. Configure AI
From the settings menu, choose your preferred provider and model. Enter your API key — it will be stored encrypted.

### 3. Chat and Commands

```
# File analysis
"Find performance issues in PlayerController.cs"

# Code generation
"Create a ScriptableObject-based ItemData script for an inventory system"

# Bug fixing
"Getting a NullReferenceException, what's causing it?"

# Unity Editor control (if MCP is connected)
"Add a Player capsule to the scene and attach a Rigidbody component"

# Compact context
/compact
```

### 4. Approval Workflow
When the AI wants to create or modify a file:
1. The chat stream pauses
2. A diff viewer opens (current vs. new content)
3. Click "Approve" or "Reject"
4. The AI continues based on your decision or generates an alternative

---

## Unity MCP Integration

Unity Architect AI integrates [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) (9.5k stars), giving the AI direct control over the Unity Editor.

### Setup

**Fully Automatic** — no manual installation needed.

1. Open your Unity project (Unity Editor must be running)
2. Click the **Unity MCP toggle** in the top-right of the app
3. The toggle starts the Unity MCP server via `unity_mcp_manager`, installs all required dependencies, and establishes the connection to Unity Editor automatically
4. When the toggle turns green (`Unity connected ✓`), everything is ready

> **Note:** The toggle cannot connect if Unity Editor is not open. Start Unity first, then press the toggle.

### Available Tools (40+)

| Category | Tools |
|---|---|
| Scene | `manage_scene`, `find_gameobjects`, `manage_gameobject` |
| Components | `manage_components`, `manage_physics`, `manage_animation` |
| UI | `manage_ui`, `manage_camera` |
| Prefab | `manage_prefabs`, `manage_scriptable_object` |
| Visuals | `manage_material`, `manage_shader`, `manage_texture`, `manage_graphics` |
| Scripting | `manage_script`, `validate_script`, `apply_text_edits` |
| Build | `manage_build`, `manage_packages`, `manage_editor` |
| VFX | `manage_vfx` |

### Multi-Instance Support

When multiple Unity projects are open at once:

```python
# Route commands to a specific instance
set_active_instance(instance_id="MyGame_2023")
```

---

## Agentic System Details

### Tool Registry

```python
# Available tools
read_file(file_path: str)              # Read file (max 500 lines, with summary)
write_file(file_path: str, content)    # Write file (requires approval)
delete_file(file_path: str)            # Delete file (requires approval)
list_directory(dir_path: str)          # List directory contents
search_in_project(query: str, exts)    # Semantic project search
find_files(pattern: str)               # Filename pattern matching
run_command(command: str)              # Terminal command (security checked)
save_to_memory(content: str)           # Save to memory
recall_memory()                        # Read from memory
```

### SSE Event Stream

```
POST /chat → SSE stream opens

event: thinking
data: {"thinking_text": "User is asking about PlayerController issue..."}

event: tool_call
data: {"tool_name": "read_file", "arguments": {"file_path": "Assets/Scripts/Player.cs"}}

event: tool_result
data: {"output": "using UnityEngine;\npublic class PlayerController..."}

event: tool_call
data: {"tool_name": "search_in_project", "arguments": {"query": "GetComponent"}}

event: response
data: {"text": "Found GetComponent call in Update(). Let's move it to Start()..."}

event: done
data: {}
```

### Intent Classifier

Before processing each message, the system classifies its intent:

- `GENERATION` — Generate new files or code → Code pipeline
- `ANALYSIS` — Linting, performance review → Analysis pipeline
- `CHAT` — Conversation, question, planning → Direct response (no tool calls)

This prevents planning messages like "We're going to build an inventory system" from unnecessarily triggering file creation.

---

## API Reference

### Core Endpoints

```
POST /chat
  Body: { user_id, conversation_id, message, model, workspace_path }
  Response: SSE stream

POST /analyze
  Body: { user_id, workspace_path }
  Response: { analysis_report, lint_errors, rag_status }

POST /conversations
  Body: { user_id, title }
  Response: { conversation_id }

POST /compact
  Body: { user_id, conversation_id }
  Response: { summary, tokens_saved }

POST /mcp-abort-all
  Response: { status, rejected_count }
  # Rejects all pending approval gates (called on stream cancel)

GET /mcp-approval-result/{gate_id}
  Response: { approved: bool }
  # Frontend polls for approval result

POST /mcp-approval-result/{gate_id}
  Body: { approved: bool }
  # User's approve/reject decision
```

### Configuration Endpoints

```
POST /save-ai-config
  Body: { user_id, provider, model, use_multi_agent }

POST /api-keys/save
  Body: { user_id, provider, api_key }  # Stored encrypted

GET /available-models
  Response: { cloud_models, local_models, cli_providers }
```

---

## Developer Notes: Lessons Learned & Architectural Decisions

This section documents the real decisions, dead ends, and lessons from the project's evolution. The commit history tells you "what I did"; this section answers "why."

---

### The Beginning: "Analysis Tool" Era

I originally built this as a Unity code **analysis** tool. In the first version, the user pasted a C# script, the system ran it through regex-based static analysis, and returned a single large JSON report.

The scoring system looked like this:
```
Final Score = (Technical Quality × 0.60) + (Game Feel × 0.40)
```

There were 8 separate agents: Intent Classifier, Orchestrator, Unity Expert, Critic, Game Feel Agent, Architect, Coder, and Clarification Gate. Each ran sequentially with its own token budget. When a user said "fix this script," the system would: plan → expert fixes → critic reviews → game feel check → report.

**The problem:** This pipeline averaged 45-60 seconds. Even when the user just said "rename this variable," all 8 agents fired.

**What I learned:** An analytical architecture is the wrong paradigm for interactive development. The difference between a report tool and a development partner is the user's tolerance for waiting. 60 seconds is fine for a report; it's fatal for "just fix this."

---

### Partner Mode: "Less Talking AI"

I simplified the pipeline — 4 steps down to 2. More importantly, I added an **intent classifier**.

I had to build this to fix a specific bug I kept hitting: when a user typed "We're going to build an inventory system, what do you think?", the system classified it as GENERATION and started creating an empty inventory script. The user was just asking for an opinion.

```python
# Rule I added
"we're going to", "we'll build", "planning", "thinking about" → CHAT (no code generation)
"create", "build", "add", "fix" → GENERATION
```

**What I learned:** No matter how smart the classifier is, intent detection breaks without keyword-based signals. LLMs need to be nudged toward the safe side — "if unsure, pick CHAT."

---

### The Big Shift: From Analysis Tool to Agentic IDE

This is the most critical architectural decision in the project, and the one that took the most time to get right.

In the old model, the user asked, a one-shot response came back, and the conversation ended. The AI had no way to see the working files, read error logs, or access the terminal. Every answer was written in a vacuum.

**What pushed me to this decision:** A user's message: "Error: NullReferenceException at PlayerController.cs:47, fix it." The AI couldn't see line 47, so it could only give generic advice. What would a senior dev do? Open the file, read line 47, understand the context, fix it.

That gap is what made me switch to a tool use architecture:

```
Old model:  User → [single LLM call] → Response
New model:  User → [LLM] → tool call → [result] → [LLM] → ... → Response
```

`AgentRunner` and `ToolRegistry` are the product of that shift. I rewrote about 40% of the codebase during this transition — that was an expected cost, and it needed to happen early.

---

### main.py Problems: God Object vs. Refactor

At one point `main.py` had grown to 2000+ lines. Auth, chat logic, OAuth, analysis, configuration — everything in one file. Adding any new feature meant starting by understanding this file; merge conflicts had become routine.

In Sprints 7-8 I did a full route refactor:

```
Before: main.py (2000+ lines, everything here)

After:
├── routes/auth_routes.py         # Auth only
├── routes/conversation_routes.py # Chat only
├── routes/config_routes.py       # Config only
├── routes/analysis_routes.py     # Analysis only
├── auth_utils.py                 # Session/token helpers
└── main.py                       # Bootstrap only (~30 lines)
```

After this refactor I moved noticeably faster for the next 3 sprints.

**What I learned:** "I'll just put it here for now" always gets paid back later. A 2000-line file isn't just code debt — it's cognitive load debt.

---

### The MCP Decision: Why a CLI Layer?

In Sprint 10 I had to make a critical architectural choice: should the AI run tools directly through the backend, or through CLI tools (Claude Code, Codex, Gemini)?

The problem with a direct backend approach: rewriting the tool calling implementation for every new model, handling each model's different function calling format, and constantly rebuilding security boundaries.

The advantage of the CLI approach: Claude Code, Codex, and Gemini CLI already have their own tool ecosystems, security layers, and MCP support. Positioning myself as an MCP server on top of them means inheriting the power of each CLI automatically.

```
Old approach:  Frontend → Backend → [my own tool code] → file system
New approach:  Frontend → Backend → CLI (MCP client) → MCP server → file system
```

**Cost I paid:** Learning 3 different CLI configuration formats (JSON, TOML, JSON) and managing the behavioral differences between them.

---

### Gemini's Hidden Tool Name Collision

During Gemini CLI integration I ran into a strange issue. I registered an MCP tool called `write_file`. When connected to Gemini CLI, the tool was invisible — the error was:

```
Tool 'mcp_antigravity_write_file' not found
```

Instead of spending hours on log analysis, I asked Gemini CLI directly:
> "Which MCP tools can you see, and does your built-in tool list include `write_file`?"

The answer was clear: Gemini CLI had a built-in tool named `write_file`, and MCP tools with the same name were silently suppressed. Renaming it to `save_file` fixed it completely.

**What I learned:** When debugging CLI tools, the fastest path is asking the tool itself, not reading logs. I got to the fix in 5 minutes.

---

### JSON Policy's Silent Failure

When writing the security policy for Gemini CLI, I used JSON format:

```json
{"rules": [{"toolName": "run_shell_command", "decision": "deny"}]}
```

No error message. The policy file was read, processed, accepted. But Gemini was still running `run_shell_command`. I spent a long time debugging — until I finally read the documentation carefully and found that TOML format was required:

```toml
[[rule]]
toolName = "run_shell_command"
decision = "deny"
```

**What I learned:** "No error" doesn't mean success. Security configurations always need to be actively tested — especially the kind that silently fail with no feedback.

---

### The Stop Button: Simple on the Surface, Two Layers Deep

When the user clicks "Stop," what should happen? In my first implementation I used AbortController to close the SSE stream. The frontend stopped receiving responses.

But the backend CLI process was still running. And it was waiting for approval to write a file — polling indefinitely until the approval came. AbortController only cut the HTTP connection; it didn't stop the waiting logic in the backend.

I wrote the fix in two parts:
1. `/mcp-abort-all` endpoint — rejects all pending approval gates
2. `stopMessage()` calls this endpoint on every stop action

```typescript
stopMessage: () => {
  abortControllerRef.current?.abort();              // Cut the SSE connection
  fetch(`${API}/mcp-abort-all`, { method: 'POST' }); // Clean up zombie gates
}
```

**What I learned:** Cancellation semantics span multiple layers. "Frontend cancelled" and "operation cancelled" are not the same thing. Every async boundary needs its own cancellation mechanism.

---

### Removing Auth: From Multi-User Web Architecture to Local Desktop

I started the project reflexively with web-app patterns: bcrypt, JWT, session DB, OAuth2 (Google + GitHub), rate limiting. ~2000 lines of auth code, 4 separate database tables (`users`, `sessions`, `oauth_states`, `oauth_completions`), 7 endpoints.

One day I realized: **this is an Electron application.** The user already has physical access to the device. The multi-user layer was providing only fake security — an attacker would already have file system access, API keys, the user's data. JWT defends against web attack vectors; a local application has no web attack vectors.

In the refactor, I tore out the entire auth layer. An **ephemeral token** took its place:

```typescript
// Frontend/frontend/main/background.ts
const localAppToken = randomUUID()  // New on every app launch
// Passed as env var to backend and MCP subprocesses
spawn(backend, { env: { ...process.env, LOCAL_APP_TOKEN: localAppToken } })
// Renderer receives it via IPC
ipcMain.handle('app-token-get', () => localAppToken)
```

```python
# Backend/app/auth_utils.py
def _check_token(token):
    expected = os.environ.get("LOCAL_APP_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(401, "Invalid token")
    # Empty expected → dev mode, token check skipped
```

The `users` table now has a single row: `(id=1, username='local')`. The sessions/OAuth tables were dropped.

**Numeric outcome:** ~2000 lines deleted, 7 endpoints reduced to stubs (kept for frontend compatibility), 4 tables removed. Pytest runtime dropped 40% (auth fixtures gone).

**What I learned:** Architecture has to match the application context. Copying web patterns into a local application only manufactures technical debt. If the only answer to "why is this code here?" is "because that's how it's done," that code should go.

---

### The agy Adventure: Learning the Limits of Embedding a CLI (xD)

This was the project's biggest dead end. For a while it limped along with a **warning banner** — until I found the right channel (`run_command` bridge) and **actually solved it**. Here's how it played out.

#### Act 1: "We have 27 days"

One morning I learned that Google was sunsetting Gemini CLI in 27 days. Antigravity CLI (`agy`) was the replacement — a hot-swap migration was needed. The logic seemed simple: call `--print` mode, pipe the prompt to stdin, read the output. Same pattern as Claude Code.

It looked like 3 hours of work. **It took three days.**

#### Act 2: "Where are the tool calls?"

I set up the hot-swap. agy was returning text answers. But on file-write requests, MCP tools were **never being called**. The frontend approval panel never opened, and the backend log had no `CallToolRequest` entries.

I spent hours sifting through config files: `mcp_config.json`, `settings.json`, `disabledTools`, `trust: true`. Everything looked correct. Then I found this **critical line** in the agy log:

```
[ERROR] checkpoint model generated tool calls
```

I asked agy itself (yes, I literally ran `agy` and had an argument with it). Then I asked Codex. Both reached the same conclusion: **`--print` mode blocks tool dispatch by design.** The model generates a tool call, agy catches it, says "you're non-interactive, you can't call tools," and re-prompts the LLM for a text-only response.

> *This is where I forgot that every dead end is a lesson, and fell into the "I'll find a flag for sure" trap.*

#### Act 3: "We'll use `-i` mode!"

I thought I'd found the solution. Use `--prompt-interactive` (`-i`) instead of `--print`, and tools would work. agy and Codex both endorsed this:

> "Do an stdin EOF for graceful exit, bubbletea will auto-fallback on PIPE, no problem."

First try: `-i` flag, stdin PIPE. Result:

```
bubbletea: error opening TTY: bubbletea: could not open TTY:
open /dev/tty: device not configured
```

bubbletea (agy's TUI library) refused to run over PIPE. **A real PTY was required.**

#### Act 4: PTY and the Terminal Hijack Disaster

Python `pty.openpty()`, `termios.tcsetattr()` to disable echo, `TIOCSWINSZ` to set dimensions, `start_new_session=True` to detach from parent. All by the book. Ran it.

The user's `npm run dev` terminal **showed agy's TUI**. Sign-in flow, spinners, "press ctrl+d again to exit", "Do you want to allow Bash(git status)?" prompts — all flowing from the backend-spawned subprocess into the user's terminal. Meanwhile, the backend could read nothing from stdout.

How was that possible? `start_new_session=True` should have detached from the controlling tty. But agy was finding `/dev/tty` through the parent chain anyway. To force the slave PTY as the controlling tty, I'd need a `TIOCSCTTY` ioctl. **And worse:** `--dangerously-skip-permissions` in `-i` mode wasn't bypassing native shell command prompts. So even if PTY worked, agy would still ask "allow git status?"

#### Act 5: Research — We're Not Alone

I scoured the web. Looked at `google-antigravity/antigravity-cli` on GitHub. Issue #187 was right there, open with **no response from Google**:

> *"Windows: agy.exe produces no stdout when spawned non-interactively (stdio: ['ignore', 'pipe', 'pipe'])"*

The exact same problem, from another user's mouth. Then in the Gemini API docs I found the "Antigravity Agent" endpoint:

> *"function_calling and mcp are not yet supported."*

On top of that, agy runs in Google's cloud sandbox — it couldn't write to our Unity workspace anyway.

The verdict was clear: **`--print` mode doesn't dispatch MCP tools. `-i` mode requires interactive TUI, not automation-friendly. The Antigravity API doesn't yet support function calling.** All three roads closed.

#### Act 6: Acceptance and the Banner

I reverted the PTY changes. Went back to `--print` mode. agy returned text answers — couldn't call my `save_file` MCP tool, but at least it wasn't hijacking the user's terminal anymore.

Then I noticed something: agy was writing files and running terminal commands in some cases — bypassing our approval bridge, through Antigravity's own sandbox. To the user, the behavior looked like "the AI is doing things without asking me."

The only honest fix: **tell the user.**

```tsx
{isAgyModel && !agyBannerDismissed && (
  <div className="bg-yellow-500/15 border-yellow-500/40 ...">
    <AlertTriangle />
    <span>{t('chat.agyNotice')}</span>
    {/* "Antigravity CLI: file writes and terminal commands run
         automatically without approval (Google MCP approval
         integration is not yet available)." */}
    <button onClick={dismissAgyBanner}><X /></button>
  </div>
)}
```

Yellow, dismissible, persisted in sessionStorage. The user sees it once at app launch, dismisses it, moves on.

#### Scene 7: The Fix — "I Was Knocking on the Wrong Door"

The banner held for a few days. Then I asked the question again: *how does agy use unityMCP?* Because unityMCP **worked** — agy could add GameObjects to the scene. If `--print` loads no MCP at all, how was unityMCP working?

An isolated test (only unityMCP registered, asked agy to "list all your tools and call `read_console`") gave the answer. agy explained it itself:

> *"My `read_console` tool is lazily loaded via the HTTP MCP server, so I wrote a Python script in the workspace that connects via `streamable_http_client` to `http://127.0.0.1:8080/mcp` and called the tool from there."*

**That was the lightbulb moment.** agy `--print` genuinely doesn't load MCP natively (my original diagnosis was right). But agy is clever enough: when it sees an HTTP MCP server's URL in the config, it uses `run_command` to **write its own bridge script** and connect to it. unityMCP "worked" because it was HTTP and agy reached it over `run_command` — not via the MCP protocol.

So in `--print` mode the **only real channel agy sees is `run_command`.** I'd been knocking on the wrong door the whole time: instead of forcing MCP tool dispatch, I should have used `run_command`.

**The fix — a `unityai` CLI bridge:**

1. I wrote `Backend/app/unityai_cli.py` + `Backend/unityai` (shell wrapper). This CLI **shares the exact same `approval_bridge`** as the MCP tools — so a `unityai save-file ...` call opens the approval card just like `mcp__unityai__save_file` would. agy invokes it via `run_command`.

2. I disabled agy's **real** built-in write tools via `disabledTools`: `write_to_file`, `replace_file_content`, `multi_replace_file_content`. (The old list had **wrong names** like `write_file`/`modify_file` — agy has no such tools, so it never took effect. I learned the correct names by having agy dump its own tool list.) With write tools disabled, agy's only path to create a file is `run_command`, which we route to `unityai save-file` → **the approval card appears.**

3. I **removed** the yellow banner — it was lying now. agy goes through the approval gate just like Claude Code/Codex.

Isolated test + live test: agy called `unityai save-file` via `run_command`, the file was created with the correct content **and an approval card**. The tool-dispatch problem I'd fought for three days dissolved once I dropped down to the right abstraction layer (`run_command`) — the whole hot-swap saga fit into a week.

**One small caveat that remains (honesty corner):** we can't disable `run_command` — because we invoke the `unityai` CLI through it (a catch-22). So agy could theoretically **bypass** approval via raw shell (`echo > x.cs`) or by bridging to unityMCP's `manage_script` tool over `run_command`. We only discourage this via the prompt; it's not a 100% guarantee. In practice, with write tools disabled, agy naturally gravitates to `unityai`. For comparison: Claude Code & Codex load MCP **natively**, so `mcp__unityMCP__manage_script` is **hard-banned** there via `--disallowedTools`; agy lacks that guarantee. An acceptable trade-off — so agy can keep using unityMCP freely for scene control.

#### Lessons Learned

1. **Embedding a CLI is categorically different from API integration.** A CLI is designed for users — interactive TUI, permission prompts, terminal control. Forcing it into a programmatic shape is fighting the wrong layer.

2. **Don't forget to verify when you ask an AI agent.** agy said "PIPE has fallback, stdin EOF gives graceful exit." Both were wrong. Codex said the same thing. AI agents don't *remember* their own library behavior — they *guess*. Every recommendation needs an isolated test.

3. **"It doesn't work" is a valid answer.** I spent three days wrestling with PTY because it *should* have been solvable. It wasn't (yet). Accepting that and giving the user clear information beats a fragile hack every time.

4. **Check GitHub Issues early.** Issue #187 was already there. Looking on day one would have saved me two days.

5. **Document the dead ends.** That's what this section is for. So the next developer (or me in 6 months) doesn't walk the same road.

---

### Practical Rules: What I'd Want You to Know Before Contributing

1. **Always write CLI configurations to global scope.** Gemini CLI in headless mode does not read project-level `.gemini/settings.json` — only `~/.gemini/settings.json`.

2. **Use `strip()` comparison in approval gates.** `original == content` won't catch trailing newline differences; the diff viewer opens unnecessarily.

3. **Check MCP tool names against CLI built-in lists.** Every CLI has its own built-in tools; name collisions are silent.

4. **Nudge the intent classifier toward the safe side.** In edge cases, prefer CHAT over GENERATION. Creating the wrong file is much worse than giving the wrong conversational response.

5. **Split routes early.** Any route file over 500 lines should be broken up. This was the most expensive technical debt in this project.

6. **Before spawning a CLI as a subprocess, scan upstream Issues.** I spent 3 days integrating `agy` with MCP before finding Issue #187 in the `google-antigravity/antigravity-cli` repo — exact same problem, no response from Google. A 5-minute search would have saved me 2 days.

7. **Verify claims AI agents make about their own libraries.** I asked agy "how do you behave on PIPE?" — it said "I fall back." Lie. An isolated test is always more reliable than an AI's answer.

---

## Contributing

This project is in active development. To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Run backend tests: `cd Backend && pytest`
4. Run frontend tests: `cd Frontend/frontend && npm test`
5. Open a pull request

---

## Developer

**Burak Emre Erdemci**

This project is an open-source portfolio and research effort for developers who want to fundamentally transform their Unity development workflow with AI.

[MIT License](LICENSE)
