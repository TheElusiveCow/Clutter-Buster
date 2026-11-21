"""Real Windows frosted-glass blur ("acrylic") behind a window.

Uses SetWindowCompositionAttribute. If it is not available, it returns False
and the app simply paints a soft see-through background instead. Never crashes.
"""
import sys

ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19


def enable_blur(hwnd, tint_argb=0x60F2F4F8):
    """Returns "acrylic", "blur" or "" (nothing worked)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p),
                        ("SizeOfData", ctypes.c_size_t)]

        func = ctypes.windll.user32.SetWindowCompositionAttribute
        func.argtypes = [wintypes.HWND, ctypes.POINTER(WINCOMPATTRDATA)]
        func.restype = wintypes.BOOL
        a = (tint_argb >> 24) & 0xFF
        r = (tint_argb >> 16) & 0xFF
        g = (tint_argb >> 8) & 0xFF
        b = tint_argb & 0xFF
        abgr = (a << 24) | (b << 16) | (g << 8) | r
        for state, name in ((ACCENT_ENABLE_ACRYLICBLURBEHIND, "acrylic"), (ACCENT_ENABLE_BLURBEHIND, "blur")):
            accent = ACCENT_POLICY(state, 2, abgr, 0)
            data = WINCOMPATTRDATA(WCA_ACCENT_POLICY,
                                   ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
                                   ctypes.sizeof(accent))
            if func(int(hwnd), ctypes.byref(data)):
                return name
        return ""
    except Exception:
        return ""
