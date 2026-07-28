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

                Directory.CreateDirectory(destFolder);

                for (int i = 0; i < NuGetEntries.Length; i++)
                {
                    string dllName = NuGetEntries[i].dllName;
                    File.WriteAllBytes(Path.Combine(destFolder, dllName), extractedDlls[i]);
                    Debug.Log($"[MCP] Extracted {dllName} ({extractedDlls[i].Length / 1024}KB) → Assets/{PluginsRelPath}/{dllName}");
                }

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
