using System;
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
        public static AnimationEntry Detect(string fbxPath, string configuredClipName = null)
        {
            string fileName = Path.GetFileNameWithoutExtension(fbxPath);

            // Kategori tespiti kaynağı: kullanıcının verdiği klip adı (setup_clips ile
            // ayarlanmışsa) önce gelir; yoksa dosya adından "Karakter_Anim_Walk" ya da
            // Mixamo "Karakter@Walk" gibi önekler ayıklanıp anlamlı son ek kullanılır.
            string detectSource = !string.IsNullOrEmpty(configuredClipName)
                ? configuredClipName
                : StripAnimMarker(fileName);
            string lower = detectSource.ToLowerInvariant();

            var entry = new AnimationEntry
            {
                FbxPath  = fbxPath,
                ClipName = !string.IsNullOrEmpty(configuredClipName) ? configuredClipName : fileName,
            };

            Categorize(lower, entry);

            // Klip adı tanınmadıysa (ör. Türkçe "Yürüme") dosya adı konvansiyonuna
            // geri düş — "X_Anim_Walk.fbx" içindeki "Yürüme" yine Walk olarak yakalanır.
            if (entry.Category == AnimCategory.Unknown && !string.IsNullOrEmpty(configuredClipName))
                Categorize(StripAnimMarker(fileName).ToLowerInvariant(), entry);

            entry.Loop = AutoDetectLoop(entry.Category);
            return entry;
        }

        // "Yagmaci_Anim_Walk" → "Walk", "Hero_Animation_Attack" → "Attack",
        // "Ch03@Running" → "Running". Marker yoksa dosya adını olduğu gibi döndürür
        // (geriye dönük uyumlu — eski düz "Walk.fbx" adları da çalışmaya devam eder).
        private static string StripAnimMarker(string fileName)
        {
            string[] markers = { "_animation_", "_anim_", "_anims_", "@" };
            string lower = fileName.ToLowerInvariant();
            foreach (var m in markers)
            {
                int idx = lower.LastIndexOf(m, StringComparison.Ordinal);
                if (idx >= 0 && idx + m.Length < fileName.Length)
                    return fileName.Substring(idx + m.Length);
            }
            return fileName;
        }

        public static bool HasDirectionalWalks(IEnumerable<AnimationEntry> entries)
        {
            var walks = entries.Where(e => e.Category == AnimCategory.LocomotionWalk).ToList();
            // Directional = birden fazla yön varyantı VEYA herhangi biri sol/sağ (BlendX != 0)
            return walks.Count > 1 || walks.Any(e => e.BlendX != 0f);
        }

        public static bool HasDirectionalRuns(IEnumerable<AnimationEntry> entries)
        {
            var runs = entries.Where(e => e.Category == AnimCategory.LocomotionRun).ToList();
            return runs.Count > 1 || runs.Any(e => e.BlendX != 0f);
        }

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
