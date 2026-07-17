using System.Collections.Generic;
using System.Linq;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace MCPForUnity.Editor.Tools
{
    /// <summary>
    /// Tool for searching GameObjects in the scene.
    /// Returns instance IDs plus a lightweight per-object summary (name + path)
    /// with pagination support, so callers don't need one extra resource
    /// round-trip per result just to see what matched (N+1 avoidance).
    /// For detailed GameObject data, use the unity://scene/gameobject/{id} resource.
    /// </summary>
    [McpForUnityTool("find_gameobjects")]
    public static class FindGameObjects
    {
        /// <summary>
        /// Handles the find_gameobjects command.
        /// </summary>
        /// <param name="params">Command parameters</param>
        /// <returns>Paginated list of instance IDs</returns>
        public static object HandleCommand(JObject @params)
        {
            if (@params == null)
            {
                return new ErrorResponse("Parameters cannot be null.");
            }

            var p = new ToolParams(@params);

            // Parse search parameters
            string searchMethod = p.Get("searchMethod", "by_name");

            // Try searchTerm, search_term, or target (for backwards compatibility)
            string searchTerm = p.Get("searchTerm");
            if (string.IsNullOrEmpty(searchTerm))
            {
                searchTerm = p.Get("target");
            }

            if (string.IsNullOrEmpty(searchTerm))
            {
                return new ErrorResponse("'searchTerm' or 'target' parameter is required.");
            }

            // Pagination parameters using standard PaginationRequest
            var pagination = PaginationRequest.FromParams(@params, defaultPageSize: 50);
            pagination.PageSize = Mathf.Clamp(pagination.PageSize, 1, 500);

            // Search options (supports multiple parameter name variants)
            bool includeInactive = p.GetBool("includeInactive", false) ||
                                   p.GetBool("searchInactive", false);

            var matchMode = GameObjectLookup.ParseMatchMode(p.Get("matchMode", "exact"));

            try
            {
                // Get all matching instance IDs
                var allIds = GameObjectLookup.SearchGameObjects(searchMethod, searchTerm, includeInactive, 0, matchMode);

                // Use standard pagination response
                var paginatedResult = PaginationResponse<int>.Create(allIds, pagination);

                // Lightweight summary for the returned page only (≤ pageSize objects):
                // enough for the agent to pick a target without a follow-up resource call.
                var objects = paginatedResult.Items.Select(id =>
                {
                    var go = GameObjectLookup.FindById(id);
                    return new
                    {
                        instanceID = id,
                        name = go != null ? go.name : null,
                        path = go != null ? GameObjectLookup.GetGameObjectPath(go) : null
                    };
                }).ToList();

                return new SuccessResponse("Found GameObjects", new
                {
                    instanceIDs = paginatedResult.Items,
                    objects,
                    pageSize = paginatedResult.PageSize,
                    cursor = paginatedResult.Cursor,
                    nextCursor = paginatedResult.NextCursor,
                    totalCount = paginatedResult.TotalCount,
                    hasMore = paginatedResult.HasMore
                });
            }
            catch (System.Exception ex)
            {
                McpLog.Error($"[FindGameObjects] Error searching GameObjects: {ex.Message}");
                return new ErrorResponse($"Error searching GameObjects: {ex.Message}");
            }
        }
    }
}
