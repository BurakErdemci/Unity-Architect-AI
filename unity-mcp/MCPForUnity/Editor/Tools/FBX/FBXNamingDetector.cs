using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace MCPForUnity.Editor.Tools.FBX
{
    internal enum AnimCategory { Idle, LocomotionWalk, LocomotionRun, Jump, Attack, Trigger, Unknown }

    internal class AnimationEntry
    {
        public string FbxPath;
        public string ClipName;
        public AnimCategory Category;
        public float BlendX;
        public float BlendY;
        public bool Loop;
        public string TriggerName;
    }

    internal static class FBXNamingDetector
    {
        public static AnimationEntry Detect(string fbxPath)
        {
            string fileName = Path.GetFileNameWithoutExtension(fbxPath);
            string lower    = fileName.ToLowerInvariant();

            var entry = new AnimationEntry
            {
                FbxPath  = fbxPath,
                ClipName = fileName,
            };

            Categorize(lower, entry);
            entry.Loop = AutoDetectLoop(entry.Category);
            return entry;
        }

        public static bool HasDirectionalWalks(IEnumerable<AnimationEntry> entries) =>
            entries.Any(e => e.Category == AnimCategory.LocomotionWalk);

        public static bool HasDirectionalRuns(IEnumerable<AnimationEntry> entries) =>
            entries.Any(e => e.Category == AnimCategory.LocomotionRun);

        // ── Private ───────────────────────────────────────────────────────────

        private static void Categorize(string lower, AnimationEntry entry)
        {
            if (lower.StartsWith("idle"))
            { entry.Category = AnimCategory.Idle; return; }

            if (lower.StartsWith("walkforward") || lower.StartsWith("walkfront"))
            { entry.Category = AnimCategory.LocomotionWalk; entry.BlendX = 0; entry.BlendY = 1; return; }
            if (lower.StartsWith("walkbackward") || lower.StartsWith("walkback"))
            { entry.Category = AnimCategory.LocomotionWalk; entry.BlendX = 0; entry.BlendY = -1; return; }
            if (lower.StartsWith("walkleft"))
            { entry.Category = AnimCategory.LocomotionWalk; entry.BlendX = -1; entry.BlendY = 0; return; }
            if (lower.StartsWith("walkright"))
            { entry.Category = AnimCategory.LocomotionWalk; entry.BlendX = 1; entry.BlendY = 0; return; }
            if (lower.StartsWith("walk"))
            { entry.Category = AnimCategory.LocomotionWalk; entry.BlendX = 0; entry.BlendY = 1; return; }

            if (lower.StartsWith("runforward") || lower.StartsWith("runfront"))
            { entry.Category = AnimCategory.LocomotionRun; entry.BlendX = 0; entry.BlendY = 2; return; }
            if (lower.StartsWith("runbackward") || lower.StartsWith("runback"))
            { entry.Category = AnimCategory.LocomotionRun; entry.BlendX = 0; entry.BlendY = -2; return; }
            if (lower.StartsWith("runleft"))
            { entry.Category = AnimCategory.LocomotionRun; entry.BlendX = -2; entry.BlendY = 0; return; }
            if (lower.StartsWith("runright"))
            { entry.Category = AnimCategory.LocomotionRun; entry.BlendX = 2; entry.BlendY = 0; return; }
            if (lower.StartsWith("run") || lower.StartsWith("sprint"))
            { entry.Category = AnimCategory.LocomotionRun; entry.BlendX = 0; entry.BlendY = 2; return; }

            if (lower.StartsWith("jump"))
            { entry.Category = AnimCategory.Jump; entry.TriggerName = "Jump"; return; }

            if (lower.StartsWith("attack") || lower.StartsWith("slash") || lower.StartsWith("punch"))
            { entry.Category = AnimCategory.Attack; entry.TriggerName = "Attack"; return; }

            if (lower.StartsWith("fall"))
            { entry.Category = AnimCategory.Trigger; entry.TriggerName = "Fall"; return; }
            if (lower.StartsWith("die") || lower.StartsWith("death"))
            { entry.Category = AnimCategory.Trigger; entry.TriggerName = "Die"; return; }
            if (lower.StartsWith("hit") || lower.StartsWith("damage"))
            { entry.Category = AnimCategory.Trigger; entry.TriggerName = "Hit"; return; }
            if (lower.StartsWith("dodge") || lower.StartsWith("roll"))
            { entry.Category = AnimCategory.Trigger; entry.TriggerName = "Dodge"; return; }

            entry.Category    = AnimCategory.Unknown;
            entry.TriggerName = Capitalize(lower);
        }

        private static bool AutoDetectLoop(AnimCategory cat) =>
            cat == AnimCategory.Idle ||
            cat == AnimCategory.LocomotionWalk ||
            cat == AnimCategory.LocomotionRun;

        private static string Capitalize(string s) =>
            string.IsNullOrEmpty(s) ? s : char.ToUpperInvariant(s[0]) + s.Substring(1);
    }
}
