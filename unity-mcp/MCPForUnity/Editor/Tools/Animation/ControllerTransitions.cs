using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEditor.Animations;

namespace MCPForUnity.Editor.Tools.Animation
{
    /// <summary>
    /// Update/remove/serialize AnimatorStateTransitions, including AnyState transitions.
    /// A transition is identified by fromState + toState + layerIndex (default 0) +
    /// transitionIndex (default 0, disambiguates parallel transitions between the same pair).
    /// Update semantics: only fields present in params are changed; 'conditions' (if present)
    /// REPLACES all conditions. All inputs are validated BEFORE any mutation (atomic).
    /// </summary>
    internal static class ControllerTransitions
    {
        internal const string ValidConditionModes = "greater, less, equals, not_equal, if (true), if_not (false)";
        internal const string ValidInterruptionSources = "None, Source, Destination, SourceThenDestination, DestinationThenSource";

        // ── Entry points ──────────────────────────────────────────────────────

        public static object UpdateTransition(JObject @params)
        {
            var controller = ControllerCreate.LoadController(@params);
            if (controller == null)
                return ControllerCreate.ControllerNotFoundError(@params);

            var found = FindTransition(controller, @params, out object findError);
            if (found == null)
                return findError;

            // Validate everything first (atomic), then mutate.
            var plan = ValidateProperties(controller, @params, out object validationError);
            if (plan == null)
                return validationError;

            plan.ApplyTo(found.Transition);

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            return new
            {
                success = true,
                message = $"Updated transition '{found.FromName}' -> '{found.ToName}' (#{found.Index}) in layer {found.LayerIndex}",
                data = new
                {
                    controllerPath = AssetDatabase.GetAssetPath(controller),
                    layerIndex = found.LayerIndex,
                    transition = SerializeTransition(found.FromName, found.Index, found.Transition)
                }
            };
        }

        public static object RemoveTransition(JObject @params)
        {
            var controller = ControllerCreate.LoadController(@params);
            if (controller == null)
                return ControllerCreate.ControllerNotFoundError(@params);

            var found = FindTransition(controller, @params, out object findError);
            if (found == null)
                return findError;

            object removedSnapshot = SerializeTransition(found.FromName, found.Index, found.Transition);

            if (found.IsAnyState)
                found.StateMachine.RemoveAnyStateTransition(found.Transition);
            else
                found.FromState.RemoveTransition(found.Transition);

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            int remaining = found.IsAnyState
                ? found.StateMachine.anyStateTransitions.Length
                : found.FromState.transitions.Length;

            return new
            {
                success = true,
                message = $"Removed transition '{found.FromName}' -> '{found.ToName}' (#{found.Index}) from layer {found.LayerIndex}",
                data = new
                {
                    controllerPath = AssetDatabase.GetAssetPath(controller),
                    layerIndex = found.LayerIndex,
                    removedTransition = removedSnapshot,
                    remainingTransitionsFromSource = remaining
                }
            };
        }

        // ── Lookup ────────────────────────────────────────────────────────────

        internal sealed class FoundTransition
        {
            public AnimatorStateTransition Transition;
            public AnimatorStateMachine StateMachine;
            public AnimatorState FromState;          // null when AnyState
            public bool IsAnyState;
            public string FromName;
            public string ToName;
            public int Index;                        // index among transitions with the same from→to pair
            public int LayerIndex;
        }

        internal static bool IsAnyStateName(string name) =>
            string.Equals(name, "AnyState", StringComparison.OrdinalIgnoreCase)
            || string.Equals(name, "Any", StringComparison.OrdinalIgnoreCase)
            || string.Equals(name, "Any State", StringComparison.OrdinalIgnoreCase);

        internal static string DestinationName(AnimatorStateTransition t) =>
            t.isExit ? "Exit" : (t.destinationState?.name ?? t.destinationStateMachine?.name ?? "(none)");

        internal static string[] StateNames(AnimatorStateMachine sm) =>
            sm.states.Select(cs => cs.state.name).ToArray();

        private static FoundTransition FindTransition(AnimatorController controller, JObject @params, out object error)
        {
            error = null;

            string fromStateName = @params["fromState"]?.ToString();
            string toStateName = @params["toState"]?.ToString();
            if (string.IsNullOrEmpty(fromStateName) || string.IsNullOrEmpty(toStateName))
            {
                error = new { success = false, message = "'fromState' and 'toState' are required" };
                return null;
            }

            int layerIndex = @params["layerIndex"]?.ToObject<int>() ?? 0;
            if (layerIndex < 0 || layerIndex >= controller.layers.Length)
            {
                error = new { success = false, message = $"Layer index {layerIndex} out of range (controller has {controller.layers.Length} layers: 0..{controller.layers.Length - 1})" };
                return null;
            }

            var sm = controller.layers[layerIndex].stateMachine;
            bool isAnyState = IsAnyStateName(fromStateName);

            AnimatorState fromState = null;
            AnimatorStateTransition[] sourceTransitions;
            string fromDisplay;

            if (isAnyState)
            {
                sourceTransitions = sm.anyStateTransitions;
                fromDisplay = "AnyState";
            }
            else
            {
                fromState = sm.states.FirstOrDefault(cs => cs.state.name == fromStateName).state;
                if (fromState == null)
                {
                    error = new { success = false, message = $"State '{fromStateName}' not found in layer {layerIndex}. Available states: [{string.Join(", ", StateNames(sm))}]" };
                    return null;
                }
                sourceTransitions = fromState.transitions;
                fromDisplay = fromState.name;
            }

            var candidates = sourceTransitions
                .Where(t => string.Equals(DestinationName(t), toStateName, StringComparison.Ordinal))
                .ToList();

            if (candidates.Count == 0)
            {
                string existing = sourceTransitions.Length == 0
                    ? "(none)"
                    : string.Join(", ", sourceTransitions.Select((t, i) => $"{fromDisplay}->{DestinationName(t)}"));
                error = new { success = false, message = $"No transition from '{fromDisplay}' to '{toStateName}' in layer {layerIndex}. Existing transitions from this source: [{existing}]" };
                return null;
            }

            int transitionIndex = @params["transitionIndex"]?.ToObject<int>() ?? 0;
            if (transitionIndex < 0 || transitionIndex >= candidates.Count)
            {
                error = new { success = false, message = $"transitionIndex {transitionIndex} out of range: {candidates.Count} transition(s) exist from '{fromDisplay}' to '{toStateName}' (valid: 0..{candidates.Count - 1})" };
                return null;
            }

            return new FoundTransition
            {
                Transition = candidates[transitionIndex],
                StateMachine = sm,
                FromState = fromState,
                IsAnyState = isAnyState,
                FromName = fromDisplay,
                ToName = toStateName,
                Index = transitionIndex,
                LayerIndex = layerIndex,
            };
        }

        // ── Property application (two-phase: validate, then mutate) ──────────

        internal sealed class TransitionEdit
        {
            public bool? HasExitTime;
            public float? ExitTime;
            public float? Duration;
            public bool? HasFixedDuration;
            public float? Offset;
            public TransitionInterruptionSource? InterruptionSource;
            public bool? OrderedInterruption;
            public bool? CanTransitionToSelf;
            public bool? Solo;
            public bool? Mute;
            public List<(AnimatorConditionMode mode, float threshold, string parameter)> ReplaceConditions; // null = leave as-is

            public void ApplyTo(AnimatorStateTransition t)
            {
                if (HasExitTime.HasValue) t.hasExitTime = HasExitTime.Value;
                if (ExitTime.HasValue) t.exitTime = ExitTime.Value;
                if (Duration.HasValue) t.duration = Duration.Value;
                if (HasFixedDuration.HasValue) t.hasFixedDuration = HasFixedDuration.Value;
                if (Offset.HasValue) t.offset = Offset.Value;
                if (InterruptionSource.HasValue) t.interruptionSource = InterruptionSource.Value;
                if (OrderedInterruption.HasValue) t.orderedInterruption = OrderedInterruption.Value;
                if (CanTransitionToSelf.HasValue) t.canTransitionToSelf = CanTransitionToSelf.Value;
                if (Solo.HasValue) t.solo = Solo.Value;
                if (Mute.HasValue) t.mute = Mute.Value;
                if (ReplaceConditions != null)
                {
                    t.conditions = Array.Empty<AnimatorCondition>();
                    foreach (var (mode, threshold, parameter) in ReplaceConditions)
                        t.AddCondition(mode, threshold, parameter);
                }
            }
        }

        /// <summary>
        /// Parses/validates all transition properties present in params WITHOUT mutating anything.
        /// Returns null + error on invalid input (unknown enum value, bad condition, condition
        /// parameter that doesn't exist on the controller).
        /// </summary>
        internal static TransitionEdit ValidateProperties(AnimatorController controller, JObject @params, out object error)
        {
            error = null;
            var edit = new TransitionEdit();

            edit.HasExitTime = @params["hasExitTime"]?.ToObject<bool?>();
            edit.ExitTime = @params["exitTime"]?.ToObject<float?>();
            edit.Duration = @params["duration"]?.ToObject<float?>();
            edit.HasFixedDuration = @params["hasFixedDuration"]?.ToObject<bool?>();
            edit.Offset = @params["offset"]?.ToObject<float?>();
            edit.OrderedInterruption = @params["orderedInterruption"]?.ToObject<bool?>();
            edit.CanTransitionToSelf = @params["canTransitionToSelf"]?.ToObject<bool?>();
            edit.Solo = @params["solo"]?.ToObject<bool?>();
            edit.Mute = @params["mute"]?.ToObject<bool?>();

            string interruption = @params["interruptionSource"]?.ToString();
            if (!string.IsNullOrEmpty(interruption))
            {
                if (!TryParseInterruptionSource(interruption, out var src))
                {
                    error = new { success = false, message = $"Invalid interruptionSource '{interruption}'. Valid: {ValidInterruptionSources}" };
                    return null;
                }
                edit.InterruptionSource = src;
            }

            JToken conditionsToken = @params["conditions"];
            if (conditionsToken is JArray conditionsArray)
            {
                var parameterNames = controller.parameters.Select(p => p.name).ToArray();
                var parsed = new List<(AnimatorConditionMode, float, string)>();
                foreach (var condItem in conditionsArray)
                {
                    if (condItem is not JObject condObj)
                    {
                        error = new { success = false, message = "Each condition must be an object: {\"parameter\": <name>, \"mode\": <mode>, \"threshold\": <number>}" };
                        return null;
                    }

                    string paramName = condObj["parameter"]?.ToString();
                    if (string.IsNullOrEmpty(paramName))
                    {
                        error = new { success = false, message = $"Condition is missing 'parameter'. Available parameters: [{string.Join(", ", parameterNames)}]" };
                        return null;
                    }
                    if (!parameterNames.Contains(paramName))
                    {
                        error = new { success = false, message = $"Condition parameter '{paramName}' does not exist on the controller. Available parameters: [{string.Join(", ", parameterNames)}]" };
                        return null;
                    }

                    string modeStr = condObj["mode"]?.ToString();
                    AnimatorConditionMode mode;
                    if (string.IsNullOrEmpty(modeStr))
                    {
                        mode = AnimatorConditionMode.Greater; // historical default
                    }
                    else if (!TryParseConditionMode(modeStr, out mode))
                    {
                        error = new { success = false, message = $"Invalid condition mode '{modeStr}'. Valid: {ValidConditionModes}" };
                        return null;
                    }

                    float threshold = condObj["threshold"]?.ToObject<float>() ?? 0f;
                    parsed.Add((mode, threshold, paramName));
                }
                edit.ReplaceConditions = parsed; // empty array => clear all conditions
            }

            return edit;
        }

        internal static bool TryParseConditionMode(string s, out AnimatorConditionMode mode)
        {
            switch (s?.ToLowerInvariant())
            {
                case "greater": mode = AnimatorConditionMode.Greater; return true;
                case "less": mode = AnimatorConditionMode.Less; return true;
                case "equals": mode = AnimatorConditionMode.Equals; return true;
                case "notequal":
                case "not_equal": mode = AnimatorConditionMode.NotEqual; return true;
                case "if":
                case "true": mode = AnimatorConditionMode.If; return true;
                case "ifnot":
                case "if_not":
                case "false": mode = AnimatorConditionMode.IfNot; return true;
                default: mode = AnimatorConditionMode.Greater; return false;
            }
        }

        internal static bool TryParseInterruptionSource(string s, out TransitionInterruptionSource src)
        {
            switch (s?.Replace("_", "").ToLowerInvariant())
            {
                case "none": src = TransitionInterruptionSource.None; return true;
                case "source": src = TransitionInterruptionSource.Source; return true;
                case "destination": src = TransitionInterruptionSource.Destination; return true;
                case "sourcethendestination": src = TransitionInterruptionSource.SourceThenDestination; return true;
                case "destinationthensource": src = TransitionInterruptionSource.DestinationThenSource; return true;
                default: src = TransitionInterruptionSource.None; return false;
            }
        }

        // ── Serialization (single source of truth; feedback #2) ─────────────

        internal static object SerializeTransition(string fromState, int index, AnimatorStateTransition t)
        {
            var conditions = t.conditions.Select(c => new
            {
                parameter = c.parameter,
                mode = c.mode.ToString(),
                threshold = c.threshold
            }).ToList<object>();

            return new
            {
                fromState,
                toState = DestinationName(t),
                index,
                hasExitTime = t.hasExitTime,
                exitTime = t.exitTime,
                duration = t.duration,
                hasFixedDuration = t.hasFixedDuration,
                offset = t.offset,
                interruptionSource = t.interruptionSource.ToString(),
                orderedInterruption = t.orderedInterruption,
                canTransitionToSelf = t.canTransitionToSelf,
                solo = t.solo,
                mute = t.mute,
                conditions
            };
        }

        /// <summary>
        /// Serializes a list of transitions from one source, computing per-destination indices
        /// (the same indices update/remove accept as 'transitionIndex').
        /// </summary>
        internal static List<object> SerializeTransitionList(string fromState, IEnumerable<AnimatorStateTransition> transitions)
        {
            var result = new List<object>();
            var perDestinationCount = new Dictionary<string, int>();
            foreach (var t in transitions)
            {
                string dest = DestinationName(t);
                perDestinationCount.TryGetValue(dest, out int idx);
                perDestinationCount[dest] = idx + 1;
                result.Add(SerializeTransition(fromState, idx, t));
            }
            return result;
        }
    }
}
