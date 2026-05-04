"""
Tool Registry — Agentic AI'ın kullanabileceği tüm araçları ve LLM function schemas'ını tutar.
"""
import json
import logging
from typing import Any, Dict, Callable

from tools.file_tools import read_file, write_file, list_directory
from tools.search_tools import search_in_project, find_files

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# TOOL TANIMLARI (LLM'e gönderilecek schema)
# ══════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Unity projesindeki bir dosyayı okur. Dosya yolunu workspace root'a göre ver (örn: Assets/Scripts/Player/PlayerMovement.cs)",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Okunacak dosyanın workspace root'a göre yolu"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "search_in_project",
        "description": "Projede metin/pattern arar. Tüm .cs dosyalarında arama yapar ve eşleşen satırları döndürür.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Aranacak metin veya pattern"
                },
                "file_extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Aranacak dosya uzantıları (varsayılan: .cs). Örnek: [\".cs\", \".shader\"]"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "find_files",
        "description": "Dosya adına göre proje içinde arama yapar. Örnek: 'Player' ile başlayan tüm scriptleri bul.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Dosya adında aranacak pattern (büyük/küçük harf duyarsız)"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "list_directory",
        "description": "Belirtilen klasörün içeriğini listeler. Dosya ve alt klasörleri gösterir.",
        "parameters": {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "Listelenecek klasör yolu (workspace root'a göre). Örnek: Assets/Scripts"
                },
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sadece bu uzantılara sahip dosyaları göster. Boş bırakılırsa hepsini gösterir."
                }
            },
            "required": ["dir_path"]
        }
    },
    {
        "name": "write_file",
        "description": "Unity projesinde bir dosya oluşturur veya günceller. Tam dosya içeriğini yaz.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Yazılacak dosyanın workspace root'a göre yolu"
                },
                "content": {
                    "type": "string",
                    "description": "Dosyaya yazılacak tam içerik"
                }
            },
            "required": ["file_path", "content"]
        }
    },
]


# ══════════════════════════════════════════════
# TOOL ÇALIŞTIRICI
# ══════════════════════════════════════════════

# Tool name → function mapping
_TOOL_FUNCTIONS: Dict[str, Callable] = {
    "read_file": read_file,
    "search_in_project": search_in_project,
    "find_files": find_files,
    "list_directory": list_directory,
    "write_file": write_file,
}

# Hangi tool'lar workspace_path parametresi alıyor
_TOOLS_NEEDING_WORKSPACE = {"read_file", "write_file", "list_directory", "search_in_project", "find_files"}


def execute_tool(tool_name: str, arguments: Dict[str, Any], workspace_path: str) -> Dict[str, Any]:
    """Verilen tool'u güvenli şekilde çalıştırır."""
    func = _TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return {"success": False, "error": f"Bilinmeyen araç: {tool_name}"}

    try:
        # workspace_path parametresini otomatik ekle
        if tool_name in _TOOLS_NEEDING_WORKSPACE:
            arguments["workspace_path"] = workspace_path

        # Dosya yollarını absolute path'e çevir
        if "file_path" in arguments and not arguments["file_path"].startswith("/"):
            arguments["file_path"] = f"{workspace_path}/{arguments['file_path']}"
        if "dir_path" in arguments and not arguments["dir_path"].startswith("/"):
            arguments["dir_path"] = f"{workspace_path}/{arguments['dir_path']}"

        result = func(**arguments)
        logger.info(f"  🔧 Tool [{tool_name}] çalıştırıldı: success={result.get('success', '?')}")
        return result
    except Exception as e:
        logger.error(f"  🔧 Tool [{tool_name}] HATA: {e}")
        return {"success": False, "error": str(e)}


def get_gemini_tool_declarations() -> list:
    """Gemini API formatında tool declarations döndürür."""
    return [
        {
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                }
                for t in TOOL_DEFINITIONS
            ]
        }
    ]


def get_openai_tool_declarations() -> list:
    """OpenAI/Anthropic function calling formatında tool declarations döndürür."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
        }
        for t in TOOL_DEFINITIONS
    ]
