"""The toolbar on the desktop layer (behind your windows):

  [ :: | magnifier  Search shortcuts...  Ctrl+Space | + New Group | gear ]      <- a floating pill

Drag it by the grip (the dots on the left) anywhere on the main screen; it remembers
where you left it. Drop it near a screen corner (within ~60 px) and it tucks into that
corner as a quarter-circle wedge: the search field runs along the curve, with round
+ and gear buttons below it. Drag the wedge (by the dots in the corner) out again and
it turns back into the pill. "Lock layout" stops it moving; the gear menu has
"Reset toolbar position". Pressing Ctrl+Space (or your own shortcut) opens quick search.
"""
import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker,
                           QPen, QPolygonF, QRadialGradient)

from . import decor, hotkey
from .glass import DesktopLayerWindow, draw_edit_outline, draw_glass, draw_neon, draw_shadow
from .theme import THEME, qcolor, rad

M = 10                  # transparent margin round the pill (room for the shadow)
PAD, GAP = 6, 8
PILL_H, BOX_H = 58, 46
GRIP_W, SEARCH_W, NEW_W, GEAR_W = 22, 430, 150, 46
WEDGE_R = 224           # radius of the corner wedge
WEDGE_BAND = WEDGE_R - 46
SNAP = 60               # drop this close to a corner to tuck the toolbar into it
CORNERS = ("tl", "tr", "bl", "br")
DRAG_START = 6
# the bits along the wedge's curve (degrees from the horizontal screen edge)
SEARCH_A, PLUS_A, GEAR_A = (9.0, 58.0), 70.0, 83.0
TEXT = "Search shortcuts..."


def pill_size():
    return (2 * M + 2 * PAD + GRIP_W + SEARCH_W + NEW_W + GEAR_W + 3 * GAP, 2 * M + PILL_H)


class SearchBar(DesktopLayerWindow):
    """The whole toolbar (search + New Group + gear). Kept under its old name; the
    controller's `actions` points at this same window."""
    ui_key = "search_pos"

    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setMouseTracking(True)
        self._hover = None
        self.hotkey_ok = None
        self.corner = None           # None = floating pill, else "tl"/"tr"/"bl"/"br"
        self._drag = None            # (press global pos, window pos at press, started?)
        self._snap = None            # corner we'd tuck into if dropped now
        self._undo_enabled, self._undo_label = False, ""
        self.setFixedSize(*pill_size())

    # ------------------------------------------------------------ shape
    @property
    def wedge(self):
        return self.corner in CORNERS

    def set_corner(self, corner):
        corner = corner if corner in CORNERS else None
        if corner == self.corner and self.size() == self._size_for(corner):
            return
        self.corner = corner
        self.setFixedSize(self._size_for(corner))
        self.update()

    def _size_for(self, corner):
        from PySide6.QtCore import QSize
        if corner in CORNERS:
            return QSize(WEDGE_R + 4, WEDGE_R + 4)
        return QSize(*pill_size())

    def pill_rect(self):
        return QRectF(M, M, self.width() - 2 * M, PILL_H)

    def _box(self, x, w):
        return QRectF(x, M + (PILL_H - BOX_H) / 2, w, BOX_H)

    def grip_rect(self):
        if self.wedge:
            c = self._pt(WEDGE_R * 0.26, 45)
            return QRectF(c.x() - 18, c.y() - 18, 36, 36)
        return self._box(M + PAD, GRIP_W)

    def search_rect(self):
        if self.wedge:
            return self._band_path().boundingRect()
        return self._box(M + PAD + GRIP_W + GAP, SEARCH_W)

    def new_rect(self):
        if self.wedge:
            c = self._pt(WEDGE_BAND, PLUS_A)
            return QRectF(c.x() - 17, c.y() - 17, 34, 34)
        return self._box(self.search_rect().right() + GAP, NEW_W)

    def gear_rect(self):
        if self.wedge:
            c = self._pt(WEDGE_BAND, GEAR_A)
            return QRectF(c.x() - 17, c.y() - 17, 34, 34)
        return self._box(self.new_rect().right() + GAP, GEAR_W)

    # wedge maths: C = the screen corner, u along the top/bottom edge, v along the side edge
    def _frame(self):
        S = self.width()
        return {"tl": (QPointF(0, 0), (1, 0), (0, 1)), "tr": (QPointF(S, 0), (-1, 0), (0, 1)),
                "bl": (QPointF(0, S), (1, 0), (0, -1)), "br": (QPointF(S, S), (-1, 0), (0, -1))}[self.corner]

    def _pt(self, r, deg):
        C, u, v = self._frame()
        a = math.radians(deg)
        return QPointF(C.x() + r * (math.cos(a) * u[0] + math.sin(a) * v[0]),
                       C.y() + r * (math.cos(a) * u[1] + math.sin(a) * v[1]))

    def _polar(self, pos):
        C, u, v = self._frame()
        dx, dy = pos.x() - C.x(), pos.y() - C.y()
        a, b = dx * u[0] + dy * u[1], dx * v[0] + dy * v[1]
        return math.hypot(a, b), math.degrees(math.atan2(b, a))

    def _wedge_path(self):
        C = self._frame()[0]
        poly = [C] + [self._pt(WEDGE_R, d) for d in range(0, 91, 2)]
        path = QPainterPath()
        path.addPolygon(QPolygonF(poly))
        path.closeSubpath()
        return path

    def _arc(self, r, a0, a1, step=1.5):
        path = QPainterPath(self._pt(r, a0))
        d = a0
        while d < a1:
            d = min(a1, d + step)
            path.lineTo(self._pt(r, d))
        return path

    def _band_path(self):
        st = QPainterPathStroker()
        st.setWidth(36)
        st.setCapStyle(Qt.RoundCap)
        return st.createStroke(self._arc(WEDGE_BAND, *SEARCH_A)).simplified()

    def _reading_forward(self):
        """Run the text along the curve so it's never upside down."""
        return self.corner in ("tr", "br")

    # ------------------------------------------------------------ painting
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255, 1))
        if self.wedge:
            self._paint_wedge(p)
        else:
            self._paint_pill(p)
        p.end()

    def _inner_box(self, p, r, key, radius):
        hot = self._hover == key
        p.setPen(QPen(qcolor("card_border"), 1.2 if not THEME.get("border_w", 1) > 2 else 2.0))
        p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
        p.drawRoundedRect(r, radius, radius)

    def _paint_pill(self, p):
        pr = self.pill_rect()
        rr = rad(PILL_H / 2)
        draw_shadow(p, pr, rr, 0.8)
        draw_glass(p, pr, rr, fill_key="glass_fill_hover", hover=False, strip=True)
        draw_neon(p, pr, rr)
        # grip: 2 x 3 dots
        g = self.grip_rect()
        self._dots(p, g.center(), self._hover == "grip")
        sr = self.search_rect()
        self._inner_box(p, sr, "search", rad(BOX_H / 2))
        self._inner_box(p, self.new_rect(), "new", rad(BOX_H / 2))
        self._inner_box(p, self.gear_rect(), "gear", rad(BOX_H / 2))
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        self._magnifier(p, QPointF(sr.left() + 22, sr.center().y()))
        p.setFont(f)
        p.setPen(qcolor("hint_text"))
        p.drawText(sr.adjusted(42, 0, -10, 0), Qt.AlignLeft | Qt.AlignVCenter, TEXT)
        hf = QFont(self.font())
        hf.setPointSizeF(8.5)
        p.setFont(hf)
        p.drawText(sr.adjusted(0, 0, -16, 0), Qt.AlignRight | Qt.AlignVCenter, self.hint_text())
        bf = QFont(self.font())
        bf.setPointSizeF(10.5)
        bf.setWeight(QFont.DemiBold)
        p.setFont(bf)
        p.setPen(qcolor("button_text"))
        p.drawText(self.new_rect(), Qt.AlignCenter, "+  New Group")
        draw_gear(p, self.gear_rect().center(), 10.5, qcolor("button_text"))
        if self._snap:
            self._snap_hint(p, pr, rr)
        if self.c.edit_mode:
            draw_edit_outline(p, pr, rr, handles=False)

    def _paint_wedge(self, p):
        path = self._wedge_path()
        p.save()
        p.fillPath(path, qcolor("glass_fill_hover"))
        p.setClipPath(path)
        C = self._frame()[0]
        shine = QRadialGradient(C, WEDGE_R)
        shine.setColorAt(0, qcolor("glass_shine"))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), shine)
        if THEME.get("decor") in ("stars", "frost"):
            decor.inside(p, path, QRectF(self.rect()), 0)
        p.restore()
        # the curved edge
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(qcolor("glass_border"), max(1.2, float(THEME.get("border_w", 1.0)))))
        p.drawPath(self._arc(WEDGE_R - 0.8, 0, 90))
        if THEME.get("glow"):
            acc = QColor(THEME["default_accent"])
            for i, a in ((3, 50), (1.5, 110)):
                acc.setAlpha(a)
                p.setPen(QPen(acc, i))
                p.drawPath(self._arc(WEDGE_R - 1, 0, 90))
        # search band along the curve
        band = self._band_path()
        p.setPen(QPen(qcolor("card_border"), 1.2))
        p.setBrush(qcolor("card_fill_hot" if self._hover == "search" else "card_fill"))
        p.drawPath(band)
        self._curved_text(p)
        for key, r in (("new", self.new_rect()), ("gear", self.gear_rect())):
            p.setPen(QPen(qcolor("card_border"), 1.2))
            p.setBrush(qcolor("card_fill_hot" if self._hover == key else "card_fill"))
            p.drawEllipse(r)
        c = self.new_rect().center()
        p.setPen(QPen(qcolor("button_text"), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(c.x() - 7, c.y()), QPointF(c.x() + 7, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 7), QPointF(c.x(), c.y() + 7))
        draw_gear(p, self.gear_rect().center(), 9.5, qcolor("button_text"))
        self._dots(p, self.grip_rect().center(), self._hover == "grip")
        if self.c.edit_mode:
            p.setPen(QPen(QColor(THEME["default_accent"]), 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

    def _curved_text(self, p):
        f = QFont(self.font())
        f.setPointSizeF(9.5)
        fm = QFontMetricsF(f)
        a0, a1 = SEARCH_A
        fwd = self._reading_forward()
        r = WEDGE_BAND
        step = lambda w: math.degrees(w / r)           # noqa: E731  arc degrees for w pixels
        start = a0 + step(6) if fwd else a1 - step(6)
        # magnifier first, then the words
        mag_a = start + (step(8) if fwd else -step(8))
        self._magnifier(p, self._pt(r, mag_a), 5.5)
        ang = mag_a + (step(16) if fwd else -step(16))
        p.setFont(f)
        p.setPen(qcolor("hint_text"))
        end_a = a1 - step(4) if fwd else a0 + step(4)
        for ch in TEXT:
            w = fm.horizontalAdvance(ch)
            mid = ang + (step(w / 2) if fwd else -step(w / 2))
            if (fwd and mid > end_a) or (not fwd and mid < end_a):
                break
            pt = self._pt(r, mid)
            d = 0.5
            t1, t2 = self._pt(r, mid - d), self._pt(r, mid + d)
            tx, ty = (t2.x() - t1.x(), t2.y() - t1.y()) if fwd else (t1.x() - t2.x(), t1.y() - t2.y())
            p.save()
            p.translate(pt)
            p.rotate(math.degrees(math.atan2(ty, tx)))
            p.drawText(QPointF(-w / 2, (fm.ascent() - fm.descent()) / 2), ch)
            p.restore()
            ang += step(w) if fwd else -step(w)

    def _magnifier(self, p, c, r=7.0):
        p.setPen(QPen(qcolor("icon_glyph"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(c.x() - 1, c.y() - 2), r, r)
        k = r * 0.72
        p.drawLine(QPointF(c.x() - 1 + k, c.y() - 2 + k), QPointF(c.x() + 2 + k * 1.3, c.y() + 1 + k * 1.3))

    def _dots(self, p, c, hot=False):
        col = QColor(qcolor("icon_glyph"))
        col.setAlpha(230 if hot else 150)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        for dx in (-3.5, 3.5):
            for dy in (-7, 0, 7):
                p.drawEllipse(QPointF(c.x() + dx, c.y() + dy), 2.0, 2.0)

    def _snap_hint(self, p, r, rr):
        acc = QColor(THEME["default_accent"])
        p.setPen(QPen(acc, 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rr, rr)

    def hint_text(self):
        return self.c.search_hotkey()["text"] if self.hotkey_ok is not False else "click to search"

    # ------------------------------------------------------------ hotkey (unchanged)
    def default_pos(self, avail):
        w, _h = pill_size()
        return int(avail.center().x() - w / 2), avail.top() + 12

    def search_global_center_x(self):
        return self.mapToGlobal(self.search_rect().center().toPoint()).x()

    def register_hotkey(self, hk=None):
        hk = hk or self.c.search_hotkey()
        self.hotkey_ok = hotkey.register(int(self.winId()), hk["mods"], hk["vk"])
        self.update()
        return self.hotkey_ok

    def on_hotkey(self, hotkey_id):
        if hotkey_id == hotkey.HOTKEY_ID:
            self.c.open_quick_search()

    def update_undo(self, enabled, label):
        self._undo_enabled, self._undo_label = enabled, label

    # ------------------------------------------------------------ mouse
    def hit(self, pos):
        if self.wedge:
            r, a = self._polar(pos)
            if r > WEDGE_R or a < -1 or a > 91:
                return None
            for key in ("new", "gear"):
                rc = getattr(self, key + "_rect")()
                if math.hypot(pos.x() - rc.center().x(), pos.y() - rc.center().y()) <= 19:
                    return key
            if self._band_path().contains(QPointF(pos)):
                return "search"
            if r < WEDGE_BAND - 26:
                return "grip"
            return "body"
        for key in ("grip", "search", "new", "gear"):
            if getattr(self, key + "_rect")().adjusted(0, -4, 0, 4).contains(QPointF(pos)):
                return key
        return "body" if self.pill_rect().contains(QPointF(pos)) else None

    def can_move(self):
        return not self.c.layout_locked()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self.hit(e.position())
        self._press_key = h
        if self.can_move() and (h == "grip" or (self.c.edit_mode and h is not None)):
            self._drag = [e.globalPosition().toPoint(), self.pos(), False, e.position()]

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            g0, w0, started, local0 = self._drag
            gp = e.globalPosition().toPoint()
            if not started and (gp - g0).manhattanLength() < DRAG_START:
                return
            if not started:
                self._drag[2] = True
                if self.wedge:                        # pull it out: back to the pill, grip under the mouse
                    self.set_corner(None)
                    gc = self.grip_rect().center()
                    self._drag[1] = gp - QPoint(int(gc.x()), int(gc.y()))
                    self._drag[0] = gp
                    g0, w0 = self._drag[0], self._drag[1]
                self.setCursor(Qt.ClosedHandCursor)
            self.move(w0 + (gp - g0))
            snap = self.c.toolbar_snap_corner(self.geometry(), gp)
            if snap != self._snap:
                self._snap = snap
                self.update()
            return
        h = self.hit(e.position())
        if h != self._hover:
            self._hover = h
            self.on_hover(h)
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._drag is not None:
            started = self._drag[2]
            self._drag = None
            if started:
                snap, self._snap = self._snap, None
                self.setCursor(Qt.OpenHandCursor)
                self.c.toolbar_moved(snap, self.pos())
                return
        key = self.hit(e.position())
        if key == getattr(self, "_press_key", None) and not self.c.edit_mode:   # a click = press + release on it
            self.on_click(key)
        self._press_key = None

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def on_hover(self, h):
        locked = self.c.layout_locked()
        if h == "grip" or (self.c.edit_mode and h):
            self.setCursor(Qt.ArrowCursor if locked else Qt.OpenHandCursor)
            self.setToolTip("Layout is locked - unlock it in the gear menu to move the toolbar" if locked else
                            "Drag to move the toolbar. Drop it in a screen corner to tuck it in there.")
            return
        self.setCursor(Qt.IBeamCursor if h == "search" else Qt.PointingHandCursor if h in ("new", "gear")
                       else Qt.ArrowCursor)
        tips = {"search": f"Search ({self.c.search_hotkey()['text']})", "new": "Make a new empty group",
                "gear": "Settings: auto organize, undo, themes, hide/lock, sound, transparency, tidy up..."}
        self.setToolTip(tips.get(h, ""))

    def on_click(self, key):
        if key == "search":
            self.c.open_quick_search()
        elif key == "new":
            self.c.create_group()
        elif key == "gear":
            r = self.gear_rect()
            self.c.show_quick_menu(QRect(self.mapToGlobal(r.topLeft().toPoint()), r.size().toSize()))


ActionBar = SearchBar   # old name: New Group + gear now live in the same toolbar


def draw_gear(p, c, r, color):
    """A simple cog: 8 teeth, a ring and a hole."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    teeth = 8
    pts = []
    for i in range(teeth * 4):
        a = (i / (teeth * 4)) * 2 * math.pi - math.pi / 2
        rr = r if (i % 4) in (1, 2) else r * 0.74
        pts.append(QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a)))
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(c, r * 0.32, r * 0.32)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path.subtracted(hole))
    p.restore()
