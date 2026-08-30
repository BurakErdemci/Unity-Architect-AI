"""Bundled (frozen) veya PATH (dev) ffmpeg/yt-dlp binary'lerini çözer.
Frozen: PyInstaller binaries'i sys._MEIPASS/bin veya exe-yanı /bin altına koyar.
Dev: PATH'ten (shutil.which). Son çare: çıplak isim (subprocess PATH'te arar)."""
import os
import sys
import shutil
import logging

logger = logging.getLogger(__name__)


def _candidate_dirs():
    dirs = []
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        dirs.append(os.path.join(mp, "bin"))
    # exe-yanı /bin (frozen bundle) + exe dizini (dev: backend venv/Scripts — pip ile
    # kurulu yt-dlp.exe burada olur → dev'de sistem PATH'ine gerek kalmaz).
    exe_dir = os.path.dirname(sys.executable)
    dirs.append(os.path.join(exe_dir, "bin"))
    dirs.append(exe_dir)
    return dirs


def _find(name: str, exe: str):
    """Returns the path actually found, or ``None``.

    Separate from `_resolve`, which falls back to the bare name and so left the
    caller unable to TELL APART "found it" from "not found, will try the bare
    name". The cost of not telling them apart was measured: a missing binary
    blows up inside subprocess, the error lands in `_prepare_videos`'s broad
    `except`, and the user saw nothing beyond "a video could not be processed".

    ⚠️ On Windows the extension is not necessarily `.exe`: on this machine
    yt-dlp is installed as `~/bin/yt-dlp.CMD` (measured 30 Aug 2026) and
    `shutil.which` finds it through PATHEXT — searching the bundle dir for an
    `.exe` alone would have called it missing.
    """
    for d in _candidate_dirs():
        p = os.path.join(d, exe)
        if os.path.exists(p):
            return p
    return shutil.which(name)


def _resolve(name: str, exe: str) -> str:
    found = _find(name, exe)
    if found:
        return found
    logger.warning(f"[video_bin] '{name}' bulunamadı (bundle/PATH); çıplak isimle denenecek")
    return exe


def ffmpeg_path() -> str:
    return _resolve("ffmpeg", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def ytdlp_path() -> str:
    return _resolve("yt-dlp", "yt-dlp.exe" if os.name == "nt" else "yt-dlp")


def missing_binaries(need_ytdlp: bool) -> "list[str]":
    """Names of the binaries that could not be resolved (empty = all present)."""
    missing = []
    if not _find("ffmpeg", "ffmpeg.exe" if os.name == "nt" else "ffmpeg"):
        missing.append("ffmpeg")
    if need_ytdlp and not _find("yt-dlp", "yt-dlp.exe" if os.name == "nt" else "yt-dlp"):
        missing.append("yt-dlp")
    return missing
