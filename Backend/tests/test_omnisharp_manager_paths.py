import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from omnisharp.omnisharp_manager import _path_to_uri, _uri_to_path, _lsp_diag_to_problem


def test_uri_roundtrip_windows():
    p = "C:\\Unity Projeler\\TPS Shooter Game\\Assets\\Player.cs"
    uri = _path_to_uri(p)
    assert uri.startswith("file:///")
    assert _uri_to_path(uri).replace("/", "\\") == p


def test_diag_conversion_one_based():
    d = {"range": {"start": {"line": 4, "character": 2}, "end": {"line": 4, "character": 9}},
         "message": "x", "severity": 1}
    prob = _lsp_diag_to_problem("Assets/Player.cs", d)
    assert prob == {"file": "Assets/Player.cs", "line": 5, "column": 3,
                    "endColumn": 10, "message": "x", "severity": "error"}
