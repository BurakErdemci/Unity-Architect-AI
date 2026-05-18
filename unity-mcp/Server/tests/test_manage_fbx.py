"""Tests for manage_fbx tool — Python-side validation only, no Unity connection."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from services.tools.manage_fbx import ALL_ACTIONS, VALID_ACTIONS


class TestActionLists:
    def test_all_actions_is_complete(self):
        assert set(ALL_ACTIONS) == set(VALID_ACTIONS)

    def test_no_duplicate_actions(self):
        assert len(ALL_ACTIONS) == len(set(ALL_ACTIONS))

    def test_expected_actions_present(self):
        assert {"get_info", "configure_rig", "setup_clips", "full_setup"}.issubset(set(ALL_ACTIONS))


class TestManageFBXValidation:
    def _run(self, coro):
        return asyncio.run(coro)

    def _ctx(self):
        ctx = MagicMock()
        ctx.get_state = AsyncMock(return_value=None)
        return ctx

    def test_unknown_action_returns_error(self):
        from services.tools.manage_fbx import manage_fbx
        result = self._run(manage_fbx(self._ctx(), action="nonexistent"))
        assert result["success"] is False
        assert "Unknown action" in result["message"]

    def test_missing_path_on_get_info_returns_error(self):
        from services.tools.manage_fbx import manage_fbx
        result = self._run(manage_fbx(self._ctx(), action="get_info", path=None))
        assert result["success"] is False
        assert "path" in result["message"].lower()

    def test_configure_rig_requires_path(self):
        from services.tools.manage_fbx import manage_fbx
        result = self._run(manage_fbx(self._ctx(), action="configure_rig", path=None))
        assert result["success"] is False

    def test_full_setup_requires_character_fbx(self):
        from services.tools.manage_fbx import manage_fbx
        result = self._run(manage_fbx(self._ctx(), action="full_setup", path=None))
        assert result["success"] is False
        assert "character_fbx" in result["message"].lower()
