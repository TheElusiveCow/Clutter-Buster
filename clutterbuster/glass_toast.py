"""A small glass message in the bottom-right corner with two buttons (e.g. OK / Not now)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .glasswin import GlassPanel, M


class GlassToast(GlassPanel):
    accepted = Signal()
    rejected = Signal()

    def __init__(self, title, detail="", ok_text="OK", cancel_text="Not now"):
        super().__init__("Clutter Buster", closable=False)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._done = False
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(10, 6, 10, 8)
        lay.setSpacing(8)
        t = QLabel("\U0001F6E1  " + title)
        t.setObjectName("h2")
        t.setWordWrap(True)
        lay.addWidget(t)
        if detail:
            d = QLabel(detail)
            d.setObjectName("hint")
            d.setWordWrap(True)
            lay.addWidget(d)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton(cancel_text)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(lambda: self._finish(False))
        row.addWidget(self.cancel_btn)
        self.ok_btn = QPushButton(ok_text)
        self.ok_btn.setObjectName("primary")
        self.ok_btn.setCursor(Qt.PointingHandCursor)
        self.ok_btn.clicked.connect(lambda: self._finish(True))
        row.addWidget(self.ok_btn)
        lay.addLayout(row)
        self.setFixedWidth(420)
        lay.activate()
        self.setFixedHeight(self.body.sizeHint().height() + 2 * M + 12)

    def _finish(self, ok):
        if self._done:
            return
        self._done = True
        self.close()
        (self.accepted if ok else self.rejected).emit()

    def show_corner(self, avail):
        self.move(avail.right() - self.width() - 8, avail.bottom() - self.height() - 8)
        self.show_on_top()
