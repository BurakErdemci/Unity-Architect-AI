using System.Collections.Generic;
using System.Linq;

namespace MCPForUnity.Editor.Tools.Sprite2D
{
    internal enum SpriteAnimCategory
    {
        Idle,
        Locomotion,   // walk veya run — 1D blend tree adayı
        Jump,
        Combat,       // attack, slash, combo vb. — trigger state
        Object,       // open, close, activate — tek durum
        Generic,
    }

    internal enum ControllerComplexity
    {
        Single,       // tek animasyon veya object/generic → basit tek state
        BlendTree1D,  // locomotion → Speed float parametreli 1D blend tree
        StateMachine, // combat varsa → trigger state'ler
        Full,         // locomotion + combat → blend tree + trigger state'ler
    }

    internal class SpriteAnimEntry
    {
        public string ClipName;
        public SpriteAnimCategory Category;
        public bool Loop;
        public string TriggerName;
        public float BlendValue; // 1D blend tree için: walk=1, run=2
    }

    internal static class SpriteNamingDetector
    {
        public static SpriteAnimEntry Detect(string clipName)
        {
            string lower = clipName.ToLowerInvariant();
            var entry = new SpriteAnimEntry { ClipName = clipName };
            Categorize(lower, entry);
            entry.Loop = AutoDetectLoop(entry.Category);
            return entry;
        }

        public static ControllerComplexity DecideComplexity(IEnumerable<SpriteAnimEntry> entries)
        {
            bool hasLocomotion = entries.Any(e => e.Category == SpriteAnimCategory.Locomotion);
            bool hasCombat     = entries.Any(e => e.Category == SpriteAnimCategory.Combat);

            if (hasLocomotion && hasCombat) return ControllerComplexity.Full;
            if (hasLocomotion)              return ControllerComplexity.BlendTree1D;
            if (hasCombat)                 return ControllerComplexity.StateMachine;
            return ControllerComplexity.Single;
        }

        // ── Private ──────────────────────────────────────────────────────────

        private static void Categorize(string lower, SpriteAnimEntry entry)
        {
            if (lower.Contains("idle") || lower.Contains("stand"))
            { entry.Category = SpriteAnimCategory.Idle; return; }

            if (lower.Contains("walk"))
            { entry.Category = SpriteAnimCategory.Locomotion; entry.BlendValue = 1f; return; }

            if (lower.Contains("run") || lower.Contains("sprint"))
            { entry.Category = SpriteAnimCategory.Locomotion; entry.BlendValue = 2f; return; }

            if (lower.Contains("jump") || lower.Contains("fall") || lower.Contains("land"))
            { entry.Category = SpriteAnimCategory.Jump; entry.TriggerName = Capitalize(lower.Split('_')[0]); return; }

            if (lower.Contains("attack") || lower.Contains("slash") || lower.Contains("punch") ||
                lower.Contains("combo")  || lower.Contains("cast")  || lower.Contains("shoot"))
            { entry.Category = SpriteAnimCategory.Combat; entry.TriggerName = Capitalize(lower.Split('_')[0]); return; }

            if (lower.Contains("open") || lower.Contains("close") || lower.Contains("activate") ||
                lower.Contains("die")  || lower.Contains("death") || lower.Contains("hurt") ||
                lower.Contains("hit"))
            { entry.Category = SpriteAnimCategory.Object; entry.TriggerName = Capitalize(lower.Split('_')[0]); return; }

            entry.Category    = SpriteAnimCategory.Generic;
            entry.TriggerName = Capitalize(lower);
        }

        private static bool AutoDetectLoop(SpriteAnimCategory cat) =>
            cat == SpriteAnimCategory.Idle || cat == SpriteAnimCategory.Locomotion;

        private static string Capitalize(string s) =>
            string.IsNullOrEmpty(s) ? s : char.ToUpperInvariant(s[0]) + s.Substring(1);
    }
}
