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


MOD_ALT, MOD_SHIFT = 0x0001, 0x0004
DEFAULT = {"mods": MOD_CONTROL, "vk": VK_SPACE, "text": "Ctrl+Space"}
LAST_ERROR = [0]


def register(hwnd, mods=MOD_CONTROL, vk=VK_SPACE):
    """Ask Windows for the shortcut. False if another program already has it."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        u32.RegisterHotKey.restype = wintypes.BOOL
        ok = bool(u32.RegisterHotKey(int(hwnd), HOTKEY_ID, int(mods) | MOD_NOREPEAT, int(vk)))
        if not ok:
            LAST_ERROR[0] = ctypes.get_last_error()
            log.info("Shortcut %s is already used by another program (Windows error %s)",
                     describe(mods, vk), LAST_ERROR[0])
        return ok
    except Exception:
        log.exception("Hotkey registration failed")
        return False


def describe(mods, vk):
    parts = [n for m, n in ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift")) if int(mods) & m]
    return "+".join(parts + [key_name(vk)])


def key_name(vk):
    vk = int(vk)
    if vk == VK_SPACE:
        return "Space"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return {0x09: "Tab", 0x0D: "Enter", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
            0x21: "PageUp", 0x22: "PageDown", 0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".",
            0xBF: "/", 0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}.get(vk, f"Key{vk}")


def from_qt(key, modifiers):
    """A key press (Qt) -> (mods, vk, text), or None if it isn't a usable shortcut.
    Needs at least one of Ctrl / Alt / Shift plus a normal key (no Windows key needed)."""
    from PySide6.QtCore import Qt
    mods = 0
    if modifiers & Qt.ControlModifier:
        mods |= MOD_CONTROL
    if modifiers & Qt.AltModifier:
        mods |= MOD_ALT
    if modifiers & Qt.ShiftModifier:
        mods |= MOD_SHIFT
    k = int(key)
    if Qt.Key_A <= k <= Qt.Key_Z or Qt.Key_0 <= k <= Qt.Key_9:
        vk = k                                          # same codes as Windows
    elif Qt.Key_F1 <= k <= Qt.Key_F24:
        vk = 0x70 + (k - int(Qt.Key_F1))
    else:
        vk = {int(Qt.Key_Space): VK_SPACE, int(Qt.Key_Tab): 0x09, int(Qt.Key_Return): 0x0D,
              int(Qt.Key_Insert): 0x2D, int(Qt.Key_Delete): 0x2E, int(Qt.Key_Home): 0x24, int(Qt.Key_End): 0x23,
              int(Qt.Key_PageUp): 0x21, int(Qt.Key_PageDown): 0x22, int(Qt.Key_Semicolon): 0xBA,
              int(Qt.Key_Equal): 0xBB, int(Qt.Key_Comma): 0xBC, int(Qt.Key_Minus): 0xBD, int(Qt.Key_Period): 0xBE,
              int(Qt.Key_Slash): 0xBF, int(Qt.Key_QuoteLeft): 0xC0, int(Qt.Key_BracketLeft): 0xDB,
              int(Qt.Key_Backslash): 0xDC, int(Qt.Key_BracketRight): 0xDD, int(Qt.Key_Apostrophe): 0xDE}.get(k)
    if vk is None or not mods:
        return None
    return mods, vk, describe(mods, vk)


def unregister(hwnd):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.user32.UnregisterHotKey(int(hwnd), HOTKEY_ID)
    except Exception:
        pass
