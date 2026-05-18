using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.FBX
{
    internal static class FBXImportSetup
    {
        // ── GetInfo ──────────────────────────────────────────────────────────

        public static object GetInfo(JObject @params)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            if (importer == null)
                return new ErrorResponse($"No ModelImporter found at '{path}'. Is it an FBX?");

            var clipInfos = importer.clipAnimations.Select(c => new
            {
                name        = c.name,
                start_frame = (int)c.firstFrame,
                end_frame   = (int)c.lastFrame,
                loop        = c.loopTime,
            }).ToArray();

            var allAssets        = AssetDatabase.LoadAllAssetsAtPath(path);
            int embeddedTextures = allAssets.OfType<Texture2D>().Count();
            int embeddedMaterials= allAssets.OfType<Material>().Count();
            var avatar           = allAssets.OfType<Avatar>().FirstOrDefault();

            return new
            {
                success            = true,
                path,
                rig_type           = importer.animationType.ToString(),
                avatar_setup       = importer.avatarSetup.ToString(),
                source_avatar      = importer.sourceAvatar != null
                                         ? AssetDatabase.GetAssetPath(importer.sourceAvatar)
                                         : null,
                scale_factor       = importer.globalScale,
                import_animation   = importer.importAnimation,
                clip_count         = clipInfos.Length,
                clips              = clipInfos,
                embedded_textures  = embeddedTextures,
                embedded_materials = embeddedMaterials,
                avatar_valid       = avatar != null && avatar.isValid,
                avatar_humanoid    = avatar != null && avatar.isHuman,
            };
        }

        // ── ConfigureRig ─────────────────────────────────────────────────────

        public static object ConfigureRig(JObject @params)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            if (importer == null)
                return new ErrorResponse($"No ModelImporter found at '{path}'.");

            string rigTypeStr  = @params["rigType"]?.ToString() ?? "Humanoid";
            string avatarSetup = @params["avatarSetup"]?.ToString() ?? "create";

            importer.animationType = rigTypeStr == "Generic"
                ? ModelImporterAnimationType.Generic
                : ModelImporterAnimationType.Human;

            if (avatarSetup == "copy")
            {
                string sourceAvatarPath = @params["sourceAvatar"]?.ToString();
                if (string.IsNullOrEmpty(sourceAvatarPath))
                    return new ErrorResponse("'sourceAvatar' is required when avatarSetup='copy'.");

                var allSourceAssets = AssetDatabase.LoadAllAssetsAtPath(
                    AssetPathUtility.SanitizeAssetPath(sourceAvatarPath));
                var sourceAvatar = allSourceAssets.OfType<Avatar>().FirstOrDefault();
                if (sourceAvatar == null)
                    return new ErrorResponse(
                        $"No Avatar sub-asset found at '{sourceAvatarPath}'. " +
                        "Run configure_rig with avatarSetup='create' on the character first.");

                importer.avatarSetup  = ModelImporterAvatarSetup.CopyFromOther;
                importer.sourceAvatar = sourceAvatar;
            }
            else
            {
                importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            }

            importer.SaveAndReimport();

            var diagnostics = new FBXDiagnosticBuilder();

            var allAssets   = AssetDatabase.LoadAllAssetsAtPath(path);
            var avatar      = allAssets.OfType<Avatar>().FirstOrDefault();
            bool humanoidOk = avatar != null && avatar.isHuman && avatar.isValid;

            if (importer.animationType == ModelImporterAnimationType.Human && !humanoidOk)
            {
                var missingBones = new List<string>();
                if (avatar != null)
                {
                    var mappedHumanNames = new HashSet<string>(
                        avatar.humanDescription.human.Select(b => b.humanName));
                    missingBones = Enumerable.Range(0, HumanTrait.BoneCount)
                        .Where(i => HumanTrait.RequiredBone(i) && !mappedHumanNames.Contains(HumanTrait.BoneName[i]))
                        .Select(i => HumanTrait.BoneName[i])
                        .ToList();
                }

                diagnostics.AddError(
                    "AVATAR_BONE_MISMATCH",
                    "Humanoid avatar oluşturulamadı — bazı kemikler eşlenemedi.",
                    new { missing_bones = missingBones.ToArray() },
                    new[]
                    {
                        "FBX'i 3D yazılımında aç, kemikleri Unity'nin beklediği adlarla yeniden adlandır (Hips, Spine, LeftUpperArm vb.)",
                        "Generic rig kullan — retargeting çalışmaz ama animasyon oynar",
                        "Unity Avatar Configuration window'da manuel kemik haritalaması yap (Inspector → Rig → Configure)",
                    }
                );
            }

            int embeddedTextures = allAssets.OfType<Texture2D>().Count();
            if (embeddedTextures > 0)
            {
                diagnostics.AddWarning(
                    "EMBEDDED_TEXTURES",
                    $"FBX içinde {embeddedTextures} gömülü texture var — karakter pembe görünebilir.",
                    new { texture_count = embeddedTextures },
                    new[] { "Inspector → Materials sekmesi → Extract Textures butonuna tıkla" }
                );
            }

            return new
            {
                success         = !diagnostics.HasErrors,
                path,
                rig_type        = importer.animationType.ToString(),
                avatar_valid    = humanoidOk,
                avatar_humanoid = humanoidOk,
                diagnostics     = diagnostics.Build(),
            };
        }

        // ── SetupClips ───────────────────────────────────────────────────────

        public static object SetupClips(JObject @params)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            if (importer == null)
                return new ErrorResponse($"No ModelImporter found at '{path}'.");

            var clipsToken = @params["clips"] as JArray;
            if (clipsToken == null || clipsToken.Count == 0)
                return new ErrorResponse("'clips' array is required and must not be empty.");

            var newClips = new List<ModelImporterClipAnimation>();
            foreach (JObject clipDef in clipsToken)
            {
                string name = clipDef["name"]?.ToString();
                if (string.IsNullOrEmpty(name))
                    return new ErrorResponse("Each clip must have a 'name'.");

                var clip = new ModelImporterClipAnimation
                {
                    name       = name,
                    firstFrame = clipDef["start_frame"]?.ToObject<float>() ?? 0f,
                    lastFrame  = clipDef["end_frame"]?.ToObject<float>() ?? 60f,
                };

                bool? loopOverride = clipDef["loop"]?.ToObject<bool?>();
                clip.loopTime = loopOverride ?? AutoDetectLoop(name);
                newClips.Add(clip);
            }

            importer.clipAnimations = newClips.ToArray();
            importer.SaveAndReimport();

            return new
            {
                success    = true,
                path,
                clip_count = newClips.Count,
                clips      = newClips.Select(c => new
                {
                    name        = c.name,
                    start_frame = (int)c.firstFrame,
                    end_frame   = (int)c.lastFrame,
                    loop        = c.loopTime,
                }).ToArray(),
            };
        }

        // ── Helpers ──────────────────────────────────────────────────────────

        internal static bool AutoDetectLoop(string clipName)
        {
            string lower = clipName.ToLowerInvariant();
            if (lower.StartsWith("idle") || lower.StartsWith("walk") ||
                lower.StartsWith("run")  || lower.StartsWith("sprint"))
                return true;
            return false;
        }

        internal static Avatar GetAvatarFromFBX(string fbxPath)
        {
            return AssetDatabase.LoadAllAssetsAtPath(fbxPath)
                .OfType<Avatar>()
                .FirstOrDefault();
        }
    }
}
