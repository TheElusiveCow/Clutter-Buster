"""The broom icon by the clock, its menu, and the Settings window (placeholder in stage 1)."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidgetAction)

from . import paths
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


class SettingsDialog(QDialog):
    def __init__(self, controller):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.c = controller
        self.setWindowTitle("Clutter Buster - Settings")
        self.setWindowIcon(broom_icon())
        lay = QVBoxLayout(self)
        title = QLabel("<h2>Clutter Buster</h2>")
        lay.addWidget(title)
        lay.addWidget(QLabel(
            "Stage 2.<br>"
            "Neon Gamer &amp; custom themes, Edit mode sliders and start-with-Windows arrive in stage 3.<br><br>"
            f"Your groups are saved in:<br><code>{paths.app_dir()}</code>"))
        row = QHBoxLayout()
        remove = QPushButton("Remove Clutter Buster")
        remove.setStyleSheet(RED_CSS)
        remove.clicked.connect(lambda: (self.close(), self.c.request_remove()))
        row.addWidget(remove)
        row.addStretch(1)
        ok = QPushButton("Close")
        ok.clicked.connect(self.close)
        row.addWidget(ok)
        lay.addLayout(row)


class Tray(QSystemTrayIcon):
    def __init__(self, controller):
        super().__init__(broom_icon())
        self.c = controller
        self.setToolTip("Clutter Buster")
        m = QMenu()
        m.addAction("Settings...", self.c.show_settings)
        m.addAction("Edit layout...", self.c.edit_layout)
        self.undo_action = m.addAction("Undo", self.c.undo)
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
