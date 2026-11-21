"""Keeps Clutter Buster's tiles and search bar on the DESKTOP LAYER.

That means: just above the wallpaper/desktop icons, but BEHIND every normal
app window - exactly like desktop icons. Two tricks:
 1. place_on_desktop_layer(): slide our window down so it sits right above
    the desktop itself.
 2. lock_zorder(): when Windows (or a click) tries to bring our window to the
    front, quietly say "no" (SWP_NOZORDER). Only our own placement calls may
    change the stacking order.
"""
import sys

IS_WIN = sys.platform == "win32"
WM_WINDOWPOSCHANGING = 0x0046
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER = 0x1, 0x2, 0x4
SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x10, 0x200
GW_HWNDPREV = 3
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x8
HWND_TOP = 0

_internal = [0]
_own = set()
SHOWCASE = [False]  # demo screenshots only: put windows on top instead of behind
HWND_TOPMOST = -1
WM_HOTKEY = 0x0312

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _u32 = ctypes.WinDLL("user32")
    _u32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    _u32.FindWindowExW.restype = wintypes.HWND
    _u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _u32.FindWindowW.restype = wintypes.HWND
    _u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _u32.GetWindow.restype = wintypes.HWND
    _u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _u32.GetWindowLongW.restype = ctypes.c_long
    _u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u32.SetWindowPos.restype = wintypes.BOOL
    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _u32.EnumWindows.argtypes = [_EnumProc, wintypes.LPARAM]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND),
                    ("x", ctypes.c_int), ("y", ctypes.c_int), ("cx", ctypes.c_int),
                    ("cy", ctypes.c_int), ("flags", ctypes.c_uint)]


def register(hwnd):
    _own.add(int(hwnd))


def unregister(hwnd):
    _own.discard(int(hwnd))


def find_desktop_host():
    """The top-level window that holds the desktop icons (Progman or a WorkerW)."""
    if not IS_WIN:
        return None
    found = []

    def cb(h, _l):
        if _u32.FindWindowExW(h, None, "SHELLDLL_DefView", None):
            found.append(h)
            return False
        return True

    _u32.EnumWindows(_EnumProc(cb), 0)
    return found[0] if found else _u32.FindWindowW("Progman", None)


def place_on_desktop_layer(hwnd):
    if not IS_WIN or not hwnd:
        return False
    if SHOWCASE[0]:
        _internal[0] += 1
        try:
            return bool(_u32.SetWindowPos(int(hwnd), HWND_TOPMOST, 0, 0, 0, 0,
                                          SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))
        finally:
            _internal[0] -= 1
    try:
        host = find_desktop_host()
        after = None
        if host:
            prev = _u32.GetWindow(host, GW_HWNDPREV)
            while prev and int(prev) in _own:
                prev = _u32.GetWindow(prev, GW_HWNDPREV)
            if prev and not (_u32.GetWindowLongW(prev, GWL_EXSTYLE) & WS_EX_TOPMOST):
                after = prev
        if after is None:
            after = HWND_TOP  # no normal windows above the desktop at all
        _internal[0] += 1
        try:
            return bool(_u32.SetWindowPos(int(hwnd), after, 0, 0, 0, 0,
                                          SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER))
        finally:
            _internal[0] -= 1
    except Exception:
        return False


def handle_native(message):
    """Call from QWidget.nativeEvent.
    - Stops anything else from raising our desktop-layer window.
    - Returns the hotkey id if this message is a global hotkey press, else None."""
    if not IS_WIN:
        return None
    try:
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY:
            return int(msg.wParam)
        if msg.message == WM_WINDOWPOSCHANGING and msg.lParam and not _internal[0] and not SHOWCASE[0]:
            wp = WINDOWPOS.from_address(msg.lParam)
            wp.flags |= SWP_NOZORDER
    except Exception:
        pass
    return None


def force_foreground(hwnd):
    """Bring a window to the front (allowed right after a hotkey press)."""
    if not IS_WIN or not hwnd:
        return
    try:
        _u32.SetForegroundWindow(int(hwnd))
    except Exception:
        pass
