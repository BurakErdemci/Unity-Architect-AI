using System.Linq;
using NUnit.Framework;
using UnityEngine;
using Newtonsoft.Json.Linq;
using MCPForUnity.Editor.Tools;

namespace MCPForUnityTests.Editor.Tools
{
    /// <summary>
    /// Verifies find_gameobjects match_mode (exact/contains/prefix) and the
    /// lightweight per-object summary (instanceID/name/path) in responses.
    /// </summary>
    public class FindGameObjectsMatchModeTests
    {
        private GameObject propA;
        private GameObject propB;
        private GameObject other;

        [SetUp]
        public void SetUp()
        {
            propA = new GameObject("Prop_VendingMachine");
            propB = new GameObject("Prop_Terminal");
            other = new GameObject("MainCamera_Test");
        }

        [TearDown]
        public void TearDown()
        {
            foreach (var go in new[] { propA, propB, other })
            {
                if (go != null)
                    Object.DestroyImmediate(go);
            }
        }

        private static JObject Search(string term, string matchMode = null)
        {
            var @params = new JObject
            {
                ["searchMethod"] = "by_name",
                ["searchTerm"] = term
            };
            if (matchMode != null)
            {
                @params["matchMode"] = matchMode;
            }

            return JObject.FromObject(FindGameObjects.HandleCommand(@params));
        }

        private static string[] Names(JObject result)
        {
            return result.SelectToken("data.objects")
                .Select(o => o.Value<string>("name"))
                .ToArray();
        }

        [Test]
        public void ExactMode_IsDefault_AndCaseSensitive()
        {
            var result = Search("Prop_VendingMachine");
            Assert.IsTrue(result.Value<bool>("success"), $"Search should succeed: {result}");
            CollectionAssert.AreEquivalent(new[] { "Prop_VendingMachine" }, Names(result));

            var lower = Search("prop_vendingmachine");
            Assert.AreEqual(0, lower.SelectToken("data.instanceIDs").Count(),
                "Exact match should remain case-sensitive");
        }

        [Test]
        public void PrefixMode_FindsAllProps_CaseInsensitive()
        {
            var result = Search("prop_", matchMode: "prefix");
            Assert.IsTrue(result.Value<bool>("success"), $"Search should succeed: {result}");
            CollectionAssert.AreEquivalent(
                new[] { "Prop_VendingMachine", "Prop_Terminal" }, Names(result));
        }

        [Test]
        public void ContainsMode_MatchesSubstring()
        {
            var result = Search("vending", matchMode: "contains");
            Assert.IsTrue(result.Value<bool>("success"), $"Search should succeed: {result}");
            CollectionAssert.AreEquivalent(new[] { "Prop_VendingMachine" }, Names(result));
        }

        [Test]
        public void Objects_Summary_CarriesInstanceIdNameAndPath()
        {
            var result = Search("Prop_Terminal");
            var obj = result.SelectToken("data.objects[0]") as JObject;

            Assert.IsNotNull(obj, $"objects summary should be present: {result}");
            Assert.AreEqual(propB.GetInstanceID(), obj.Value<int>("instanceID"));
            Assert.AreEqual("Prop_Terminal", obj.Value<string>("name"));
            Assert.AreEqual("Prop_Terminal", obj.Value<string>("path"));
        }
    }
}
