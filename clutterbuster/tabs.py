"""Tabs inside groups: the segmented tab bar (  IT | Servers | Tickets  + ) and the optional
List view (Name / Date modified / Type). Shared by big panels and the popup."""
import datetime
import os

from PySide6.QtCore import QFileInfo, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QFileIconProvider

from . import icons
from .desktop_files import is_url
from .theme import THEME, is_dark, neon_gradient, qcolor

TAB_H = 26
PLUS_W = 22
ROW_H = 26
HEAD_H = 22
_types = {}
_prov = None


# ------------------------------------------------------------------ tab bar
def tab_font(base, pt=9.0):
    f = QFont(base)
    f.setPointSizeF(pt)
    f.setWeight(QFont.DemiBold)
    return f


class Segs(list):
    """[(tab id, rect)] plus the font the bar was fitted with ("more" = the ▾ overflow button)."""
    font = None
    hidden = ()


MORE = "more"


def bar_layout(font, tabs, x, y, max_w, plus=True, current=None, h=TAB_H, min_pt=7.0, dots_ok=False):
    """Fit the tabs into max_w - always, at any size:
    1) natural widths, shrinking the font a little if needed;
    2) equal widths with long names cut short with '…';
    3) too many: the selected tab + as many as fit, and a '▾' button listing them all.
    -> (segments, track rect, plus rect or None). An empty list means not even one fits."""
    room = max_w - ((PLUS_W + 6) if plus else 0) - 4
    base_pt = font.pointSizeF() if font.pointSizeF() > 0 else 9.0
    pts = [base_pt]
    while pts[-1] - 0.75 >= min_pt:
        pts.append(pts[-1] - 0.75)
    segs = Segs()
    widths, use = None, list(tabs)
    for pt in pts:
        f = QFont(font)
        f.setPointSizeF(pt)
        fm = QFontMetrics(f)
        pad = 12 if pt == base_pt else 9
        nat = [fm.horizontalAdvance(t.get("name") or "Tab") + 2 * pad for t in tabs]
        if sum(nat) <= room:
            widths = nat
            break
    if widths is None:
        min_w = fm.horizontalAdvance("Abc\u2026") + 10
        if min_w * len(tabs) <= room:
            widths = [room / len(tabs)] * len(tabs)
        else:
            more_w = fm.horizontalAdvance("\u25be 99") + 12
            k = int((room - more_w) // min_w)
            if dots_ok and k < 2:      # not even two readable pills: the caller shows dots
                segs.font = f
                return segs, QRectF(), None
            k = max(1, k)
            use = list(tabs[:k])
            if current and current not in [t["id"] for t in use]:
                cur = next((t for t in tabs if t["id"] == current), None)
                if cur is not None:
                    use[-1] = cur
            segs.hidden = tuple(t["id"] for t in tabs if t not in use)
            widths = [(room - more_w) / k] * k + [more_w]
            use = use + [{"id": MORE, "name": "\u25be %d" % len(segs.hidden)}]
    segs.font = f
    track = QRectF(x, y, sum(widths) + 4, h)
    cx = x + 2
    for t, w in zip(use, widths):
        segs.append((t["id"], QRectF(cx, y + 2, w, h - 4)))
        cx += w
    segs.names = {t["id"]: (t.get("name") or "Tab") for t in use}
    plus_r = QRectF(track.right() + 6, y + (h - PLUS_W) / 2, PLUS_W, PLUS_W) if plus else None
    return segs, track, plus_r


def plus_only(x, y):
    return QRectF(x, y + (TAB_H - PLUS_W) / 2, PLUS_W, PLUS_W)


def paint_plus(p, r, hover=False):
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    p.setPen(QPen(qcolor("card_border"), 1))
    p.setBrush(qcolor("card_fill_hot" if hover else "card_fill"))
    p.drawEllipse(r)
    pen = QPen(qcolor("hint_text") if not hover else qcolor("panel_text"), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    c = r.center()
    p.drawLine(c.x() - 5, c.y(), c.x() + 5, c.y())
    p.drawLine(c.x(), c.y() - 5, c.x(), c.y() + 5)
    p.restore()


def paint_bar(p, font, tabs, segs, track, plus_r, current, accent, hover=None, drop=None):
    """Segmented pill. Selected tab = a darker pill (Clean White) / a glowing glass pill (Neon)."""
    dark = is_dark()
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    font = getattr(segs, "font", None) or font
    p.setFont(font)
    rr = track.height() / 2
    p.setPen(QPen(QColor(255, 255, 255, 30) if dark else QColor(0, 0, 0, 22), 1))
    p.setBrush(QColor(255, 255, 255, 16) if dark else QColor(20, 24, 40, 18))
    p.drawRoundedRect(track, rr, rr)
    names = {t["id"]: (t["name"] or "Tab") for t in tabs}
    names.update(getattr(segs, "names", {}))
    fm = QFontMetrics(font)
    for tid, r in segs:
        sel = tid == current
        sr = (r.height()) / 2
        if sel:
            if dark:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 46))
                p.drawRoundedRect(r, sr, sr)
                if THEME.get("glow") and THEME.get("glow_strength", 0) > 0.01:
                    a = int(120 + 135 * THEME.get("glow_strength", 0.6))
                    p.setPen(QPen(QBrush(neon_gradient(r.center(), min(255, a), accent)), 1.6))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), sr, sr)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(44, 46, 58, 225))
                p.drawRoundedRect(r, sr, sr)
        elif tid == hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 22) if dark else QColor(0, 0, 0, 14))
            p.drawRoundedRect(r, sr, sr)
        if tid == drop:
            p.setPen(QPen(QColor(accent), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), sr, sr)
        if sel:
            p.setPen(QColor(255, 255, 255) if not dark else qcolor("title_text"))
        else:
            p.setPen(qcolor("panel_subtext"))
        p.drawText(r.adjusted(4, 0, -4, 0), Qt.AlignCenter,
                   fm.elidedText(names.get(tid, ""), Qt.ElideRight, int(r.width() - 9)))
    if plus_r is not None:
        paint_plus(p, plus_r, hover == "+")
    p.restore()


def hit_bar(segs, plus_r, pos):
    for tid, r in segs:
        if r.contains(pos):
            return tid
    if plus_r is not None and plus_r.adjusted(-3, -3, 3, 3).contains(pos):
        return "+"
    return None


# ------------------------------------------------------------------ list view
def item_type(path):
    if is_url(path):
        return "Website"
    if path in _types:
        return _types[path]
    global _prov
    if _prov is None:
        _prov = QFileIconProvider()
    t = ""
    try:
        t = _prov.type(QFileInfo(path))
    except Exception:
        t = ""
    if not t or t.lower() in ("file", "unknown"):
        ext = os.path.splitext(path)[1].lower()
        t = {".lnk": "Shortcut", ".url": "Internet Shortcut"}.get(ext) or \
            ("File folder" if os.path.isdir(path) else (ext[1:].upper() + " File" if ext else "File"))
    _types[path] = t
    return t


def item_date(item):
    p = item["path"]
    try:
        if is_url(p):
            d = datetime.datetime.fromisoformat(item.get("added", ""))
        else:
            d = datetime.datetime.fromtimestamp(os.path.getmtime(p))
    except (OSError, ValueError, TypeError):
        return ""
    return f"{d.month}/{d.day}/{d.year} {d.strftime('%I:%M %p').lstrip('0')}"


def columns(width):
    """[(key, title, x offset, width)] - narrow panels drop Type, then Date."""
    cols = [("name", "Name", 0, width)]
    if width >= 300:
        dw = 132
        tw = 104 if width >= 420 else 0
        nw = width - dw - tw
        cols = [("name", "Name", 0, nw), ("date", "Date modified", nw, dw)]
        if tw:
            cols.append(("type", "Type", nw + dw, tw))
    return cols


def rows_per_page(h):
    return max(1, int((h - HEAD_H) // ROW_H))


def row_rects(rect, n):
    return [QRectF(rect.left(), rect.top() + HEAD_H + i * ROW_H, rect.width(), ROW_H) for i in range(n)]


def paint_list(p, rect, g, indices, base_font, hover=None, selected=None, drop=None, accent=None):
    """indices = item indexes on this page. Draws the header and one row per item."""
    p.save()
    p.setRenderHint(p.RenderHint.Antialiasing)
    hf = QFont(base_font)
    hf.setPointSizeF(8.3)
    p.setFont(hf)
    cols = columns(rect.width())
    p.setPen(qcolor("hint_text"))
    for _k, title, x, w in cols:
        p.drawText(QRectF(rect.left() + x + (30 if _k == "name" else 6), rect.top(), w - 10, HEAD_H),
                   Qt.AlignLeft | Qt.AlignVCenter, title)
    p.setPen(QPen(qcolor("divider"), 1))
    p.drawLine(rect.left(), rect.top() + HEAD_H - 1, rect.right(), rect.top() + HEAD_H - 1)
    nf = QFont(base_font)
    nf.setPointSizeF(9)
    sf = QFont(base_font)
    sf.setPointSizeF(8.3)
    fm, sfm = QFontMetrics(nf), QFontMetrics(sf)
    for idx, rr in zip(indices, row_rects(rect, len(indices))):
        it = g["items"][idx]
        if idx in (hover, selected, drop):
            p.setPen(QPen(QColor(accent), 1.4) if idx == drop else Qt.NoPen)
            col = QColor(accent) if idx == selected else qcolor("item_hover")
            if idx == selected:
                col.setAlpha(70)
            p.setBrush(col)
            p.drawRoundedRect(rr.adjusted(1, 1, -1, -1), 6, 6)
        icons.icon_for(it["path"]).paint(p, QRectF(rr.left() + 6, rr.top() + 4, 18, 18).toRect())
        for k, _t, x, w in cols:
            if k == "name":
                p.setFont(nf)
                p.setPen(qcolor("panel_text"))
                txt = fm.elidedText(icons.item_name(it), Qt.ElideRight, int(w - 40))
                p.drawText(QRectF(rr.left() + 30, rr.top(), w - 34, rr.height()), Qt.AlignLeft | Qt.AlignVCenter, txt)
            else:
                p.setFont(sf)
                p.setPen(qcolor("panel_subtext"))
                txt = item_date(it) if k == "date" else item_type(it["path"])
                p.drawText(QRectF(rr.left() + x + 6, rr.top(), w - 10, rr.height()), Qt.AlignLeft | Qt.AlignVCenter,
                           sfm.elidedText(txt, Qt.ElideRight, int(w - 10)))
    p.restore()
