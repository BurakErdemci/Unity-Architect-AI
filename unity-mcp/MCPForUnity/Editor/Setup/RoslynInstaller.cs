using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Networking;

namespace MCPForUnity.Editor.Setup
{
    public static class RoslynInstaller
    {
        private const string PluginsRelPath = "Plugins/Roslyn";

        // Staging and backup sit next to the destination, inside Assets/Plugins/, for two
        // reasons. Sharing a parent means sharing a volume, so Directory.Move is a rename
        // the filesystem completes atomically rather than a copy that can stop halfway.
        // And a trailing '~' makes Unity treat a folder as hidden: the asset pipeline never
        // imports it, so a DLL is only ever seen by the Editor once the whole set is in
        // place. A staging folder without that suffix would be imported and loaded, which
        // is the exact failure this indirection exists to prevent.
        private const string StagingFolderSuffix = ".mcp-staging~";
        private const string BackupFolderSuffix = ".mcp-backup~";

        // The DLLs installed here are loaded into the Editor app domain and back the
        // runtime_compilation tool, so a downloaded package is directly executed code.
        // Every entry therefore carries the SHA-256 of the exact .nupkg nuget.org serves
        // for that pinned version; the digest is checked before the archive is opened.
        // To (re)compute one:
        //   curl -sL https://api.nuget.org/v3-flatcontainer/<id>/<ver>/<id>.<ver>.nupkg | shasum -a 256
        private static readonly (string packageId, string version, string dllPath, string dllName, string sha256)[] NuGetEntries =
        {
            ("microsoft.codeanalysis.common",    "4.12.0", "lib/netstandard2.0/Microsoft.CodeAnalysis.dll",       "Microsoft.CodeAnalysis.dll",       "9a6fce286df33cb01e4d5199b6e2f1486fa3a500ce7219f5a321ea041256d87a"),
            ("microsoft.codeanalysis.csharp",    "4.12.0", "lib/netstandard2.0/Microsoft.CodeAnalysis.CSharp.dll","Microsoft.CodeAnalysis.CSharp.dll","9b58b5439a7212ae25028623344f5b6848d3a651fcf9b5f1e70480f9e3267a19"),
            ("system.collections.immutable",     "8.0.0",  "lib/netstandard2.0/System.Collections.Immutable.dll", "System.Collections.Immutable.dll", "17b3958ca370a6a6d487c95389d6ea256622e3bea7b2af67fba934f90551a37c"),
            ("system.reflection.metadata",       "8.0.0",  "lib/netstandard2.0/System.Reflection.Metadata.dll",   "System.Reflection.Metadata.dll",   "750182df425ab880d63565ccad234e2677156b5ba6475b228dacd8c140dd4881"),
        };

        public static bool IsInstalled()
        {
            string folder = Path.Combine(Application.dataPath, PluginsRelPath);
            foreach (var entry in NuGetEntries)
            {
                if (!File.Exists(Path.Combine(folder, entry.dllName)))
                    return false;
            }
            return true;
        }

        public static void Install(bool interactive = true)
        {
            if (IsInstalled() && interactive)
            {
                if (!EditorUtility.DisplayDialog(
                        "Roslyn Already Installed",
                        $"Roslyn DLLs are already present in Assets/{PluginsRelPath}.\nReinstall?",
                        "Reinstall", "Cancel"))
                    return;
            }

            string destFolder = Path.Combine(Application.dataPath, PluginsRelPath);

            try
            {
                // Everything is downloaded, verified and extracted before a single byte is
                // written to Assets/. Writing as we go left a half-installed folder behind
                // whenever one package failed, which IsInstalled() reports as "not installed"
                // but Unity still tries to load.
                byte[][] extractedDlls = new byte[NuGetEntries.Length][];
                string blockedReason = null;

                for (int i = 0; i < NuGetEntries.Length; i++)
                {
                    var (packageId, pkgVersion, dllPathInZip, _, expectedSha256) = NuGetEntries[i];

                    if (interactive)
                    {
                        EditorUtility.DisplayProgressBar(
                            "Installing Roslyn",
                            $"Downloading {packageId} v{pkgVersion}...",
                            (float)i / NuGetEntries.Length);
                    }

                    string url =
                        $"https://api.nuget.org/v3-flatcontainer/{packageId}/{pkgVersion}/{packageId}.{pkgVersion}.nupkg";

                    using (var request = UnityWebRequest.Get(url))
                    {
                        request.timeout = 30;
                        request.SendWebRequest();
                        while (!request.isDone)
                            System.Threading.Thread.Sleep(50);

                        if (request.result != UnityWebRequest.Result.Success)
                            throw new Exception($"Failed to download {packageId}: {request.error}");

                        byte[] nupkgBytes = request.downloadHandler.data;

                        // Verify the raw payload before ZipArchive ever parses it: an
                        // unverified archive is untrusted input, and its DLLs become
                        // executable code the moment they land in Assets/.
                        string integrityError;
                        if (!TryVerifyPackageDigest(nupkgBytes, expectedSha256, out integrityError))
                        {
                            blockedReason = $"{packageId} {pkgVersion} — {integrityError}";
                            Debug.LogError(
                                $"[MCP] Roslyn INTEGRITY CHECK FAILED for {blockedReason}. The download itself " +
                                $"succeeded, but the bytes are not the pinned package, so nothing was extracted " +
                                $"and nothing was written to Assets/{PluginsRelPath}/.");
                            break;
                        }

                        byte[] dllBytes = ExtractFileFromZip(nupkgBytes, dllPathInZip);

                        if (dllBytes == null)
                        {
                            blockedReason = $"{packageId} {pkgVersion} — {dllPathInZip} is missing from the package";
                            Debug.LogError(
                                $"[MCP] Could not find {dllPathInZip} in {packageId}.{pkgVersion}.nupkg. " +
                                "Roslyn installation aborted; nothing was written.");
                            break;
                        }

                        extractedDlls[i] = dllBytes;
                    }
                }

                if (blockedReason != null)
                {
                    if (interactive)
                    {
                        EditorUtility.ClearProgressBar();
                        EditorUtility.DisplayDialog(
                            "Roslyn Installation Blocked",
                            $"A package failed verification and was NOT installed:\n{blockedReason}\n\n" +
                            "This is not a network error — the bytes served did not match the digest pinned in " +
                            "RoslynInstaller. Nothing was copied into your project. See the Console for details.",
                            "OK");
                    }
                    return;
                }

                if (interactive)
                    EditorUtility.DisplayProgressBar("Installing Roslyn", "Installing DLLs...", 0.9f);

                string[] dllNames = new string[NuGetEntries.Length];
                for (int i = 0; i < NuGetEntries.Length; i++)
                    dllNames[i] = NuGetEntries[i].dllName;

                PublishFolderAtomically(destFolder, dllNames, extractedDlls);

                for (int i = 0; i < NuGetEntries.Length; i++)
                    Debug.Log($"[MCP] Extracted {dllNames[i]} ({extractedDlls[i].Length / 1024}KB) → Assets/{PluginsRelPath}/{dllNames[i]}");

                if (interactive)
                    EditorUtility.DisplayProgressBar("Installing Roslyn", "Refreshing assets...", 0.95f);

                AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);

                if (interactive)
                {
                    EditorUtility.ClearProgressBar();
                    EditorUtility.DisplayDialog(
                        "Roslyn Installed",
                        $"Roslyn DLLs and dependencies installed to Assets/{PluginsRelPath}/.\n\n" +
                        "The runtime_compilation tool is now available via MCP.",
                        "OK");
                }

                Debug.Log($"[MCP] Roslyn installation complete ({NuGetEntries.Length} DLLs). runtime_compilation is now available.");
            }
            catch (Exception e)
            {
                if (interactive) EditorUtility.ClearProgressBar();
                Debug.LogError($"[MCP] Failed to install Roslyn: {e}");

                if (interactive)
                {
                    EditorUtility.DisplayDialog(
                        "Installation Failed",
                        $"Could not download Roslyn DLLs:\n{e.Message}\n\n" +
                        "You can manually download Microsoft.CodeAnalysis.CSharp from NuGet " +
                        "and place the DLLs in Assets/Plugins/Roslyn/.",
                        "OK");
                }
            }
        }

        /// <summary>
        /// Checks a downloaded .nupkg against its pinned SHA-256. Returns false with a
        /// human-readable reason on any doubt — including a digest that was never filled
        /// in. A placeholder must fail loudly rather than wave the payload through, so
        /// anything that is not 64 hex characters is treated as "no digest recorded".
        /// </summary>
        public static bool TryVerifyPackageDigest(byte[] payload, string expectedSha256, out string error)
        {
            if (payload == null || payload.Length == 0)
            {
                error = "the download produced no data";
                return false;
            }

            bool wellFormed = !string.IsNullOrEmpty(expectedSha256) && expectedSha256.Length == 64;
            if (wellFormed)
            {
                foreach (char c in expectedSha256)
                {
                    bool isHex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
                    if (!isHex)
                    {
                        wellFormed = false;
                        break;
                    }
                }
            }

            if (!wellFormed)
            {
                error = $"no expected SHA-256 is recorded for this package (found \"{expectedSha256}\"); " +
                        "fill in the digest in RoslynInstaller.NuGetEntries";
                return false;
            }

            string actual;
            using (var sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(payload);
                var sb = new StringBuilder(hash.Length * 2);
                foreach (byte b in hash)
                    sb.Append(b.ToString("x2"));
                actual = sb.ToString();
            }

            if (!string.Equals(actual, expectedSha256, StringComparison.OrdinalIgnoreCase))
            {
                error = $"SHA-256 mismatch (expected {expectedSha256.ToLowerInvariant()}, got {actual})";
                return false;
            }

            error = null;
            return true;
        }

        /// <summary>
        /// Publishes a whole set of files into <paramref name="destFolder"/> so the folder is
        /// only ever observed holding all of them or none of them.
        ///
        /// Writing the files one by one into the destination was verified-then-torn: the
        /// digest gate guarantees the bytes are right, but a disk-full, a permission error or
        /// a crash on the second write still left a folder mixing new and old DLLs. Mixed
        /// Roslyn assemblies load, then fail at call sites with missing-member errors, so the
        /// damage surfaces far away from its cause.
        ///
        /// The set is therefore assembled in a hidden sibling folder and swapped in with two
        /// renames. Anything that already lives in the destination (existing .meta files,
        /// DLLs a user dropped in by hand) is copied into staging first, so the swap replaces
        /// the folder without dropping its contents — .meta in particular carries the asset
        /// GUID and the plugin import settings, which a fresh folder would silently reset.
        /// </summary>
        public static void PublishFolderAtomically(string destFolder, string[] fileNames, byte[][] fileContents)
        {
            if (fileNames == null || fileContents == null || fileNames.Length != fileContents.Length)
                throw new ArgumentException("fileNames and fileContents must be non-null and the same length");

            string parent = Path.GetDirectoryName(destFolder);
            string leaf = Path.GetFileName(destFolder);
            string staging = Path.Combine(parent, leaf + StagingFolderSuffix);
            string backup = Path.Combine(parent, leaf + BackupFolderSuffix);

            Directory.CreateDirectory(parent);

            // Fixed names rather than per-run unique ones: a run killed mid-swap leaves its
            // scratch folders behind, and a fixed name means the next run reclaims them
            // instead of accumulating one more.
            //
            // Reclaiming them has to succeed before anything is published. Logging a failed
            // delete and carrying on would let a previous run's files ride into staging and
            // then get renamed onto the destination, producing exactly the mixed assembly set
            // this atomic publish exists to prevent. On Windows a DLL the Editor still holds
            // open makes that failure ordinary, no adversary required.
            RequireScratchFolderCleared(staging);
            RequireScratchFolderCleared(backup);

            bool backupHoldsTheOnlyCopy = false;
            try
            {
                Directory.CreateDirectory(staging);
                if (Directory.Exists(destFolder))
                    CopyDirectory(destFolder, staging);

                for (int i = 0; i < fileNames.Length; i++)
                {
                    string stagedPath = Path.Combine(staging, fileNames[i]);
                    File.WriteAllBytes(stagedPath, fileContents[i]);

                    // Read back rather than trust the write. A full volume can report success
                    // and produce a short file, and a truncated assembly is exactly what must
                    // never reach the destination.
                    byte[] readBack = File.ReadAllBytes(stagedPath);
                    if (readBack.Length != fileContents[i].Length)
                        throw new IOException(
                            $"{fileNames[i]} was written to staging as {readBack.Length} bytes but should be " +
                            $"{fileContents[i].Length}; the volume is likely full. Nothing was installed.");

                    for (int b = 0; b < readBack.Length; b++)
                    {
                        if (readBack[b] != fileContents[i][b])
                            throw new IOException(
                                $"{fileNames[i]} read back differently than it was written (first difference at " +
                                $"byte {b}). Nothing was installed.");
                    }
                }

                bool destMovedAside = false;
                if (Directory.Exists(destFolder))
                {
                    // If the Editor holds the old DLLs open — the normal case on Windows once
                    // runtime_compilation has run — this throws, and it throws before anything
                    // has been modified. A reinstall that cannot proceed leaves the previous
                    // install exactly as it was instead of half-replacing it.
                    Directory.Move(destFolder, backup);
                    destMovedAside = true;
                }

                try
                {
                    Directory.Move(staging, destFolder);
                }
                catch
                {
                    if (destMovedAside)
                    {
                        try
                        {
                            Directory.Move(backup, destFolder);
                        }
                        catch (Exception restoreError)
                        {
                            // Both renames failed, so the previous install now exists only under
                            // the backup name. It must survive cleanup and the user must be told
                            // where it is; deleting it here would turn a failed install into lost data.
                            backupHoldsTheOnlyCopy = true;
                            Debug.LogError(
                                $"[MCP] Roslyn install failed AND the previous install could not be moved back. " +
                                $"It is intact at \"{backup}\" — rename that folder to \"{destFolder}\" to restore it. " +
                                $"Restore error: {restoreError}");
                        }
                    }
                    throw;
                }
            }
            finally
            {
                DeleteDirectoryLoudly(staging);
                if (!backupHoldsTheOnlyCopy)
                    DeleteDirectoryLoudly(backup);
            }
        }

        /// <summary>
        /// Removes a scratch folder and throws if it is still there afterwards. This is the
        /// pre-flight counterpart to <see cref="DeleteDirectoryLoudly"/>: before the swap a
        /// leftover folder changes what gets published, so refusing to start is correct, while
        /// in the finally block the install is already over and throwing would only mask the
        /// original failure.
        /// </summary>
        private static void RequireScratchFolderCleared(string path)
        {
            try
            {
                if (Directory.Exists(path))
                    Directory.Delete(path, true);
            }
            catch (Exception e)
            {
                throw new IOException(
                    $"Could not clear the leftover folder \"{path}\": {e.Message}. Nothing was " +
                    "installed. Close Unity (or whatever holds those files open), delete the " +
                    "folder by hand, and install again.", e);
            }

            if (Directory.Exists(path))
                throw new IOException(
                    $"The leftover folder \"{path}\" is still present after being deleted. " +
                    "Nothing was installed; delete it by hand and install again.");
        }

        /// <summary>
        /// Deletes a scratch folder if it exists. Never throws: it runs from a finally block,
        /// where throwing would replace the real failure with a cleanup failure. A delete that
        /// fails is reported instead of swallowed, because a leftover folder changes what the
        /// next install does.
        /// </summary>
        private static void DeleteDirectoryLoudly(string path)
        {
            try
            {
                if (Directory.Exists(path))
                    Directory.Delete(path, true);
            }
            catch (Exception e)
            {
                Debug.LogError(
                    $"[MCP] Could not remove the temporary folder \"{path}\": {e.Message}. " +
                    "Unity ignores it (the name ends with '~'), but delete it by hand if it lingers.");
            }
        }

        private static void CopyDirectory(string sourceDir, string targetDir)
        {
            Directory.CreateDirectory(targetDir);

            foreach (string file in Directory.GetFiles(sourceDir))
                File.Copy(file, Path.Combine(targetDir, Path.GetFileName(file)), true);

            foreach (string dir in Directory.GetDirectories(sourceDir))
                CopyDirectory(dir, Path.Combine(targetDir, Path.GetFileName(dir)));
        }

        private static byte[] ExtractFileFromZip(byte[] zipBytes, string entryPath)
        {
            entryPath = entryPath.Replace('\\', '/');

            using (var stream = new MemoryStream(zipBytes))
            using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                foreach (var entry in archive.Entries)
                {
                    if (entry.FullName.Replace('\\', '/').Equals(entryPath, StringComparison.OrdinalIgnoreCase))
                    {
                        using (var entryStream = entry.Open())
                        using (var output = new MemoryStream())
                        {
                            entryStream.CopyTo(output);
                            return output.ToArray();
                        }
                    }
                }
            }

            return null;
        }
    }
}
