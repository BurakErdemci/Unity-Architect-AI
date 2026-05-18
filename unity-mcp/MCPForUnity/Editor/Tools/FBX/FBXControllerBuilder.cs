using System.Collections.Generic;

namespace MCPForUnity.Editor.Tools.FBX
{
    internal static class FBXControllerBuilder
    {
        public static object Build(
            IList<AnimationEntry> entries,
            string controllerPath,
            bool overwrite,
            FBXDiagnosticBuilder diagnostics) =>
            new { success = false, message = "Not implemented" };
    }
}
