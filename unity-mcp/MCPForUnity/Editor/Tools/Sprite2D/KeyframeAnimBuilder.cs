using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.Sprite2D
{
    internal static class KeyframeAnimBuilder
    {
        /// <summary>
        /// params:
        ///   target          - GameObject adı veya "path/in/hierarchy"
        ///   clip_name       - AnimationClip adı (dosya adı olarak da kullanılır)
        ///   output_dir      - .anim ve .controller kayıt dizini
        ///   property        - "position", "rotation", "scale", "alpha", "color"
        ///   keyframes       - [{time: float, value: [x,y,z] veya float, easing: "linear"|"ease_in"|"ease_out"|"ease_in_out"}]
        ///   loop            - bool (default false)
        ///   duration        - toplam süre (son keyframe'den alınır eğer belirtilmezse)
        /// </summary>
        public static object AddKeyframeAnim(JObject @params, SpriteDiagnosticBuilder diagnostics)
        {
            string targetName = @params["target"]?.ToString();
            if (string.IsNullOrEmpty(targetName))
                return new ErrorResponse("'target' is required (GameObject name or hierarchy path).");

            var go = FindGameObject(targetName);
            if (go == null)
                return new ErrorResponse($"GameObject '{targetName}' not found in scene.");

            string clipName  = @params["clip_name"]?.ToString() ?? "NewAnimation";
            string outputDir = @params["output_dir"]?.ToString() ?? "Assets/Animations";
            string property  = @params["property"]?.ToString()  ?? "position";
            bool loop        = @params["loop"]?.ToObject<bool>() ?? false;

            outputDir = AssetPathUtility.SanitizeAssetPath(outputDir) ?? outputDir;
            if (!AssetDatabase.IsValidFolder(outputDir))
                CreateFolders(outputDir);

            var keyframesToken = @params["keyframes"] as JArray;
            if (keyframesToken == null || keyframesToken.Count == 0)
                return new ErrorResponse("'keyframes' array is required.");

            var clip = new AnimationClip { name = clipName };

            // Property'ye göre curve oluştur
            bool ok = BuildCurves(clip, property, keyframesToken, go, diagnostics);
            if (!ok) return new { success = false, diagnostics = diagnostics.Build() };

            var settings = AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime = loop;
            AnimationUtility.SetAnimationClipSettings(clip, settings);

            string clipPath = $"{outputDir}/{clipName}.anim";
            if (AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath) != null)
                AssetDatabase.DeleteAsset(clipPath);
            AssetDatabase.CreateAsset(clip, clipPath);

            // Animator controller oluştur / güncelle
            string controllerPath = $"{outputDir}/{go.name}_Controller.controller";
            AnimatorController controller;
            if (AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath) != null)
                controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            else
                controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);

            // State ekle
            var sm    = controller.layers[0].stateMachine;
            var state = sm.AddState(clipName);
            state.motion = clip;
            if (sm.defaultState == null) sm.defaultState = state;

            // Animator component ekle (yoksa)
            var animator = go.GetComponent<Animator>();
            if (animator == null) animator = go.AddComponent<Animator>();
            animator.runtimeAnimatorController = controller;

            AssetDatabase.SaveAssets();

            return new
            {
                success         = true,
                target          = targetName,
                clip_path       = clipPath,
                controller_path = controllerPath,
                property,
                keyframe_count  = keyframesToken.Count,
                loop,
                diagnostics     = diagnostics.Build(),
            };
        }

        // ── Helpers ──────────────────────────────────────────────────────────

        private static bool BuildCurves(
            AnimationClip clip,
            string property,
            JArray keyframesToken,
            GameObject go,
            SpriteDiagnosticBuilder diagnostics)
        {
            switch (property.ToLowerInvariant())
            {
                case "position":
                    return BuildVector3Curves(clip, "", typeof(Transform),
                        "localPosition.x", "localPosition.y", "localPosition.z",
                        keyframesToken);

                case "rotation":
                    return BuildVector3Curves(clip, "", typeof(Transform),
                        "localEulerAnglesRaw.x", "localEulerAnglesRaw.y", "localEulerAnglesRaw.z",
                        keyframesToken);

                case "scale":
                    return BuildVector3Curves(clip, "", typeof(Transform),
                        "localScale.x", "localScale.y", "localScale.z",
                        keyframesToken);

                case "alpha":
                    // CanvasGroup varsa kullan; yoksa ekle (UI Image varsa Image.color.a tercih edilir)
                    if (go.GetComponent<UnityEngine.UI.Image>() != null && go.GetComponent<CanvasGroup>() == null)
                        return BuildFloatCurve(clip, "", typeof(UnityEngine.UI.Image), "m_Color.a", keyframesToken);
                    if (go.GetComponent<CanvasGroup>() == null) go.AddComponent<CanvasGroup>();
                    return BuildFloatCurve(clip, "", typeof(CanvasGroup), "m_Alpha", keyframesToken);

                case "color":
                    return BuildVector3Curves(clip, "", DetectColorComponent(go),
                        "m_Color.r", "m_Color.g", "m_Color.b",
                        keyframesToken);

                default:
                    diagnostics.AddError(
                        "PROPERTY_NOT_FOUND",
                        $"Unknown property '{property}'. Valid: position, rotation, scale, alpha, color.",
                        null,
                        new[] { "Use one of: position, rotation, scale, alpha, color" }
                    );
                    return false;
            }
        }

        private static bool BuildVector3Curves(
            AnimationClip clip, string path, Type componentType,
            string propX, string propY, string propZ,
            JArray keyframesToken)
        {
            var kx = new List<Keyframe>();
            var ky = new List<Keyframe>();
            var kz = new List<Keyframe>();

            foreach (JObject kf in keyframesToken)
            {
                float t      = kf["time"]?.ToObject<float>() ?? 0f;
                var valToken = kf["value"];
                float x = 0, y = 0, z = 0;
                if (valToken is JArray arr && arr.Count >= 3)
                { x = arr[0].ToObject<float>(); y = arr[1].ToObject<float>(); z = arr[2].ToObject<float>(); }
                else if (valToken != null)
                { x = y = z = valToken.ToObject<float>(); }

                string easing = kf["easing"]?.ToString() ?? "linear";
                float tin = 0, tout = 0;
                if (easing == "ease_in")          { tin = 0; tout = float.PositiveInfinity; }
                else if (easing == "ease_out")    { tin = float.PositiveInfinity; tout = 0; }
                else if (easing == "ease_in_out") { tin = float.PositiveInfinity; tout = float.PositiveInfinity; }

                kx.Add(new Keyframe(t, x, tin, tout));
                ky.Add(new Keyframe(t, y, tin, tout));
                kz.Add(new Keyframe(t, z, tin, tout));
            }

            clip.SetCurve(path, componentType, propX, new AnimationCurve(kx.ToArray()));
            clip.SetCurve(path, componentType, propY, new AnimationCurve(ky.ToArray()));
            clip.SetCurve(path, componentType, propZ, new AnimationCurve(kz.ToArray()));
            return true;
        }

        private static bool BuildFloatCurve(
            AnimationClip clip, string path, Type componentType,
            string prop, JArray keyframesToken)
        {
            var keys = new List<Keyframe>();
            foreach (JObject kf in keyframesToken)
            {
                float t = kf["time"]?.ToObject<float>()  ?? 0f;
                float v = kf["value"]?.ToObject<float>() ?? 0f;
                keys.Add(new Keyframe(t, v));
            }
            clip.SetCurve(path, componentType, prop, new AnimationCurve(keys.ToArray()));
            return true;
        }

        private static Type DetectColorComponent(GameObject go)
        {
            if (go.GetComponent<SpriteRenderer>() != null) return typeof(SpriteRenderer);
            if (go.GetComponent<UnityEngine.UI.Image>() != null) return typeof(UnityEngine.UI.Image);
            return typeof(SpriteRenderer); // fallback
        }

        private static GameObject FindGameObject(string name)
        {
            // Önce tam hiyerarşi path dene, sonra ada göre bul.
            // Doğrudan FindObjectsByType değil — sürüm uyumu shim üzerinden (CS0618).
            var all = MCPForUnity.Runtime.Helpers.UnityFindObjectsCompat.FindAll<GameObject>(true);
            foreach (var go in all)
            {
                if (GetHierarchyPath(go) == name || go.name == name)
                    return go;
            }
            return null;
        }

        private static string GetHierarchyPath(GameObject go)
        {
            string path = go.name;
            var t = go.transform.parent;
            while (t != null) { path = t.name + "/" + path; t = t.parent; }
            return path;
        }

        private static void CreateFolders(string path)
        {
            string parent = Path.GetDirectoryName(path)?.Replace('\\', '/') ?? "Assets";
            if (!AssetDatabase.IsValidFolder(parent))
                CreateFolders(parent);
            string folderName = Path.GetFileName(path);
            if (!string.IsNullOrEmpty(folderName))
                AssetDatabase.CreateFolder(parent, folderName);
        }
    }
}
