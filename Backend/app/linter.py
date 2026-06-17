import os
import subprocess
import tempfile
import re
import platform
import glob
import json
from typing import List, Dict, Any

def get_editors_from_hub() -> List[tuple]:
    """
    Parses Unity Hub configuration files to auto-detect all registered Unity editor installations.
    This provides generic, zero-config editor path resolution across different users' machines.
    """
    os_name = platform.system()
    hub_paths = []
    
    if os_name == "Darwin": # macOS
        hub_paths = [os.path.expanduser("~/Library/Application Support/UnityHub")]
    elif os_name == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            hub_paths = [os.path.join(appdata, "UnityHub")]
    else: # Linux
        hub_paths = [os.path.expanduser("~/.config/UnityHub")]
        
    discovered_editors = []
    for hub_path in hub_paths:
        for json_file in ["editors-v2.json", "editors.json"]:
            full_json_path = os.path.join(hub_path, json_file)
            if os.path.exists(full_json_path):
                try:
                    with open(full_json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # editors-v2.json format: {"data": [{"version": "6000.2.9f1", "location": ["/Applications/Unity/..."]}]}
                        editors_list = data.get("data", []) if isinstance(data, dict) else data
                        if isinstance(editors_list, list):
                            for item in editors_list:
                                if isinstance(item, dict):
                                    locs = item.get("location", [])
                                    version = item.get("version")
                                    if isinstance(locs, list):
                                        for loc in locs:
                                            discovered_editors.append((version, loc))
                                    elif isinstance(locs, str):
                                        discovered_editors.append((version, locs))
                except Exception as e:
                    print(f"[UNITYHUB_PARSER_ERROR] Failed parsing {json_file}: {e}", flush=True)
                    
    return discovered_editors

def resolve_base_unity(loc: str) -> str:
    """
    Normalizes different installation path configurations (e.g. pointing directly to the app or binary)
    to a standard 'base_unity' path containing the internal compiler/dependency files.
    """
    os_name = platform.system()
    if os_name == "Darwin":
        if loc.endswith(".app"):
            return os.path.join(loc, "Contents")
        elif "Unity.app" in loc:
            parts = loc.split("Unity.app")
            return os.path.join(parts[0], "Unity.app", "Contents")
    elif os_name == "Windows":
        if loc.endswith("Unity.exe"):
            editor_dir = os.path.dirname(loc)
            return os.path.join(editor_dir, "Data")
        elif "Editor" in loc:
            parts = loc.split("Editor")
            return os.path.join(parts[0], "Editor", "Data")
    return loc

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

    # 2. Common install roots to search in case they are not in Unity Hub config
    search_roots = []
    if os_name == "Darwin": # macOS
        search_roots = [
            "/Applications/Unity/Hub/Editor", 
            "/Applications/Unity",
            os.path.expanduser("~/Applications/Unity/Hub/Editor"),
            os.path.expanduser("~/Applications/Unity")
        ]
    elif os_name == "Windows":
        search_roots = [
            r"C:\Program Files\Unity\Hub\Editor", 
            r"C:\Program Files\Unity",
            r"D:\Program Files\Unity\Hub\Editor",
            r"D:\Unity\Hub\Editor",
            r"E:\Unity\Hub\Editor",
            r"C:\Unity\Hub\Editor"
        ]

    # 3. Discover registered installations from Unity Hub config
    discovered = get_editors_from_hub()
    base_unity = None
    
    # Priority A: Find exact matching version from Hub
    if target_version:
        for ver, loc in discovered:
            if ver == target_version:
                resolved = resolve_base_unity(loc)
                if os.path.exists(resolved):
                    base_unity = resolved
                    break

    # Priority B: Search in common roots for the exact target version
    if not base_unity and target_version:
        for root in search_roots:
            ver_path = os.path.join(root, target_version)
            if os_name == "Darwin":
                ver_path = os.path.join(ver_path, "Unity.app/Contents")
            else:
                ver_path = os.path.join(ver_path, "Editor/Data")
                
            if os.path.exists(ver_path):
                base_unity = ver_path
                break

    # Priority C: Find any Hub editor matching the major version (e.g. Unity 6 series '6000')
    if not base_unity and target_version:
        major = target_version.split('.')[0] if '.' in target_version else target_version
        for ver, loc in discovered:
            if ver and ver.startswith(major):
                resolved = resolve_base_unity(loc)
                if os.path.exists(resolved):
                    base_unity = resolved
                    break

    # Priority D: Fall back to the highest version available in Hub
    if not base_unity and discovered:
        try:
            discovered.sort(key=lambda x: x[0] or "", reverse=True)
        except: pass
        for ver, loc in discovered:
            resolved = resolve_base_unity(loc)
            if os.path.exists(resolved):
                base_unity = resolved
                break

    # Priority E: Generic deep search in roots
    if not base_unity:
        for root in search_roots:
            pattern = os.path.join(root, "*")
            for folder in glob.glob(pattern):
                potential = os.path.join(folder, "Unity.app/Contents") if os_name == "Darwin" else os.path.join(folder, "Editor", "Data")
                if os.path.exists(potential):
                    base_unity = potential
                    break
            if base_unity: break

    # 4. Final Paths
    if base_unity:
        # Check if we are in Unity 6 layout (nested under Resources/Scripting)
        unity6_mono = os.path.join(base_unity, "Resources", "Scripting", "MonoBleedingEdge")
        unity6_managed = os.path.join(base_unity, "Resources", "Scripting", "Managed")
        
        if os.path.exists(unity6_mono) and os.path.exists(unity6_managed):
            mbe_path = unity6_mono
            managed_path = unity6_managed
        else:
            mbe_path = os.path.join(base_unity, "MonoBleedingEdge")
            managed_path = os.path.join(base_unity, "Managed")
            
        # csc konumu Unity sürümüne göre değişir. Windows'ta MonoBleedingEdge/bin/csc.exe
        # genelde YOK; gerçek Roslyn derleyicisi lib/mono/.../Roslyn altında. Adayları
        # sırayla dene, ilk var olanı kullan. (Mac: lint_csharp'ın posix dalı bin/csc'yi
        # Roslyn'e yönlendirdiği için orada eski davranışı koru.)
        if os_name == "Windows":
            csc_candidates = [
                os.path.join(mbe_path, "bin", "Roslyn", "csc.exe"),
                os.path.join(mbe_path, "lib", "mono", "msbuild", "Current", "bin", "Roslyn", "csc.exe"),
                os.path.join(mbe_path, "bin", "csc.exe"),
                os.path.join(base_unity, "Tools", "Roslyn", "csc.exe"),
                os.path.join(mbe_path, "lib", "mono", "4.5", "csc.exe"),
            ]
            csc = next((c for c in csc_candidates if os.path.exists(c)),
                       os.path.join(mbe_path, "bin", "csc.exe"))
        else:
            csc = os.path.join(mbe_path, "bin", "csc")

        return {
            "csc": csc,
            "managed": managed_path,
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

        # asmdef-bound dirs are packages Unity compiles to separate DLLs in Library/ScriptAssemblies.
        # Compiling their source AND linking their DLL produces CS0436 type conflicts → treat them as precompiled.
        asmdef_dirs = []
        for root, dirs, files in os.walk(assets_path):
            if any(f.endswith(".asmdef") for f in files):
                asmdef_dirs.append(root)

        for root, dirs, files in os.walk(assets_path):
            if any(root == d or root.startswith(d + os.sep) for d in asmdef_dirs):
                continue
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
        
        scripting_path = os.path.dirname(unity_managed_path)
        netcorerun_path = os.path.join(scripting_path, "netcorerun")
        if not os.path.exists(netcorerun_path):
            netcorerun_path = os.path.join(scripting_path, "Tools", "netcorerun")
            
        shims_path = os.path.join(scripting_path, "NetStandard", "compat", "2.1.0", "shims", "netstandard")
        
        potential_dll_paths = [
            os.path.join(unity_managed_path, "UnityEngine"),
            unity_managed_path,
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
                    # full_project'te tüm Assembly-CSharp* (main, Editor, firstpass, firstpass-Editor) hariç —
                    # bunların source'unu zaten derliyoruz, hem source hem DLL referans olunca CS0436/CS0121 üretir.
                    if full_project and f.startswith("Assembly-CSharp"):
                        continue
                    refs.append(f"-r:{os.path.join(project_dll_path, f)}")
                    found_refs.add(f)

        # Plugins: precompiled 3rd party DLLs (DOTween core, etc.) — always needed.
        # Source under Plugins (e.g. DOTween Modules) is part of Assembly-CSharp source and
        # references types from these DLLs, so skipping them breaks full_project lint.
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
            
        # Mac fix: Use mono directly if csc is a broken script (only if csc is in a standard /bin/csc folder)
        mono_path = csc_path.replace("/bin/csc", "/bin/mono")
        csc_exe = csc_path.replace("/bin/csc", "/lib/mono/msbuild/Current/bin/Roslyn/csc.exe")

        # Windows fix: Unity'nin MonoBleedingEdge altındaki Roslyn csc.exe bir Mono
        # assembly'sidir; doğrudan çalıştırılınca "System.Text.Encoding.CodePages
        # yüklenemedi" verir. mono.exe ile çalıştırmak gerekir (Mac'teki mantığın eşi).
        win_mono = ""
        if os.name == "nt":
            _i = csc_path.find("MonoBleedingEdge")
            if _i != -1:
                _cand = os.path.join(csc_path[:_i + len("MonoBleedingEdge")], "bin", "mono.exe")
                if os.path.exists(_cand):
                    win_mono = _cand

        # Derleyiciyi çalıştıran komut öneki (mono gerekiyorsa mono + csc.exe)
        if win_mono:
            runner = [win_mono, csc_path]
        elif os.name == 'posix' and "/bin/csc" in csc_path and os.path.exists(mono_path) and os.path.exists(csc_exe):
            runner = [mono_path, csc_exe]
        else:
            runner = [csc_path]

        compile_args = ["-target:library", "-noconfig", "-nologo", "-langversion:preview", f"-out:{out_tmp_path}"] + refs + sources

        # Windows: full_project'te yüzlerce -r: referansı komut satırı uzunluk sınırını
        # aşar (WinError 206). csc'nin response dosyası desteğiyle (@file.rsp) çöz.
        rsp_path = None
        if os.name == "nt":
            def _q(a: str) -> str:
                if a.startswith("-r:"):   return '-r:"' + a[3:] + '"'
                if a.startswith("-out:"): return '-out:"' + a[5:] + '"'
                if a.startswith("-"):     return a
                return '"' + a + '"'
            with tempfile.NamedTemporaryFile(suffix=".rsp", delete=False, mode="w", encoding="utf-8") as rsp:
                rsp.write("\n".join(_q(a) for a in compile_args))
                rsp_path = rsp.name
            cmd = runner + ["@" + rsp_path]
        else:
            cmd = runner + compile_args

        print(f"[LINTER_CMD] Executing C# compiler command: {' '.join(cmd)} (args: {len(compile_args)})", flush=True)

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if os.path.exists(out_tmp_path): os.remove(out_tmp_path)
        if rsp_path and os.path.exists(rsp_path): os.remove(rsp_path)

        # 4. Parse
        errors = []
        combined_output = stdout + stderr
        if combined_output.strip():
            print(f"[LINTER_RAW_OUTPUT] Compiler output:\n{combined_output.strip()}", flush=True)
        # Pattern to match filename.cs(line,col) or just (line,col)
        pattern = re.compile(r'(?:.*[\\/])?([^\\/]+\.cs)\((\d+),(\d+)\):\s+(error|warning)\s+CS\d+:\s+(.*)')
        
        for line in combined_output.splitlines():
            match = pattern.search(line)
            if match:
                msg = match.group(5).strip()

                # Filter linter-setup noise — these aren't user code issues:
                # CS0436: source type X conflicts with imported type X (single-file mode references
                #         Assembly-CSharp.dll which contains the same type; harmless here)
                # CS0731: type forwarder cycle (Mono runtime mscorlib vs .NET Standard shim mismatch
                #         — a csc setup quirk, has nothing to do with user code)
                if "conflicts with the imported type" in msg:
                    continue
                if "type forwarder" in msg and "causes a cycle" in msg:
                    continue

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
                col = int(match.group(3))
                # CSC hata mesajından identifier uzunluğunu çıkar (örn: 'Rigidbody2D' → 11)
                id_match = re.search(r"'([^']+)'", msg)
                end_col = col + len(id_match.group(1)) if id_match else col + 1

                errors.append({
                    "file": os.path.relpath(file_found, workspace_path) if os.path.isabs(file_found) else file_found,
                    "line": int(match.group(2)),
                    "column": col,
                    "endColumn": end_col,
                    "severity": match.group(4).strip(),
                    "message": msg
                })
        
        return errors

    except Exception as e:
        print(f"Linter error: {e}")
        return []
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
