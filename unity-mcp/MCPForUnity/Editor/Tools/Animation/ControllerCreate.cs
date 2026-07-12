using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Helpers;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace MCPForUnity.Editor.Tools.Animation
{
    internal static class ControllerCreate
    {
        public static object Create(JObject @params)
        {
            string controllerPath = @params["controllerPath"]?.ToString();
            if (string.IsNullOrEmpty(controllerPath))
                return new { success = false, message = "'controllerPath' is required (e.g. 'Assets/Animations/Player.controller')" };

            controllerPath = AssetPathUtility.SanitizeAssetPath(controllerPath);
            if (controllerPath == null)
                return new { success = false, message = "Invalid asset path" };

            if (!controllerPath.EndsWith(".controller", StringComparison.OrdinalIgnoreCase))
                controllerPath += ".controller";

            string dir = Path.GetDirectoryName(controllerPath)?.Replace('\\', '/');
            if (!string.IsNullOrEmpty(dir) && !AssetDatabase.IsValidFolder(dir))
                CreateFoldersRecursive(dir);

            var existing = AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
            if (existing != null)
                return new { success = false, message = $"AnimatorController already exists at '{controllerPath}'. Delete it first or use a different path." };

            var controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
            AssetDatabase.SaveAssets();

            return new
            {
                success = true,
                message = $"Created AnimatorController at '{controllerPath}'",
                data = new
                {
                    path = controllerPath,
                    name = controller.name,
                    layerCount = controller.layers.Length,
                    parameterCount = controller.parameters.Length
                }
            };
        }

        public static object AddState(JObject @params)
        {
            var controller = LoadController(@params);
            if (controller == null)
                return ControllerNotFoundError(@params);

            string stateName = @params["stateName"]?.ToString();
            if (string.IsNullOrEmpty(stateName))
                return new { success = false, message = "'stateName' is required" };

            int layerIndex = @params["layerIndex"]?.ToObject<int>() ?? 0;
            if (layerIndex < 0 || layerIndex >= controller.layers.Length)
                return new { success = false, message = $"Layer index {layerIndex} out of range (controller has {controller.layers.Length} layers)" };

            var rootStateMachine = controller.layers[layerIndex].stateMachine;

            // Check for duplicate state name
            foreach (var existingState in rootStateMachine.states)
            {
                if (existingState.state.name == stateName)
                    return new { success = false, message = $"State '{stateName}' already exists in layer {layerIndex}" };
            }

            var state = rootStateMachine.AddState(stateName);

            // Optionally assign a clip
            string clipPath = @params["clipPath"]?.ToString();
            if (!string.IsNullOrEmpty(clipPath))
            {
                clipPath = AssetPathUtility.SanitizeAssetPath(clipPath);
                if (clipPath != null)
                {
                    var clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
                    if (clip != null)
                        state.motion = clip;
                }
            }

            float speed = @params["speed"]?.ToObject<float>() ?? 1f;
            state.speed = speed;

            bool isDefault = @params["isDefault"]?.ToObject<bool>() ?? false;
            if (isDefault)
                rootStateMachine.defaultState = state;

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            return new
            {
                success = true,
                message = $"Added state '{stateName}' to layer {layerIndex}",
                data = new
                {
                    stateName,
                    layerIndex,
                    hasMotion = state.motion != null,
                    speed = state.speed,
                    isDefault
                }
            };
        }

        public static object AddTransition(JObject @params)
        {
            var controller = LoadController(@params);
            if (controller == null)
                return ControllerNotFoundError(@params);

            string fromStateName = @params["fromState"]?.ToString();
            string toStateName = @params["toState"]?.ToString();
            if (string.IsNullOrEmpty(fromStateName) || string.IsNullOrEmpty(toStateName))
                return new { success = false, message = "'fromState' and 'toState' are required" };

            int layerIndex = @params["layerIndex"]?.ToObject<int>() ?? 0;
            if (layerIndex < 0 || layerIndex >= controller.layers.Length)
                return new { success = false, message = $"Layer index {layerIndex} out of range (controller has {controller.layers.Length} layers: 0..{controller.layers.Length - 1})" };

            var rootStateMachine = controller.layers[layerIndex].stateMachine;

            bool isAnyState = ControllerTransitions.IsAnyStateName(fromStateName);

            AnimatorState toState = null;
            foreach (var cs in rootStateMachine.states)
            {
                if (cs.state.name == toStateName) toState = cs.state;
            }

            if (toState == null)
                return new { success = false, message = $"State '{toStateName}' not found in layer {layerIndex}. Available states: [{string.Join(", ", ControllerTransitions.StateNames(rootStateMachine))}]" };

            AnimatorState fromState = null;
            if (!isAnyState)
            {
                foreach (var cs in rootStateMachine.states)
                {
                    if (cs.state.name == fromStateName) fromState = cs.state;
                }

                if (fromState == null)
                    return new { success = false, message = $"State '{fromStateName}' not found in layer {layerIndex}. Available states: [{string.Join(", ", ControllerTransitions.StateNames(rootStateMachine))}]" };
            }

            // Validate ALL provided properties (incl. conditions, enums, condition-parameter
            // existence) BEFORE creating the transition — invalid input leaves the controller untouched.
            var edit = ControllerTransitions.ValidateProperties(controller, @params, out object validationError);
            if (edit == null)
                return validationError;

            AnimatorStateTransition transition;
            if (isAnyState)
            {
                transition = rootStateMachine.AddAnyStateTransition(toState);
                fromStateName = "AnyState";
            }
            else
            {
                transition = fromState.AddTransition(toState);
            }

            // Historical defaults (backward compatible), then apply provided overrides.
            transition.hasExitTime = true;
            transition.duration = 0.25f;
            transition.exitTime = 0.75f;
            edit.ApplyTo(transition);

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            // Per-destination index (the value update/remove accept as 'transitionIndex').
            var sourceTransitions = isAnyState ? rootStateMachine.anyStateTransitions : fromState.transitions;
            int newIndex = 0;
            foreach (var t in sourceTransitions)
            {
                if (ReferenceEquals(t, transition)) break;
                if (ControllerTransitions.DestinationName(t) == toStateName) newIndex++;
            }

            return new
            {
                success = true,
                message = $"Added transition from '{fromStateName}' to '{toStateName}' (#{newIndex}) with {transition.conditions.Length} conditions",
                data = new
                {
                    controllerPath = AssetDatabase.GetAssetPath(controller),
                    layerIndex,
                    transition = ControllerTransitions.SerializeTransition(fromStateName, newIndex, transition)
                }
            };
        }

        public static object AddParameter(JObject @params)
        {
            var controller = LoadController(@params);
            if (controller == null)
                return ControllerNotFoundError(@params);

            string paramName = @params["parameterName"]?.ToString();
            if (string.IsNullOrEmpty(paramName))
                return new { success = false, message = "'parameterName' is required" };

            string typeStr = @params["parameterType"]?.ToString()?.ToLowerInvariant() ?? "float";

            AnimatorControllerParameterType paramType;
            switch (typeStr)
            {
                case "float": paramType = AnimatorControllerParameterType.Float; break;
                case "int":
                case "integer": paramType = AnimatorControllerParameterType.Int; break;
                case "bool":
                case "boolean": paramType = AnimatorControllerParameterType.Bool; break;
                case "trigger": paramType = AnimatorControllerParameterType.Trigger; break;
                default:
                    return new { success = false, message = $"Unknown parameter type '{typeStr}'. Valid: float, int, bool, trigger" };
            }

            // Check for duplicate
            foreach (var existing in controller.parameters)
            {
                if (existing.name == paramName)
                    return new { success = false, message = $"Parameter '{paramName}' already exists" };
            }

            controller.AddParameter(paramName, paramType);

            // Set default value if provided
            JToken defaultValue = @params["defaultValue"];
            if (defaultValue != null)
            {
                var allParams = controller.parameters;
                var addedParam = allParams[allParams.Length - 1];

                switch (paramType)
                {
                    case AnimatorControllerParameterType.Float:
                        addedParam.defaultFloat = defaultValue.ToObject<float>();
                        break;
                    case AnimatorControllerParameterType.Int:
                        addedParam.defaultInt = defaultValue.ToObject<int>();
                        break;
                    case AnimatorControllerParameterType.Bool:
                        addedParam.defaultBool = defaultValue.ToObject<bool>();
                        break;
                }

                controller.parameters = allParams;
            }

            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();

            return new
            {
                success = true,
                message = $"Added {typeStr} parameter '{paramName}'",
                data = new
                {
                    parameterName = paramName,
                    parameterType = typeStr,
                    totalParameters = controller.parameters.Length
                }
            };
        }

        public static object GetInfo(JObject @params)
        {
            var controller = LoadController(@params);
            if (controller == null)
                return ControllerNotFoundError(@params);

            var layers = new List<object>();
            for (int i = 0; i < controller.layers.Length; i++)
            {
                var layer = controller.layers[i];
                var states = new List<object>();
                foreach (var cs in layer.stateMachine.states)
                {
                    // Full transition serialization (incl. interruptionSource, offset, solo/mute)
                    // with per-destination 'index' — the same value update/remove take as transitionIndex.
                    var transitions = ControllerTransitions.SerializeTransitionList(cs.state.name, cs.state.transitions);

                    states.Add(new
                    {
                        name = cs.state.name,
                        speed = cs.state.speed,
                        hasMotion = cs.state.motion != null,
                        motionName = cs.state.motion?.name,
                        isDefault = layer.stateMachine.defaultState == cs.state,
                        transitionCount = cs.state.transitions.Length,
                        transitions
                    });
                }

                // AnyState transitions live on the state machine, not on any state —
                // previously they were invisible in get_info.
                var anyStateTransitions = ControllerTransitions.SerializeTransitionList(
                    "AnyState", layer.stateMachine.anyStateTransitions);

                layers.Add(new
                {
                    index = i,
                    name = layer.name,
                    stateCount = layer.stateMachine.states.Length,
                    states,
                    anyStateTransitionCount = layer.stateMachine.anyStateTransitions.Length,
                    anyStateTransitions
                });
            }

            var parameters = new List<object>();
            foreach (var p in controller.parameters)
            {
                parameters.Add(new
                {
                    name = p.name,
                    type = p.type.ToString(),
                    defaultFloat = p.defaultFloat,
                    defaultInt = p.defaultInt,
                    defaultBool = p.defaultBool
                });
            }

            return new
            {
                success = true,
                data = new
                {
                    path = AssetDatabase.GetAssetPath(controller),
                    name = controller.name,
                    layerCount = controller.layers.Length,
                    parameterCount = controller.parameters.Length,
                    layers,
                    parameters
                }
            };
        }

        public static object AssignToGameObject(JObject @params)
        {
            var controller = LoadController(@params);
            if (controller == null)
                return ControllerNotFoundError(@params);

            var go = ObjectResolver.ResolveGameObject(@params["target"], @params["searchMethod"]?.ToString());
            if (go == null)
                return new { success = false, message = "Target GameObject not found" };

            var animator = go.GetComponent<Animator>();
            if (animator == null)
            {
                Undo.RecordObject(go, "Add Animator Component");
                animator = Undo.AddComponent<Animator>(go);
            }

            Undo.RecordObject(animator, "Assign AnimatorController");
            animator.runtimeAnimatorController = controller;
            EditorUtility.SetDirty(go);
            AssetDatabase.SaveAssets();

            return new
            {
                success = true,
                message = $"Assigned controller '{controller.name}' to '{go.name}'",
                data = new
                {
                    gameObject = go.name,
                    controllerName = controller.name,
                    controllerPath = AssetDatabase.GetAssetPath(controller)
                }
            };
        }

        internal static AnimatorController LoadController(JObject @params)
        {
            string controllerPath = @params["controllerPath"]?.ToString();
            if (string.IsNullOrEmpty(controllerPath))
                return null;

            controllerPath = AssetPathUtility.SanitizeAssetPath(controllerPath);
            if (controllerPath == null)
                return null;

            return AssetDatabase.LoadAssetAtPath<AnimatorController>(controllerPath);
        }

        internal static object ControllerNotFoundError(JObject @params)
        {
            string path = @params["controllerPath"]?.ToString() ?? "(not specified)";
            return new { success = false, message = $"AnimatorController not found at '{path}'. Provide a valid 'controllerPath'." };
        }

        private static void CreateFoldersRecursive(string folderPath)
        {
            if (AssetDatabase.IsValidFolder(folderPath))
                return;

            string parent = Path.GetDirectoryName(folderPath)?.Replace('\\', '/');
            if (!string.IsNullOrEmpty(parent) && parent != "Assets" && !AssetDatabase.IsValidFolder(parent))
                CreateFoldersRecursive(parent);

            string folderName = Path.GetFileName(folderPath);
            if (!string.IsNullOrEmpty(parent) && !string.IsNullOrEmpty(folderName))
                AssetDatabase.CreateFolder(parent, folderName);
        }
    }
}
