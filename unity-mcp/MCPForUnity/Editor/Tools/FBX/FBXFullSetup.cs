using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json;

namespace MCPForUnity.Editor.Tools.FBX
{
    internal static class FBXFullSetup
    {
        public static object Run(JObject @params)
        {
            string characterFbx = @params["characterFbx"]?.ToString();
            if (string.IsNullOrEmpty(characterFbx))
                return new ErrorResponse("'characterFbx' is required.");

            characterFbx = AssetPathUtility.SanitizeAssetPath(characterFbx);
            if (!AssetDatabase.AssetPathExists(characterFbx))
                return new ErrorResponse($"Character FBX not found: '{characterFbx}'");

            var animPaths = new List<string>();
            var animToken = @params["animationFbxs"] as JArray;
            if (animToken != null)
            {
                foreach (var t in animToken)
                {
                    string p = AssetPathUtility.SanitizeAssetPath(t?.ToString() ?? "");
                    if (!string.IsNullOrEmpty(p)) animPaths.Add(p);
                }
            }

            string controllerPath    = @params["controllerPath"]?.ToString() ?? DefaultControllerPath(characterFbx);
            bool overwriteController = @params["overwriteController"]?.ToObject<bool>() ?? false;
            bool addToScene          = @params["addToScene"]?.ToObject<bool>() ?? false;
            string sceneTarget       = @params["sceneTarget"]?.ToString();

            var diagnostics = new FBXDiagnosticBuilder();

            // ── Step 1: Configure character rig ──────────────────────────────

            var rigParams = new JObject
            {
                ["path"]        = characterFbx,
                ["rigType"]     = "Humanoid",
                ["avatarSetup"] = "create",
            };
            var rigResult = FBXImportSetup.ConfigureRig(rigParams);
            if (rigResult is ErrorResponse)
                return rigResult;

            // Bug fix: ConfigureRig diagnostics'lerini (AVATAR_BONE_MISMATCH vb.) propagate et
            MergeDiagnostics(rigResult, diagnostics);

            var charAvatar  = FBXImportSetup.GetAvatarFromFBX(characterFbx);
            bool charHumanoidOk = charAvatar != null && charAvatar.isHuman && charAvatar.isValid;

            var charAssets = AssetDatabase.LoadAllAssetsAtPath(characterFbx);
            int embTex = charAssets.OfType<Texture2D>().Count();
            if (embTex > 0)
            {
                diagnostics.AddWarning(
                    "EMBEDDED_TEXTURES",
                    $"Karakter FBX'inde {embTex} gömülü texture — karakter pembe görünebilir.",
                    new { texture_count = embTex, fbx = characterFbx },
                    new[] { "Inspector → Materials → Extract Textures" }
                );
            }

            // ── Step 2: Configure animation FBXs ─────────────────────────────

            var entries     = new List<AnimationEntry>();
            var animResults = new List<object>();

            foreach (var animPath in animPaths)
            {
                if (!AssetDatabase.AssetPathExists(animPath))
                {
                    diagnostics.AddError(
                        "FBX_NOT_FOUND",
                        $"Animasyon FBX bulunamadı: '{animPath}'",
                        new { path = animPath },
                        new[] { "Dosyanın Assets klasörü içinde olduğunu kontrol et" }
                    );
                    continue;
                }

                var entry = FBXNamingDetector.Detect(animPath);
                entries.Add(entry);

                var charImporter = AssetImporter.GetAtPath(characterFbx) as ModelImporter;
                var animImporter = AssetImporter.GetAtPath(animPath) as ModelImporter;
                if (charImporter != null && animImporter != null)
                {
                    float charScale = charImporter.globalScale;
                    float animScale = animImporter.globalScale;
                    if (Math.Abs(charScale - animScale) > 0.01f)
                    {
                        diagnostics.AddWarning(
                            "ANIMATION_SCALE_MISMATCH",
                            $"'{Path.GetFileName(animPath)}' scale ({animScale}) karakter scale'inden ({charScale}) farklı.",
                            new { char_scale = charScale, anim_scale = animScale, anim_fbx = animPath },
                            new[]
                            {
                                "Animasyon FBX'ini 3D yazılımında aç, scale'i apply et ve karakter ile aynı değere export et",
                                "Her iki FBX'i de aynı scale ayarıyla Unity'ye import et",
                            }
                        );
                    }
                }

                var animRigParams = new JObject
                {
                    ["path"]        = animPath,
                    ["rigType"]     = "Humanoid",
                    ["avatarSetup"] = charHumanoidOk ? "copy" : "create",
                    ["sourceAvatar"]= characterFbx,
                };
                FBXImportSetup.ConfigureRig(animRigParams);

                // Bug fix: gerçek frame aralığını FBX'ten oku (default 0→60 truncation'ı önler)
                float firstFrame = 0f, lastFrame = 60f;
                var animImporter = AssetImporter.GetAtPath(animPath) as ModelImporter;
                if (animImporter != null)
                {
                    var defaults = animImporter.defaultClipAnimations;
                    var customs  = animImporter.clipAnimations;
                    var source   = (customs != null && customs.Length > 0) ? customs : defaults;
                    if (source != null && source.Length > 0)
                    {
                        firstFrame = source[0].firstFrame;
                        lastFrame  = source[0].lastFrame;
                    }
                }

                var clipDefs = new JArray
                {
                    new JObject
                    {
                        ["name"]        = entry.ClipName,
                        ["loop"]        = entry.Loop,
                        ["start_frame"] = (int)firstFrame,
                        ["end_frame"]   = (int)lastFrame,
                    }
                };
                FBXImportSetup.SetupClips(new JObject { ["path"] = animPath, ["clips"] = clipDefs });

                animResults.Add(new
                {
                    path     = animPath,
                    clip     = entry.ClipName,
                    category = entry.Category.ToString(),
                    loop     = entry.Loop,
                });
            }

            // ── Step 3: Build AnimatorController ─────────────────────────────

            string builtControllerPath = null;
            if (entries.Count > 0)
            {
                var controllerResult = FBXControllerBuilder.Build(entries, controllerPath, overwriteController, diagnostics);

                if (diagnostics.HasErrors)
                {
                    return new
                    {
                        success     = false,
                        character   = new { path = characterFbx, humanoid_ok = charHumanoidOk },
                        animations  = animResults.ToArray(),
                        diagnostics = diagnostics.Build(),
                    };
                }

                builtControllerPath = controllerResult as string;
            }

            // ── Step 4: Add to scene ──────────────────────────────────────────

            string placedGameObject = null;
            if (addToScene && !string.IsNullOrEmpty(builtControllerPath))
                placedGameObject = PlaceInScene(characterFbx, builtControllerPath, sceneTarget);

            return new
            {
                success      = true,
                character    = new { path = characterFbx, humanoid_ok = charHumanoidOk },
                animations   = animResults.ToArray(),
                controller   = builtControllerPath,
                scene_object = placedGameObject,
                diagnostics  = diagnostics.Build(),
            };
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        private static void MergeDiagnostics(object result, FBXDiagnosticBuilder target)
        {
            try
            {
                var json  = JsonConvert.SerializeObject(result);
                var obj   = JObject.Parse(json);
                var diags = obj["diagnostics"] as JArray;
                if (diags == null) return;
                foreach (JObject d in diags)
                {
                    string code = d["code"]?.ToString()     ?? "";
                    string msg  = d["message"]?.ToString()  ?? "";
                    string sev  = d["severity"]?.ToString() ?? "info";
                    var fixes   = (d["fix_options"] as JArray)
                        ?.Select(f => f.ToString()).ToArray() ?? new string[0];
                    if (sev == "error")        target.AddError(code, msg, null, fixes);
                    else if (sev == "warning") target.AddWarning(code, msg, null, fixes);
                    else                       target.AddInfo(code, msg, null);
                }
            }
            catch { /* non-critical — diagnostics kaybedilse de flow durmamalı */ }
        }

        private static string DefaultControllerPath(string characterFbxPath)
        {
            string dir  = Path.GetDirectoryName(characterFbxPath)?.Replace('\\', '/') ?? "Assets";
            string name = Path.GetFileNameWithoutExtension(characterFbxPath);
            return $"{dir}/{name}Controller.controller";
        }

        private static string PlaceInScene(string characterFbxPath, string controllerPath, string sceneTarget)
        {
            var controller = AssetDatabase.LoadAssetAtPath<UnityEditor.Animations.AnimatorController>(controllerPath);
            if (controller == null) return null;

            GameObject go;
            if (!string.IsNullOrEmpty(sceneTarget))
            {
                go = GameObject.Find(sceneTarget);
                if (go == null) go = new GameObject(sceneTarget);
            }
            else
            {
                go = new GameObject(Path.GetFileNameWithoutExtension(characterFbxPath));
            }

            var animator = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
            animator.runtimeAnimatorController = controller;
            return go.name;
        }
    }
}
