using System.Collections.Generic;
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
        public static AnimationEntry Detect(string fbxPath) =>
            new AnimationEntry { FbxPath = fbxPath, Category = AnimCategory.Unknown };

        public static bool HasDirectionalWalks(IEnumerable<AnimationEntry> entries) =>
            entries.Any(e => e.Category == AnimCategory.LocomotionWalk);

        public static bool HasDirectionalRuns(IEnumerable<AnimationEntry> entries) =>
            entries.Any(e => e.Category == AnimCategory.LocomotionRun);
    }
}
