"""All colors and sizes live here.

Stage 1 ships the "Clean White" theme. Later stages add "Neon Gamer" and a
custom theme maker; they only need to provide another dictionary like CLEAN_WHITE.
"""
from PySide6.QtGui import QColor, QLinearGradient

# The thin rainbow strip that matches Brian's RGB PC build.
RGB_STOPS = [
    (255, 45, 120), (255, 150, 0), (255, 225, 0),
    (0, 215, 120), (0, 165, 255), (150, 80, 255),
]

CLEAN_WHITE = {
    "name": "Clean White",
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
    # the big popup
    "panel_fill": (250, 251, 253, 236),
    "popup_fill": (251, 252, 254, 248),
    "panel_text": (28, 28, 34, 255),
    "panel_subtext": (100, 100, 112, 255),
    "title_text": (28, 28, 34, 255),
    "title_glow": (255, 255, 255, 210),
    "item_hover": (0, 0, 0, 18),
    "dot_on": (40, 40, 48, 220),
    "dot_off": (40, 40, 48, 70),
    # background behind the popup: real Windows blur tint (AARRGGBB),
    # or a soft wash if the blur is not available
    "backdrop_blur_tint": 0x60F2F4F8,
    "backdrop_fallback": (236, 239, 246, 165),
    "backdrop_min": (255, 255, 255, 3),
    # search bar
    "search_text": (28, 28, 34, 255),
    "button_fill": (255, 255, 255, 235),
    "button_text": (28, 28, 34, 255),
    # sizes (in screen points; Windows scaling is handled automatically)
    "tile_size": 72,
    "tile_radius": 18,
    "tile_window": (96, 112),
    "grid_cell": (100, 116),
    "panel_radius": 36,
    "popup_icon": 64,
    "popup_cols": 3,
    "popup_rows": 3,
    # stage 2: cards behind icons (like the Clean White mockup), panels, dock, badges
    "card_fill": (255, 255, 255, 230),
    "card_border": (20, 30, 60, 22),
    "panel_title_text": (28, 28, 34, 255),
    "hint_text": (120, 122, 135, 255),
    "badge_text": (255, 255, 255, 255),
    "selection": (0, 160, 255, 40),
    "dock_handle": (255, 255, 255, 150),
    "default_accent": "#0A84FF",
}

# Accent colors offered in the group right-click menu (iOS-like system colors).
ACCENTS = [
    ("Blue", "#0A84FF"), ("Purple", "#9B5CFF"), ("Pink", "#FF3B7F"), ("Red", "#FF453A"),
    ("Orange", "#FF9F0A"), ("Yellow", "#FFD60A"), ("Green", "#30D158"), ("Teal", "#40C8E0"),
    ("Gray", "#8E8E93"),
]

# --- Notes for stage 3 "Neon Gamer" (from Brian's mockups) ---------------------
# dark smoked glass (~rgba(15,18,35,190)), each group outlined with a glowing neon
# border in its accent color (cyan/purple/orange/green), white labels, a dark search
# bar with a purple glow outline, a dark dock that shows labels under icons, a dark
# popup with a cyan glow border, and in edit mode: a top bar "Clutter Buster | EDIT
# LAYOUT" + Done button, "..." menu on each panel, dashed selection with corner
# handles, a dotted grid, and a Group settings card (icon size, glass transparency,
# glow strength sliders, glow color swatches).

THEME = dict(CLEAN_WHITE)


def qcolor(key):
    return QColor(*THEME[key])


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
