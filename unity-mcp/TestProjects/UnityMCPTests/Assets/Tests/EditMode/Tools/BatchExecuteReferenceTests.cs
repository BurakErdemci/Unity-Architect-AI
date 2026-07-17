using NUnit.Framework;
using UnityEngine;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Tools;

namespace MCPForUnityTests.Editor.Tools
{
    /// <summary>
    /// Verifies batch_execute reference chaining: "$[i].path" param values resolve
    /// against earlier command results, and invalid references fail loudly.
    /// </summary>
    public class BatchExecuteReferenceTests
    {
        [OneTimeSetUp]
        public void OneTimeSetUp()
        {
            CommandRegistry.Initialize();
        }

        [Test]
        public void CreateThenModify_ViaInstanceIdReference_Chains()
        {
            string goName = "BatchRefGO_" + System.Guid.NewGuid().ToString("N").Substring(0, 8);
            GameObject created = null;

            try
            {
                var batchParams = new JObject
                {
                    ["commands"] = new JArray
                    {
                        new JObject
                        {
                            ["tool"] = "manage_gameobject",
                            ["params"] = new JObject
                            {
                                ["action"] = "create",
                                ["name"] = goName
                            }
                        },
                        new JObject
                        {
                            ["tool"] = "manage_gameobject",
                            ["params"] = new JObject
                            {
                                ["action"] = "modify",
                                ["target"] = "$[0].data.instanceID",
                                ["search_method"] = "by_id",
                                ["position"] = new JArray { 1.0f, 2.0f, 3.0f }
                            }
                        }
                    }
                };

                var result = BatchExecute.HandleCommand(batchParams).GetAwaiter().GetResult();
                var resultObj = JObject.FromObject(result);

                Assert.IsTrue(resultObj.Value<bool>("success"), $"Chained batch should succeed: {resultObj}");

                created = GameObject.Find(goName);
                Assert.IsNotNull(created, $"GameObject '{goName}' should exist in scene");
                Assert.AreEqual(new Vector3(1f, 2f, 3f), created.transform.localPosition,
                    "Second command should have modified the object created by the first via '$[0].data.instanceID'");
            }
            finally
            {
                if (created != null)
                    Object.DestroyImmediate(created);
            }
        }

        [Test]
        public void ForwardReference_FailsThatCommandWithClearError()
        {
            var batchParams = new JObject
            {
                ["commands"] = new JArray
                {
                    new JObject
                    {
                        ["tool"] = "manage_gameobject",
                        ["params"] = new JObject
                        {
                            ["action"] = "modify",
                            ["target"] = "$[1].data.instanceID",
                            ["search_method"] = "by_id",
                            ["set_active"] = false
                        }
                    }
                }
            };

            var result = BatchExecute.HandleCommand(batchParams).GetAwaiter().GetResult();
            var resultObj = JObject.FromObject(result);

            Assert.IsFalse(resultObj.Value<bool>("success"), "Forward reference should fail the batch");
            string firstError = resultObj.SelectToken("data.results[0].error")?.ToString();
            StringAssert.Contains("has not executed yet", firstError,
                "Error should explain that references may only point to earlier commands");
        }

        [Test]
        public void MissingPath_FailsWithAvailableKeysHint()
        {
            string goName = "BatchRefGO_" + System.Guid.NewGuid().ToString("N").Substring(0, 8);
            GameObject created = null;

            try
            {
                var batchParams = new JObject
                {
                    ["commands"] = new JArray
                    {
                        new JObject
                        {
                            ["tool"] = "manage_gameobject",
                            ["params"] = new JObject
                            {
                                ["action"] = "create",
                                ["name"] = goName
                            }
                        },
                        new JObject
                        {
                            ["tool"] = "manage_gameobject",
                            ["params"] = new JObject
                            {
                                ["action"] = "modify",
                                ["target"] = "$[0].data.noSuchKey",
                                ["search_method"] = "by_id",
                                ["set_active"] = false
                            }
                        }
                    }
                };

                var result = BatchExecute.HandleCommand(batchParams).GetAwaiter().GetResult();
                var resultObj = JObject.FromObject(result);

                Assert.IsFalse(resultObj.Value<bool>("success"), "Missing reference path should fail the batch");
                string secondError = resultObj.SelectToken("data.results[1].error")?.ToString();
                StringAssert.Contains("not found in the result", secondError,
                    "Error should say the path was not found in the referenced result");
            }
            finally
            {
                created = GameObject.Find(goName);
                if (created != null)
                    Object.DestroyImmediate(created);
            }
        }

        [Test]
        public void NonReferenceStrings_AreLeftUntouched()
        {
            string goName = "BatchRefGO_" + System.Guid.NewGuid().ToString("N").Substring(0, 8);
            GameObject created = null;

            try
            {
                // "$100 prize" starts with '$' but is not a "$[i]" reference — must pass through as-is.
                var batchParams = new JObject
                {
                    ["commands"] = new JArray
                    {
                        new JObject
                        {
                            ["tool"] = "manage_gameobject",
                            ["params"] = new JObject
                            {
                                ["action"] = "create",
                                ["name"] = goName,
                                ["tag"] = "Untagged"
                            }
                        }
                    }
                };

                var result = BatchExecute.HandleCommand(batchParams).GetAwaiter().GetResult();
                var resultObj = JObject.FromObject(result);

                Assert.IsTrue(resultObj.Value<bool>("success"), $"Batch without references should succeed: {resultObj}");

                created = GameObject.Find(goName);
                Assert.IsNotNull(created, "Plain string params should be untouched by reference resolution");
            }
            finally
            {
                if (created != null)
                    Object.DestroyImmediate(created);
            }
        }
    }
}
