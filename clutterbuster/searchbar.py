"""The always-visible bars at the top (on the desktop layer, behind your windows):

  [ magnifier  Search shortcuts and files...     Ctrl+Space ]   <- SearchBar
                                                [ + New Group ] [ gear ]   <- ActionBar

Clicking the search box (or pressing Ctrl+Space anywhere) opens the quick search.
In Edit layout both bars get a dashed outline and can be dragged somewhere else
(they snap to a 16px grid). Outside Edit layout they stay put.
"""
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from . import hotkey
from .glass import DesktopLayerWindow, draw_edit_outline, draw_glass, draw_neon, draw_shadow
from .theme import qcolor, rad

SEARCH_W, NEW_W, GEAR_W, GAP, H, M = 520, 150, 52, 10, 46, 10


class _Bar(DesktopLayerWindow):
    ui_key = ""

    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setMouseTracking(True)
        self._hover = None

    def boxes(self):
        return []

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255, 1))
        for key, r in self.boxes():
            rr = rad(14)
            draw_shadow(p, r, rr, 0.8)
            draw_glass(p, r, rr, fill_key="glass_fill_hover", hover=self._hover == key, strip=(key == "search"))
            draw_neon(p, r, rr)
        self.paint_contents(p)
        if self.c.edit_mode:
            for _key, r in self.boxes():
                draw_edit_outline(p, r, rad(14), handles=False)
        p.end()

    def paint_contents(self, p):
        pass

    def _hit(self, pos):
        for key, r in self.boxes():
            if r.contains(pos):
                return key
        return None

    # edit layout: drag the whole bar
    def mousePressEvent(self, e):
        if self.c.edit_mode and e.button() == Qt.LeftButton:
            self.edit_press(e)

    def mouseMoveEvent(self, e):
        if self.c.edit_mode:
            self.setCursor(Qt.SizeAllCursor)
            self.setToolTip("Drag to move (Edit layout)")
            if e.buttons() & Qt.LeftButton:
                self.edit_drag(e)
            return
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.on_hover(h)
            self.update()

    def on_hover(self, h):
        pass

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.c.edit_mode:
            pt = self.edit_release()
            if pt is not None:
                self.c.bar_moved(self.ui_key, self, pt)
            return
        self.on_click(self._hit(e.position()))

    def on_click(self, key):
        pass


class SearchBar(_Bar):
    ui_key = "search_pos"

    def __init__(self, controller):
        super().__init__(controller)
        self.setFixedSize(SEARCH_W + 2 * M, H + 2 * M)
        self.hotkey_ok = None

    def search_rect(self):
        return QRectF(M, M, SEARCH_W, H)

    def boxes(self):
        return [("search", self.search_rect())]

    def default_pos(self, avail):
        # centre the search box on the screen
        return int(avail.center().x() - M - SEARCH_W / 2), avail.top() + 12

    def search_global_center_x(self):
        return self.mapToGlobal(self.search_rect().center().toPoint()).x()

    def register_hotkey(self):
        self.hotkey_ok = hotkey.register(int(self.winId()))
        return self.hotkey_ok

    def on_hotkey(self, hotkey_id):
        if hotkey_id == hotkey.HOTKEY_ID:
            self.c.open_quick_search()

    def update_undo(self, enabled, label):
        pass

    def paint_contents(self, p):
        f = QFont(self.font())
        f.setPointSizeF(11)
        hf = QFont(self.font())
        hf.setPointSizeF(9)
        sr = self.search_rect()
        p.setPen(QPen(qcolor("icon_glyph"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(sr.left() + 25, sr.center().y() - 2), 7, 7)
        p.drawLine(QPointF(sr.left() + 30, sr.center().y() + 3), QPointF(sr.left() + 35, sr.center().y() + 8))
        p.setFont(f)
        p.setPen(qcolor("hint_text"))
        p.drawText(sr.adjusted(48, 0, -10, 0), Qt.AlignLeft | Qt.AlignVCenter, "Search shortcuts and files...")
        p.setFont(hf)
        hint = "Ctrl+Space" if self.hotkey_ok is not False else "click to search"
        p.drawText(sr.adjusted(0, 0, -16, 0), Qt.AlignRight | Qt.AlignVCenter, hint)

    def on_hover(self, h):
        self.setCursor(Qt.IBeamCursor if h == "search" else Qt.ArrowCursor)
        self.setToolTip("Search (Ctrl+Space)" if h else "")

    def on_click(self, key):
        if key == "search":
            self.c.open_quick_search()


class ActionBar(_Bar):
    """[ + New Group ] [ gear ]  - the gear opens the compact glass menu (quickmenu.py)."""
    ui_key = "actions_pos"

    def __init__(self, controller):
        super().__init__(controller)
        self.setFixedSize(NEW_W + GEAR_W + GAP + 2 * M, H + 2 * M)
        self._undo_enabled = False
        self._undo_label = ""

    def new_rect(self):
        return QRectF(M, M, NEW_W, H)

    def gear_rect(self):
        return QRectF(M + NEW_W + GAP, M, GEAR_W, H)

    def boxes(self):
        return [("new", self.new_rect()), ("gear", self.gear_rect())]

    def update_undo(self, enabled, label):
        self._undo_enabled = enabled
        self._undo_label = label

    def paint_contents(self, p):
        bf = QFont(self.font())
        bf.setPointSizeF(10.5)
        bf.setWeight(QFont.DemiBold)
        p.setFont(bf)
        p.setPen(qcolor("button_text"))
        p.drawText(self.new_rect(), Qt.AlignCenter, "+  New Group")
        draw_gear(p, self.gear_rect().center(), 10.5, qcolor("button_text"))

    def on_hover(self, h):
        self.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
        tips = {"new": "Make a new empty group",
                "gear": "Settings: auto organize, undo, themes, hide/lock, sound, transparency, tidy up..."}
        self.setToolTip(tips.get(h, ""))

    def on_click(self, key):
        if key == "new":
            self.c.create_group()
        elif key == "gear":
            r = self.gear_rect()
            self.c.show_quick_menu(QRect(self.mapToGlobal(r.topLeft().toPoint()), r.size().toSize()))


def draw_gear(p, c, r, color):
    """A simple cog: 8 teeth, a ring and a hole."""
    import math
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
