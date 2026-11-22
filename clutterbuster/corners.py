"""Corner pictures: a small, semi-transparent picture in the lower-right of a fence.

A group's "corner" setting:
  (missing)        -> the theme's own picture (if the theme has one)
  "none"           -> no picture
  "asset:<name>"   -> one of the bundled pictures (assets/corners/<name>.png)
  a file path      -> your own picture (copied into %APPDATA%/ClutterBuster/pictures)

The picture is painted UNDER the icons and shrinks so it doesn't sit behind them.
"""
import os
import shutil
import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImageReader, QPainter, QPainterPath, QPixmap

from . import paths
from .theme import THEME

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "corners")
ASSETS = [("space", "Planet + rocket"), ("cabin", "Log cabin"), ("holiday", "Tree + present"),
          ("winter", "Snowman"), ("springfield", "Donut"), ("doghouse", "Doghouse")]
IMAGE_FILTER = "Pictures (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"

_cache = {}


def asset_path(name):
    return os.path.join(ASSET_DIR, f"{name}.png")


def pictures_dir():
    d = os.path.join(paths.app_dir(), "pictures")
    os.makedirs(d, exist_ok=True)
    return d


def choices():
    """(label, value) for the menus; "choose" = pick your own picture."""
    return ([("Theme default", "theme"), ("None", "none")]
            + [(label, "asset:" + key) for key, label in ASSETS]
            + [("Choose image...", "choose")])


def label_for(value):
    if not value:
        return "Theme default"
    for label, v in choices():
        if v == value:
            return label
    return "My picture: " + os.path.basename(str(value))


def path_for(group, th=None):
    """The picture file to paint for a group (or None)."""
    th = THEME if th is None else th
    v = (group or {}).get("corner")
    if v == "none":
        return None
    if isinstance(v, str) and v.startswith("asset:"):
        p = asset_path(v[6:])
        return p if os.path.exists(p) else None
    if isinstance(v, str) and v and os.path.exists(v):
        return v
    key = th.get("corner")
    if key:
        p = asset_path(key) if not os.path.isabs(str(key)) else key
        return p if os.path.exists(p) else None
    return None


def import_picture(src):
    """Copy a picture into our pictures folder; returns the new path (or raises OSError)."""
    if not QImageReader(src).canRead():
        raise OSError("That file isn't a picture Clutter Buster can read.")
    base, ext = os.path.splitext(os.path.basename(src))
    safe = "".join(ch for ch in base if ch.isalnum() or ch in " -_")[:40] or "picture"
    dest = os.path.join(pictures_dir(), f"{safe}-{int(time.time())}{ext.lower()}")
    shutil.copy2(src, dest)
    return dest


def pixmap(path, size):
    key = (path, int(size))
    pm = _cache.get(key)
    if pm is None:
        if len(_cache) > 80:
            _cache.clear()
        src = QPixmap(path)
        if src.isNull():
            pm = QPixmap()
        else:
            pm = soften(src.scaled(int(size), int(size), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        _cache[key] = pm
    return pm


def soften(pm):
    """Rounded corners (~25 %) and a feathered, fading edge - no hard square photo edges."""
    w, h = pm.width(), pm.height()
    if w < 4 or h < 4:
        return pm
    mask = QPixmap(w, h)
    mask.fill(Qt.transparent)
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.Antialiasing)
    mp.setCompositionMode(QPainter.CompositionMode_Source)
    m = min(w, h)
    feather = max(2.0, m * 0.08)
    steps = 8
    for i in range(steps):
        inset = feather * i / steps
        r = QRectF(inset, inset, w - 2 * inset, h - 2 * inset)
        rad = max(1.0, m * 0.25 - inset)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        mp.fillPath(path, QColor(0, 0, 0, int(255 * (i + 1) / steps)))
    mp.end()
    out = QPixmap(pm)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    p.drawPixmap(0, 0, mask)
    p.end()
    return out


def place(area, avoid, max_frac=0.32, lo=26, hi=120):
    """The biggest square in the lower-right of `area` that doesn't touch the `avoid`
    rects (icons). Falls back to the smallest size if nothing is free."""
    big = max(lo, min(hi, min(area.width(), area.height()) * max_frac))
    s = big
    while s >= lo:
        r = QRectF(area.right() - s, area.bottom() - s, s, s)
        if not any(r.intersects(a) for a in avoid):
            return r, True
        s -= 4
    return QRectF(area.right() - lo, area.bottom() - lo, lo, lo), False


def draw(p, glass, group, avoid=(), margin=8):
    path = path_for(group)
    if not path:
        return None
    area = glass.adjusted(margin, margin, -margin, -margin)
    r, free = place(area, list(avoid))
    pm = pixmap(path, r.width() * max(1.0, p.device().devicePixelRatioF() if p.device() else 1.0))
    if pm.isNull():
        return None
    w, h = pm.width(), pm.height()
    k = r.width() / max(w, h)
    dw, dh = w * k, h * k
    target = QRectF(r.right() - dw, r.bottom() - dh, dw, dh)
    p.save()
    p.setOpacity(0.82 if free else 0.42)
    p.drawPixmap(target, pm, QRectF(0, 0, w, h))
    p.restore()
    return target
