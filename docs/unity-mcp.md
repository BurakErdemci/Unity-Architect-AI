# Unity MCP integration

The embedded Unity Editor bridge: 46 tools, zero-install setup, and the input
system that lets the agent actually play the game it just built.

---

## 🎮 Unity MCP Integration

Unifies the [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) project, giving the AI direct control of the Unity Editor.

### Setup: fully automatic
1. Open your Unity project (the Editor must be running)
2. Click the **Unity MCP toggle** in the app
3. `unity_mcp_manager` starts the MCP server with the bundled `uvx`, installs the package, and connects to the Editor
4. When the toggle turns green (`Unity connected ✓`) it's ready

> Because `uv`/`uvx` is bundled in the packaged app, the user doesn't need to install it separately. If the Unity Editor is closed the toggle can't connect — open Unity first.

> **Approval behavior:** On the Claude path, unityMCP calls that **mutate** the scene open an approval card; calls that only **read** (hierarchy, console, search) do not. On the Codex and agy paths unityMCP still runs unapproved. See [Approval scope](security.md#️-approval-scope-what-is-and-isnt-confirmed-an-honesty-note).

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

---

[← Back to the README](../README.md)
