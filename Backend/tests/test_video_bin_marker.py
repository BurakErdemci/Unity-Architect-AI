"""The build wrapper's `.fetched` marker must authenticate BYTES, not itself.

External audit, 30 Aug 2026. `zatenGuncel()` in
`Frontend/frontend/scripts/fetch-video-bins.js` skipped the platform fetch
whenever both binary filenames existed and `.fetched` matched the pinned digest
strings from `scripts/pinned_assets.json`. It never hashed either executable, so
the marker only ever proved its own text.

Reproduced: put a matching `.fetched` next to a tampered `ffmpeg.exe` /
`yt-dlp.exe` and the wrapper prints "already at the pinned version", never calls
the verifying fetch script, and `backend.spec` packages the tampered binary.
CI checks out clean, so the exposure is the persistent-disk case: a developer
machine and a self-hosted runner.

Idempotence is the constraint that makes this awkward, and it is measured here
too: re-running a build must not re-download 126 MB when nothing changed. The
answer is that the marker now records the sha256 of the installation that
PASSED verification — the pinned digest itself cannot be compared against
`ffmpeg.exe`, because that pin covers the zip the exe was extracted from.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_WRAPPER = Path(__file__).resolve().parents[2] / "Frontend" / "frontend" / "scripts" / "fetch-video-bins.js"
_NODE = shutil.which("node")

_FFMPEG_PIN = "sha256:" + "1" * 64
_YTDLP_PIN = "sha256:" + "2" * 64
_PINS = _FFMPEG_PIN + " " + _YTDLP_PIN

# The wrapper's skip line is Turkish prose; these two ASCII fragments are the
# stable anchors, because console decoding on Windows mangles the rest.
_SKIP_ANCHORS = ("[fetch-video-bins] win:", "zaten")


@unittest.skipUnless(_NODE, "node PATH'te yok")
@unittest.skipUnless(os.name == "nt", "sarmalayıcı platforma göre dallanıyor; "
                                      "kütük anahtarları burada 'win'")
class TestFetchedMarkerVerifiesTheBinaries(unittest.TestCase):
    def _fixture(self, root: Path, contents: dict) -> Path:
        script = root / "Frontend" / "frontend" / "scripts" / "fetch-video-bins.js"
        script.parent.mkdir(parents=True)
        shutil.copyfile(_WRAPPER, script)
        bin_dir = root / "Backend" / "vendor" / "bin" / "win"
        bin_dir.mkdir(parents=True)
        for name, data in contents.items():
            (bin_dir / name).write_bytes(data)
        pins = root / "scripts" / "pinned_assets.json"
        pins.parent.mkdir(parents=True)
        pins.write_text(json.dumps({"assets": {
            "ffmpeg/win": {"digest": _FFMPEG_PIN},
            "yt-dlp/win": {"digest": _YTDLP_PIN},
        }}), encoding="utf-8")
        return bin_dir

    def _run_wrapper(self, root: Path):
        r = subprocess.run([_NODE, str(root / "Frontend" / "frontend" / "scripts"
                                       / "fetch-video-bins.js")],
                           cwd=str(root), capture_output=True, text=True, timeout=60)
        return r, r.stdout + r.stderr

    @staticmethod
    def _marker(pins: str, contents: dict) -> str:
        lines = [pins]
        for name, data in contents.items():
            lines.append(f"{name} sha256:{hashlib.sha256(data).hexdigest()}")
        return "\n".join(lines) + "\n"

    def test_a_tampered_binary_is_not_skipped(self):
        contents = {"ffmpeg.exe": b"tampered-ffmpeg", "yt-dlp.exe": b"tampered-yt-dlp"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = self._fixture(root, contents)
            # A marker recording the ORIGINAL bytes, next to replaced files —
            # exactly what a persistent build directory looks like after tampering.
            (bin_dir / ".fetched").write_text(
                self._marker(_PINS, {"ffmpeg.exe": b"gercek-ffmpeg",
                                     "yt-dlp.exe": b"gercek-yt-dlp"}), encoding="utf-8")
            _r, out = self._run_wrapper(root)
        self.assertFalse(all(a in out for a in _SKIP_ANCHORS),
                         f"tampered binaries were skipped: {out}")

    def test_the_old_marker_format_does_not_authenticate_anything(self):
        # The shape the audit reproduced: pinned digest text and nothing else.
        # Absence of a byte record is not evidence, so it must not buy a skip.
        contents = {"ffmpeg.exe": b"tampered-ffmpeg", "yt-dlp.exe": b"tampered-yt-dlp"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = self._fixture(root, contents)
            (bin_dir / ".fetched").write_text(_PINS + "\n", encoding="utf-8")
            _r, out = self._run_wrapper(root)
        self.assertFalse(all(a in out for a in _SKIP_ANCHORS),
                         f"a marker with no byte record was trusted: {out}")

    def test_an_untouched_installation_is_still_skipped(self):
        # The constraint that makes the fix acceptable: hashing must not cost a
        # 126 MB re-download on every build.
        contents = {"ffmpeg.exe": b"gercek-ffmpeg", "yt-dlp.exe": b"gercek-yt-dlp"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = self._fixture(root, contents)
            (bin_dir / ".fetched").write_text(self._marker(_PINS, contents),
                                              encoding="utf-8")
            r, out = self._run_wrapper(root)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(all(a in out for a in _SKIP_ANCHORS),
                        f"an unchanged installation re-downloaded: {out}")

    def test_a_changed_pin_still_wins_over_matching_bytes(self):
        # The old guarantee must survive the new one: a bumped version in
        # pinned_assets.json re-fetches even though the files are self-consistent.
        contents = {"ffmpeg.exe": b"gercek-ffmpeg", "yt-dlp.exe": b"gercek-yt-dlp"}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bin_dir = self._fixture(root, contents)
            (bin_dir / ".fetched").write_text(
                self._marker("sha256:" + "9" * 64 + " " + _YTDLP_PIN, contents),
                encoding="utf-8")
            _r, out = self._run_wrapper(root)
        self.assertFalse(all(a in out for a in _SKIP_ANCHORS),
                         f"a stale pin was skipped: {out}")


if __name__ == "__main__":
    unittest.main()
