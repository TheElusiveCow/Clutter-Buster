"""The Ctrl+Space shortcut that works everywhere (no Windows key needed).

Uses Windows' RegisterHotKey. If another program already uses Ctrl+Space,
registration fails: we log it, show one notice, and the search bar still works.
"""
import logging
import sys

log = logging.getLogger("cb")
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
HOTKEY_ID = 0xC1B0


def register(hwnd):
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        u32.RegisterHotKey.restype = wintypes.BOOL
        ok = bool(u32.RegisterHotKey(int(hwnd), HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_SPACE))
        if not ok:
            log.info("Ctrl+Space is already used by another program (Windows error %s)", ctypes.get_last_error())
        return ok
    except Exception:
        log.exception("Hotkey registration failed")
        return False


def unregister(hwnd):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.UnregisterHotKey(int(hwnd), HOTKEY_ID)
    except Exception:
        pass
