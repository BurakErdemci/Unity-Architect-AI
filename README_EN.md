<div align="center">

# 🏗️ Unity Architect AI

**Autonomous AI Coding Partner for Unity**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![Unity MCP](https://img.shields.io/badge/Unity_MCP-Active-7B2FBE?style=for-the-badge&logo=unity&logoColor=white)](./unity-mcp)

*Not just a chatbot — an autonomous AI development environment that knows your project, reads files, writes code, runs the terminal, and directly controls the Unity Editor.*

[![Turkish README](https://img.shields.io/badge/🌐_Türkçe_README-red?style=for-the-badge)](./README.md)
[![Roadmap](https://img.shields.io/badge/🗺️_Roadmap-orange?style=for-the-badge)](./ROADMAP.md)

</div>

---

## What Is This?

Unity Architect AI is an **Agentic IDE** built for Unity developers. It brings the Claude Code and Codex CLI experience to the Unity world. It chats with the user, autonomously reads files, writes code, uses the terminal, and now directly controls the Unity Editor via MCP.

---

## Core Features

### 🧠 AI Partner Mode
Short and direct. No long reports, no unnecessary filler. The AI understands what the user wants and delivers the solution by the shortest path. MAX 200 word rule.

### 🛠️ Agentic Loop
The AI has real tools:
- `read_file`, `write_file`, `list_directory` — browses the project autonomously
- `run_terminal_command` — git push, npm install, anything
- Unity MCP tools — directly controls the Editor

Every tool call is shown to the user. Dangerous operations require approval.

### 🔌 Unity MCP Integration (Phase 5)
The AI directly controls the Unity Editor:

```
User: "Add a button to the Canvas"
       ↓
Router Agent → UI Maestro Expert
       ↓
Unity MCP (localhost:8080)
       ↓
Unity Editor: Button created ✅
```

**Supported operations:** GameObject management, UI Canvas, Script writing/compilation, Prefabs, Materials, Scene management, Console log reading.

### 🤖 Subscription Agent Support
**Claude Code** and **Codex CLI** running on your machine connect to Antigravity. These agents are forced to use Antigravity's **MCP Server** for file and terminal access — no dangerous operation runs without going through an approval gate.

### 🛡️ Approval System
- **Diff Viewer** — code changes shown before applying
- **Command Approval** — terminal commands require approval
- **Ephemeral Snapshot** — changes not written to disk until approved

### 💡 Smart Code Generation
- User drags a file or types a command
- Plan / Auto / Step-by-step modes
- AI writes code, opens it in editor, shows errors

### 🔬 C# Linter (Real Compiler)
Not AI guessing — real **Mono `csc`** compiler. Errors shown with line/column info as red squiggly lines in Monaco editor. All `.cs` files scanned automatically on project open.

### 🧠 Memory (Architect Wisdom)
At the start of each session, the AI shows a summary of its previous project analysis (Architect Wisdom panel). `/compact` summarizes history to free up token space.

### 💻 Integrated Terminal
VS Code-style terminal panel. Problems / Output / Terminal tabs. Click an error in the list — jumps to the relevant line.

### 🤖 Multi-Provider AI
Claude, GPT, Gemini, Groq, DeepSeek, Ollama, OpenRouter, Moonshot — one interface.

---

## Architecture

```
┌────────────────────────────────────────────┐
│          ELECTRON DESKTOP APP              │
│  File Explorer | Monaco Editor | AI Chat   │
│  Terminal Panel | Problems | Diff Viewer   │
└──────────────────┬─────────────────────────┘
                   │ HTTP REST + SSE
┌──────────────────▼─────────────────────────┐
│        PYTHON BACKEND (FastAPI)            │
│                                            │
│  Router Agent → AI Provider (Claude/GPT..) │
│  Agentic Loop (Tool Use) → SSE Stream      │
│                                            │
│  Antigravity MCP Server (FastMCP)          │
│  ├── file_tools (read/write/list)          │
│  ├── bash_tool (terminal + approval gate)  │
│  └── Subscription CLI Bridge              │
└──────────────────┬─────────────────────────┘
                   │ HTTP / WebSocket
┌──────────────────▼─────────────────────────┐
│       UNITY EDITOR (unity-mcp)             │
│  GameObject | Script | UI | Scene | Build  │
└────────────────────────────────────────────┘
```

---

## Download

| Platform | Link |
|----------|------|
| 🍎 macOS (Apple Silicon) | [arm64.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0-arm64.dmg) |
| 🍎 macOS (Universal) | [universal.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0.dmg) |
| 🪟 Windows | [Setup.exe](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI.Setup.1.0.0.exe) |

> macOS "damaged" error: `xattr -cr /Applications/Unity\ Architect\ AI.app`

---

## Setup (Developer)

**Requirements:** Python 3.13, Node.js 18+

```bash
# 1. Clone
git clone https://github.com/BurakErdemci/Unity-Architect-AI.git
cd Unity-Architect-AI

# 2. Backend
cd Backend
python3.13 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend
cd ../Frontend/frontend
npm install
npm run dev
```

> **Docker:** `docker compose up --build -d` → `npm run dev:docker`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.13, FastAPI, FastMCP, SQLite, Uvicorn |
| **Frontend** | Electron 34, Next.js 14, React 18, Tailwind CSS, Monaco Editor |
| **AI** | Claude, GPT, Gemini, Groq, DeepSeek, Ollama, OpenRouter |
| **Unity Bridge** | unity-mcp, MCPForUnity, WebSocket Hub |
| **Security** | MCP Approval Gate, Ephemeral Snapshot, IPC Whitelist, safeStorage |

---

## Sprint History (Summary)

| Sprint | What Was Built |
|--------|---------------|
| 1–2 | Partner mode, intent classifier, pipeline simplification, thinking system |
| 3–4 | Agentic Loop (tool use), Architect Wisdom memory panel, SSE streaming |
| 5–6 | Integrated terminal, C# Linter (Mono csc), Monaco marker integration |
| 7–8 | Auto project radar, autonomous terminal, Git command chaining |
| 9–11 | Claude Code + Codex MCP integration, Approval Gate, Ephemeral Snapshot |
| 12+ | Unity MCP integration, Expert Agent Swarm (active) |

Details → [LOCAL_REFACTOR_NOTES.md](./LOCAL_REFACTOR_NOTES.md) · [ROADMAP.md](./ROADMAP.md)

---

## 👨‍💻 Developer

**Burak Emre Erdemci**

## 📄 License

This project is licensed under the [MIT License](LICENSE).

### Third-Party Licenses

This project includes the following open-source component for Unity Editor integration:

| Component | Source | License |
|-----------|--------|---------|
| **unity-mcp** (MCPForUnity) | [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) | [MIT](./unity-mcp/LICENSE) — Copyright (c) 2025 CoplayDev |
