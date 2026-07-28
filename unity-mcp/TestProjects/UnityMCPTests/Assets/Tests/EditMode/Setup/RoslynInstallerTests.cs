using System.Text;
using MCPForUnity.Editor.Setup;
using NUnit.Framework;

namespace MCPForUnityTests.Editor.Setup
{
    /// <summary>
    /// Tests for the integrity gate in front of the Roslyn .nupkg downloads. The DLLs
    /// those packages carry are loaded into the app domain, so "the digest slot was left
    /// unfilled" must fail exactly as hard as "the bytes were tampered with".
    /// </summary>
    public class RoslynInstallerTests
    {
        // NIST vector: SHA-256("abc"). Hard-coded rather than recomputed so the test
        // does not simply re-run the implementation and agree with itself.
        private const string AbcSha256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

        private static byte[] Abc()
        {
            return Encoding.UTF8.GetBytes("abc");
        }

        [Test]
        public void MatchingDigest_Accepts()
        {
            string error;
            Assert.IsTrue(RoslynInstaller.TryVerifyPackageDigest(Abc(), AbcSha256, out error));
            Assert.IsNull(error);
        }

        [Test]
        public void MatchingDigest_IsCaseInsensitive()
        {
            string error;
            Assert.IsTrue(RoslynInstaller.TryVerifyPackageDigest(Abc(), AbcSha256.ToUpperInvariant(), out error));
            Assert.IsNull(error);
        }

        [Test]
        public void MismatchedDigest_Rejects()
        {
            string error;
            string wrong = AbcSha256.Replace('b', 'c');
            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(Abc(), wrong, out error));
            Assert.That(error, Does.Contain("mismatch"));
        }

        [Test]
        public void PlaceholderDigest_Rejects()
        {
            string error;
            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(Abc(), "TODO-DIGEST", out error));
            Assert.That(error, Does.Contain("no expected SHA-256"));
        }

        [Test]
        public void EmptyDigest_Rejects()
        {
            string error;
            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(Abc(), "", out error));
            Assert.IsNotNull(error);

            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(Abc(), null, out error));
            Assert.IsNotNull(error);
        }

        [Test]
        public void CorrectLengthButNonHexDigest_Rejects()
        {
            // 64 characters, so a length-only check would let this through.
            string error;
            string notHex = new string('z', 64);
            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(Abc(), notHex, out error));
            Assert.That(error, Does.Contain("no expected SHA-256"));
        }

        [Test]
        public void EmptyPayload_Rejects()
        {
            string error;
            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(new byte[0], AbcSha256, out error));
            Assert.IsNotNull(error);

            Assert.IsFalse(RoslynInstaller.TryVerifyPackageDigest(null, AbcSha256, out error));
            Assert.IsNotNull(error);
        }
    }
}
