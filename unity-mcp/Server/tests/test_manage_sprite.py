"""Tests for manage_sprite tool — Python-side validation only, no Unity connection."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from services.tools.manage_sprite import VALID_ACTIONS


class TestActionList:
    def test_all_six_actions_present(self):
        assert set(VALID_ACTIONS) == {
            "get_info", "slice_sheet", "setup_clips",
            "setup_controller", "full_setup", "add_keyframe_anim",
        }

    def test_no_duplicate_actions(self):
        assert len(VALID_ACTIONS) == len(set(VALID_ACTIONS))


class TestManageSpriteValidation:
    def _run(self, coro):
        return asyncio.run(coro)

    def _ctx(self):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=None)
        return ctx

    def test_unknown_action_returns_error(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(self._ctx(), action="nonexistent"))
        assert result["success"] is False
        assert "Unknown action" in result["message"]

    def test_get_info_requires_path(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(self._ctx(), action="get_info", path=None))
        assert result["success"] is False
        assert "path" in result["message"].lower()

    def test_slice_sheet_requires_path(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(self._ctx(), action="slice_sheet", path=None))
        assert result["success"] is False
        assert "path" in result["message"].lower()

    def test_slice_sheet_requires_cols_or_frame_width(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(
            self._ctx(), action="slice_sheet",
            path="Assets/test.png", cols=None, frame_width=None
        ))
        assert result["success"] is False
        assert "cols" in result["message"].lower() or "frame_width" in result["message"].lower()

    def test_full_setup_requires_path(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(self._ctx(), action="full_setup", path=None))
        assert result["success"] is False
        assert "path" in result["message"].lower()

    def test_full_setup_requires_cols_or_frame_width(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(
            self._ctx(), action="full_setup",
            path="Assets/test.png", cols=None, frame_width=None
        ))
        assert result["success"] is False
        assert "cols" in result["message"].lower() or "frame_width" in result["message"].lower()

    def test_setup_controller_requires_controller_path(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(
            self._ctx(), action="setup_controller",
            controller_path=None
        ))
        assert result["success"] is False
        assert "controller_path" in result["message"].lower()

    def test_add_keyframe_anim_requires_target(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(
            self._ctx(), action="add_keyframe_anim",
            target=None, property="position", keyframes=[{"time": 0, "value": [0, 0, 0]}]
        ))
        assert result["success"] is False
        assert "target" in result["message"].lower()

    def test_add_keyframe_anim_requires_property(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(
            self._ctx(), action="add_keyframe_anim",
            target="MyObject", property=None, keyframes=[{"time": 0, "value": [0, 0, 0]}]
        ))
        assert result["success"] is False
        assert "property" in result["message"].lower()

    def test_add_keyframe_anim_requires_keyframes(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(
            self._ctx(), action="add_keyframe_anim",
            target="MyObject", property="position", keyframes=None
        ))
        assert result["success"] is False
        assert "keyframes" in result["message"].lower()

    def test_setup_clips_requires_path(self):
        from services.tools.manage_sprite import manage_sprite
        result = self._run(manage_sprite(self._ctx(), action="setup_clips", path=None))
        assert result["success"] is False
        assert "path" in result["message"].lower()
