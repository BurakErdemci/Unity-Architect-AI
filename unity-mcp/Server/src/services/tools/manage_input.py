"""Çalışan oyuna sanal cihazlar üzerinden girdi gönderir.

Bu araç, unity-mcp'de eksik olan tek halkayı kapatıyor: play mode'a girmek
(manage_editor) ve ne olduğunu görmek (manage_camera screenshot, read_console)
zaten vardı, ama oyuna MÜDAHALE etmenin yolu yoktu.

Mekanik: Unity'nin eski `UnityEngine.Input` API'si salt okunurdur, dışarıdan
beslenemez. Input System'in `QueueStateEvent`'i olayı Unity sürecinin içinden
üretir — pencere odağı gerekmez, kullanıcı bu sırada makinesini kullanabilir.
⚠️ Sınır: oyun kodu hâlâ `Input.GetKey` yazıyorsa bu olayları GÖRMEZ.
`action="describe"` tam olarak bunu ölçüyor; bir şey çalışmıyorsa İLK oraya bak.
"""

from typing import Annotated, Any

from fastmcp import Context
from mcp.types import ToolAnnotations

from services.registry import mcp_for_unity_tool
from services.tools import get_unity_instance_from_context
from transport.unity_transport import send_with_unity_instance
from transport.legacy.unity_connection import async_send_command_with_retry

INSPECTION_ACTIONS = ["describe"]
KEYBOARD_ACTIONS = ["key"]
POINTER_ACTIONS = ["mouse_move", "mouse_button", "scroll"]
GAMEPAD_ACTIONS = ["gamepad"]
UI_ACTIONS = ["ui_click"]
COMPOSITE_ACTIONS = ["sequence"]
LIFECYCLE_ACTIONS = ["reset"]

ALL_ACTIONS = (
    INSPECTION_ACTIONS
    + KEYBOARD_ACTIONS
    + POINTER_ACTIONS
    + GAMEPAD_ACTIONS
    + UI_ACTIONS
    + COMPOSITE_ACTIONS
    + LIFECYCLE_ACTIONS
)


@mcp_for_unity_tool(
    group="core",
    description=(
        "Send simulated player input to a RUNNING Unity game (play mode only). "
        "This is how you actually play the game rather than only watch it.\n"
        "\n"
        "Typical loop: manage_editor(action='play') -> manage_input(...) -> "
        "manage_camera(action='screenshot', include_image=true) -> read_console.\n"
        "\n"
        "Actions:\n"
        "- describe: what the input bridge resolved, which virtual devices exist, which keys are "
        "held, and the project's Active Input Handling setting. START HERE when input seems ignored. "
        "Safe to call outside play mode.\n"
        "- key: properties {key|keys, state: down|up|tap, duration_ms}. 'tap' presses and releases.\n"
        "- mouse_move: properties {x, y} for absolute, or {dx, dy} for relative.\n"
        "- mouse_button: properties {button: Left|Right|Middle, state: down|up|tap}.\n"
        "- scroll: properties {y: 1} or {amount: -1}.\n"
        "- gamepad: properties {left_stick:{x,y}, right_stick:{x,y}, left_trigger, right_trigger, "
        "buttons_down:[...], buttons_up:[...]}.\n"
        "- ui_click: target='Canvas/StartButton'. Fires the uGUI Button's onClick directly, so it "
        "works even in projects whose gameplay code uses the legacy Input API.\n"
        "- sequence: properties {steps:[...]} runs several steps in ONE call. Use this for anything "
        "timed — one round trip per keystroke is far too slow to play a game. Step types: wait "
        "({ms}), key, mouse_move, mouse_button, scroll, gamepad, ui_click. Max total 60s.\n"
        "- reset: remove the virtual devices and clear all held keys. Call this if a sequence "
        "failed midway and a key may still be held down.\n"
        "\n"
        "IMPORTANT: injected events are only seen by code written against the Input System package. "
        "Gameplay code using the legacy UnityEngine.Input API will NOT see them - 'describe' reports "
        "this. Movement/aim input in such projects cannot be driven; ui_click still works."
    ),
    annotations=ToolAnnotations(
        title="Manage Input",
        destructiveHint=True,
    ),
)
async def manage_input(
    ctx: Context,
    action: Annotated[str, "The input action to perform."],
    target: Annotated[
        str | None,
        "For ui_click: the GameObject hierarchy path or name of the Button (e.g. 'Canvas/StartButton').",
    ] = None,
    properties: Annotated[
        dict[str, Any] | str | None,
        "Action-specific parameters (dict or JSON string). See the action list in the description.",
    ] = None,
) -> dict[str, Any]:
    """Send simulated player input into a running Unity play mode session."""
    action_normalized = (action or "").lower()

    if action_normalized not in ALL_ACTIONS:
        return {
            "success": False,
            "message": (
                f"Unknown action '{action}'. Available actions — "
                f"inspection: {', '.join(INSPECTION_ACTIONS)}; "
                f"keyboard: {', '.join(KEYBOARD_ACTIONS)}; "
                f"pointer: {', '.join(POINTER_ACTIONS)}; "
                f"gamepad: {', '.join(GAMEPAD_ACTIONS)}; "
                f"ui: {', '.join(UI_ACTIONS)}; "
                f"composite: {', '.join(COMPOSITE_ACTIONS)}; "
                f"lifecycle: {', '.join(LIFECYCLE_ACTIONS)}."
            ),
        }

    unity_instance = await get_unity_instance_from_context(ctx)

    params_dict: dict[str, Any] = {"action": action_normalized}
    if properties is not None:
        params_dict["properties"] = properties
    if target is not None:
        params_dict["target"] = target

    result = await send_with_unity_instance(
        async_send_command_with_retry,
        unity_instance,
        "manage_input",
        params_dict,
    )

    if not isinstance(result, dict):
        return {"success": False, "message": str(result)}
    return result
