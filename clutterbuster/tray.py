"""The broom icon by the clock and its menu. (The Settings window lives in settings.py.)"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QMenu, QPushButton, QSystemTrayIcon, QWidgetAction

from .theme import rgb_gradient

RED_CSS = ("QPushButton{background:#e5293b;color:white;font-weight:bold;border:none;"
           "border-radius:6px;padding:7px 14px;} QPushButton:hover{background:#c81e2f;}")


def broom_icon():
    """Draw a little broom: RGB handle + golden bristles."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(rgb_gradient(50, 4, 28, 38), 6, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(52, 5), QPointF(30, 36))
    p.setPen(QPen(QColor(120, 80, 20), 2))
    p.setBrush(QColor(240, 190, 60))
    bristles = QPolygonF([QPointF(24, 30), QPointF(38, 40), QPointF(28, 60), QPointF(4, 46)])
    p.drawPolygon(bristles)
    p.setPen(QPen(QColor(150, 100, 25), 1.5))
    for i in range(1, 5):
        t = i / 5
        a = QPointF(24 + 14 * t, 30 + 10 * t)
        b = QPointF(4 + 24 * t, 46 + 14 * t)
        p.drawLine(a, b)
    p.setPen(QPen(QColor(90, 60, 15), 3))
    p.drawLine(QPointF(23, 31), QPointF(38, 41))
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, controller):
        super().__init__(broom_icon())
        self.c = controller
        self.setToolTip("Clutter Buster")
        m = QMenu()
        m.addAction("Settings...", self.c.show_settings)
        m.addAction("Automatically do it...", self.c.auto_organize)
        m.addAction("Edit layout", self.c.edit_layout)
        self.undo_action = m.addAction("Undo", self.c.undo)
        self.hide_action = m.addAction("Hide all groups", self.c.toggle_groups_hidden)
        self.hide_action.setCheckable(True)
        self.lock_action = m.addAction("Lock layout", lambda: self.c.set_locked(not self.c.layout.prefs.get("locked")))
        self.lock_action.setCheckable(True)
        self.fix_action = m.addAction("\u26A0  Fix hiding permission...", lambda: self.c.fix_permissions())
        self.fix_action.setVisible(False)
        m.aboutToShow.connect(self.refresh_toggles)
        m.addSeparator()
        m.addAction("Quit (shows everything on the desktop again)", self.c.quit)
        m.addSeparator()
        btn = QPushButton("Remove Clutter Buster")
        btn.setStyleSheet(RED_CSS)
        wa = QWidgetAction(m)
        wa.setDefaultWidget(btn)
        btn.clicked.connect(lambda: (m.hide(), self.c.request_remove()))
        m.addAction(wa)
        self.menu = m
        self.setContextMenu(m)

    def update_undo(self, enabled, label):
        self.undo_action.setEnabled(enabled)
        self.undo_action.setText(f"Undo {label}" if enabled else "Undo")

    def refresh_toggles(self):
        prefs = self.c.layout.prefs
        self.hide_action.setChecked(bool(prefs.get("groups_hidden")))
        self.lock_action.setChecked(bool(prefs.get("locked")))
        try:
            n = len(self.c.permfix_candidates())
        except Exception:
            n = 0
        self.fix_action.setVisible(n > 0)
        self.fix_action.setText(f"\u26A0  Fix hiding permission... ({n})" if n else "Fix hiding permission...")
