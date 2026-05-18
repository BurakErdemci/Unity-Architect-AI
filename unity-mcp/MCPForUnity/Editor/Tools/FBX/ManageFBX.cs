using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.FBX
{
    [McpForUnityTool("manage_fbx", AutoRegister = false, Group = "animation")]
    public static class ManageFBX
    {
        private static readonly string[] ValidActions = { "get_info", "configure_rig", "setup_clips", "full_setup" };

        public static object HandleCommand(JObject @params)
        {
            string action = @params["action"]?.ToString()?.ToLowerInvariant();
            if (string.IsNullOrEmpty(action))
                return new ErrorResponse("'action' is required. Valid: get_info, configure_rig, setup_clips, full_setup");

            switch (action)
            {
                case "get_info":       return FBXImportSetup.GetInfo(@params);
                case "configure_rig":  return FBXImportSetup.ConfigureRig(@params);
                case "setup_clips":    return FBXImportSetup.SetupClips(@params);
                case "full_setup":     return FBXFullSetup.Run(@params);
                default:
                    return new ErrorResponse(
                        $"Unknown action '{action}'. Valid: {string.Join(", ", ValidActions)}"
                    );
            }
        }
    }
}
