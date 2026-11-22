"""All colors and sizes live here.

Two built-in themes - "Clean White" and "Neon Gamer" - plus your own saved themes.
The live theme is the THEME dictionary below; every window reads its colors from it,
so switching theme just refills THEME and repaints.

The look can also be tuned with four sliders (Edit layout / Settings):
icon size, icons per row, glass transparency and glow strength.
"""
import sys

from PySide6.QtGui import QColor, QConicalGradient, QLinearGradient

# The thin rainbow strip / neon glow that matches Brian's RGB PC build.
RGB_STOPS = [
    (255, 45, 120), (255, 150, 0), (255, 225, 0),
    (0, 215, 120), (0, 165, 255), (150, 80, 255),
]

CLEAN_WHITE = {
    "name": "Clean White",
    "dark": False,
    "glow": False,           # no animated neon edges, just the RGB strip on top
    # frosted glass (tiles, search bar)
    "glass_fill": (255, 255, 255, 170),
    "glass_fill_hover": (255, 255, 255, 215),
    "glass_border": (255, 255, 255, 235),
    "glass_shine": (255, 255, 255, 90),
    "shadow": (0, 0, 0, 22),
    "rgb_stops": RGB_STOPS,
    "strip_height": 3,
    "accent": (0, 160, 255, 255),
    # labels under tiles sit on the wallpaper, like normal desktop icon labels
    "label_text": (255, 255, 255, 255),
    "label_shadow": (0, 0, 0, 190),
    # popup and big panels
    "panel_fill": (250, 251, 253, 236),
    "popup_fill": (251, 252, 254, 248),
    "panel_text": (28, 28, 34, 255),
    "panel_subtext": (100, 100, 112, 255),
    "title_text": (28, 28, 34, 255),
    "item_hover": (0, 0, 0, 18),
    "dot_on": (40, 40, 48, 220),
    "dot_off": (40, 40, 48, 70),
    # search bar and buttons
    "search_text": (28, 28, 34, 255),
    "button_text": (28, 28, 34, 255),
    "icon_glyph": (90, 90, 100, 255),
    "disabled_text": (28, 28, 34, 90),
    "divider": (0, 0, 0, 18),
    "bubble_fill": (30, 30, 36, 225),
    # cards behind icons (like the Clean White mockup)
    "card_fill": (255, 255, 255, 230),
    "card_fill_hot": (255, 255, 255, 252),
    "card_border": (20, 30, 60, 22),
    "panel_title_text": (28, 28, 34, 255),
    "hint_text": (120, 122, 135, 255),
    "badge_text": (255, 255, 255, 255),
    "dock_handle": (255, 255, 255, 150),
    "default_accent": "#0A84FF",
    # sizes (in screen points; Windows scaling is handled automatically)
    "popup_icon": 64,
    "radius_scale": 1.0,
}

NEON_GAMER = dict(CLEAN_WHITE)
NEON_GAMER.update({
    "name": "Neon Gamer",
    "dark": True,
    "glow": True,            # animated RGB glow along the edges
    "glass_fill": (16, 18, 36, 192),
    "glass_fill_hover": (24, 27, 50, 214),
    "glass_border": (150, 160, 255, 60),
    "glass_shine": (255, 255, 255, 12),
    "shadow": (0, 0, 0, 70),
    "strip_height": 0,
    "accent": (0, 220, 255, 255),
    "label_shadow": (0, 0, 0, 230),
    "panel_fill": (13, 15, 32, 214),
    "popup_fill": (11, 13, 28, 236),
    "panel_text": (232, 236, 255, 255),
    "panel_subtext": (160, 166, 196, 255),
    "title_text": (244, 246, 255, 255),
    "item_hover": (255, 255, 255, 20),
    "dot_on": (235, 238, 255, 230),
    "dot_off": (235, 238, 255, 70),
    "search_text": (232, 236, 255, 255),
    "button_text": (232, 236, 255, 255),
    "icon_glyph": (200, 205, 235, 255),
    "disabled_text": (232, 236, 255, 80),
    "divider": (255, 255, 255, 24),
    "bubble_fill": (12, 14, 30, 240),
    "card_fill": (255, 255, 255, 14),
    "card_fill_hot": (255, 255, 255, 34),
    "card_border": (255, 255, 255, 26),
    "panel_title_text": (244, 246, 255, 255),
    "hint_text": (150, 156, 188, 255),
    "dock_handle": (170, 120, 255, 190),
    "default_accent": "#00D2FF",
})

BUILT_IN = {"Clean White": CLEAN_WHITE, "Neon Gamer": NEON_GAMER}
AUTO = "auto"

# Accent colors offered in the group right-click menu (iOS-like system colors).
ACCENTS = [
    ("Blue", "#0A84FF"), ("Purple", "#9B5CFF"), ("Pink", "#FF3B7F"), ("Red", "#FF453A"),
    ("Orange", "#FF9F0A"), ("Yellow", "#FFD60A"), ("Green", "#30D158"), ("Teal", "#40C8E0"),
    ("Gray", "#8E8E93"),
]

# Slider defaults (Edit layout + Settings > Appearance)
DEFAULT_UI = {"icon_size": 64, "per_row": 3, "transparency": 35, "glow": 60}
SLIDERS = [  # key, label, min, max, unit
    ("icon_size", "Icon size", 40, 96, " px"),
    ("per_row", "Icons per row", 2, 6, ""),
    ("transparency", "Glass transparency", 0, 100, " %"),
    ("glow", "Glow strength", 0, 100, " %"),
]

THEME = dict(CLEAN_WHITE)
PHASE = [0.0]        # animation position of the neon glow (0..1, goes round and round)


# ------------------------------------------------------------------ building a theme
def _rgba(hex_color, a=255):
    c = QColor(hex_color)
    return (c.red(), c.green(), c.blue(), a)


def _lum(hex_color):
    c = QColor(hex_color)
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255


def custom_to_theme(ct):
    """A saved custom theme {name, accent, tint, text, blur, glow, roundness} -> full theme dict."""
    tint = ct.get("tint", "#141830")
    dark = _lum(tint) < 0.5
    t = dict(NEON_GAMER if dark else CLEAN_WHITE)
    blur = max(0, min(100, int(ct.get("blur", 50))))
    frost = 0.75 + blur / 200          # more "blur" = milkier, more frosted glass
    for key, base_a in (("glass_fill", 175), ("glass_fill_hover", 210), ("panel_fill", 222), ("popup_fill", 240)):
        t[key] = _rgba(tint, min(255, int(base_a * frost)))
    t["glass_shine"] = (255, 255, 255, int((8 if dark else 50) + blur * (0.25 if dark else 0.6)))
    text = ct.get("text", "#FFFFFF" if dark else "#1C1C22")
    tc = QColor(text)
    for key in ("panel_text", "title_text", "search_text", "button_text", "panel_title_text"):
        t[key] = (tc.red(), tc.green(), tc.blue(), 255)
    t["panel_subtext"] = (tc.red(), tc.green(), tc.blue(), 170)
    t["hint_text"] = (tc.red(), tc.green(), tc.blue(), 150)
    t["disabled_text"] = (tc.red(), tc.green(), tc.blue(), 80)
    t["icon_glyph"] = (tc.red(), tc.green(), tc.blue(), 200)
    t["dot_on"] = (tc.red(), tc.green(), tc.blue(), 220)
    t["dot_off"] = (tc.red(), tc.green(), tc.blue(), 70)
    acc = ct.get("accent", "#00D2FF")
    t["default_accent"] = QColor(acc).name()
    t["accent"] = _rgba(acc)
    t["glow"] = int(ct.get("glow", 60)) > 0
    t["glow_scale"] = int(ct.get("glow", 60)) / 100
    t["radius_scale"] = 0.3 + int(ct.get("roundness", 55)) / 100 * 1.3
    t["name"] = ct.get("name", "Custom")
    t["custom"] = True
    return t


def custom_from_builtin(name):
    """A built-in theme as an editable custom-theme starting point (saved as a copy)."""
    t = BUILT_IN.get(name, CLEAN_WHITE)

    def hx(key, fallback):
        v = t.get(key)
        return QColor(*v[:3]).name() if isinstance(v, (tuple, list)) else fallback

    return {"name": f"{name} (my copy)", "accent": t.get("default_accent", "#0A84FF"),
            "tint": hx("glass_fill", "#FFFFFF"), "text": hx("panel_text", "#1C1C22"),
            "blur": 50, "glow": 60 if t.get("glow") else 0, "roundness": 55}


def windows_prefers_light():
    """True/False from Windows' app light/dark mode setting, None if unknown."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
    except OSError:
        return None


def resolve(choice, custom_themes):
    """The theme choice ("auto", a built-in or a custom name) -> the theme name actually shown."""
    if choice == AUTO or not choice:
        light = windows_prefers_light()
        return "Clean White" if light in (True, None) else "Neon Gamer"
    if choice in BUILT_IN or any(ct.get("name") == choice for ct in custom_themes):
        return choice
    return resolve(AUTO, custom_themes)


def build(name, ui, custom_themes=()):
    if name in BUILT_IN:
        t = dict(BUILT_IN[name])
    else:
        ct = next((c for c in custom_themes if c.get("name") == name), None)
        t = custom_to_theme(ct) if ct else dict(CLEAN_WHITE)
    ui = {**DEFAULT_UI, **(ui or {})}
    # glass transparency: 35 % is the designed look; 0 % = solid, 100 % = very see-through
    tr = max(0, min(100, int(ui["transparency"])))
    f = (1 - 0.8 * tr / 100) / (1 - 0.8 * 0.35)
    for key, floor in (("glass_fill", 25), ("glass_fill_hover", 40), ("panel_fill", 60), ("popup_fill", 110)):
        r, g, b, a = t[key]
        t[key] = (r, g, b, int(max(floor, min(255, a * f))))
    r, g, b, a = t["card_fill"]
    t["card_fill"] = (r, g, b, int(max(8, min(255, a * (0.5 + 0.5 * f)))))
    t["popup_icon"] = int(ui["icon_size"])
    t["per_row"] = int(ui["per_row"])
    t["glow_strength"] = max(0, min(100, int(ui["glow"]))) / 100 * t.get("glow_scale", 1.0)
    return t


def apply(name, ui, custom_themes=()):
    """Refill the live THEME in place (every window keeps its reference to it)."""
    t = build(name, ui, custom_themes)
    THEME.clear()
    THEME.update(t)
    return t


# ------------------------------------------------------------------ helpers
def qcolor(key):
    return QColor(*THEME[key])


def rad(r):
    """Corner radius adjusted by the theme's roundness."""
    return max(2.0, r * THEME.get("radius_scale", 1.0))


def accent_color(group):
    """A group's accent as a QColor (falls back to the theme default)."""
    c = QColor((group or {}).get("accent") or THEME["default_accent"])
    return c if c.isValid() else QColor(THEME["default_accent"])


def rgb_gradient(x1, y1, x2, y2, alpha=255):
    grad = QLinearGradient(x1, y1, x2, y2)
    stops = THEME["rgb_stops"]
    for i, (r, g, b) in enumerate(stops):
        grad.setColorAt(i / (len(stops) - 1), QColor(r, g, b, alpha))
    return grad


def neon_gradient(center, alpha=255, accent=None):
    """A gradient that runs round a shape and slowly turns (PHASE).
    With an accent: mostly the group's color with a rainbow 'comet' sweeping round.
    Without: the full RGB rainbow."""
    grad = QConicalGradient(center, -PHASE[0] * 360)
    stops = THEME["rgb_stops"]
    if accent is None:
        seq = stops + [stops[0]]
        for i, (r, g, b) in enumerate(seq):
            grad.setColorAt(i / (len(seq) - 1), QColor(r, g, b, alpha))
        return grad
    a = QColor(accent)
    ac = QColor(a.red(), a.green(), a.blue(), alpha)
    grad.setColorAt(0.0, ac)
    grad.setColorAt(0.52, ac)
    for i, (r, g, b) in enumerate(stops):
        grad.setColorAt(0.58 + i * 0.065, QColor(r, g, b, alpha))
    grad.setColorAt(1.0, ac)
    return grad


def is_dark():
    return bool(THEME.get("dark"))


def css_rgba(key, alpha=None):
    r, g, b, a = THEME[key]
    return f"rgba({r},{g},{b},{a if alpha is None else alpha})"
