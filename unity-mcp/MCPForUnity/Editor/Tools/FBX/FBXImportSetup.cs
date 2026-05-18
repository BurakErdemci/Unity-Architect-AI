using Newtonsoft.Json.Linq;

namespace MCPForUnity.Editor.Tools.FBX
{
    internal static class FBXImportSetup
    {
        public static object GetInfo(JObject p) => new { success = false, message = "Not implemented" };
        public static object ConfigureRig(JObject p) => new { success = false, message = "Not implemented" };
        public static object SetupClips(JObject p) => new { success = false, message = "Not implemented" };
        internal static UnityEngine.Avatar GetAvatarFromFBX(string fbxPath) => null;
    }
}
