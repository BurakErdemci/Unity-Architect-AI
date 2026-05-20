"""
Unity Editor screenshot tool.
Mac: screencapture + Quartz ile window-specific capture.
Windows: pywin32 ile minimize/arka planda bile capture.
"""
import base64
import io
import os
import platform
import subprocess
import tempfile


def _get_unity_window_id_mac() -> str | None:
    """Quartz ile Unity Editor penceresinin CGWindowID'sini döndürür."""
    try:
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        for w in window_list:
            owner = w.get("kCGWindowOwnerName", "")
            if "Unity" in owner and "Hub" not in owner:
                wid = w.get("kCGWindowNumber")
                if wid:
                    return str(wid)
    except ImportError:
        pass
    return None


def _capture_mac() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        window_id = _get_unity_window_id_mac()
        if window_id:
            subprocess.run(
                ["screencapture", "-x", "-l", window_id, path],
                check=True, timeout=10, capture_output=True
            )
        else:
            # Quartz bulunamadı — tam ekran fallback
            subprocess.run(
                ["screencapture", "-x", path],
                check=True, timeout=10, capture_output=True
            )
        with open(path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _capture_windows() -> bytes:
    import win32con
    import win32gui
    import win32ui
    from PIL import Image

    hwnd = None

    def enum_cb(h, _):
        nonlocal hwnd
        title = win32gui.GetWindowText(h)
        if "Unity" in title and "Unity Hub" not in title:
            hwnd = h

    win32gui.EnumWindows(enum_cb, None)
    if not hwnd:
        raise RuntimeError("Unity Editor penceresi bulunamadı. Unity açık mı?")

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

    bmp_info = bmp.GetInfo()
    bmp_bits = bmp.GetBitmapBits(True)
    img = Image.frombuffer(
        "RGB",
        (bmp_info["bmWidth"], bmp_info["bmHeight"]),
        bmp_bits, "raw", "BGRX", 0, 1
    )

    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def capture_unity_screenshot() -> dict:
    """
    Unity Editor penceresinin screenshot'ını alır.
    Dönen dict'te image_base64 key'i agent_runner tarafından vision input olarak inject edilir.
    """
    try:
        from PIL import Image
    except ImportError:
        return {"success": False, "error": "Pillow kurulu değil. 'pip install Pillow' çalıştır."}

    try:
        sys_platform = platform.system()
        if sys_platform == "Windows":
            raw = _capture_windows()
        else:
            raw = _capture_mac()

        img = Image.open(io.BytesIO(raw))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((1280, 1280), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        b64 = base64.b64encode(buf.getvalue()).decode()

        return {
            "success": True,
            "image_base64": f"data:image/jpeg;base64,{b64}",
            "width": img.width,
            "height": img.height,
            "platform": sys_platform.lower(),
            "message": "Unity Editor screenshot alındı",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
