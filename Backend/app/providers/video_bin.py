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


def _resolve(name: str, exe: str) -> str:
    for d in _candidate_dirs():
        p = os.path.join(d, exe)
        if os.path.exists(p):
            return p
    found = shutil.which(name)
    if found:
        return found
    logger.warning(f"[video_bin] '{name}' bulunamadı (bundle/PATH); çıplak isimle denenecek")
    return exe


def ffmpeg_path() -> str:
    return _resolve("ffmpeg", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")


def ytdlp_path() -> str:
    return _resolve("yt-dlp", "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
