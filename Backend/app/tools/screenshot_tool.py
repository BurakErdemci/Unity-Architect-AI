"""
Unity Editor screenshot tool.
Mac: screencapture + Quartz ile window-specific capture.
Windows: pywin32 ile minimize/arka planda bile capture.
Linux: harici CLI aracıyla TAM EKRAN (pencereye özel değil) — best-effort.
"""
import base64
import io
import os
import platform
import shutil
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


# Linux'ta tek bir standart yok: masaüstü ortamına/oturum tipine (X11 vs Wayland)
# göre farklı araç kurulu oluyor. İlk BULUNAN kullanılır; hiçbiri yoksa kullanıcıya
# ne kuracağı söylenir. Hepsi PNG üretir (aşağıdaki Image.open bunu bekliyor).
# NOT: pencereye özel capture YOK — Wayland altında bir uygulamanın başka bir
# pencereyi yakalaması compositor izni gerektiriyor; tam ekran alınır. Mac dalı
# da Quartz yokken aynı fallback'i yapıyor, davranış tutarlı.
# SINANMADI: bu dal canlı bir Linux masaüstünde çalıştırılmadı (ürün dağıtımı
# Win+Mac); komut satırları araçların dokümante kullanımına göre yazıldı.
_LINUX_CAPTURE_COMMANDS = [
    ("grim", lambda path: ["grim", path]),                                  # Wayland
    ("gnome-screenshot", lambda path: ["gnome-screenshot", "-f", path]),    # GNOME
    ("spectacle", lambda path: ["spectacle", "-b", "-n", "-f", "-o", path]),  # KDE
    ("scrot", lambda path: ["scrot", "-o", path]),                          # X11
    ("import", lambda path: ["import", "-window", "root", path]),           # ImageMagick
]


def _capture_linux() -> bytes:
    tool = next((t for t in _LINUX_CAPTURE_COMMANDS if shutil.which(t[0])), None)
    if tool is None:
        names = ", ".join(t[0] for t in _LINUX_CAPTURE_COMMANDS)
        raise RuntimeError(
            f"Linux'ta ekran görüntüsü için bir CLI aracı bulunamadı. "
            f"Şunlardan birini kur: {names}"
        )
    name, build_cmd = tool
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        subprocess.run(build_cmd(path), check=True, timeout=10, capture_output=True)
        with open(path, "rb") as f:
            data = f.read()
        if not data:
            raise RuntimeError(f"{name} boş dosya üretti (ekran erişim izni var mı?)")
        return data
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
        # Dallanma AÇIK olmalı: eskiden "Windows değilse mac" deniyordu ve Linux'ta
        # var olmayan `screencapture` çağrılıp anlamsız bir hata dönüyordu.
        # Bilinmeyen bir OS'te sessizce yanlış aracı denemek yerine adıyla söyle.
        sys_platform = platform.system()
        if sys_platform == "Windows":
            raw = _capture_windows()
        elif sys_platform == "Darwin":
            raw = _capture_mac()
        elif sys_platform == "Linux":
            raw = _capture_linux()
        else:
            return {"success": False,
                    "error": f"Ekran görüntüsü bu platformda desteklenmiyor: {sys_platform}"}

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
