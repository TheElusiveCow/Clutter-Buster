"""Talks to Windows about desktop items.

SAFETY: this module never moves, renames, copies over, or deletes anything.
The ONLY change it can make to your files is switching the "Hidden" checkbox
(the same one in a file's Properties window) on or off.
"""
import logging
import os
import sys
import uuid

IS_WIN = sys.platform == "win32"
log = logging.getLogger("cb")

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

FOLDERID_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
FOLDERID_PUBLIC_DESKTOP = "C4AA340D-F20F-4863-AFEF-F87EF2E6BA25"

# On non-Windows computers (only used for automated tests) we pretend the
# hidden flag lives in this set instead of on real files.
_fake_hidden = set()

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    _k32.GetFileAttributesW.restype = wintypes.DWORD
    _k32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _k32.SetFileAttributesW.restype = wintypes.BOOL
    _shell32 = ctypes.WinDLL("shell32")
    _shell32.SHChangeNotify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _shell32.SHChangeNotify.restype = None

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    def _known_folder(guid_text):
        u = uuid.UUID(guid_text)
        g = _GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_void_p()
        hr = _shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out))
        if hr != 0 or not out.value:
            return None
        try:
            return ctypes.wstring_at(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)


def is_url(p):
    """Website items are stored as their web address (http/https)."""
    return isinstance(p, str) and p.lower().startswith(("http://", "https://"))


def norm(p):
    """A comparable version of a path (same file -> same text). Web addresses stay as-is."""
    if is_url(p):
        return p.strip().rstrip("/").lower()
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def desktop_dirs():
    """Your own Desktop folder (even if OneDrive moved it) and the Public Desktop."""
    if os.environ.get("CLUTTERBUSTER_SHOWCASE"):
        return []  # showcase/demo mode never looks at (or touches) your real desktop
    dirs = []
    if IS_WIN:
        for guid in (FOLDERID_DESKTOP, FOLDERID_PUBLIC_DESKTOP):
            try:
                p = _known_folder(guid)
            except Exception:
                p = None
            if p:
                dirs.append(p)
        if not dirs:
            dirs = [os.path.join(os.path.expanduser("~"), "Desktop"),
                    os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")]
    else:
        # test mode only
        env = os.environ.get("CLUTTERBUSTER_TEST_DESKTOPS", "")
        dirs = [d for d in env.split(os.pathsep) if d]
    seen, out = set(), []
    for d in dirs:
        if d and norm(d) not in seen and os.path.isdir(d):
            seen.add(norm(d))
            out.append(d)
    return out


def is_on_desktop(p):
    if is_url(p):
        return False
    parent = norm(os.path.dirname(norm(p)))
    return any(parent == norm(d) for d in desktop_dirs())


def list_desktop_items():
    """Everything sitting on the desktop (both folders). Skips Windows' own desktop.ini."""
    items = []
    for d in desktop_dirs():
        try:
            for entry in os.scandir(d):
                name = entry.name.lower()
                if name == "desktop.ini" or name.startswith("~$"):
                    continue
                items.append(entry.path)
        except OSError:
            continue
    return items


def get_attrs(p):
    if not IS_WIN:
        return (FILE_ATTRIBUTE_HIDDEN if norm(p) in _fake_hidden else 0) if os.path.exists(p) else None
    a = _k32.GetFileAttributesW(p)
    return None if a == INVALID_FILE_ATTRIBUTES else a


def is_hidden(p):
    a = get_attrs(p)
    return None if a is None else bool(a & FILE_ATTRIBUTE_HIDDEN)


def set_hidden(p, hidden):
    """Turn the Hidden flag on/off. Returns True if it worked. Touches nothing else."""
    a = get_attrs(p)
    if a is None:
        return False
    if not IS_WIN:
        (_fake_hidden.add if hidden else _fake_hidden.discard)(norm(p))
        return True
    if hidden:
        new = (a | FILE_ATTRIBUTE_HIDDEN) & ~FILE_ATTRIBUTE_NORMAL
    else:
        new = a & ~FILE_ATTRIBUTE_HIDDEN
        if new == 0:
            new = FILE_ATTRIBUTE_NORMAL
    if new == a:
        return True
    ok = bool(_k32.SetFileAttributesW(p, new))
    if not ok:
        err = ctypes.get_last_error()
        log.info("Could not change Hidden flag on %s (Windows error %s)", p, err)
        return False
    notify_changed(p)
    return True


def notify_changed(p):
    """Ask the desktop to refresh so the change shows up right away."""
    if not IS_WIN:
        return
    try:
        SHCNF_PATHW = 0x0005
        buf = ctypes.create_unicode_buffer(p)
        _shell32.SHChangeNotify(0x00000800, SHCNF_PATHW, ctypes.cast(buf, ctypes.c_void_p), None)  # attributes
        _shell32.SHChangeNotify(0x00002000, SHCNF_PATHW, ctypes.cast(buf, ctypes.c_void_p), None)  # update item
        pbuf = ctypes.create_unicode_buffer(os.path.dirname(p))
        # update the desktop folder too, and flush so Explorer redraws right away
        _shell32.SHChangeNotify(0x00001000, SHCNF_PATHW | 0x2000, ctypes.cast(pbuf, ctypes.c_void_p), None)
    except Exception:
        log.exception("Desktop refresh failed")


def explorer_shows_hidden_files():
    """True if Explorer is set to 'Show hidden items' (then hidden items look faded instead of vanishing)."""
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced") as k:
            return winreg.QueryValueEx(k, "Hidden")[0] == 1
    except OSError:
        return False
