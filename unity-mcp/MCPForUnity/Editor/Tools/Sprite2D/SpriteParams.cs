using System;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Helpers;

namespace MCPForUnity.Editor.Tools.Sprite2D
{
    /// <summary>
    /// Reads the sprite tool's numeric parameters without throwing and without rounding.
    /// ToObject&lt;T&gt; does both; measured through the live tool 2026-08-21: an out-of-int
    /// grid value or start_frame threw OverflowException (a transport failure, not a named
    /// refusal), start_frame 2.7 silently became 3, and fps NaN wrote a clip with NaN times.
    /// Shared rather than private because the same parameters are read in three places.
    /// </summary>
    internal static class SpriteParams
    {
        internal static bool TryReadAssetPath(JObject @params, string key, out string path, out string error)
        {
            error = null;
            path = @params[key]?.ToString();
            if (string.IsNullOrEmpty(path))
            {
                error = $"'{key}' is required.";
                return false;
            }

            path = AssetPathUtility.SanitizeAssetPath(path);
            if (path == null)
            {
                error = $"'{key}' must stay under Assets/ and cannot contain '..'.";
                return false;
            }
            if (path != "Assets" && !AssetPathUtility.IsValidAssetPath(path))
            {
                error = $"'{key}' contains a character that is not allowed in an asset path.";
                return false;
            }
            return true;
        }

        /// <summary>
        /// Validates a clip name that is about to be composed into an asset path, and hands
        /// back the composed path. The name is the only untrusted segment of that path: a
        /// separator escapes the output folder, and a character like ':' is legal in an asset
        /// path while being illegal in a file name. Shared so the two actions that compose
        /// such a path refuse the same names for the same reasons.
        /// </summary>
        internal static bool TryReadClipName(string clipName, string outputDir, string suffix,
                                             out string assetPath, out string reason, out string[] fixes)
        {
            // Measured: "nested/walk" either threw from CreateAsset or, where the folder
            // existed, wrote the clip outside output_dir.
            if (clipName.Contains("/") || clipName.Contains("\\"))
            {
                assetPath = null;
                reason = "the name cannot contain a path separator";
                fixes = new[] { "Remove '..' and path separators from the clip name." };
                return false;
            }

            assetPath = AssetPathUtility.SanitizeAssetPath($"{outputDir}/{clipName}{suffix}");
            if (assetPath == null || !AssetPathUtility.IsValidAssetPath(assetPath))
            {
                assetPath = null;
                reason = "the name cannot be used as a file name";
                fixes = new[] { "Remove '..', path separators and characters like : * ? \" < > | from the clip name." };
                return false;
            }

            reason = null;
            fixes = null;
            return true;
        }

        /// <summary>
        /// Reads one number out of a position that has no field name to give
        /// ValidateNumericField - an array element, or a field whose label the caller wants to
        /// spell itself. Same finiteness and range rules as TryReadFiniteFloat.
        /// </summary>
        internal static bool TryReadFiniteNumber(JToken token, string label, out float value, out string error)
        {
            value = 0f;
            error = null;

            if (!ParamCoercion.IsNumericToken(token))
            {
                string got = token == null ? "nothing" : token.Type.ToString().ToLowerInvariant();
                error = $"{label} must be a number, got {got}.";
                return false;
            }

            double raw;
            try
            {
                raw = token.Value<double>();
            }
            catch (Exception)
            {
                error = $"{label} is out of range for a number.";
                return false;
            }

            if (double.IsNaN(raw) || double.IsInfinity(raw))
            {
                error = $"{label} must be a finite number.";
                return false;
            }
            // Read as double first: the cast would silently make an infinity of this.
            if (raw > float.MaxValue || raw < -float.MaxValue)
            {
                error = $"{label} is out of range for a 32-bit float.";
                return false;
            }

            value = (float)raw;
            return true;
        }

        /// <summary>
        /// Reads an optional whole number. Returns false with a caller-facing reason when
        /// the value is present but is not a whole number an int can hold.
        /// </summary>
        internal static bool TryReadWholeNumber(JObject @params, string key, int fallback,
                                                out int value, out string error)
        {
            value = fallback;
            if (!ParamCoercion.ValidateIntegerField(@params, key, out error))
            {
                error = $"'{key}' {error}.";
                return false;
            }

            JToken token = @params[key];
            if (token == null || token.Type == JTokenType.Null)
                return true;

            long raw;
            try
            {
                raw = token.Value<long>();
            }
            catch (Exception)
            {
                // Too large for long parses as a BigInteger, still typed Integer, and throws.
                error = $"'{key}' must fit in a 32-bit integer.";
                return false;
            }

            if (raw < int.MinValue || raw > int.MaxValue)
            {
                // Worded unlike the range guards elsewhere on purpose: with shared wording a
                // test still passed while the cast wrapped and a LATER guard did the refusing
                // (measured on the page_size and cols tests, which both did).
                error = $"'{key}' must fit in a 32-bit integer; got {raw}.";
                return false;
            }

            value = (int)raw;
            return true;
        }

        /// <summary>
        /// Reads an optional flag. Needed for `loop`, which hides inside the untyped `clips`
        /// array where nothing above C# validates it - measured 2026-08-21: ToObject&lt;bool?&gt;
        /// threw on `loop: "maybe"` and silently accepted `loop: 2`.
        /// </summary>
        internal static bool TryReadBool(JObject @params, string key, bool fallback,
                                         out bool value, out string error)
        {
            value = fallback;
            error = null;

            JToken token = @params[key];
            if (token == null || token.Type == JTokenType.Null)
                return true;

            bool? parsed = ParamCoercion.CoerceBoolNullable(token);
            if (parsed == null)
            {
                error = $"'{key}' must be true or false; got {token.Type.ToString().ToLowerInvariant()}.";
                return false;
            }

            value = parsed.Value;
            return true;
        }

        /// <summary>
        /// Reads an optional rate. NaN and the infinities pass every comparison-based guard
        /// (`fps &lt;= 0f` is false for NaN), so a NaN rate reached the keyframe arithmetic
        /// and wrote a clip whose frame times were all NaN.
        /// </summary>
        internal static bool TryReadFiniteFloat(JObject @params, string key, float fallback,
                                                out float value, out string error)
        {
            value = fallback;
            if (!ParamCoercion.ValidateNumericField(@params, key, out error))
            {
                error = $"'{key}' {error}.";
                return false;
            }

            JToken token = @params[key];
            if (token == null || token.Type == JTokenType.Null)
                return true;

            double raw;
            try
            {
                raw = token.Value<double>();
            }
            catch (Exception)
            {
                error = $"'{key}' is out of range for a number.";
                return false;
            }

            if (double.IsNaN(raw) || double.IsInfinity(raw))
            {
                error = $"'{key}' must be a finite number.";
                return false;
            }

            // Read as double first: the cast would silently make an infinity of this.
            if (raw > float.MaxValue || raw < -float.MaxValue)
            {
                error = $"'{key}' is out of range for a 32-bit float.";
                return false;
            }

            value = (float)raw;
            return true;
        }
    }
}
