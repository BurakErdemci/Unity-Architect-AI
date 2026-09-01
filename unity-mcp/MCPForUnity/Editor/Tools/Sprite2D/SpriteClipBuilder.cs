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
        /// Builds AnimationClips out of sliced sprites and saves them as .anim assets.
        /// params:
        ///   path         - sprite texture asset path
        ///   clips        - [{name, start_frame, end_frame, fps (opt, def=12), loop (opt)}]
        ///   output_dir   - where the clips are written (default: the sprite's own folder)
        ///   overwrite    - bool (default false); an existing clip is kept unless this is true
        /// </summary>
        public static object SetupClips(JObject @params, SpriteDiagnosticBuilder diagnostics)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            if (path == null)
                return new ErrorResponse("'path' must stay under Assets/ and cannot contain '..'.");

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

            // A refused path comes back null; falling back to the raw value would hand
            // traversal sequences straight through.
            outputDir = AssetPathUtility.SanitizeAssetPath(outputDir);
            if (outputDir == null)
                return new ErrorResponse("'output_dir' must stay under Assets/ and cannot contain '..'.");
            if (!AssetDatabase.IsValidFolder(outputDir))
                CreateFolders(outputDir);

            bool overwrite = @params["overwrite"]?.ToObject<bool>() ?? false;

            var createdClips = new List<object>();

            foreach (JToken clipToken in clipsToken)
            {
                // Measured: a non-object clips entry threw InvalidCastException on a typed cast.
                if (!(clipToken is JObject clipDef))
                {
                    diagnostics.AddWarning("CLIP_NOT_AN_OBJECT", "A clips entry is not an object - skipped.", null, new[] { "Each clip must be an object with a 'name'." });
                    continue;
                }

                string clipName = clipDef["name"]?.ToString();
                if (string.IsNullOrEmpty(clipName))
                { diagnostics.AddWarning("CLIP_NO_NAME", "Clip name is missing — skipped.", null, new[] { "Add a 'name' field to each clip definition." }); continue; }

                // Measured: "nested/walk" either threw from CreateAsset or, where the folder
                // existed, wrote the clip outside output_dir.
                if (clipName.Contains("/") || clipName.Contains("\\"))
                {
                    diagnostics.AddWarning("CLIP_BAD_NAME", $"Clip '{clipName}': the name cannot contain a path separator - skipped.", null, new[] { "Remove '..' and path separators from the clip name." });
                    continue;
                }

                // Sequential, not chained with ||: a short-circuited call leaves its out
                // parameter unassigned and the second value is used below.
                int endFrame = allSprites.Length - 1;
                bool rangeOk = SpriteParams.TryReadWholeNumber(clipDef, "start_frame", 0, out int startFrame, out string frameError);
                if (rangeOk) rangeOk = SpriteParams.TryReadWholeNumber(clipDef, "end_frame", allSprites.Length - 1, out endFrame, out frameError);
                if (!rangeOk)
                {
                    diagnostics.AddWarning("CLIP_BAD_RANGE", $"Clip '{clipName}': {frameError} - skipped.", null, new[] { "start_frame and end_frame must be whole numbers within a sprite index." });
                    continue;
                }
                if (endFrame > allSprites.Length - 1)
                {
                    // Skip/Take clamps silently: an end_frame past the last sprite produced a
                    // shorter clip and reported success.
                    diagnostics.AddWarning("CLIP_BAD_RANGE", $"Clip '{clipName}': end_frame {endFrame} is past the last sprite index {allSprites.Length - 1} - skipped.", null, new[] { $"This sheet has {allSprites.Length} sprites, so end_frame must be at most {allSprites.Length - 1}." });
                    continue;
                }
                if (startFrame < 0 || endFrame < startFrame)
                {
                    // Skip yields everything for a negative count: start_frame=-2 with
                    // end_frame=3 wrote frames 0..5 as a success. Named here rather than left
                    // to CLIP_EMPTY, which says the result was empty, not which input was wrong.
                    diagnostics.AddWarning("CLIP_BAD_RANGE", $"Clip '{clipName}': frame range [{startFrame},{endFrame}] is invalid - skipped.", null, new[] { "start_frame must be 0 or more, and end_frame must not be below start_frame." });
                    continue;
                }
                // `fps <= 0f` is false for NaN, so a NaN rate wrote a clip of NaN keyframe
                // times and reported success.
                if (!SpriteParams.TryReadFiniteFloat(clipDef, "fps", 12f, out float fps, out string fpsError))
                {
                    diagnostics.AddWarning("CLIP_BAD_FPS", $"Clip '{clipName}': {fpsError} - skipped.", null, new[] { "Leave fps out to use the default of 12." });
                    continue;
                }
                if (fps <= 0f)
                {
                    // Times are i / fps, so a non-positive rate puts every key at infinity.
                    diagnostics.AddWarning("CLIP_BAD_FPS", $"Clip '{clipName}': fps must be greater than 0, got {fps} - skipped.", null, new[] { "Leave fps out to use the default of 12." });
                    continue;
                }

                var entry      = SpriteNamingDetector.Detect(clipName);
                if (!SpriteParams.TryReadBool(clipDef, "loop", entry.Loop, out bool loop, out string loopError))
                {
                    diagnostics.AddWarning("CLIP_BAD_LOOP", $"Clip '{clipName}': {loopError} - skipped.", null, new[] { "Leave loop out to let the clip name decide." });
                    continue;
                }

                var frameSprites = allSprites.Skip(startFrame).Take(endFrame - startFrame + 1).ToArray();
                if (frameSprites.Length == 0)
                {
                    diagnostics.AddWarning("CLIP_EMPTY", $"Clip '{clipName}': no frames in range [{startFrame},{endFrame}].", null, new[] { "Check start_frame/end_frame against total sprite count." });
                    continue;
                }

                if (frameSprites.Length <= 2)
                    diagnostics.AddWarning("LOW_FRAME_COUNT", $"Clip '{clipName}' has only {frameSprites.Length} frame(s) — animation may not be visible.", null, new string[0]);

                // Refusals come before the allocation: a `new AnimationClip` that never becomes
                // an asset leaks. The delete stays next to CreateAsset for the same reason.
                string clipPath = AssetPathUtility.SanitizeAssetPath($"{outputDir}/{clipName}.anim");
                if (clipPath == null)
                {
                    diagnostics.AddWarning("CLIP_BAD_NAME", $"Clip '{clipName}': the name cannot be used as a file name - skipped.", null, new[] { "Remove '..' and path separators from the clip name." });
                    continue;
                }

                var existing = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
                if (existing != null && !overwrite)
                {
                    // Measured: an unrelated clip at this path was replaced by a request carrying
                    // no overwrite field. Same policy as the controller builder: destruction
                    // needs authorisation.
                    diagnostics.AddWarning("CLIP_EXISTS", $"Clip '{clipName}': an animation clip already exists at '{clipPath}' - skipped.", new { path = clipPath }, new[] { "Set overwrite=true to replace it.", "Choose a different clip name or output_dir." });
                    continue;
                }

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

        // Plain string sort puts hero_10 before hero_2, which reorders the animation.
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
                    // Left-pad the run of digits so a lexicographic sort compares them numerically.
                    sb.Append(name.Substring(start, i - start).PadLeft(10, '0'));
                }
                else
                {
                    sb.Append(name[i++]);
                }
            }
            return sb.ToString();
        }

        /// <summary>Creates an asset folder and any missing parents above it.</summary>
        internal static void CreateFolders(string path)
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
