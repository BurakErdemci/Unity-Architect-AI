using System;
using System.Diagnostics;
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

        [Test]
        [Platform(Exclude = "Win", Reason = "the leftover folder is made undeletable with a Unix permission bit")]
        public void UnclearableStagingRemnant_AbortsBeforeCreatingTheDestination()
        {
            // Staging carries a fixed name so a killed run's folder gets reclaimed instead of
            // accumulating. When that reclaim fails, carrying on is what produces the mixed
            // assembly set the swap exists to prevent: staging survives with a dead run's
            // files in it, CreateDirectory accepts the folder that is already there, and the
            // final rename puts those files in the destination. Refusing to start is the only
            // outcome that keeps the published set equal to the verified input.
            CreateUnclearableStagingRemnant();
            try
            {
                Assert.Catch<Exception>(() => RoslynInstaller.PublishFolderAtomically(
                    dest,
                    new[] { "A.dll" },
                    new[] { Bytes("alpha") }));

                Assert.IsFalse(Directory.Exists(dest),
                    "a publish went ahead on top of a staging folder that could not be cleared");
            }
            finally
            {
                RestoreScratchPermissions();
            }
        }

        [Test]
        [Platform(Exclude = "Win", Reason = "the leftover folder is made undeletable with a Unix permission bit")]
        public void UnclearableStagingRemnant_NeitherPublishesItNorDisturbsTheInstall()
        {
            Directory.CreateDirectory(dest);
            File.WriteAllText(Path.Combine(dest, "A.dll"), "old-alpha");

            CreateUnclearableStagingRemnant();
            try
            {
                Assert.Catch<Exception>(() => RoslynInstaller.PublishFolderAtomically(
                    dest,
                    new[] { "A.dll" },
                    new[] { Bytes("new-alpha") }));

                Assert.IsFalse(File.Exists(Path.Combine(dest, LockedFolderName, "remnant.dll")),
                    "a dead run's file was published into the destination");
                Assert.AreEqual("old-alpha", File.ReadAllText(Path.Combine(dest, "A.dll")),
                    "the working install was replaced by an install that could not be staged");
            }
            finally
            {
                RestoreScratchPermissions();
            }
        }

        private const string LockedFolderName = "locked";

        /// <summary>
        /// Leaves behind the staging folder of a run that died mid-swap, and makes it
        /// impossible to delete. On Unix a file is unlinked by writing to the folder that
        /// holds it, so dropping the write bit on an inner folder blocks the recursive delete
        /// while leaving staging itself writable — the same shape as a Windows Editor holding
        /// one DLL open, which is the ordinary way this happens in the field.
        /// Callers must run <see cref="RestoreScratchPermissions"/> afterwards, otherwise the
        /// scratch tree cannot be torn down and the next run starts dirty.
        /// </summary>
        private void CreateUnclearableStagingRemnant()
        {
            string staging = dest + StagingSuffix;
            string locked = Path.Combine(staging, LockedFolderName);
            Directory.CreateDirectory(locked);
            File.WriteAllText(Path.Combine(locked, "remnant.dll"), "left behind by a dead run");

            if (!Chmod("0555 \"" + locked + "\""))
                Assert.Fail("chmod could not run, so this environment cannot build the leftover folder under test");

            // Proving the block instead of assuming it. Running as root, or on a filesystem
            // that ignores permission bits, the delete below succeeds — and the test would
            // then exercise an ordinary clean staging path while still reporting green.
            try
            {
                Directory.Delete(staging, true);
            }
            catch (Exception)
            {
                return;
            }

            Assert.Fail("the staging remnant deleted cleanly despite chmod 0555; this environment cannot reproduce the failure under test");
        }

        /// <summary>
        /// Puts the write bit back across the whole scratch tree. Recursive from the root
        /// rather than aimed at the folder that was locked, because a publish that wrongly
        /// went ahead has renamed that folder into the destination.
        /// </summary>
        private void RestoreScratchPermissions()
        {
            Chmod("-R u+rwX \"" + root + "\"");
        }

        /// <summary>
        /// Runs /bin/chmod. File.SetUnixFileMode does not exist in the .NET profile Unity
        /// 2021 ships, so the permission change has to go through the binary.
        /// </summary>
        private static bool Chmod(string arguments)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("/bin/chmod", arguments)
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardError = true
                };

                using (Process process = Process.Start(psi))
                {
                    process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    return process.ExitCode == 0;
                }
            }
            catch (Exception)
            {
                return false;
            }
        }
    }
}
