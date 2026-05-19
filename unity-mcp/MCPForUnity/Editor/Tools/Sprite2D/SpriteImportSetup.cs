using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using MCPForUnity.Editor.Helpers;
#pragma warning disable CS0618 // TextureImporter.spritesheet — Unity 6'da obsolete ama ISpriteEditorDataProvider alternatifsiz karmaşık; Unity 7'ye kadar kabul edilebilir

namespace MCPForUnity.Editor.Tools.Sprite2D
{
    internal static class SpriteImportSetup
    {
        // ── GetInfo ──────────────────────────────────────────────────────────

        public static object GetInfo(JObject @params)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
                return new ErrorResponse($"No TextureImporter found at '{path}'. Is it a texture/sprite?");

            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            int w = texture != null ? texture.width  : 0;
            int h = texture != null ? texture.height : 0;

            var existingSlices = importer.spritesheet.Select(s => new
            {
                name   = s.name,
                x      = (int)s.rect.x,
                y      = (int)s.rect.y,
                width  = (int)s.rect.width,
                height = (int)s.rect.height,
            }).ToArray();

            // Texture'ı base64 olarak yükle (vision analizi için)
            string imageBase64 = null;
            try
            {
                string fullPath = Path.Combine(
                    Application.dataPath.Replace("/Assets", ""),
                    path
                );
                if (File.Exists(fullPath))
                {
                    byte[] bytes = File.ReadAllBytes(fullPath);
                    string ext = Path.GetExtension(path).ToLowerInvariant();
                    string mime = (ext == ".jpg" || ext == ".jpeg") ? "image/jpeg" : "image/png";
                    imageBase64 = $"data:{mime};base64," + Convert.ToBase64String(bytes);
                }
            }
            catch { /* base64 opsiyonel — hata olursa null bırak */ }

            var result = new
            {
                success       = true,
                path,
                width         = w,
                height        = h,
                sprite_mode   = importer.spriteImportMode.ToString(),
                pixels_per_unit = importer.spritePixelsPerUnit,
                filter_mode   = importer.filterMode.ToString(),
                slice_count   = existingSlices.Length,
                slices        = existingSlices,
                image_base64  = imageBase64,
            };

            return result;
        }

        // ── SliceSheet ───────────────────────────────────────────────────────

        public static object SliceSheet(JObject @params, SpriteDiagnosticBuilder diagnostics)
        {
            string path = @params["path"]?.ToString();
            if (string.IsNullOrEmpty(path))
                return new ErrorResponse("'path' is required.");

            path = AssetPathUtility.SanitizeAssetPath(path);
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
                return new ErrorResponse($"No TextureImporter found at '{path}'.");

            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            if (texture == null)
                return new ErrorResponse($"Could not load texture at '{path}'.");

            int texW = texture.width;
            int texH = texture.height;

            // cols/rows veya frame_width/frame_height'ten grid hesapla
            int cols = @params["cols"]?.ToObject<int>() ?? 0;
            int rows = @params["rows"]?.ToObject<int>() ?? 1;
            int frameW = @params["frame_width"]?.ToObject<int>() ?? 0;
            int frameH = @params["frame_height"]?.ToObject<int>() ?? 0;

            if (cols <= 0 && frameW <= 0)
                return new ErrorResponse("Either 'cols' or 'frame_width' is required.");

            if (frameW <= 0) frameW = texW / cols;
            if (frameH <= 0) frameH = texH / rows;
            if (cols  <= 0) cols   = texW / frameW;
            if (rows  <= 0) rows   = texH / frameH;

            int totalFrames = cols * rows;
            if (totalFrames == 0)
            {
                diagnostics.AddError(
                    "SLICE_EMPTY",
                    "Grid hesabı 0 frame üretiyor — cols/rows veya frame boyutları yanlış.",
                    new { cols, rows, frame_width = frameW, frame_height = frameH, texture_width = texW, texture_height = texH },
                    new[] { "cols ve rows değerlerini kontrol et", "Texture boyutlarını doğrula (get_info ile)" }
                );
                return new { success = false, diagnostics = diagnostics.Build() };
            }

            string baseName = @params["base_name"]?.ToString()
                ?? Path.GetFileNameWithoutExtension(path);

            var metas = new SpriteMetaData[totalFrames];
            for (int r = 0; r < rows; r++)
            {
                for (int c = 0; c < cols; c++)
                {
                    int i = r * cols + c;
                    metas[i] = new SpriteMetaData
                    {
                        name      = $"{baseName}_{i}",
                        rect      = new Rect(c * frameW, texH - (r + 1) * frameH, frameW, frameH),
                        pivot     = new Vector2(0.5f, 0.5f),
                        alignment = 0,
                    };
                }
            }

            importer.textureType      = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritesheet      = metas;
            importer.filterMode       = FilterMode.Point; // pixel-perfect default
            importer.SaveAndReimport();

            return new
            {
                success      = true,
                path,
                cols,
                rows,
                frame_width  = frameW,
                frame_height = frameH,
                total_frames = totalFrames,
                diagnostics  = diagnostics.Build(),
            };
        }
    }
}
