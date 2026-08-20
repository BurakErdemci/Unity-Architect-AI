# Approval and security architecture

What the approval gate covers, what it deliberately does not, and how the local
token architecture works. The honesty note about approval scope is the part worth
reading first.

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
  > **Why the old name in that path?** `~/.unity_architect_ai/` and the keyring service name are **legacy paths, deliberately kept for backward compatibility**. They are the address of your existing encryption key and database — renaming them during the move to Gamachine would have made every already-installed user's saved keys undecryptable. The rename stops at the user's data directory on purpose.

---

---

[← Back to the README](../README.md)
