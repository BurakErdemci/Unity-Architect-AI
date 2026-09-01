using System;
using Newtonsoft.Json.Linq;

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
        /// <summary>
        /// Reads an optional whole number. Returns false with a caller-facing reason when
        /// the value is present but is not a whole number an int can hold.
        /// </summary>
        internal static bool TryReadWholeNumber(JObject @params, string key, int fallback,
                                                out int value, out string error)
        {
            value = fallback;
            error = null;

            JToken token = @params?[key];
            // An explicit JSON null arrives as a JValue, not a C# null; it means "unset".
            if (token == null || token.Type == JTokenType.Null)
                return true;

            if (token.Type != JTokenType.Integer)
            {
                error = $"'{key}' must be a whole number; got {token.Type.ToString().ToLowerInvariant()}.";
                return false;
            }

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
        /// threw on `loop: "maybe"` and silently accepted `loop: 2`. Top-level flags arrive
        /// already coerced by FastMCP, but this layer owns the conversion, so it refuses here
        /// rather than trusting the layer above.
        /// </summary>
        internal static bool TryReadBool(JObject @params, string key, bool fallback,
                                         out bool value, out string error)
        {
            value = fallback;
            error = null;

            JToken token = @params?[key];
            if (token == null || token.Type == JTokenType.Null)
                return true;

            if (token.Type != JTokenType.Boolean)
            {
                error = $"'{key}' must be true or false; got {token.Type.ToString().ToLowerInvariant()}.";
                return false;
            }

            value = token.Value<bool>();
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
            error = null;

            JToken token = @params?[key];
            if (token == null || token.Type == JTokenType.Null)
                return true;

            if (token.Type != JTokenType.Integer && token.Type != JTokenType.Float)
            {
                error = $"'{key}' must be a number; got {token.Type.ToString().ToLowerInvariant()}.";
                return false;
            }

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
