using System.Collections;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine.TestTools;
using MCPForUnity.Editor.Tools;
using static MCPForUnityTests.Editor.TestUtilities;

namespace MCPForUnityTests.Editor.Tools
{
    // HandleCommand async Task<object> döndürür (AssemblyBuilder derlemesi editor
    // update loop'unda tamamlanır) → testler [UnityTest] coroutine ile task'ı
    // poll'lar. Ana thread'i bloklamak (task.Result) derlemeyi kilitler — yapma.
    public class ExecuteCodeTests
    {
        [SetUp]
        public void SetUp()
        {
            // clear_history senkron tamamlanır (await'siz yol) — Result güvenli.
            ExecuteCode.HandleCommand(new JObject { ["action"] = "clear_history" }).GetAwaiter().GetResult();
        }

        // ──────────────────── Execute: success cases ────────────────────

        [UnityTest]
        public IEnumerator Execute_ReturnString_ReturnsSuccess()
        {
            var t = Execute("return \"hello\";");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual("hello", result["data"]["result"].Value<string>());
        }

        [UnityTest]
        public IEnumerator Execute_ReturnInt_ReturnsSuccess()
        {
            var t = Execute("return 42;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual(42, result["data"]["result"].Value<int>());
        }

        [UnityTest]
        public IEnumerator Execute_ReturnNull_NoResultValue()
        {
            var t = Execute("int x = 1; return null;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            var data = result["data"] as JObject;
            if (data != null)
                Assert.IsNull(data["result"], "Expected no 'result' key when code returns null");
        }

        [UnityTest]
        public IEnumerator Execute_VoidReturn_Succeeds()
        {
            var t = Execute("UnityEngine.Debug.Log(\"test\"); return null;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
        }

        [UnityTest]
        public IEnumerator Execute_UnityAPI_CanAccessSceneManager()
        {
            var t = Execute(
                "var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();\n" +
                "return scene.name;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.IsNotNull(result["data"]["result"]);
        }

        [UnityTest]
        public IEnumerator Execute_Generics_ListOfString()
        {
            var t = Execute(
                "var list = new System.Collections.Generic.List<string>();\n" +
                "list.Add(\"a\"); list.Add(\"b\");\n" +
                "return list;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            var arr = result["data"]["result"] as JArray;
            Assert.IsNotNull(arr, "Expected array result");
            Assert.AreEqual(2, arr.Count);
        }

        [UnityTest]
        public IEnumerator Execute_LINQ_SelectWorks()
        {
            var t = Execute(
                "var nums = new int[] { 1, 2, 3 };\n" +
                "return nums.Select(n => n * 2).ToList();");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            var arr = result["data"]["result"] as JArray;
            Assert.IsNotNull(arr);
            Assert.AreEqual(3, arr.Count);
            Assert.AreEqual(2, arr[0].Value<int>());
            Assert.AreEqual(6, arr[2].Value<int>());
        }

        [UnityTest]
        public IEnumerator Execute_Dictionary_ReturnsStructured()
        {
            var t = Execute(
                "var dict = new Dictionary<string, int> { { \"a\", 1 }, { \"b\", 2 } };\n" +
                "return dict;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.IsNotNull(result["data"]["result"]);
        }

        [UnityTest]
        public IEnumerator Execute_ProjectTypes_AreAccessible()
        {
            // AssemblyBuilder referans seti proje assembly'lerini içermeli —
            // testin kendi tipine (bu sınıf) kod içinden erişilebilmeli.
            var t = Execute(
                "return typeof(MCPForUnityTests.Editor.Tools.ExecuteCodeTests).Name;");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual("ExecuteCodeTests", result["data"]["result"].Value<string>());
        }

        // ──────────────────── Execute: error cases ────────────────────

        [UnityTest]
        public IEnumerator Execute_CompilationError_ReturnsErrors()
        {
            var t = Execute("int x = \"not an int\";");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("Compilation failed", result.Value<string>("error"));
            Assert.IsNotNull(result["data"]["errors"]);
        }

        [UnityTest]
        public IEnumerator Execute_RuntimeException_ReturnsError()
        {
            var t = Execute("throw new System.Exception(\"boom\");");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("boom", result.Value<string>("error"));
        }

        [UnityTest]
        public IEnumerator Execute_MissingCode_ReturnsError()
        {
            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "execute"
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("code", result.Value<string>("error").ToLowerInvariant());
        }

        [UnityTest]
        public IEnumerator Execute_EmptyCode_ReturnsError()
        {
            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "execute",
                ["code"] = "   "
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
        }

        // ──────────────────── Safety checks ────────────────────

        [UnityTest]
        public IEnumerator Execute_SafetyChecks_BlocksFileDelete()
        {
            var t = Execute("System.IO.File.Delete(\"x\");");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("Blocked pattern", result.Value<string>("error"));
        }

        [UnityTest]
        public IEnumerator Execute_SafetyChecks_BlocksProcessStart()
        {
            var t = Execute("Process.Start(\"cmd\");");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("Blocked pattern", result.Value<string>("error"));
        }

        [UnityTest]
        public IEnumerator Execute_SafetyChecks_BlocksInfiniteLoop()
        {
            var t = Execute("while (true) { }");
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("Blocked pattern", result.Value<string>("error"));
        }

        [UnityTest]
        public IEnumerator Execute_SafetyChecksDisabled_AllowsBlockedPattern()
        {
            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "execute",
                ["code"] = "while (true) { break; }  return null;",
                ["safety_checks"] = false
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            if (!result.Value<bool>("success"))
            {
                var error = result.Value<string>("error") ?? "";
                Assert.IsFalse(error.Contains("Blocked pattern"),
                    "Safety checks should be disabled but still blocked");
            }
        }

        // ──────────────────── History ────────────────────

        [UnityTest]
        public IEnumerator GetHistory_Empty_ReturnsZero()
        {
            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "get_history"
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual(0, result["data"]["total"].Value<int>());
        }

        [UnityTest]
        public IEnumerator GetHistory_AfterExecution_RecordsEntry()
        {
            var exec = Execute("return 1;");
            while (!exec.IsCompleted) yield return null;

            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "get_history"
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual(1, result["data"]["total"].Value<int>());
            var entries = result["data"]["entries"] as JArray;
            Assert.IsNotNull(entries);
            Assert.AreEqual(1, entries.Count);
            Assert.IsTrue(entries[0]["success"].Value<bool>());
        }

        [UnityTest]
        public IEnumerator GetHistory_Limit_RespectsParameter()
        {
            foreach (var code in new[] { "return 1;", "return 2;", "return 3;" })
            {
                var exec = Execute(code);
                while (!exec.IsCompleted) yield return null;
            }

            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "get_history",
                ["limit"] = 2
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual(3, result["data"]["total"].Value<int>());
            var entries = result["data"]["entries"] as JArray;
            Assert.AreEqual(2, entries.Count);
        }

        [UnityTest]
        public IEnumerator ClearHistory_RemovesAll()
        {
            foreach (var code in new[] { "return 1;", "return 2;" })
            {
                var exec = Execute(code);
                while (!exec.IsCompleted) yield return null;
            }

            var clear = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "clear_history"
            });
            while (!clear.IsCompleted) yield return null;
            var clearResult = ToJObject(clear.Result);
            Assert.IsTrue(clearResult.Value<bool>("success"), clearResult.ToString());

            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "get_history"
            });
            while (!t.IsCompleted) yield return null;
            var historyResult = ToJObject(t.Result);
            Assert.AreEqual(0, historyResult["data"]["total"].Value<int>());
        }

        // ──────────────────── Replay ────────────────────

        [UnityTest]
        public IEnumerator Replay_ValidIndex_ReExecutes()
        {
            var exec = Execute("return 42;");
            while (!exec.IsCompleted) yield return null;

            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "replay",
                ["index"] = 0
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsTrue(result.Value<bool>("success"), result.ToString());
            Assert.AreEqual(42, result["data"]["result"].Value<int>());
        }

        [UnityTest]
        public IEnumerator Replay_InvalidIndex_ReturnsError()
        {
            var exec = Execute("return 1;");
            while (!exec.IsCompleted) yield return null;

            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "replay",
                ["index"] = 99
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("Invalid history index", result.Value<string>("error"));
        }

        [UnityTest]
        public IEnumerator Replay_EmptyHistory_ReturnsError()
        {
            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "replay",
                ["index"] = 0
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
        }

        // ──────────────────── Action validation ────────────────────

        [UnityTest]
        public IEnumerator UnknownAction_ReturnsError()
        {
            var t = ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "invalid_action"
            });
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
            StringAssert.Contains("Unknown action", result.Value<string>("error"));
        }

        [UnityTest]
        public IEnumerator NullParams_ReturnsError()
        {
            var t = ExecuteCode.HandleCommand(null);
            while (!t.IsCompleted) yield return null;
            var result = ToJObject(t.Result);

            Assert.IsFalse(result.Value<bool>("success"), result.ToString());
        }

        // ──────────────────── Helpers ────────────────────

        private static Task<object> Execute(string code)
        {
            return ExecuteCode.HandleCommand(new JObject
            {
                ["action"] = "execute",
                ["code"] = code
            });
        }
    }
}
