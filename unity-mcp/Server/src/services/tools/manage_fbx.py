"""
FBX character & animation integration tool.
Automates: humanoid rig setup, retargeting, AnimatorController construction.
"""
from typing import Annotated, Any, Literal

from fastmcp import Context
from mcp.types import ToolAnnotations

from services.registry import mcp_for_unity_tool
from services.tools import get_unity_instance_from_context
from transport.unity_transport import send_with_unity_instance
from transport.legacy.unity_connection import async_send_command_with_retry

VALID_ACTIONS = [
    "get_info",
    "configure_rig",
    "setup_clips",
    "full_setup",
]

ALL_ACTIONS = VALID_ACTIONS  # single flat list — no prefix groups needed


@mcp_for_unity_tool(
    group="animation",
    description=(
        "FBX character and animation integration. "
        "get_info: read current import settings. "
        "configure_rig: set Humanoid/Generic rig and avatar. "
        "setup_clips: configure clip names, frames, and loop. "
        "full_setup: one command — configure character, retarget animations, build AnimatorController "
        "with smart naming detection (walkforward, walkleft, runright, jump, attack…)."
    ),
    annotations=ToolAnnotations(
        title="Manage FBX",
        destructiveHint=True,
    ),
)
async def manage_fbx(
    ctx: Context,
    action: Annotated[
        Literal["get_info", "configure_rig", "setup_clips", "full_setup"],
        "Action to perform.",
    ],
    path: Annotated[
        str | None,
        "FBX asset path (e.g. 'Assets/Characters/Hero.fbx'). Required for get_info, configure_rig, setup_clips.",
    ] = None,
    rig_type: Annotated[
        Literal["Humanoid", "Generic"] | None,
        "Rig type for configure_rig. Default: Humanoid.",
    ] = None,
    avatar_setup: Annotated[
        Literal["create", "copy"] | None,
        "create = new avatar from this model, copy = copy from source_avatar.",
    ] = None,
    source_avatar: Annotated[
        str | None,
        "Asset path to source Avatar (.fbx) for avatar_setup='copy'.",
    ] = None,
    clips: Annotated[
        list[dict[str, Any]] | None,
        "Clip configs for setup_clips: [{name, start_frame, end_frame, loop}]. loop defaults to auto-detect.",
    ] = None,
    character_fbx: Annotated[
        str | None,
        "Character FBX path for full_setup (e.g. 'Assets/Characters/Hero.fbx').",
    ] = None,
    animation_fbxs: Annotated[
        list[str] | None,
        "Animation FBX paths for full_setup.",
    ] = None,
    controller_path: Annotated[
        str | None,
        "Where to create the .controller asset (e.g. 'Assets/Animators/Hero.controller').",
    ] = None,
    overwrite_controller: Annotated[bool, "Overwrite controller if it already exists."] = False,
    add_to_scene: Annotated[bool, "Attach Animator + controller to a scene GameObject."] = False,
    scene_target: Annotated[
        str | None,
        "Existing GameObject name to attach to. Creates new if None.",
    ] = None,
) -> dict[str, Any]:
    """FBX character and animation integration tool."""

    action_lower = action.lower() if action else ""

    if action_lower not in VALID_ACTIONS:
        return {
            "success": False,
            "message": f"Unknown action '{action}'. Valid: {', '.join(VALID_ACTIONS)}",
        }

    # Python-side validation (avoids unnecessary Unity round-trips)
    if action_lower in ("get_info", "configure_rig", "setup_clips") and not path:
        return {"success": False, "message": f"'path' is required for action '{action}'."}

    if action_lower == "full_setup" and not character_fbx:
        return {"success": False, "message": "'character_fbx' is required for full_setup."}

    unity_instance = await get_unity_instance_from_context(ctx)

    params: dict[str, Any] = {"action": action_lower}

    if path is not None:
        params["path"] = path
    if rig_type is not None:
        params["rigType"] = rig_type
    if avatar_setup is not None:
        params["avatarSetup"] = avatar_setup
    if source_avatar is not None:
        params["sourceAvatar"] = source_avatar
    if clips is not None:
        params["clips"] = clips
    if character_fbx is not None:
        params["characterFbx"] = character_fbx
    if animation_fbxs is not None:
        params["animationFbxs"] = animation_fbxs
    if controller_path is not None:
        params["controllerPath"] = controller_path
    if overwrite_controller:
        params["overwriteController"] = True
    if add_to_scene:
        params["addToScene"] = True
    if scene_target is not None:
        params["sceneTarget"] = scene_target

    result = await send_with_unity_instance(
        async_send_command_with_retry,
        unity_instance,
        "manage_fbx",
        params,
    )
    return result if isinstance(result, dict) else {"success": False, "message": str(result)}
