<div align="center">

# 🏗️ Unity Architect AI

**AI-Powered Unity C# Code Analysis, Review, and Generation Platform**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-34-47848F?style=for-the-badge&logo=electron&logoColor=white)](https://electronjs.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![Anthropic](https://img.shields.io/badge/Claude-API-191919?style=for-the-badge&logo=anthropic&logoColor=white)](https://anthropic.com)

*Professional-grade Unity code review, Game Feel analysis, and enterprise-level code generation from scratch — powered by a Multi-Agent AI pipeline.*

---

[![AI Comparison](https://img.shields.io/badge/🤖_AI_Comparison-See_Models-6366f1?style=for-the-badge)](./AI_COMPARISON.md)

---

## ⬇️ Download

| Platform | Download Link |
|----------|---------------|
| 🍎 macOS (Apple Silicon — arm64) | [Unity.Architect.AI-1.0.0-arm64.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0-arm64.dmg) |
| 🍎 macOS (Universal — Intel + Apple Silicon) | [Unity.Architect.AI-1.0.0.dmg](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity.Architect.AI-1.0.0.dmg) |
| 🪟 Windows | [Unity Architect AI Setup 1.0.0.exe](https://github.com/BurakErdemci/Unity-Architect-AI/releases/download/v1.0.0/Unity%20Architect%20AI%20Setup%201.0.0.exe) |

> All releases: [GitHub Releases →](https://github.com/BurakErdemci/Unity-Architect-AI/releases)

> **macOS notice:** If you get a "damaged" error, run this in Terminal:
> ```bash
> xattr -cr /Applications/Unity\ Architect\ AI.app
> ```

</div>

## 📋 Table of Contents

- [Features](#-features)
- [Multi-Agent Architecture](#-multi-agent-architecture)
- [Pipeline System](#-pipeline-system)
- [Architecture Overview](#-architecture-overview)
- [Security Architecture](#-security-architecture)
- [Dev Stories & Lessons Learned](#-dev-stories--lessons-learned)
- [Installation](#-installation)
- [Usage](#-usage)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [API Documentation](#-api-documentation)
- [Roadmap](#-roadmap)
- [License](#-license)

---

## ✨ Features

### 🧠 LLM-Based Intent Classification

A hybrid classifier that analyzes user messages and routes them to the correct pipeline:

| Intent | Trigger | Pipeline |
|--------|---------|----------|
| `GREETING` | "Hello", "How are you" | Direct greeting response |
| `GENERATION` | "Write an FPS movement system", "Create an inventory system" | Code Generation Pipeline |
| `ANALYSIS` | "Analyze this code", C# code detected | Multi-Agent Analysis Pipeline |
| `CHAT` | "What is NavMesh in Unity?" | General conversation |
| `OUT_OF_SCOPE` | "Give me a recipe" | Polite refusal |

> Two-layer approach: **Fast static filter** (regex) + **LLM fallback** (Claude/Groq for ambiguous cases).

### 📚 KB Mode — Local Unity Knowledge Base (Offline Support)

One of Unity Architect AI's unique features: it can answer Unity questions **without an internet connection or AI API key**.

- **Local knowledge base** (`unity_kb.json`) — hundreds of Unity-specific rules, best practices, and explanations
- **Offline operation** — KB Mode activates when no AI service is selected or available
- **Instant response** — zero latency with no API calls
- **Coverage:** Performance rules, physics, camera, animation, shaders, UI/Canvas, and more
- **Works alongside AI** — KB content is injected as context into AI responses for more accurate results

---

### 🎮 Game Feel Analysis

Goes beyond code quality — rates **what the player will actually feel** when running the code:

| Category | Weight | Example Check |
|----------|--------|---------------|
| 🕹️ Movement | 30% | Snappy vs Floaty? rb.velocity vs AddForce? |
| ⚔️ Combat | 25% | Input → Action delay? Feedback present? |
| 🎯 Physics | 20% | Correct FixedUpdate? Fall multiplier? |
| 📷 Camera | 15% | Smooth follow? LateUpdate? |
| ✨ Juice | 10% | Screen shake, hit-stop, particles? |

### 📊 Unified Scoring System

Converts independent agent evaluations into **a single score** using a weighted average:

```
Final Score = (Technical Review × 0.60) + (Game Feel × 0.40)
```

- Single clean quality score **on a 0–10 scale**
- If score drops **below 8.0**, the Expert agent automatically rewrites the code (Reflexive Loop)
- **Score Clamping:** All scores are forced to the 0–10 range (protection against negative/overflow scores)

### 🖥️ IDE-Like User Interface

- **3-panel layout** — File Explorer | Code Editor | AI Chat
- **Pitch Black** theme — dark, premium design
- **Syntax highlighting** — C# code coloring
- **Markdown rendering** — rich formatting, emoji and score badges in AI responses
- **Drag & drop files** — drop `.cs` files directly into the editor

### 🏗️ Workspace System

- **Login → Select Workspace → App** flow
- Automatically remembers the last opened workspace
- File read/write support (within workspace)

### 🤖 Multi-Provider AI Support

| Provider | Type | Usage | Models |
|----------|------|-------|--------|
| **Anthropic Claude** | ☁️ Cloud | Multi-Agent Pipeline + Hybrid mode | Claude 4.6 Sonnet, Claude 4.6 Opus |
| **OpenAI** | ☁️ Cloud | Direct OpenAI API | GPT-5.4, GPT-5.4-mini, GPT-5.4-nano |
| **OpenRouter** | ☁️ Cloud | 200+ model access | Kimi K2.5, GPT-5.4, Claude, Gemini, etc. |
| **Groq** | ☁️ Cloud | Fast single-agent analysis | Llama, Mixtral |
| **Google Gemini** | ☁️ Cloud | Alternative cloud provider | Gemini Pro, Gemini Ultra |
| **DeepSeek** | ☁️ Cloud | OpenAI-compatible API | DeepSeek Coder |
| **Moonshot** | ☁️ Cloud | Kimi model family | Kimi K2.5 |
| **Ollama** | 🖥️ Local | Local model support | Any local model |

> **Hybrid Claude + ChatGPT Mode:** Claude handles architectural planning, ChatGPT (OpenAI / OpenRouter) writes the code. Game Feel analysis always stays on Claude. This combination significantly reduces cost on long code generation. A single toggle switches to full Claude mode.

### 🔐 OAuth Login

Fast login with Google and GitHub accounts:

| Provider | Status |
|----------|--------|
| **Google** | ✅ OAuth 2.0 |
| **GitHub** | ✅ OAuth 2.0 |
| **Username/Password** | ✅ Classic registration/login |

### 🔎 Static Analysis — Auto-Detected Issues

<details>
<summary><b>Performance</b></summary>

- `GetComponent<T>()` called every frame
- `GameObject.Find()` / `FindObjectOfType()` inside Update
- `Camera.main` repeated access
- String concatenation every frame
- `Input.GetKeyDown()` inside FixedUpdate

</details>

<details>
<summary><b>Physics</b></summary>

- Moving with `transform.position` while Rigidbody is present
- Using `transform.Translate` while Rigidbody is present

</details>

<details>
<summary><b>Best Practice</b></summary>

- Using `tag ==` instead of `CompareTag()`
- Public fields — `[SerializeField] private` suggestion
- Frequent `Destroy` calls — Object Pooling suggestion

</details>

---

## 🤖 Multi-Agent Architecture

The system uses **8 independent agents**, each with a specific area of expertise.

> **Hybrid Claude + ChatGPT Mode:** Claude handles architectural planning (Orchestrator), ChatGPT writes the code (Coder) — via direct OpenAI API or OpenRouter. ChatGPT is significantly more cost-effective for long code blocks. Game Feel analysis always stays on Claude. A single toggle switches the entire pipeline to full Claude mode.

### Analysis Pipeline Agents

| Agent | Role | Output | Provider |
|-------|------|--------|----------|
| 🎯 **Intent Classifier** | Detects user intent | `GREETING`, `GENERATION`, `ANALYSIS`, `CHAT` | Claude |
| 📋 **Orchestrator** | Creates architectural fix plan | Short technical map (max 100 words) | Claude |
| 🔧 **Unity Expert** | Fixes/rewrites code per plan | Clean, enterprise-level C# code | Claude or ChatGPT* |
| ⚖️ **Critic** | Reviews and scores the fixed code | JSON: `{score, review_message, fatal_errors_found}` | Claude or ChatGPT* |
| 🎮 **Game Feel** | Evaluates game feel | JSON: `{game_feel_score, movement, combat, physics, ...}` | **Always Claude** |

*In hybrid mode, Expert and Critic use ChatGPT (OpenAI / OpenRouter). In full Claude mode, all agents run on Claude.

### Code Generation Pipeline Agents

| Agent | Role | Output |
|-------|------|--------|
| 🚦 **Clarification Gate** | Detects missing info in ambiguous requests | Maximum 4 questions or "pass" decision |
| 🏗️ **Architect** | Creates architectural plan from scratch | Short design blueprint (STEP 0→3 scope guarantee) |
| 💻 **Coder** | Generates code from plan | Fully working C# code |

### Agent Safety Mechanisms

```
┌─────────────────────────────────────────────────────┐
│              AGENT CONSTRAINT SYSTEM                │
├─────────────────────────────────────────────────────┤
│ ✅ max_tokens Limits:                               │
│    • Critic: 1024 tokens (short and concise)        │
│    • Game Feel: 1500 tokens                         │
│    • Coder: 8192 tokens (full architecture output)  │
│                                                     │
│ ✅ Negative Constraints (Role Drift Prevention):    │
│    • Critic: "NEVER write code"                     │
│    • Game Feel: "NEVER produce code blocks"         │
│                                                     │
│ ✅ Post-Processing:                                 │
│    • Code block stripping (from Critic responses)   │
│    • Score clamping (forced to 0-10 range)          │
│    • JSON cleanup and recovery (Validator)          │
└─────────────────────────────────────────────────────┘
```

---

## ⚙️ Pipeline System

### 🔍 Tier 1 — Single Agent Analysis (All providers)

```
User Code → Static Analysis → AI Analysis → Code Fix → Result
```

Fast and simple; analysis and fix in a single LLM call.

### 🔗 Tier 2 — Multi-Agent Analysis (Claude + ChatGPT)

```
                    ┌─────────────┐
                    │ Orchestrator│ Creates plan
                    └──────┬──────┘
                           │
              ┌────►┌──────▼──────┐
              │     │   Expert    │ Fixes code
              │     └──────┬──────┘
              │            │
              │     ┌──────▼──────────────────┐
              │     │    asyncio.gather()      │ ← Runs in parallel
              │     │  ┌────────┐ ┌──────────┐ │
              │     │  │ Critic │ │Game Feel │ │
              │     │  │(1024t) │ │ (1500t)  │ │
              │     │  └───┬────┘ └────┬─────┘ │
              │     └──────┼───────────┼───────┘
              │            │           │
              │     ┌──────▼───────────▼──────┐
              │     │  Unified Score (0-10)    │
              │     │  Tech×0.6 + GameFeel×0.4 │
              │     └──────────┬───────────────┘
              │                │
              │        Score < 8.0?
              │           YES │ NO
              └───────────────┘  │
                                 ▼
                          ✅ Final Report
```

- **Reflexive Loop:** If score < 8.0, Expert automatically rewrites the code (max 2 attempts)
- **Combined Feedback:** On retry, both technical and game feel criticism are sent together

### 🆕 Tier 3 — Code Generation Pipeline (Multi-Agent, Hybrid Claude + ChatGPT)

```
User Request
      │
      ▼
Clarification Gate ──── Ambiguous? ──► Ask Questions (max 4) ──► User Answers
      │ Specific Enough                                                │
      │◄───────────────────────────────────────────────────────────────┘
      ▼
  Architect [Claude]
  ┌─────────────────────────────────────────────────┐
  │ STEP 0: List all user requests                  │
  │ STEP 1-2: Architecture plan (Section A + B)     │
  │ STEP 3: Scope verification (every request ✅)   │
  └─────────────────┬───────────────────────────────┘
                    │ File list (e.g. 23 files)
                    ▼
              Batch Splitter
              (BATCH_SIZE = 10)
         ┌────────┬────────┐
         ▼        ▼        ▼
      Batch 1  Batch 2  Batch 3
      (10 f.)  (10 f.)  (3 f.)
         │        │        │
         └────────┴────────┘
                  │ each batch → Coder
                  ▼
         Coder [Claude or ChatGPT*]
          (max 8192 tokens)
                  │
                  ▼
         Game Feel Loop [Claude]
    (silent review, rewrites if score is low)
                  │
                  ▼
           ✅ Final Code
```

*In hybrid mode, Coder uses ChatGPT (direct OpenAI or OpenRouter). In full Claude mode, all agents run on Claude.

- **Clarification Gate:** Asks questions for ambiguous requests (max 4, in a single message). After the user answers, the `skip_gate` mechanism skips it — never asks twice.
- **Architect Scope Guarantee:** STEP 0 enumerates all user requests. STEP 3 verifies each one with ✅/❌. If any feature is ❌, Architect loops back and adds it.
- **Batch Splitting:** Large systems (e.g. 23-file RPG) are split into batches of 10. Each batch is a separate Coder call. User types "continue" to start the next batch.
- **Continuation State:** Batch state is stored in `continuation_store`; "continue / yes / ok" is auto-detected.

### 🆕 Tier 4 — SingleAgent Code Generation (All providers)

```
User Request → Single AI Call (Plan + Code + Game Feel rules embedded) → Final Code
                                        │
                              Token limit reached?
                                   YES │ NO
                                       │    ▼
                              Open ``` ▼  Result
                              closed + "continue" message
```

- All providers (OpenAI, OpenRouter, Groq, Gemini, DeepSeek, Ollama, Claude) use this pipeline
- Provider-specific token limits: Google 65K, Groq 32K, others 16K
- English prompts for better LLM output quality
- Game Feel rules, Save/Load rules, and output format embedded directly in prompt
- Response is auto-closed on token cutoff; user can type "continue" to resume
- **Groq Free Tier:** 413/token-limit error shows a user-friendly message instead of raw API error

---

## 🏛️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ELECTRON (Nextron)                        │
│  ┌──────────┐  ┌─────────────────┐  ┌────────────────────┐ │
│  │   File   │  │  Code Editor    │  │   AI Chat          │ │
│  │ Explorer │  │  (Syntax HL)    │  │   (Markdown)       │ │
│  │          │  │                 │  │   Score Badge      │ │
│  │ .cs      │  │  C# highlight   │  │   Game Feel UI     │ │
│  │ files    │  │                 │  │   Score Graph      │ │
│  └──────────┘  └─────────────────┘  └───────┬────────────┘ │
│                                              │              │
└──────────────────────────────────────────────┼──────────────┘
                                               │ HTTP (REST)
┌──────────────────────────────────────────────┼──────────────┐
│              PYTHON BACKEND (FastAPI)         │              │
│                                               │              │
│  ┌──────────────┐   ┌────────────────────────▼───────────┐  │
│  │   Intent     │   │         Pipeline Router            │  │
│  │  Classifier  │──▶│  GREETING → Direct Response        │  │
│  │ (LLM+Regex)  │   │  ANALYSIS → Multi-Agent Pipeline   │  │
│  └──────────────┘   │  GENERATION → Code Gen Pipeline    │  │
│                      │  CHAT → General Conversation       │  │
│                      └───────────────┬───────────────────┘  │
│                                      │                      │
│  ┌────────────┐  ┌──────────┐  ┌─────▼──────┐              │
│  │  Static    │  │  Report  │  │ Agent Team │              │
│  │ Analyzer   │  │  Engine  │  │ (8 Agents) │              │
│  │  (regex)   │  │ (score)  │  │            │              │
│  └────────────┘  └──────────┘  └─────┬──────┘              │
│                                      │                      │
│  ┌───────────────┐  ┌────────┐  ┌────▼───────────────────┐ │
│  │ AI Providers  │  │ SQLite │  │ Validator + Sanitizer  │ │
│  │ (8 providers) │  │   DB   │  │ (JSON clean, clamp)    │ │
│  └───────────────┘  └────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔐 Security Architecture

### IPC Channel Whitelist

All `invoke` calls between the renderer and main process in Electron go through a fixed whitelist. Any channel not on the list is immediately rejected with `Promise.reject`:

```typescript
// main/helpers/ipc-whitelist.ts
export const ALLOWED_INVOKE_CHANNELS = new Set([
  'open-file-dialog', 'open-folder-dialog',
  'read-directory', 'read-file',
  'write-file', 'file-exists', 'write-multiple-files',
  'session-get', 'session-set', 'session-clear',
  'get-backend-base-url',
])
```

IPC tests (`__tests__/ipc-whitelist.test.ts`) import the real `ipc-whitelist.ts` file — if the source file is broken, tests fail too.

### File System Protection

All file operations are protected against path traversal attacks using `path.resolve()` + `path.relative()`:

| Handler | Restriction |
|---------|-------------|
| `read-directory` | Workspace directory only |
| `read-file` | Inside workspace + `.cs` files only |
| `write-file` / `write-multiple-files` | `workspace/Assets/Scripts/**/*.cs` |
| `file-exists` | `workspace/Assets/Scripts/**/*.cs` |

```typescript
// These all return false
isAllowedWorkspaceReadFile('/etc/passwd', workspace)
isAllowedUnityScriptPath('../../../secrets.cs', workspace)
isAllowedUnityScriptPath('/tmp/exploit.cs', workspace)
```

### Session Token Security — `safeStorage`

Session tokens are stored in the OS encrypted storage, not `localStorage`:

- **Windows** → DPAPI (Data Protection API)
- **macOS** → Keychain

The `session.enc` file is stored encrypted under `app.getPath('userData')`. Existing `localStorage` tokens are automatically migrated to `safeStorage` on first launch.

If `safeStorage` is unavailable (headless environment, etc.), the user is explicitly warned — no silent persistence loss.

### API Key At-Rest Encryption

Users' AI provider API keys are stored encrypted in SQLite using Fernet. The encryption key is kept in the OS keystore (not in the same directory as the database):

```
Priority order:
1. API_KEY_ENCRYPTION_KEY env var
2. Windows Credential Manager / macOS Keychain  (keyring)
3. Fallback: ~/.unity_architect_ai/api_key_fernet.key
```

Existing installations are automatically migrated to keystore on first launch.

User passwords are hashed with bcrypt — irreversible.

### Rate Limiting — Sliding Window

IP-based sliding window against brute-force and credential stuffing attacks:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /login` | 5 attempts | 5 minutes |
| `POST /auth/complete/{code}` | 10 attempts | 1 minute |

Counter resets on successful login — legitimate users don't stay blocked.

### Backend Port Security

The backend doesn't run on a fixed port 8000. At startup, it gets a random port from the OS via `net.createServer({ port: 0 })`. The port is passed to the renderer only through the `get-backend-base-url` IPC channel — the renderer cannot determine the URL itself.

### OAuth Security

- All OAuth callbacks are protected against CSRF via `state` token validation
- `postMessage` is only sent to known `localhost` and `app://` origins
- OAuth callback completion codes are single-use (`consume_oauth_completion`)
- `.env` is not included in the build — if OAuth credentials are missing, buttons are automatically hidden

### Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `ipc-whitelist.test.ts` | 23 | Whitelist correctness, injection attempts, case bypass |
| `file-security.test.ts` | 20 | Path traversal, workspace boundary, extension check |
| `session-storage.test.ts` | 20 | Round-trip, migration, fallback without encryption |
| `regression-ipc.test.ts` | 18 | background.ts ↔ preload synchronization |
| `toast.test.ts` | 19 | Hook logic, auto-dismiss, type correctness |
| `test_auth_rate_limit.py` | 8 | Rate limit integration tests (FastAPI TestClient) |

---

## 🛠️ Dev Stories & Lessons Learned

Real problems encountered during development and how they were solved:

---

### 1. "Claude Rewrites Code → Token Explosion" — Hybrid Claude + ChatGPT Architecture

In the initial design, the entire Multi-Agent pipeline used Claude: planning, coding, analysis, game feel — all Claude. Two core problems emerged:

- **Reflexive Loop cost:** The Game Feel agent frequently disliked the code (score < 8.0). This triggered the Reflexive Loop, meaning the Expert rewrote the code — Orchestrator + Expert + Critic + Game Feel + Expert again + Critic again. Each loop means new Claude calls. On large systems, costs spiraled out of control after a few loops.
- **Claude is expensive for long code:** Claude is strong at coding but costly for long blocks. ChatGPT produces the same quality code at a fraction of the price.

**Solution — Claude + ChatGPT hybrid mode:**

Claude handles architectural planning (Orchestrator) — once, short, and cheap. ChatGPT writes the actual code (direct OpenAI API or OpenRouter GPT-5.4). For long code blocks, ChatGPT is far more cost-effective than Claude. Game Feel analysis stays on Claude — Claude is more precise for nuanced game feel interpretation.

- **Supported in hybrid mode:** ChatGPT models via direct OpenAI API or OpenRouter (GPT-5.4, etc.)
- **Full Claude mode:** Users can point the entire pipeline to Claude with a single toggle
- **Result:** Same quality output, token cost drops significantly

---

### 2. Architect Only Planned 3 of 7 Features

Real user test: 7 features requested for an RPG — movement, combat, enemy AI, **inventory, equipment, quest system, save/load**. Looking at the Architect's plan, only movement, combat, and AI were there. 4 features missing.

**Why did it happen?** The Architect prompt said "fulfill the user's requests" but there was no mechanism to verify which requests were actually fulfilled. With a large scope, AI planned what came to mind first and forgot the rest.

**Solution: STEP 0 + STEP 3**

```
STEP 0: Numbered every request in the user's message.
  REQUEST-1: inventory system
  REQUEST-2: equipment
  ...
  TOTAL: 7 requests

STEP 3: Verified each request.
  ✅ REQUEST-1: inventory → InventoryManager.cs
  ❌ REQUEST-2: equipment → NO FILE → add to STEP 2 immediately
```

Now the Architect verifies its own plan. If it finds ❌, it can't proceed without fixing it.

---

### 3. Clarification Gate Asked Questions Twice

When a user made an ambiguous request, the Gate asked questions. When the user answered, the Gate asked **again** — as if it had never seen the first conversation.

**Why?** `context_summary` was only 200 characters. When the answer came in, the Gate couldn't see the original prompt + questions, re-evaluated everything and asked again.

**Fix 1:** Raised `context_summary` limit to 800 characters.
**Fix 2:** If the last assistant message has a question mark, `skip_gate = True` — pass directly to Architect.
**Fix 3:** `_combined_prompt` — original request + user's answers are merged and sent to Architect. Architect sees full context, not just short answers.

---

### 4. "Continue" Gave Wrong Error

When single agent hit the token limit and the user typed "continue", the system returned "no active batch session" error.

**Why?** The multi-agent batch system fills `continuation_store`. Single agent doesn't — token cutoff is not its mechanism. But the "continue" guard didn't distinguish between the two.

**Fix:** Extra check in the guard: does the last assistant message contain "Token limit reached"? If yes, it's a single-agent cutoff — don't show `no_state_msg`, continue as normal conversation.

---

### 5. Save System Was Using PlayerPrefs

In RPG code generated by single agent, SaveSystem kept saving data with `PlayerPrefs` every time. This is acceptable for small, temporary data in Unity, but wrong for a save/load system — large data, non-binary structure, platform limitations.

**Fix:** Added a `[SAVE/LOAD RULES]` section to the single agent prompt:
```
- Use JSON file: Application.persistentDataPath + "/save.json"
- NEVER use PlayerPrefs (unless user explicitly requests it)
- JsonUtility.ToJson / FromJson + File.WriteAllText / ReadAllText
```

Subsequent generations produce SaveManager with correct JSON implementation.

---

### 6. Token Limit on Large Systems — Batch System

A 23-file RPG system doesn't fit in a single Coder call. At the 8192 token limit, half-written code, open curly braces, and syntax errors appeared.

**Fix:** Parsed the Architect plan's file list and split it into groups of 10. Each group is a separate Coder call. Showed the user "Batch 1/3 complete, shall I continue?". State stored in `continuation_store`; user types "continue" to start the next batch.

Real test: A complete 23-file RPG system (PlayerController, EnemyAI, InventoryManager, CraftingManager, QuestManager, SaveManager included) was generated flawlessly in 3 batches.

---

## 🚀 Installation

### Requirements

| Requirement | Version | Note |
|-------------|---------|------|
| **Python** | **3.13** | 3.14 not supported — no `grpcio` wheel |
| **Node.js** | 18+ | |
| **npm** | 9+ | Comes with Node.js |

> **Important:** Use Python **3.13**. Python 3.14 causes `pip install` to fail because `grpcio` has not yet published a wheel for it.

### 1. Clone the Repo

```bash
git clone https://github.com/BurakErdemci/Unity-Architect-AI.git
cd Unity-Architect-AI
```

### 2. Backend Setup

#### Install Python 3.13 (if not already installed)

**macOS:**
```bash
brew install python@3.13
```

**Windows:**
```powershell
winget install Python.Python.3.13
# Restart terminal after installation
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install python3.13 python3.13-venv
```

---

#### Create virtual environment (venv)

**macOS / Linux:**
```bash
cd Backend
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
cd Backend
py -3.13 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> **Why `py -3.13`?** On Windows with multiple Python versions installed, `python` may target the wrong version. `py -3.13` uses the Python Launcher to target exactly 3.13.

---

#### Create .env file

Create `Backend/.env`. If you don't plan to use Google or GitHub OAuth, you can leave it empty:

**macOS / Linux:**
```bash
cat > .env << EOF
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
EOF
```

**Windows** — create the file in a text editor:
```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
```

> **Note:** These variables are only for Google/GitHub OAuth login. API keys for Anthropic, OpenAI, Gemini, etc. are NOT entered here. They are entered via the in-app Settings screen and stored encrypted in the OS secure store (Keychain / Windows Credential Manager).

---

### 3. Frontend Setup

```bash
cd Frontend/frontend
npm install

# Start the app (Electron + Next.js)
# If venv is active, backend starts automatically — no need to run uvicorn separately
npm run dev
```

The application will open automatically.

> **Note:** When `npm run dev` is run, Electron automatically starts the backend using `Backend/venv/Scripts/python` (Windows) or `Backend/venv/bin/python` (macOS/Linux).
>
> **Password must be at least 8 characters on the registration screen.**

### 4. Docker Setup (Recommended — No Python installation required)

You can run the backend without installing Python using Docker. Only **Docker Desktop** and **Node.js** are required.

> **Note:** AI API keys for Anthropic, OpenAI, Groq, etc. are NOT placed in `.env`. They are entered via the in-app Settings screen and stored encrypted in the OS secure keystore (Keychain/Credential Manager).

#### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS/Linux)
- Node.js 18+

#### Step 1 — Create `.env` file (optional)

Skip this step if you won't use Google or GitHub login — Docker will continue automatically. If you want OAuth, create `Backend/.env` and fill in the relevant fields.

> **Note:** Docker Compose won't error if `.env` is missing (`required: false`). If you're using a very old Docker Desktop (`docker compose version` < 2.24), you may need to create an empty file: `echo. > Backend\.env` (Windows) or `touch Backend/.env` (macOS/Linux).

#### Step 2 — Start Docker backend

```bash
# From the project root directory
docker compose up --build -d
```

First run downloads dependencies (~1-2 minutes). Subsequent starts are much faster.

Health check:
```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok","service":"unity-architect-ai"}
```

#### Step 3 — Install and start frontend

```bash
cd Frontend/frontend
npm install

# Start in Docker mode (does not spawn Python, connects to Docker backend)
npm run dev:docker
```

---

## 💡 Usage

### Basic Flow

1. **Login** — Register / login with username and password
2. **Select Workspace** — Choose your Unity project's `Assets/Scripts` folder
3. **Select File** — Click a `.cs` file in the left panel
4. **Analyze** — Type "Analyze this code" in chat, or paste code directly
5. **Generate from Scratch** — Send a request like "Write me an FPS movement system"
6. **Review Results** — Unified score, technical review, and game feel report

### Example Use Cases

| Scenario | Example Prompt | Pipeline |
|----------|---------------|----------|
| Analyze existing code | Select file → "Analyze" | Multi-Agent |
| Generate from scratch | "Write me a physics-based zombie chase system" | Code Generation |
| Performance optimization | "Find the performance issues in this code" | Multi-Agent |
| General Unity question | "How does Object Pooling work in Unity?" | Chat |

---

## 🛠️ Tech Stack

### Backend
| Technology | Usage |
|-----------|-------|
| **Python 3.9+** (recommended: 3.13) | Main backend language |
| **FastAPI** | REST API framework |
| **SQLite / SQLAlchemy** | User data, chat history, workspace |
| **Uvicorn** | ASGI server |
| **Anthropic SDK** | Claude API integration |
| **Groq SDK** | Groq API integration |
| **google-generativeai** | Gemini API integration |
| **Ollama** | Local AI model management |
| **passlib + bcrypt** | Password hashing |

### Frontend
| Technology | Usage |
|-----------|-------|
| **Electron 34** | Desktop application framework |
| **Next.js 14** | React framework |
| **React 18** | UI components |
| **Tailwind CSS** | Pitch Black theme & styling |
| **Framer Motion** | Premium animations |
| **react-markdown** | Markdown rendering in AI responses |
| **react-syntax-highlighter** | C# code coloring |
| **Lucide React** | Icon library |

### Tools
| Tool | Usage |
|------|-------|
| **Nextron** | Electron + Next.js integration |
| **electron-builder** | App packaging (exe/dmg) |
| **Axios** | HTTP client |
| **unittest** | Python test framework |

---

## 📁 Project Structure

```
Unity-Architect-AI/
├── Backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app + endpoints + timeout management
│   │   ├── ai_providers.py          # 6 AI providers (max_tokens support)
│   │   ├── analyzer.py              # Static code analysis engine (regex)
│   │   ├── database.py              # SQLite database management
│   │   ├── prompts.py               # Prompt templates and Unity rules
│   │   ├── report_engine.py         # Weighted scoring system
│   │   ├── validator.py             # JSON cleanup, score clamping, response validation
│   │   │
│   │   └── pipelines/
│   │       ├── base.py                    # Pipeline base classes
│   │       ├── single_agent_pipeline.py   # Tier 1: Single agent analysis
│   │       ├── multi_agent_pipeline.py    # Tier 2: Multi-Agent + Reflexive Loop
│   │       ├── code_generation_pipeline.py # Tier 3: Code generation from scratch
│   │       │
│   │       └── agents/
│   │           ├── intent_classifier.py   # 🎯 Intent detection (LLM + Regex)
│   │           ├── orchestrator.py        # 📋 Fix plan creator
│   │           ├── unity_expert.py        # 🔧 Code fixer (Coder)
│   │           ├── critic.py              # ⚖️ Technical reviewer (max 1024t)
│   │           ├── game_feel_agent.py     # 🎮 Game feel analyst
│   │           ├── architect_generation.py # 🏗️ From-scratch architecture planner
│   │           └── coder_generation.py    # 💻 From-scratch code generator (max 8192t)
│   │
│   ├── tests/
│   │   └── test_validator.py        # Validator unit tests (12 tests)
│   ├── requirements.txt
│   ├── Dockerfile                   # Backend Docker image
│   ├── .dockerignore
│   └── .env                         # OAuth credentials — Google/GitHub only (not in git)
│
├── Frontend/
│   └── frontend/
│       ├── main/
│       │   ├── background.ts        # Electron main process + Backend auto-start
│       │   └── preload.ts           # IPC bridge (file system)
│       ├── renderer/
│       │   ├── pages/
│       │   │   └── home.tsx         # Main app component (3-panel layout)
│       │   ├── components/          # UI components
│       │   └── styles/
│       │       └── globals.css      # Pitch Black theme
│       ├── package.json
│       ├── nextron.config.js
│       └── electron-builder.yml
│
├── docker-compose.yml              # Docker backend startup
├── .env.example                    # Example environment variables
├── .gitignore
└── README.md
```

---

## 📡 API Documentation

While backend is running: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/register` | New user registration |
| `POST` | `/login` | User login |
| `POST` | `/chat` | Chat with AI (pipeline active, 300s timeout) |
| `POST` | `/analyze` | Static code analysis |
| `POST` | `/save-ai-config` | Save AI provider and model settings |
| `GET` | `/available-models` | List available AI models (Ollama + Cloud) |
| `POST` | `/conversations` | Create new conversation |
| `GET` | `/conversations/{user_id}` | User's conversations |
| `DELETE` | `/conversations/{conv_id}` | Delete conversation |
| `POST` | `/save-workspace` | Save workspace path |
| `GET` | `/last-workspace/{user_id}` | Get last workspace path |
| `POST` | `/write-file` | Write file (within workspace) |
| `GET` | `/auth/google/url` | Google OAuth initiation URL |
| `GET` | `/auth/google/callback` | Google OAuth callback |
| `GET` | `/auth/github/url` | GitHub OAuth initiation URL |
| `GET` | `/auth/github/callback` | GitHub OAuth callback |

---

## 🗺️ Roadmap

### ✅ Completed (Sprint 1 & 2.1)

- [x] IDE-like 3-panel UI (Pitch Black theme)
- [x] Multi-provider AI support (Claude, Groq, Gemini, Ollama, OpenAI, DeepSeek)
- [x] Static code analysis engine (Unity C# regex rules)
- [x] Multi-Agent Analysis Pipeline (Orchestrator → Expert → Critic → Game Feel)
- [x] Code Generation Pipeline from scratch (Architect → Coder → Game Feel Loop)
- [x] LLM-based Intent Classifier
- [x] Game Feel Agent Integration
- [x] Unified Scoring System (Technical 60% + Game Feel 40%)
- [x] Reflexive Loop (auto-rewrite if score is low)
- [x] Agent Hardening (max_tokens, negative constraints, post-processing)
- [x] Pipeline Performance Optimization (parallel agent execution)
- [x] JSON Robustness (cleanup, recovery, score clamping)
- [x] Workspace management system
- [x] Chat system (multiple conversations, history)
- [x] Unit tests (Validator)

### ✅ Completed (Sprint 2.2)

- [x] OpenRouter integration (200+ model access)
- [x] Direct OpenAI API support (GPT-5.4 model family)
- [x] SingleAgent Code Generation Pipeline (non-Claude providers)
- [x] Google & GitHub OAuth login
- [x] Docker support (Dockerfile + docker-compose)
- [x] Production build (Electron + Backend bundled)
- [x] Backend auto-start (automatic startup in build)

### ✅ Completed (Sprint 2.3)

- [x] Clarification Gate — question-answer flow for ambiguous requests, asks only once
- [x] Architect STEP 0 + STEP 3 — scope guarantee, no user request can be skipped
- [x] Batch Splitting (BATCH_SIZE=10) — large systems (23+ files) generated in batches of 10
- [x] `continuation_store` — batch state in memory, next batch on "continue"
- [x] skip_gate mechanism — skip Gate after clarification answer is given
- [x] combined_prompt — original request + answers merged and sent to Architect
- [x] Single Agent token cutoff fix — "continue" no longer gives wrong error
- [x] Single Agent Save/Load rules — JSON file mandatory instead of PlayerPrefs
- [x] Groq free tier error message — 413/token-limit error converted to user-friendly message

### ✅ Completed (Sprint 2.4 — Security Hardening)

- [x] IPC channel whitelist — only permitted channels callable from renderer
- [x] File system path traversal protection — `workspace/Assets/Scripts/*.cs` boundary
- [x] Session token moved to `safeStorage` — Windows DPAPI / macOS Keychain
- [x] `localStorage → safeStorage` automatic migration
- [x] API key encryption key moved to OS keystore (keyring)
- [x] Rate limiting — `/login` (5/5min) and `/auth/complete` (10/60sec)
- [x] OAuth `app://` origin fix — OAuth flow now works in production Electron
- [x] Backend dynamic port — hardcoded 8000 removed
- [x] `.env` not included in build — OAuth buttons hidden if credentials missing
- [x] PyInstaller integration — no Python installation needed on target machine
- [x] Backend startup error persistent screen — silent failure eliminated
- [x] 108 frontend unit tests (Vitest) + 8 backend integration tests

### ✅ Completed (Sprint 2.5 — Cross-Platform & Provider Expansion)

- [x] Moonshot/Kimi K2.5 provider support added
- [x] Docker backend mode — develop with `npm run dev:docker` without Python
- [x] Windows cross-platform build — PyInstaller + electron-builder NSIS installer
- [x] Hybrid multi-agent mode — Game Feel always on Claude, technical analysis on selected provider
- [x] API key validation — user warned when sending message with provider missing a key
- [x] Minimum 8-character password warning on registration screen
- [x] Python 3.13 compatibility (requirements.txt version pins updated)

### ✅ Completed (Sprint 3)

- [x] Built-in Unity Expert (KB Mode) — local Unity knowledge base, offline support
- [x] Extended Static Analysis rules

### 📋 Planned

- [ ] Code Memory Snapshot — store previously generated files as summaries in SQLite, smart context injection for modification requests
- [ ] Dashboard and analytics graphs
- [ ] PDF report export
- [ ] Feedback learning system (user feedback → rule improvement)

---

## 👨‍💻 Developer

**Burak Emre Erdemci**

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
