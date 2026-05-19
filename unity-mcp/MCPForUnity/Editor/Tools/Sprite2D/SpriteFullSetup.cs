using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.Sprite2D
{
    internal static class SpriteFullSetup
    {
        /// <summary>
        /// params:
        ///   path             - sprite texture path (zorunlu)
        ///   cols             - grid columns (zorunlu — AI vision ile tespit eder)
        ///   rows             - grid rows (default 1)
        ///   frame_width      - alternatif: explicit frame boyutu
        ///   frame_height     - alternatif: explicit frame boyutu
        ///   clips            - [{name, start_frame, end_frame, fps, loop}]
        ///                      belirtilmezse tüm frame'ler tek clip = animation_name
        ///   animation_name   - clips belirtilmemişse kullanılır (default: dosya adı)
        ///   controller_path  - default: sprite ile aynı klasör
        ///   overwrite        - bool (default false)
        ///   add_to_scene     - hedef GameObject'e Animator ekle
        ///   scene_target     - GameObject adı
        /// </summary>
        public static object Run(JObject @params)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            if (!AssetDatabase.AssetPathExists(path))
                return new ErrorResponse($"Sprite not found: '{path}'");

            var diagnostics = new SpriteDiagnosticBuilder();

            // ── Step 1: Slice ──────────────────────────────────────────────────

            var sliceResult = SpriteImportSetup.SliceSheet(@params, diagnostics);
            if (diagnostics.HasErrors)
                return new { success = false, step = "slice_sheet", diagnostics = diagnostics.Build() };

            // ── Step 2: Clips ──────────────────────────────────────────────────

            string outputDir = @params["output_dir"]?.ToString()
                ?? Path.GetDirectoryName(path)?.Replace('\\', '/') ?? "Assets";

            var clipsToken = @params["clips"] as JArray;
            if (clipsToken == null || clipsToken.Count == 0)
            {
                // Tüm frame'ler tek clip
                string animName = @params["animation_name"]?.ToString()
                    ?? Path.GetFileNameWithoutExtension(path);
                int totalFrames = GetSliceCount(path);
                clipsToken = new JArray(new JObject
                {
                    ["name"]        = animName,
                    ["start_frame"] = 0,
                    ["end_frame"]   = totalFrames - 1,
                    ["fps"]         = 12,
                });
            }

            var clipsParams = new JObject
            {
                ["path"]       = path,
                ["clips"]      = clipsToken,
                ["output_dir"] = outputDir,
            };
            var clipResult = SpriteClipBuilder.SetupClips(clipsParams, diagnostics);
            if (diagnostics.HasErrors)
                return new { success = false, step = "setup_clips", diagnostics = diagnostics.Build() };

            // ── Step 3: Controller ─────────────────────────────────────────────

            string controllerPath = @params["controller_path"]?.ToString()
                ?? $"{outputDir}/{Path.GetFileNameWithoutExtension(path)}_Controller.controller";
            bool overwrite = @params["overwrite"]?.ToObject<bool>() ?? false;

            // Clip path'lerini doğrudan clipsToken'dan türet (anonymous object parse'ına gerek yok)
            var clipPaths = SpriteClipBuilder.GetClipPaths(clipsToken, outputDir);
            var createdClips = new JArray();
            foreach (var (cname, cpath) in clipPaths)
                createdClips.Add(new JObject { ["name"] = cname, ["path"] = cpath });

            var ctrlParams = new JObject
            {
                ["clips"]           = createdClips,
                ["controller_path"] = controllerPath,
                ["overwrite"]       = overwrite,
            };
            var ctrlResult = SpriteControllerBuilder.Build(ctrlParams, diagnostics);

            // ErrorResponse dönebilir (örn: "No valid clips loaded") — açık kontrol
            if (ctrlResult is ErrorResponse)
                return new { success = false, step = "setup_controller",
                    error = ((ErrorResponse)ctrlResult).message, diagnostics = diagnostics.Build() };

            // ── Step 4: Add to scene ───────────────────────────────────────────

            bool addToScene  = @params["add_to_scene"]?.ToObject<bool>() ?? false;
            string sceneTarget = @params["scene_target"]?.ToString();

            if (addToScene && !string.IsNullOrEmpty(sceneTarget))
            {
                var go = UnityEngine.GameObject.Find(sceneTarget);
                if (go != null)
                {
                    var controller = AssetDatabase.LoadAssetAtPath<UnityEditor.Animations.AnimatorController>(
                        AssetPathUtility.SanitizeAssetPath(controllerPath));
                    if (controller != null)
                    {
                        var animator = go.GetComponent<UnityEngine.Animator>()
                            ?? go.AddComponent<UnityEngine.Animator>();
                        animator.runtimeAnimatorController = controller;
                        diagnostics.AddInfo("SCENE_ANIMATOR_SET",
                            $"Animator set on '{sceneTarget}'.", new { target = sceneTarget });
                    }
                }
                else
                {
                    diagnostics.AddWarning("SCENE_TARGET_NOT_FOUND",
                        $"GameObject '{sceneTarget}' not found in scene.",
                        null,
                        new[] { "Check GameObject name or open the correct scene first." });
                }
            }

            // ctrlResult'tan complexity ve state_count'u çıkar (anonymous object → JObject üzerinden)
            string complexity = null;
            int stateCount = 0;
            try
            {
                var ctrlJson = JsonConvert.SerializeObject(ctrlResult);
                var ctrlObj  = JObject.Parse(ctrlJson);
                complexity  = ctrlObj["complexity"]?.ToString();
                stateCount  = ctrlObj["state_count"]?.ToObject<int>() ?? 0;
            }
            catch { /* non-critical */ }

            return new
            {
                success               = !diagnostics.HasErrors,
                sprite_path           = path,
                controller_path       = controllerPath,
                controller_complexity = complexity,
                state_count           = stateCount,
                clip_count            = clipPaths.Count,
                diagnostics           = diagnostics.Build(),
            };
        }

        private static int GetSliceCount(string path)
        {
            var sprites = AssetDatabase.LoadAllAssetsAtPath(path);
            int count = 0;
            foreach (var a in sprites)
                if (a is UnityEngine.Sprite) count++;
            return count > 0 ? count : 1;
        }
    }
}
