import os
import sys
from pathlib import Path

import pytest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../app")))

from tools.file_tools import _validate_path
from unity_ai_mcp.tools.file_tools import _resolve


def test_backend_file_tool_rejects_sibling_workspace_prefix(tmp_path: Path):
    workspace = tmp_path / "Game"
    sibling = tmp_path / "Game_backup"
    workspace.mkdir()
    sibling.mkdir()

    with pytest.raises(PermissionError):
        _validate_path(str(sibling / "Assets" / "Scripts" / "Exploit.cs"), str(workspace))


def test_mcp_file_tool_rejects_sibling_workspace_prefix(tmp_path: Path):
    workspace = tmp_path / "Game"
    sibling = tmp_path / "Game_backup"
    workspace.mkdir()
    sibling.mkdir()

    with pytest.raises(PermissionError):
        _resolve(str(sibling / "Assets" / "Scripts" / "Exploit.cs"), str(workspace))


def test_mcp_file_tool_rejects_relative_traversal_to_sibling(tmp_path: Path):
    workspace = tmp_path / "Game"
    sibling = tmp_path / "Game_backup"
    workspace.mkdir()
    sibling.mkdir()

    with pytest.raises(PermissionError):
        _resolve("../Game_backup/Assets/Scripts/Exploit.cs", str(workspace))
