"""
Unity Proje Arama Araçları — Projede pattern arama (grep benzeri).
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def search_in_project(query: str, workspace_path: str, file_extensions: list = None,
                       case_insensitive: bool = True, max_results: int = 30) -> dict:
    """
    Workspace içinde tüm dosyalarda metin arar.
    Her eşleşme için dosya adı, satır numarası ve satır içeriği döndürür.
    """
    if not file_extensions:
        file_extensions = [".cs", ".shader", ".compute", ".hlsl", ".json", ".xml", ".yaml", ".txt"]

    try:
        workspace = Path(workspace_path).resolve()
        if not workspace.exists():
            return {"success": False, "error": f"Workspace bulunamadı: {workspace_path}"}

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            pattern = re.compile(re.escape(query), flags)
        except re.error:
            pattern = re.compile(query, flags)

        results = []
        files_searched = 0

        for root, dirs, files in os.walk(str(workspace)):
            # Unity'nin gereksiz klasörlerini atla
            dirs[:] = [d for d in dirs if d not in (
                "Library", "Temp", "Logs", "obj", "Build",
                ".git", "node_modules", "__pycache__", ".vs"
            )]

            for fname in files:
                if not any(fname.endswith(ext) for ext in file_extensions):
                    continue

                fpath = os.path.join(root, fname)
                files_searched += 1

                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                rel_path = os.path.relpath(fpath, str(workspace))
                                results.append({
                                    "file": rel_path,
                                    "line": line_num,
                                    "content": line.rstrip()[:200],  # Max 200 karakter
                                })
                                if len(results) >= max_results:
                                    return {
                                        "success": True,
                                        "query": query,
                                        "results": results,
                                        "total_matches": len(results),
                                        "files_searched": files_searched,
                                        "truncated": True,
                                    }
                except (PermissionError, UnicodeDecodeError):
                    continue

        return {
            "success": True,
            "query": query,
            "results": results,
            "total_matches": len(results),
            "files_searched": files_searched,
            "truncated": False,
        }
    except Exception as e:
        return {"success": False, "error": f"Arama hatası: {str(e)}"}


def find_files(pattern: str, workspace_path: str, extensions: list = None) -> dict:
    """Dosya adına göre arama yapar (glob benzeri)."""
    try:
        workspace = Path(workspace_path).resolve()
        if not extensions:
            extensions = [".cs", ".shader"]

        matches = []
        search_pattern = pattern.lower()

        for root, dirs, files in os.walk(str(workspace)):
            dirs[:] = [d for d in dirs if d not in (
                "Library", "Temp", "Logs", "obj", "Build", ".git", "__pycache__"
            )]
            for fname in files:
                if not any(fname.endswith(ext) for ext in extensions):
                    continue
                if search_pattern in fname.lower():
                    rel_path = os.path.relpath(os.path.join(root, fname), str(workspace))
                    matches.append(rel_path)
                    if len(matches) >= 50:
                        break

        return {"success": True, "pattern": pattern, "matches": matches, "count": len(matches)}
    except Exception as e:
        return {"success": False, "error": f"Dosya arama hatası: {str(e)}"}
