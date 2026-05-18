using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.FBX
{
    internal static class FBXControllerBuilder
    {
        public static object Build(
            IList<AnimationEntry> entries,
            string controllerPath,
            bool overwrite,
            FBXDiagnosticBuilder diagnostics)
        {
            controllerPath = AssetPathUtility.SanitizeAssetPath(controllerPath);
            if (string.IsNullOrEmpty(controllerPath))
                return new ErrorResponse("'controllerPath' must be a valid asset path ending in .controller");

            if (!controllerPath.EndsWith(".controller", StringComparison.OrdinalIgnoreCase))
                controllerPath += ".controller";

            if (AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath) != null)
            {
                if (!overwrite)
                {
                    diagnostics.AddError(
                        "CONTROLLER_EXISTS",
                        $"Controller already exists at '{controllerPath}'.",
                        new { path = controllerPath },
                        new[] { "Set overwrite_controller=true to replace it" }
                    );
                    return null;
                }
                AssetDatabase.DeleteAsset(controllerPath);
            }

            string dir = Path.GetDirectoryName(controllerPath)?.Replace('\\', '/');
            if (!string.IsNullOrEmpty(dir) && !AssetDatabase.IsValidFolder(dir))
                CreateFolders(dir);

            var controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
            var rootSM     = controller.layers[0].stateMachine;

            bool hasDirectionalWalks = FBXNamingDetector.HasDirectionalWalks(entries);
            bool hasDirectionalRuns  = FBXNamingDetector.HasDirectionalRuns(entries);
            bool hasLocomotion       = entries.Any(e =>
                e.Category == AnimCategory.LocomotionWalk ||
                e.Category == AnimCategory.LocomotionRun);

            // ── Parameters ────────────────────────────────────────────────────

            if (hasLocomotion)
            {
                controller.AddParameter("Speed", AnimatorControllerParameterType.Float);
                if (hasDirectionalWalks || hasDirectionalRuns)
                {
                    controller.AddParameter("MoveX", AnimatorControllerParameterType.Float);
                    controller.AddParameter("MoveY", AnimatorControllerParameterType.Float);
                }
            }

            var triggerNames = entries
                .Where(e => !string.IsNullOrEmpty(e.TriggerName))
                .Select(e => e.TriggerName)
                .Distinct()
                .ToList();
            foreach (var t in triggerNames)
                controller.AddParameter(t, AnimatorControllerParameterType.Trigger);

            // ── Idle state ────────────────────────────────────────────────────

            var idleEntry = entries.FirstOrDefault(e => e.Category == AnimCategory.Idle);
            AnimatorState idleState = null;
            if (idleEntry != null)
            {
                var idleClip = LoadClipFromFBX(idleEntry.FbxPath);
                idleState = rootSM.AddState("Idle");
                idleState.motion = idleClip;
                rootSM.defaultState = idleState;
            }

            // ── Locomotion ────────────────────────────────────────────────────

            AnimatorState locomotionState = null;
            if (hasLocomotion)
            {
                if (hasDirectionalWalks || hasDirectionalRuns)
                {
                    BlendTree tree;
                    locomotionState = controller.CreateBlendTreeInController("Locomotion", out tree, 0);
                    tree.blendType       = BlendTreeType.SimpleDirectional2D;
                    tree.blendParameter  = "MoveX";
                    tree.blendParameterY = "MoveY";

                    foreach (var e in entries.Where(en =>
                        en.Category == AnimCategory.LocomotionWalk ||
                        en.Category == AnimCategory.LocomotionRun))
                    {
                        var clip = LoadClipFromFBX(e.FbxPath);
                        if (clip != null)
                            tree.AddChild(clip, new Vector2(e.BlendX, e.BlendY));
                    }
                }
                else
                {
                    BlendTree tree;
                    locomotionState = controller.CreateBlendTreeInController("Locomotion", out tree, 0);
                    tree.blendType      = BlendTreeType.Simple1D;
                    tree.blendParameter = "Speed";

                    var walkEntry = entries.FirstOrDefault(e => e.Category == AnimCategory.LocomotionWalk);
                    var runEntry  = entries.FirstOrDefault(e => e.Category == AnimCategory.LocomotionRun);
                    if (walkEntry != null) { var c = LoadClipFromFBX(walkEntry.FbxPath); if (c != null) tree.AddChild(c, 0.5f); }
                    if (runEntry  != null) { var c = LoadClipFromFBX(runEntry.FbxPath);  if (c != null) tree.AddChild(c, 1.0f); }
                }
            }

            if (idleState != null && locomotionState != null)
            {
                var toLocomotion = idleState.AddTransition(locomotionState);
                toLocomotion.AddCondition(AnimatorConditionMode.Greater, 0.1f, "Speed");
                toLocomotion.duration    = 0.25f;
                toLocomotion.hasExitTime = false;

                var toIdle = locomotionState.AddTransition(idleState);
                toIdle.AddCondition(AnimatorConditionMode.Less, 0.05f, "Speed");
                toIdle.duration    = 0.25f;
                toIdle.hasExitTime = false;
            }
            else if (locomotionState != null)
            {
                rootSM.defaultState = locomotionState;
            }

            // ── Trigger states ────────────────────────────────────────────────

            foreach (var e in entries.Where(en =>
                en.Category == AnimCategory.Jump   ||
                en.Category == AnimCategory.Attack ||
                en.Category == AnimCategory.Trigger||
                en.Category == AnimCategory.Unknown))
            {
                var clip      = LoadClipFromFBX(e.FbxPath);
                string sName  = string.IsNullOrEmpty(e.TriggerName) ? e.ClipName : e.TriggerName;
                var state     = rootSM.AddState(sName);
                state.motion  = clip;

                if (!string.IsNullOrEmpty(e.TriggerName))
                {
                    var any = rootSM.AddAnyStateTransition(state);
                    any.AddCondition(AnimatorConditionMode.If, 0, e.TriggerName);
                    any.duration            = 0.1f;
                    any.hasExitTime         = false;
                    any.canTransitionToSelf = false;
                }

                if (e.Category == AnimCategory.Unknown)
                {
                    diagnostics.AddInfo(
                        "UNRECOGNIZED_ANIMATION",
                        $"'{e.ClipName}' adı tanınmadı, standalone state olarak eklendi.",
                        new { name = e.ClipName, assigned_state = sName }
                    );
                }
            }

            AssetDatabase.SaveAssets();
            return controllerPath;
        }

        // ── Helpers ───────────────────────────────────────────────────────────

        private static AnimationClip LoadClipFromFBX(string fbxPath)
        {
            return AssetDatabase.LoadAllAssetsAtPath(fbxPath)
                .OfType<AnimationClip>()
                .FirstOrDefault(c => !c.name.StartsWith("__preview__"));
        }

        private static void CreateFolders(string folderPath)
        {
            if (AssetDatabase.IsValidFolder(folderPath)) return;
            string parent = Path.GetDirectoryName(folderPath)?.Replace('\\', '/');
            if (!string.IsNullOrEmpty(parent) && !AssetDatabase.IsValidFolder(parent))
                CreateFolders(parent);
            string name = Path.GetFileName(folderPath);
            if (!string.IsNullOrEmpty(parent) && !string.IsNullOrEmpty(name))
                AssetDatabase.CreateFolder(parent, name);
        }
    }
}
