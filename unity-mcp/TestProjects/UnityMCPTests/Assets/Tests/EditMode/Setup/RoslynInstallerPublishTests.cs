using System;
using System.IO;
using System.Text;
using MCPForUnity.Editor.Setup;
using NUnit.Framework;

namespace MCPForUnityTests.Editor.Setup
{
    /// <summary>
    /// Tests for the folder swap that puts the Roslyn DLLs in place. The digest gate proves
    /// the bytes are right; these prove the destination never ends up holding a mix of old
    /// and new ones, because mixed Roslyn assemblies load happily and then fail at unrelated
    /// call sites with missing-member errors.
    ///
    /// The tests work on a scratch folder outside the project, not on Assets/Plugins/Roslyn,
    /// so nothing here imports assets or touches a real install.
    /// </summary>
    public class RoslynInstallerPublishTests
    {
        private string root;
        private string dest;

        private const string StagingSuffix = ".mcp-staging~";
        private const string BackupSuffix = ".mcp-backup~";

        [SetUp]
        public void SetUp()
        {
            root = Path.Combine(Path.GetTempPath(), "MCPForUnityRoslynPublish", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            dest = Path.Combine(root, "Roslyn");
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(root))
                Directory.Delete(root, true);
        }

        private static byte[] Bytes(string s)
        {
            return Encoding.UTF8.GetBytes(s);
        }

        private void AssertNoScratchFoldersLeft()
        {
            Assert.IsFalse(Directory.Exists(dest + StagingSuffix), "staging folder was left behind");
            Assert.IsFalse(Directory.Exists(dest + BackupSuffix), "backup folder was left behind");
        }

        [Test]
        public void FreshInstall_WritesEveryFile()
        {
            RoslynInstaller.PublishFolderAtomically(
                dest,
                new[] { "A.dll", "B.dll" },
                new[] { Bytes("alpha"), Bytes("beta") });

            Assert.AreEqual("alpha", File.ReadAllText(Path.Combine(dest, "A.dll")));
            Assert.AreEqual("beta", File.ReadAllText(Path.Combine(dest, "B.dll")));
            AssertNoScratchFoldersLeft();
        }

        [Test]
        public void Reinstall_ReplacesEveryFile_AndKeepsMetaAndForeignFiles()
        {
            Directory.CreateDirectory(dest);
            File.WriteAllText(Path.Combine(dest, "A.dll"), "old-alpha");
            File.WriteAllText(Path.Combine(dest, "B.dll"), "old-beta");
            // .meta carries the asset GUID and the plugin import settings. A swap that dropped
            // it would silently re-import the DLLs with default settings under new GUIDs.
            File.WriteAllText(Path.Combine(dest, "A.dll.meta"), "guid: 1234");
            File.WriteAllText(Path.Combine(dest, "UserDropped.dll"), "not ours");

            RoslynInstaller.PublishFolderAtomically(
                dest,
                new[] { "A.dll", "B.dll" },
                new[] { Bytes("new-alpha"), Bytes("new-beta") });

            Assert.AreEqual("new-alpha", File.ReadAllText(Path.Combine(dest, "A.dll")));
            Assert.AreEqual("new-beta", File.ReadAllText(Path.Combine(dest, "B.dll")));
            Assert.AreEqual("guid: 1234", File.ReadAllText(Path.Combine(dest, "A.dll.meta")));
            Assert.AreEqual("not ours", File.ReadAllText(Path.Combine(dest, "UserDropped.dll")));
            AssertNoScratchFoldersLeft();
        }

        [Test]
        public void WriteFailureOnSecondFile_LeavesPreviousInstallIntact()
        {
            // The regression this guards: writing the set straight into the destination meant a
            // failure on the second file left the first one already replaced.
            Directory.CreateDirectory(dest);
            File.WriteAllText(Path.Combine(dest, "A.dll"), "old-alpha");
            File.WriteAllText(Path.Combine(dest, "C.dll"), "old-gamma");

            // A directory sitting where the second file must be written makes that one write —
            // and only that one — fail. It stands in for any mid-set failure (full volume,
            // permissions, the process dying): what the test needs is an exception that lands
            // after file one has already been written.
            Directory.CreateDirectory(Path.Combine(dest, "B.dll"));

            Assert.Catch<Exception>(() => RoslynInstaller.PublishFolderAtomically(
                dest,
                new[] { "A.dll", "B.dll", "C.dll" },
                new[] { Bytes("new-alpha"), Bytes("new-beta"), Bytes("new-gamma") }));

            Assert.AreEqual("old-alpha", File.ReadAllText(Path.Combine(dest, "A.dll")),
                "the first DLL was replaced even though the install failed");
            Assert.AreEqual("old-gamma", File.ReadAllText(Path.Combine(dest, "C.dll")),
                "the destination was modified by a failed install");
            Assert.IsTrue(Directory.Exists(Path.Combine(dest, "B.dll")),
                "the previous destination contents did not survive the failure");
            AssertNoScratchFoldersLeft();
        }

        [Test]
        public void WriteFailureWithNothingInstalled_CreatesNoDestination()
        {
            Assert.Catch<Exception>(() => RoslynInstaller.PublishFolderAtomically(
                dest,
                new[] { "A.dll", "missing-subfolder/B.dll" },
                new[] { Bytes("alpha"), Bytes("beta") }));

            Assert.IsFalse(Directory.Exists(dest),
                "a failed first install created a half-filled destination folder");
            AssertNoScratchFoldersLeft();
        }
    }
}
