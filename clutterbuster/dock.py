"""The favorites dock: a small glass strip under the search bar.

It hides itself until the mouse comes near (a thin hover zone with a tiny handle),
then slides/fades in. Drag things onto it to add favorites; right-click to remove.
Favorites are only references - they never hide or touch the real file.
"""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QFont, QPainter

from . import icons
from .glass import (DesktopLayerWindow, accept_drag, draw_edit_outline, draw_glass, draw_neon, draw_shadow,
                    parse_drop, read_item)
from .theme import qcolor, rad

ICON = 34
CELL = 52
PAD = 14
STRIP_H = 14     # the thin hover zone shown while hidden
FULL_H = 78
M = 8


class Dock(DesktopLayerWindow):
    def __init__(self, controller):
        super().__init__()
        self.c = controller
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.reveal = 0.0
        self.pinned = False   # stays open (showcase screenshots / while a menu is open)
        self._hover = None
        self._press = None
        self.anim = QVariantAnimation(self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._on_anim)
        self.anim.finished.connect(self._on_anim_done)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._maybe_hide)
        self.top_y = 0
        self.center_x = 0

    def favorites(self):
        return self.c.layout.favorites

    def panel_w(self):
        n = len(self.favorites())
        return max(220, n * CELL + 2 * PAD)

    def place(self, center_x, top_y):
        self.center_x, self.top_y = center_x, top_y
        self._apply_geometry()

    def _apply_geometry(self):
        w = self.panel_w() + 2 * M
        h = FULL_H + 2 * M if (self.reveal > 0 or self.anim.state() == QVariantAnimation.Running) else STRIP_H
        self.setGeometry(int(self.center_x - w / 2), int(self.top_y), int(w), int(h))
        self.update()

    def refresh(self):
        self._apply_geometry()

    # ------------------------------------------------------------ show / hide
    def show_dock(self):
        self.hide_timer.stop()
        if self.reveal >= 1 and self.anim.state() != QVariantAnimation.Running:
            return
        self.anim.stop()
        self.anim.setStartValue(self.reveal)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(180)
        self.anim.start()
        self._apply_geometry()

    def hide_dock(self):
        if self.pinned:
            return
        self.anim.stop()
        self.anim.setStartValue(self.reveal)
        self.anim.setEndValue(0.0)
        self.anim.setDuration(200)
        self.anim.start()

    def _on_anim(self, v):
        self.reveal = float(v)
        self.update()

    def _on_anim_done(self):
        self._apply_geometry()

    def _maybe_hide(self):
        if not self.geometry().contains(QCursor.pos()):
            self.hide_dock()

    # ------------------------------------------------------------ painting
    def panel_rect(self):
        w = self.panel_w()
        y_off = -(1 - self.reveal) * 24
        return QRectF(M, M + y_off, w, FULL_H - 10)

    def item_rects(self):
        pr = self.panel_rect()
        favs = self.favorites()
        x0 = pr.center().x() - len(favs) * CELL / 2
        return [(i, QRectF(x0 + i * CELL, pr.top() + (pr.height() - CELL) / 2, CELL, CELL))
                for i in range(len(favs))]

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255, 1))
        if self.reveal <= 0.01:
            # tiny handle so you know where the dock lives
            hw = 54
            p.setPen(Qt.NoPen)
            p.setBrush(qcolor("dock_handle"))
            p.drawRoundedRect(QRectF(self.width() / 2 - hw / 2, 3, hw, 5), 2.5, 2.5)
            p.end()
            return
        p.setOpacity(self.reveal)
        pr = self.panel_rect()
        draw_shadow(p, pr, rad(16), 0.9)
        draw_glass(p, pr, rad(16), fill_key="glass_fill_hover", strip=False)
        draw_neon(p, pr, rad(16))
        favs = self.favorites()
        if not favs:
            f = QFont(self.font())
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.setPen(qcolor("hint_text"))
            p.drawText(pr, Qt.AlignCenter, "Drag favorites here")
        for i, r in self.item_rects():
            if i == self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(qcolor("item_hover"))
                p.drawRoundedRect(r.adjusted(3, 3, -3, -3), 12, 12)
            ir = QRectF(r.center().x() - ICON / 2, r.center().y() - ICON / 2, ICON, ICON)
            icons.icon_for(favs[i]).paint(p, ir.toRect())
        if self.c.edit_mode:
            p.setOpacity(1.0)
            draw_edit_outline(p, pr, rad(16), handles=False)
        p.end()

    def _item_at(self, pos):
        for i, r in self.item_rects():
            if r.contains(QPointF(pos)):
                return i
        return None

    # ------------------------------------------------------------ mouse
    def enterEvent(self, e):
        self.show_dock()

    def leaveEvent(self, e):
        self._hover = None
        self.hide_timer.start(700)

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
        self.unsetCursor()
        h = self._item_at(e.position())
        if h != self._hover:
            self._hover = h
            favs = self.favorites()
            if h is not None and h < len(favs):
                p = favs[h]
                self.setToolTip(self.c.favorite_name(p))
            else:
                self.setToolTip("Favorites - drag things here")
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.c.edit_mode:
            pt = self.edit_release()
            if pt is not None:
                self.c.bar_moved("dock_pos", self, pt)
            return
        if e.button() != Qt.LeftButton or self.reveal < 0.9:
            return
        i = self._item_at(e.position())
        favs = self.favorites()
        if i is not None and i < len(favs):
            self.c.launch(favs[i])

    def contextMenuEvent(self, e):
        i = self._item_at(QPointF(e.pos()))
        favs = self.favorites()
        if i is None or i >= len(favs):
            return
        from PySide6.QtWidgets import QMenu
        path = favs[i]
        was = self.pinned
        self.pinned = True
        m = QMenu()
        m.addAction("Open", lambda: self.c.launch(path))
        m.addAction("Remove from favorites", lambda: self.c.remove_favorite(path))
        m.exec(e.globalPos())
        self.pinned = was
        self.hide_timer.start(700)

    # ------------------------------------------------------------ drops
    def dragEnterEvent(self, e):
        if accept_drag(e):
            self.show_dock()

    def dragMoveEvent(self, e):
        accept_drag(e)

    def dragLeaveEvent(self, e):
        self.hide_timer.start(700)

    def dropEvent(self, e):
        if not accept_drag(e):
            return
        item = read_item(e.mimeData())
        dropped = parse_drop(e.mimeData()) if item is None else None
        QTimer.singleShot(0, lambda: self.c.handle_favorite_drop(item, dropped))
        self.hide_timer.start(1500)
