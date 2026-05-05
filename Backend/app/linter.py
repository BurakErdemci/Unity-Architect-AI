import os
import subprocess
import tempfile
import re
from typing import List, Dict, Any

CSC_PATH = "/Library/Frameworks/Mono.framework/Versions/Current/Commands/csc"
UNITY_MANAGED_PATH = "/Applications/Unity/Unity-6000.2.9f1/Unity.app/Contents/Managed"

def lint_csharp(code: str, workspace_path: str, filename: str) -> List[Dict[str, Any]]:
    """
    Local C# linting using csc (Mono) and project DLLs.
    """
    if not os.path.exists(CSC_PATH):
        return [{"line": 1, "column": 1, "message": "C# Compiler (csc) not found at " + CSC_PATH, "severity": "warning"}]

    # 1. Prepare temp file
    with tempfile.NamedTemporaryFile(suffix=".cs", delete=False, mode='w', encoding='utf-8') as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        # 2. Gather references
        refs = []
        
        # Add core Unity DLLs & Standard Assemblies
        # We look in Managed and also in Tools/netcorerun as a fallback for netstandard
        potential_dll_paths = [
            UNITY_MANAGED_PATH,
            os.path.join(UNITY_MANAGED_PATH, "UnityEngine"),
            os.path.join(os.path.dirname(UNITY_MANAGED_PATH), "Tools", "netcorerun"),
            os.path.join(os.path.dirname(UNITY_MANAGED_PATH), "Tools", "Compilation", "Unity.ILPP.Runner")
        ]

        core_dlls = ["UnityEngine.dll", "UnityEditor.dll", "netstandard.dll", "mscorlib.dll", "System.dll", "System.Core.dll"]
        
        found_dlls = set()
        for dll in core_dlls:
            for base_path in potential_dll_paths:
                full_path = os.path.join(base_path, dll)
                if os.path.exists(full_path):
                    refs.append(f"-r:{full_path}")
                    found_dlls.add(dll)
                    break

        # Add project DLLs from Library/ScriptAssemblies
        project_dll_path = os.path.join(workspace_path, "Library", "ScriptAssemblies")
        if os.path.exists(project_dll_path):
            for f in os.listdir(project_dll_path):
                if f.endswith(".dll"):
                    refs.append(f"-r:{os.path.join(project_dll_path, f)}")

        # 3. Build command
        # -target:library (so it doesn't need Main)
        # -noconfig / -nologo (less noise)
        # -refonly (some versions) or just use /out:temp.dll but we don't care about the output
        cmd = [CSC_PATH, "-target:library", "-nologo", "-out:/dev/null"] + refs + [tmp_path]
        
        # 4. Run
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        # 5. Parse output
        # Format: filename.cs(line,col): error CSXXXX: message
        errors = []
        combined_output = stdout + stderr
        
        pattern = re.compile(r'\.cs\((\d+),(\d+)\):\s+(error|warning)\s+CS\d+:\s+(.*)')
        
        for line in combined_output.splitlines():
            match = pattern.search(line)
            if match:
                errors.append({
                    "line": int(match.group(1)),
                    "column": int(match.group(2)),
                    "severity": match.group(3),
                    "message": match.group(4).strip()
                })

        return errors

    except Exception as e:
        print(f"Linter error: {e}")
        return []
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
