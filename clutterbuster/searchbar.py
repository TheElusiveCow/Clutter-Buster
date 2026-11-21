"""The always-visible bar at the top center (Clean White mockup style):

  [ magnifier  Search shortcuts and files...     Ctrl+Space ]  [ + New Group ]  [ Undo ]

Clicking the search box (or pressing Ctrl+Space anywhere) opens the quick search.
The bar itself lives on the desktop layer, behind your windows.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from . import hotkey
from .glass import DesktopLayerWindow, draw_glass, draw_shadow
from .theme import qcolor

SEARCH_W, NEW_W, UNDO_W, GAP, H, M = 520, 150, 96, 10, 46, 10


class SearchBar(DesktopLayerWindow):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setFixedSize(SEARCH_W + NEW_W + UNDO_W + 2 * GAP + 2 * M, H + 2 * M)
        self.setMouseTracking(True)
        self._hover = None
        self._undo_enabled = False
        self._undo_label = ""
        self.hotkey_ok = None

    def search_rect(self):
        return QRectF(M, M, SEARCH_W, H)

    def new_rect(self):
        return QRectF(M + SEARCH_W + GAP, M, NEW_W, H)

    def undo_rect(self):
        return QRectF(M + SEARCH_W + GAP + NEW_W + GAP, M, UNDO_W, H)

    def place(self, avail):
        # centre the SEARCH box on the screen (buttons sit to its right)
        self.move(int(avail.center().x() - M - SEARCH_W / 2), avail.top() + 12)

    def search_global_center_x(self):
        return self.mapToGlobal(self.search_rect().center().toPoint()).x()

    def register_hotkey(self):
        self.hotkey_ok = hotkey.register(int(self.winId()))
        return self.hotkey_ok

    def on_hotkey(self, hotkey_id):
        if hotkey_id == hotkey.HOTKEY_ID:
            self.c.open_quick_search()

    def update_undo(self, enabled, label):
        self._undo_enabled = enabled
        self._undo_label = label
        self.setToolTip("")
        self.update()

    def mark_dirty(self):
        pass  # quick search reloads its list every time it opens

    # ------------------------------------------------------------ painting
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255, 1))
        f = QFont(self.font())
        f.setPointSizeF(11)
        bf = QFont(self.font())
        bf.setPointSizeF(10.5)
        bf.setWeight(QFont.DemiBold)
        hf = QFont(self.font())
        hf.setPointSizeF(9)
        for key, r in (("search", self.search_rect()), ("new", self.new_rect()), ("undo", self.undo_rect())):
            rad = 14
            draw_shadow(p, r, rad, 0.8)
            draw_glass(p, r, rad, fill_key="glass_fill_hover", hover=self._hover == key, strip=(key == "search"))
        # search box contents
        sr = self.search_rect()
        p.setPen(QPen(QColor(90, 90, 100), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(sr.left() + 25, sr.center().y() - 2), 7, 7)
        p.drawLine(QPointF(sr.left() + 30, sr.center().y() + 3), QPointF(sr.left() + 35, sr.center().y() + 8))
        p.setFont(f)
        p.setPen(qcolor("hint_text"))
        p.drawText(sr.adjusted(48, 0, -10, 0), Qt.AlignLeft | Qt.AlignVCenter, "Search shortcuts and files...")
        p.setFont(hf)
        hint = "Ctrl+Space" if self.hotkey_ok is not False else "click to search"
        p.drawText(sr.adjusted(0, 0, -16, 0), Qt.AlignRight | Qt.AlignVCenter, hint)
        # buttons
        p.setFont(bf)
        p.setPen(qcolor("button_text"))
        p.drawText(self.new_rect(), Qt.AlignCenter, "+  New Group")
        p.setPen(qcolor("button_text") if self._undo_enabled else QColor(28, 28, 34, 90))
        p.drawText(self.undo_rect(), Qt.AlignCenter, "\u21B6  Undo")
        p.end()

    # ------------------------------------------------------------ mouse
    def _hit(self, pos):
        for key, r in (("search", self.search_rect()), ("new", self.new_rect()), ("undo", self.undo_rect())):
            if r.contains(pos):
                return key
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.PointingHandCursor if h in ("new", "undo") else
                           (Qt.IBeamCursor if h == "search" else Qt.ArrowCursor))
            tips = {"undo": (f"Undo: {self._undo_label}" if self._undo_enabled else "Nothing to undo"),
                    "new": "Make a new empty group", "search": "Search (Ctrl+Space)"}
            self.setToolTip(tips.get(h, ""))
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position())
        if h == "search":
            self.c.open_quick_search()
        elif h == "new":
            self.c.create_group()
        elif h == "undo" and self._undo_enabled:
            self.c.undo()
