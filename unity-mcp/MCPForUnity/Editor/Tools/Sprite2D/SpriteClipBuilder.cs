using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.Sprite2D
{
    internal static class SpriteClipBuilder
    {
        /// <summary>
        /// Slice edilmiş sprite'lardan AnimationClip'ler oluşturur ve .anim olarak kaydeder.
        /// params:
        ///   path         - sprite texture asset path
        ///   clips        - [{name, start_frame, end_frame, fps (opt, def=12), loop (opt)}]
        ///   output_dir   - clip'lerin kaydedileceği dizin (default: sprite'la aynı)
        /// </summary>
        public static object SetupClips(JObject @params, SpriteDiagnosticBuilder diagnostics)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);

            var allSprites = AssetDatabase.LoadAllAssetsAtPath(path)
                .OfType<Sprite>()
                .OrderBy(s => NaturalSortKey(s.name))
                .ToArray();

            if (allSprites.Length == 0)
                return new ErrorResponse($"No sprites found at '{path}'. Run slice_sheet first.");

            var clipsToken = @params["clips"] as JArray;
            if (clipsToken == null || clipsToken.Count == 0)
                return new ErrorResponse("'clips' array is required.");

            string outputDir = @params["output_dir"]?.ToString()
                ?? Path.GetDirectoryName(path)?.Replace('\\', '/') ?? "Assets";

            outputDir = AssetPathUtility.SanitizeAssetPath(outputDir) ?? outputDir;
            if (!AssetDatabase.IsValidFolder(outputDir))
                CreateFolders(outputDir);

            var createdClips = new List<object>();

            foreach (JObject clipDef in clipsToken)
            {
                string clipName = clipDef["name"]?.ToString();
                if (string.IsNullOrEmpty(clipName))
                { diagnostics.AddWarning("CLIP_NO_NAME", "Clip name is missing — skipped.", null, new[] { "Add a 'name' field to each clip definition." }); continue; }

                int startFrame = clipDef["start_frame"]?.ToObject<int>() ?? 0;
                int endFrame   = clipDef["end_frame"]?.ToObject<int>()   ?? allSprites.Length - 1;
                float fps      = clipDef["fps"]?.ToObject<float>()       ?? 12f;

                var entry      = SpriteNamingDetector.Detect(clipName);
                bool loop      = clipDef["loop"]?.ToObject<bool?>() ?? entry.Loop;

                var frameSprites = allSprites.Skip(startFrame).Take(endFrame - startFrame + 1).ToArray();
                if (frameSprites.Length == 0)
                {
                    diagnostics.AddWarning("CLIP_EMPTY", $"Clip '{clipName}': no frames in range [{startFrame},{endFrame}].", null, new[] { "Check start_frame/end_frame against total sprite count." });
                    continue;
                }

                if (frameSprites.Length <= 2)
                    diagnostics.AddWarning("LOW_FRAME_COUNT", $"Clip '{clipName}' has only {frameSprites.Length} frame(s) — animation may not be visible.", null, new string[0]);

                var clip = new AnimationClip { frameRate = fps };

                var binding = new EditorCurveBinding
                {
                    type         = typeof(SpriteRenderer),
                    path         = "",
                    propertyName = "m_Sprite",
                };

                var keyframes = new ObjectReferenceKeyframe[frameSprites.Length];
                for (int i = 0; i < frameSprites.Length; i++)
                {
                    keyframes[i] = new ObjectReferenceKeyframe
                    {
                        time  = i / fps,
                        value = frameSprites[i],
                    };
                }

                AnimationUtility.SetObjectReferenceCurve(clip, binding, keyframes);

                var settings = AnimationUtility.GetAnimationClipSettings(clip);
                settings.loopTime = loop;
                AnimationUtility.SetAnimationClipSettings(clip, settings);

                string clipPath = $"{outputDir}/{clipName}.anim";
                var existing = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
                if (existing != null) AssetDatabase.DeleteAsset(clipPath);

                AssetDatabase.CreateAsset(clip, clipPath);

                createdClips.Add(new
                {
                    name        = clipName,
                    path        = clipPath,
                    frame_count = frameSprites.Length,
                    fps,
                    loop,
                    duration    = frameSprites.Length / fps,
                });
            }

            AssetDatabase.SaveAssets();

            return new
            {
                success     = true,
                sprite_path = path,
                clip_count  = createdClips.Count,
                clips       = createdClips,
                diagnostics = diagnostics.Build(),
            };
        }

        // ── Internal helper ──────────────────────────────────────────────────

        /// <summary>
        /// full_setup için: clip name → asset path listesi döner.
        /// </summary>
        internal static List<(string name, string path)> GetClipPaths(JArray clipsToken, string outputDir)
        {
            var result = new List<(string, string)>();
            foreach (JObject cd in clipsToken)
            {
                string name = cd["name"]?.ToString();
                if (!string.IsNullOrEmpty(name))
                    result.Add((name, $"{outputDir}/{name}.anim"));
            }
            return result;
        }

        internal static AnimationClip LoadClip(string clipPath) =>
            AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);

        // hero_1, hero_2, ..., hero_10 sıralaması için numeric suffix sort
        private static string NaturalSortKey(string name)
        {
            var sb = new System.Text.StringBuilder();
            int i = 0;
            while (i < name.Length)
            {
                if (char.IsDigit(name[i]))
                {
                    int start = i;
                    while (i < name.Length && char.IsDigit(name[i])) i++;
                    // Sayıyı 10 hane ile sola sıfırla → lexicographic sort numerically correct
                    sb.Append(name.Substring(start, i - start).PadLeft(10, '0'));
                }
                else
                {
                    sb.Append(name[i++]);
                }
            }
            return sb.ToString();
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
