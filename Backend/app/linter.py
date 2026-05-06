import os
import subprocess
import tempfile
import re
import platform
import glob
from typing import List, Dict, Any

def get_unity_paths(workspace_path: str = None):
    os_name = platform.system()
    
    # 1. Try to find version from project if workspace is provided
    target_version = None
    if workspace_path:
        version_file = os.path.join(workspace_path, "ProjectSettings", "ProjectVersion.txt")
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r') as f:
                    content = f.read()
                    # Look for line: m_EditorVersion: 6000.0.30f1
                    match = re.search(r'm_EditorVersion:\s*(.*)', content)
                    if match:
                        target_version = match.group(1).strip()
            except: pass

    # 2. Common install roots
    search_roots = []
    if os_name == "Darwin": # macOS
        search_roots = ["/Applications/Unity/Hub/Editor", "/Applications/Unity"]
    elif os_name == "Windows":
        search_roots = [r"C:\Program Files\Unity\Hub\Editor", r"C:\Program Files\Unity"]

    # 3. Search for the specific version or best match
    base_unity = None
    
    # Try specific version folder first
    if target_version:
        for root in search_roots:
            ver_path = os.path.join(root, target_version)
            if os_name == "Darwin":
                ver_path = os.path.join(ver_path, "Unity.app/Contents")
            else:
                ver_path = os.path.join(ver_path, "Editor/Data")
                
            if os.path.exists(ver_path):
                base_unity = ver_path
                break

    # If not found or no version, fallback to generic search
    if not base_unity:
        # Check current hardcoded fallback for development
        dev_fallback = "/Applications/Unity/Unity-6000.2.9f1/Unity.app/Contents" if os_name == "Darwin" else None
        if dev_fallback and os.path.exists(dev_fallback):
            base_unity = dev_fallback
        else:
            # Deep search in roots
            for root in search_roots:
                # Look for any folder that contains Unity.app or Editor/Data
                pattern = os.path.join(root, "*")
                for folder in glob.glob(pattern):
                    potential = os.path.join(folder, "Unity.app/Contents") if os_name == "Darwin" else os.path.join(folder, "Editor", "Data")
                    if os.path.exists(potential):
                        base_unity = potential
                        break
                if base_unity: break

    # 4. Final Paths
    if base_unity:
        return {
            "csc": os.path.join(base_unity, "MonoBleedingEdge", "bin", "csc" + (".exe" if os_name == "Windows" else "")),
            "managed": os.path.join(base_unity, "Managed"),
            "fallback_csc": "csc.exe" if os_name == "Windows" else "/Library/Frameworks/Mono.framework/Versions/Current/Commands/csc"
        }
            
    return { "csc": "csc", "managed": "", "fallback_csc": "csc" }

def lint_csharp(code: str, workspace_path: str, filename: str, full_project: bool = False) -> List[Dict[str, Any]]:
    """
    Local C# linting using csc (Mono).
    If full_project is True, it scans ALL .cs files in the workspace.
    """
    paths = get_unity_paths(workspace_path)
    csc_path = paths["csc"] if os.path.exists(paths["csc"]) else paths["fallback_csc"]
    
    if not os.path.exists(csc_path):
        return [{"line": 1, "column": 1, "message": "C# Compiler (csc) not found.", "severity": "warning"}]

    unity_managed_path = paths["managed"]

    # 1. Prepare files to compile
    sources = []
    tmp_path = None
    
    if full_project:
        # Full scan: Get all .cs files in Assets
        assets_path = os.path.join(workspace_path, "Assets")
        for root, dirs, files in os.walk(assets_path):
            # Skip hidden and non-CS
            for f in files:
                if f.endswith(".cs") and not f.startswith("."):
                    sources.append(os.path.join(root, f))
    else:
        # Single file mode: Use a temp file for the current code to support unsaved changes
        with tempfile.NamedTemporaryFile(suffix=".cs", delete=False, mode='w', encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name
        sources.append(tmp_path)

    try:
        # 2. Gather references
        refs = []
        # ... (Referans toplama mantığı aynı kalıyor, ancak projenin kendi DLL'ini (Assembly-CSharp) tam projede EKLEMIYORUZ)
        
        netcorerun_path = os.path.join(os.path.dirname(unity_managed_path), "Tools", "netcorerun")
        shims_path = os.path.join(os.path.dirname(unity_managed_path), "NetStandard", "compat", "2.1.0", "shims", "netstandard")
        
        potential_dll_paths = [
            unity_managed_path,
            os.path.join(unity_managed_path, "UnityEngine"),
            netcorerun_path,
            shims_path,
        ]

        is_modular = os.path.exists(os.path.join(unity_managed_path, "UnityEngine"))
        core_dlls = ["UnityEditor.dll", "netstandard.dll", "mscorlib.dll", "System.Runtime.dll", "System.dll", "System.Core.dll", "System.Private.CoreLib.dll"]
        
        found_refs = set()
        for dll in core_dlls:
            for base_path in potential_dll_paths:
                full_dll = os.path.join(base_path, dll)
                if os.path.exists(full_dll):
                    refs.append(f"-r:{full_dll}")
                    found_refs.add(dll)
                    break

        unity_modules_path = os.path.join(unity_managed_path, "UnityEngine")
        if os.path.exists(unity_modules_path):
            for f in os.listdir(unity_modules_path):
                if f.endswith(".dll") and f not in found_refs and f != "UnityEngine.dll":
                    refs.append(f"-r:{os.path.join(unity_modules_path, f)}")
                    found_refs.add(f)

        # Correct Facade
        modular_facade = os.path.join(unity_modules_path, "UnityEngine.dll")
        if os.path.exists(modular_facade):
            refs.append(f"-r:{modular_facade}")
        elif is_modular:
            main_facade = os.path.join(unity_managed_path, "UnityEngine.dll")
            if os.path.exists(main_facade):
                refs.append(f"-r:{main_facade}")

        # Shims
        if os.path.exists(shims_path):
            for f in os.listdir(shims_path):
                if f.endswith(".dll") and f not in found_refs:
                    refs.append(f"-r:{os.path.join(shims_path, f)}")
                    found_refs.add(f)

        # Project DLLs: Only add if NOT in full_project mode to avoid conflicts
        project_dll_path = os.path.join(workspace_path, "Library", "ScriptAssemblies")
        if os.path.exists(project_dll_path):
            for f in os.listdir(project_dll_path):
                if f.endswith(".dll") and f not in found_refs:
                    # full_project modunda kendi kodumuzun DLL'ini hariç tutmalıyız (çakışma olmaması için)
                    if full_project and f in ["Assembly-CSharp.dll", "Assembly-CSharp-Editor.dll"]:
                        continue
                    refs.append(f"-r:{os.path.join(project_dll_path, f)}")
                    found_refs.add(f)

        # Plugins (Always needed)
        # full_project modunda Assets içindeki kodlar zaten kaynak olarak eklendiği için
        # buradaki DLL'leri eklemek "Ambiguous call" (çakışma) yaratabilir.
        if not full_project:
            assets_plugins_path = os.path.join(workspace_path, "Assets", "Plugins")
            if os.path.exists(assets_plugins_path):
                for root, dirs, files in os.walk(assets_plugins_path):
                    for f in files:
                        if f.endswith(".dll") and f not in found_refs:
                            refs.append(f"-r:{os.path.join(root, f)}")
                            found_refs.add(f)

        # 3. Compile
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as out_tmp:
            out_tmp_path = out_tmp.name
            
        # Mac fix: Use mono directly if csc is a broken script
        mono_path = csc_path.replace("/bin/csc", "/bin/mono")
        csc_exe = csc_path.replace("/bin/csc", "/lib/mono/msbuild/Current/bin/Roslyn/csc.exe")
        
        if os.name == 'posix' and os.path.exists(mono_path) and os.path.exists(csc_exe):
            cmd = [mono_path, csc_exe, "-target:library", "-noconfig", "-nologo", f"-out:{out_tmp_path}"] + refs + sources
        else:
            cmd = [csc_path, "-target:library", "-noconfig", "-nologo", f"-out:{out_tmp_path}"] + refs + sources
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        
        if os.path.exists(out_tmp_path): os.remove(out_tmp_path)

        # 4. Parse
        errors = []
        combined_output = stdout + stderr
        # Pattern to match filename.cs(line,col) or just (line,col)
        pattern = re.compile(r'(?:.*[\\/])?([^\\/]+\.cs)\((\d+),(\d+)\):\s+(error|warning)\s+CS\d+:\s+(.*)')
        
        for line in combined_output.splitlines():
            match = pattern.search(line)
            if match:
                # Get the full line to extract the path correctly if possible
                # The regex (?:.*[\\/])? matches the directory part
                full_match = re.search(r'^(.*?)\.cs\(', line)
                if full_match:
                    file_found = full_match.group(1) + ".cs"
                else:
                    file_found = match.group(1)

                # If we used a temp file, replace it with the real filename
                if tmp_path and file_found in tmp_path:
                    file_found = filename

                errors.append({
                    "file": os.path.relpath(file_found, workspace_path) if os.path.isabs(file_found) else file_found,
                    "line": int(match.group(2)),
                    "column": int(match.group(3)),
                    "severity": match.group(4).strip(),
                    "message": match.group(5).strip()
                })
        
        return errors

    except Exception as e:
        print(f"Linter error: {e}")
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
