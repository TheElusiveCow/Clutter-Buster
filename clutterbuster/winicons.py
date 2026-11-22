"""Real, sharp Windows icons for shortcuts and files (Windows only; read-only).

Why this exists: Qt's built-in icon lookup caches icons by file EXTENSION for most file types
and asks for small sizes, so some shortcuts (.url links, shortcuts whose picture comes from
an 'IconLocation'/'IconFile', Steam/Epic game links) came out as the plain white
page-with-an-arrow. Here every item gets its own icon, looked up like Explorer does:

  .lnk  -> its IconLocation (+ index), else the target program's icon, else the shell's icon
  .url  -> its IconFile (+ IconIndex), else the shell's icon for that link
  other -> the shell's icon for that exact file/folder
Icons are fetched big (256/96/48 px) so they stay crisp at 150% scaling.
"""
import ctypes
import logging
import os
from ctypes import wintypes

from PySide6.QtGui import QIcon, QImage, QPixmap

from .shortcuts import lnk_info, url_info

log = logging.getLogger("cb")

_shell32 = ctypes.WinDLL("shell32")
_user32 = ctypes.WinDLL("user32")
_gdi32 = ctypes.WinDLL("gdi32")
_ole32 = ctypes.WinDLL("ole32")
HICON = wintypes.HANDLE


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", HICON), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]


IID_IImageList = GUID(0x46EB5926, 0x582E, 0x4017, (ctypes.c_ubyte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))
SHGFI_SYSICONINDEX = 0x4000
SHIL_EXTRALARGE, SHIL_JUMBO = 2, 4
ILD_TRANSPARENT = 0x1
DI_MASK, DI_NORMAL = 0x1, 0x3

_shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW),
                                    wintypes.UINT, wintypes.UINT]
_shell32.SHGetFileInfoW.restype = ctypes.c_size_t
_shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
_shell32.SHGetImageList.restype = ctypes.c_long
_user32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.POINTER(HICON), ctypes.POINTER(wintypes.UINT),
                                         wintypes.UINT, wintypes.UINT]
_user32.PrivateExtractIconsW.restype = wintypes.UINT
_user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, HICON, ctypes.c_int, ctypes.c_int,
                               wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
_user32.DestroyIcon.argtypes = [HICON]
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                    wintypes.HANDLE, wintypes.DWORD]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_com_ready = [False]


def _com():
    if not _com_ready[0]:
        try:
            _ole32.CoInitializeEx(None, 2)   # already initialised by Qt is fine too
        except Exception:
            pass
        _com_ready[0] = True


def _render(hicon, size, mask=False):
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hdc = _gdi32.CreateCompatibleDC(None)
    hbm = _gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbm:
        _gdi32.DeleteDC(hdc)
        return None
    old = _gdi32.SelectObject(hdc, hbm)
    _user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, DI_MASK if mask else DI_NORMAL)
    buf = bytearray(ctypes.string_at(bits, size * size * 4))
    _gdi32.SelectObject(hdc, old)
    _gdi32.DeleteObject(hbm)
    _gdi32.DeleteDC(hdc)
    return buf


def hicon_to_image(hicon, size):
    """HICON -> QImage (keeps transparency; handles old icons without an alpha channel)."""
    buf = _render(hicon, size)
    if buf is None:
        return None
    if not any(buf[3::4]):                       # no alpha at all: use the icon's mask
        m = _render(hicon, size, mask=True)
        if m is not None:
            for i in range(0, len(buf), 4):
                if m[i] == 0:                    # black in the mask = part of the picture
                    buf[i + 3] = 255
                else:
                    buf[i:i + 4] = b"\x00\x00\x00\x00"
    img = QImage(bytes(buf), size, size, size * 4, QImage.Format_ARGB32_Premultiplied)
    return img.copy()


def _content_span(img):
    """How big the visible picture is inside the image (jumbo icons of old programs are tiny)."""
    w = img.width()
    alpha = img.convertToFormat(QImage.Format_Alpha8)
    mn, mx = w, -1
    step = max(1, w // 64)
    for y in range(0, w, step):
        row = alpha.constScanLine(y)
        data = bytes(row)[:w]
        for x in range(0, w, step):
            if data[x] > 16:
                mn, mx = min(mn, x), max(mx, x)
    return 0 if mx < 0 else mx - mn + 1


def shell_icon(path):
    """Explorer's own icon for this exact file (no shortcut arrow), at 256 px when it has one."""
    _com()
    info = SHFILEINFOW()
    if not _shell32.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info), SHGFI_SYSICONINDEX):
        return None
    icon = QIcon()
    for shil, size in ((SHIL_JUMBO, 256), (SHIL_EXTRALARGE, 48)):
        ptr = ctypes.c_void_p()
        if _shell32.SHGetImageList(shil, ctypes.byref(IID_IImageList), ctypes.byref(ptr)) != 0 or not ptr.value:
            continue
        vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        get_icon = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint,
                                      ctypes.POINTER(HICON))(vt[10])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
        h = HICON()
        try:
            if get_icon(ptr, info.iIcon, ILD_TRANSPARENT, ctypes.byref(h)) == 0 and h.value:
                img = hicon_to_image(h, size)
                _user32.DestroyIcon(h)
                if img is not None:
                    if size == 256 and _content_span(img) < 100:
                        continue                 # small old icon floating in a big empty square
                    icon.addPixmap(QPixmap.fromImage(img))
        finally:
            release(ptr)
    return None if icon.isNull() else icon


def file_icon(path, index=0):
    """Icon number `index` (or resource id -index) from an .exe/.dll/.ico file."""
    if not path or not os.path.isfile(path):
        return None
    if path.lower().endswith(".ico"):
        ic = QIcon(path)
        return None if ic.isNull() or not ic.availableSizes() else ic
    icon = QIcon()
    for size in (256, 96, 48):
        h = HICON()
        iid = wintypes.UINT()
        n = _user32.PrivateExtractIconsW(path, int(index), size, size, ctypes.byref(h), ctypes.byref(iid), 1, 0)
        if n and n != 0xFFFFFFFF and h.value:
            img = hicon_to_image(h, size)
            _user32.DestroyIcon(h)
            if img is not None and (size != 256 or _content_span(img) >= 100):
                icon.addPixmap(QPixmap.fromImage(img))
    return None if icon.isNull() else icon


def resolve(path):
    """Returns (QIcon or None, how) for one desktop item."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".lnk":
            info = lnk_info(path)
            if info["icon_location"]:
                ic = file_icon(info["icon_location"], info["icon_index"])
                if ic:
                    return ic, "lnk IconLocation"
            t = info["target"]
            if t and os.path.isfile(t):
                ic = file_icon(t, 0) if t.lower().endswith((".exe", ".ico", ".dll")) else shell_icon(t)
                if ic:
                    return ic, "lnk target"
        elif ext == ".url":
            info = url_info(path)
            if info["icon_file"]:
                ic = file_icon(info["icon_file"], info["icon_index"])
                if ic:
                    return ic, "url IconFile"
        ic = shell_icon(path)
        if ic:
            return ic, "shell"
    except Exception:
        log.exception("Icon lookup failed for %s", path)
    return None, "none"


# ------------------------------------------------------------------ picture / video thumbnails
class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


IID_IShellItemImageFactory = GUID(0xBCC18B79, 0xBA16, 0x442F,
                                  (ctypes.c_ubyte * 8)(0x80, 0xC4, 0x8A, 0x59, 0xC3, 0x0C, 0x46, 0x3B))
SIIGBF_THUMBNAILONLY = 0x08
_shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                 ctypes.POINTER(ctypes.c_void_p)]
_shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
_gdi32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.UINT]
_GetImage = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, _SIZE, ctypes.c_int, ctypes.POINTER(wintypes.HBITMAP))
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def _hbitmap_to_image(hbm):
    bm = _BITMAP()
    if not _gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm)) or bm.bmWidth <= 0:
        return None
    w, h = bm.bmWidth, abs(bm.bmHeight)
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    hdc = _gdi32.CreateCompatibleDC(None)
    got = _gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bmi), 0)
    _gdi32.DeleteDC(hdc)
    if not got:
        return None
    raw = buf.raw
    fmt = QImage.Format_ARGB32_Premultiplied if any(raw[3::4]) else QImage.Format_RGB32
    return QImage(raw, w, h, w * 4, fmt).copy()


def shell_thumbnail(path, size=256):
    """Explorer's own thumbnail for a picture or video (works for hidden files too). Any thread.
    Returns a QImage or None (then the caller falls back to loading the picture / the type icon)."""
    try:
        _ole32.CoInitializeEx(None, 2)
    except Exception:
        pass
    path = os.path.normpath(os.path.abspath(path))     # the shell refuses mixed / and \\ separators
    ptr = ctypes.c_void_p()
    hr = _shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(IID_IShellItemImageFactory), ctypes.byref(ptr))
    if hr != 0 or not ptr.value:
        return None
    vtbl = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    try:
        hbm = wintypes.HBITMAP()
        hr = _GetImage(vtbl[3])(ptr, _SIZE(size, size), SIIGBF_THUMBNAILONLY, ctypes.byref(hbm))
        if hr != 0 or not hbm.value:
            return None
        try:
            return _hbitmap_to_image(hbm)
        finally:
            _gdi32.DeleteObject(hbm)
    except Exception:
        log.debug("thumbnail failed for %s", path, exc_info=True)
        return None
    finally:
        _Release(vtbl[2])(ptr)
