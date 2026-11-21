"""Ctrl+Space quick search: pops up on top of everything, ready to type.

Searches only your desktop items, the items in your groups, and your favorites
(no web results). Forgiving matching. Up/Down to pick, Enter to open, Esc to close.
"""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from . import desktop_layer, fuzzy
from .glass import bring_to_top, draw_glass, draw_neon, draw_shadow
from .theme import THEME, css_rgba, qcolor, rad

ROW_H = 46
MAX_ROWS = 8
BAR_H = 64
W = 680
M = 14  # shadow margin


class QuickSearch(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.c = controller
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.entries = []
        self.results = []
        self.sel = 0
        self.top = 0
        self._hover = None
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Search shortcuts, files, folders and websites")
        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)
        self.icon = QLabel("\U0001F50D", self)
        self.hint = QLabel("Esc", self)
        self.restyle()
        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade.setDuration(120)
        self.fade.setEasingCurve(QEasingCurve.OutCubic)

    def restyle(self):
        """Match the current theme (Clean White / Neon Gamer / custom)."""
        self.edit.setStyleSheet(f"QLineEdit{{background:transparent;border:none;color:{css_rgba('search_text')};"
                                f"font-size:15pt;selection-background-color:{THEME['default_accent']};}}")
        self.icon.setStyleSheet(f"background:transparent;font-size:15pt;color:{css_rgba('hint_text')};")
        self.hint.setStyleSheet(f"background:{css_rgba('item_hover')};color:{css_rgba('hint_text')};"
                                "border-radius:6px;padding:2px 7px;font-size:9pt;")

    # ------------------------------------------------------------ open / close
    def open(self, anchor_center_x, top_y, text=""):
        self.restyle()
        self.entries = self.c.search_entries()
        self.edit.setText(text)
        self._filter(text)
        self._layout()
        self.move(int(anchor_center_x - self.width() / 2), int(top_y - M))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        desktop_layer.force_foreground(int(self.winId()))
        bring_to_top(self)
        self.edit.setFocus()
        self.edit.end(False)
        self.fade.stop()
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.start()

    def close_search(self):
        self.hide()

    def _layout(self):
        rows = min(MAX_ROWS, len(self.results)) if self.edit.text().strip() else min(MAX_ROWS, len(self.results))
        h = BAR_H + (rows * ROW_H + 12 if rows else (40 if self.edit.text().strip() else 0))
        self.setFixedSize(W + 2 * M, h + 2 * M)
        self.icon.setGeometry(M + 22, M + 14, 30, 36)
        self.edit.setGeometry(M + 56, M + 12, W - 130, 40)
        self.hint.setGeometry(M + W - 62, M + 21, 44, 22)

    # ------------------------------------------------------------ filtering
    def _filter(self, text):
        text = text.strip()
        if text:
            self.results = fuzzy.rank(text, self.entries, key=lambda e: e[0], limit=60)
        else:
            self.results = list(self.entries)  # empty box: everything A-Z
        self.sel = 0
        self.top = 0
        self._layout()
        self.update()

    def _ensure_visible(self):
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + MAX_ROWS:
            self.top = self.sel - MAX_ROWS + 1

    def _launch(self, i):
        if 0 <= i < len(self.results):
            path = self.results[i][1]
            self.hide()
            self.c.launch(path)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k == Qt.Key_Escape:
                self.close_search()
                return True
            if k in (Qt.Key_Down, Qt.Key_Tab):
                if self.results:
                    self.sel = min(len(self.results) - 1, self.sel + 1)
                    self._ensure_visible()
                    self.update()
                return True
            if k in (Qt.Key_Up, Qt.Key_Backtab):
                self.sel = max(0, self.sel - 1)
                self._ensure_visible()
                self.update()
                return True
            if k == Qt.Key_PageDown:
                self.sel = min(len(self.results) - 1, self.sel + MAX_ROWS)
                self._ensure_visible()
                self.update()
                return True
            if k == Qt.Key_PageUp:
                self.sel = max(0, self.sel - MAX_ROWS)
                self._ensure_visible()
                self.update()
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._launch(self.sel)
                return True
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------ painting
    def row_rect(self, visible_i):
        return QRectF(M + 10, M + BAR_H + 4 + visible_i * ROW_H, W - 20, ROW_H - 4)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(M, M, W, self.height() - 2 * M)
        draw_shadow(p, r, rad(20), 1.4, layers=10)
        draw_glass(p, r, rad(20), fill_key="popup_fill")
        draw_neon(p, r, rad(20))
        if self.results or self.edit.text().strip():
            p.setPen(QPen(qcolor("divider"), 1))
            p.drawLine(int(r.left() + 16), int(r.top() + BAR_H), int(r.right() - 16), int(r.top() + BAR_H))
        nf = QFont(self.font())
        nf.setPointSizeF(10.5)
        sf = QFont(self.font())
        sf.setPointSizeF(8.5)
        fm = QFontMetrics(nf)
        if not self.results and self.edit.text().strip():
            p.setFont(nf)
            p.setPen(qcolor("hint_text"))
            p.drawText(QRectF(r.left(), r.top() + BAR_H, r.width(), 40), Qt.AlignCenter,
                       "No matches on your desktop or in your groups")
        for vi, i in enumerate(range(self.top, min(len(self.results), self.top + MAX_ROWS))):
            name, path, icon, where = self.results[i]
            rr = self.row_rect(vi)
            if i == self.sel:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(THEME["default_accent"]))
                p.drawRoundedRect(rr, 10, 10)
            elif i == self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(qcolor("item_hover"))
                p.drawRoundedRect(rr, 10, 10)
            icon.paint(p, int(rr.left() + 10), int(rr.top() + 7), 28, 28)
            p.setFont(nf)
            p.setPen(QColor(255, 255, 255) if i == self.sel else qcolor("panel_text"))
            p.drawText(QRectF(rr.left() + 50, rr.top(), rr.width() - 210, rr.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(name, Qt.ElideRight, int(rr.width() - 220)))
            p.setFont(sf)
            p.setPen(QColor(255, 255, 255, 220) if i == self.sel else qcolor("hint_text"))
            p.drawText(QRectF(rr.right() - 160, rr.top(), 150, rr.height()), Qt.AlignRight | Qt.AlignVCenter, where)
        p.end()

    def _row_at(self, pos):
        for vi, i in enumerate(range(self.top, min(len(self.results), self.top + MAX_ROWS))):
            if self.row_rect(vi).contains(pos):
                return i
        return None

    def mouseMoveEvent(self, e):
        h = self._row_at(e.position())
        if h != self._hover:
            self._hover = h
            self.update()

    def mousePressEvent(self, e):
        r = QRectF(M, M, W, self.height() - 2 * M)
        if not r.contains(e.position()):
            self.close_search()
            return
        i = self._row_at(e.position())
        if i is not None and e.button() == Qt.LeftButton:
            self._launch(i)

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy and self.results:
            self.top = max(0, min(max(0, len(self.results) - MAX_ROWS), self.top + (-1 if dy > 0 else 1)))
            self.update()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange and self.isVisible() and not self.isActiveWindow():
            QTimer.singleShot(80, self._maybe_close)

    def _maybe_close(self):
        if self.isVisible() and not self.isActiveWindow() and not QApplication.activePopupWidget():
            self.close_search()
