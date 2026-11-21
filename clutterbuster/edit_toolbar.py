"""The floating glass toolbar shown while Edit layout is on.

  EDIT LAYOUT                                   [ Done ]
  Drag things to move them, pull corners to resize
  Icon size          ===========o------   64 px
  Icons per row      ======o-----------   3
  Glass transparency ========o---------   35 %
  Glow strength      ===========o------   60 %
  [ Reset look ]

Every slider applies live. Done (or Esc) locks everything and saves.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .glasswin import GlassPanel, SliderRow
from .theme import DEFAULT_UI, SLIDERS

W, H = 380, 470


class EditToolbar(GlassPanel):
    def __init__(self, controller):
        super().__init__("Clutter Buster - Edit layout", closable=False)
        self.c = controller
        self.setFixedSize(W, H)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        tag = QLabel("\u270E  EDIT LAYOUT")
        tag.setObjectName("tag")
        top.addWidget(tag)
        top.addStretch(1)
        self.done = QPushButton("\u2713  Done")
        self.done.setObjectName("primary")
        self.done.setCursor(Qt.PointingHandCursor)
        self.done.setToolTip("Lock everything and save (Esc)")
        self.done.clicked.connect(self.c.exit_edit_mode)
        top.addWidget(self.done)
        lay.addLayout(top)
        hint = QLabel("Drag groups, the search bar, the dock and the New Group button to move them. "
                      "Pull corners and edges to resize groups and the popup.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addSpacing(4)
        self.rows = {}
        for key, label, lo, hi, unit in SLIDERS:
            row = SliderRow(key, label, lo, hi, unit, self.c.ui.get(key, DEFAULT_UI[key]))
            row.changed.connect(self.c.set_ui)
            self.rows[key] = row
            lay.addWidget(row)
        lay.addStretch(1)
        bottom = QHBoxLayout()
        reset = QPushButton("Reset look")
        reset.setToolTip("Sliders back to normal and the popup back to its normal size")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self.c.reset_look)
        bottom.addWidget(reset)
        bottom.addStretch(1)
        esc = QLabel("Esc = Done")
        esc.setObjectName("hint")
        bottom.addWidget(esc)
        lay.addLayout(bottom)

    def refresh_from_ui(self):
        for key, row in self.rows.items():
            row.set_value(self.c.ui.get(key, DEFAULT_UI[key]))

    def place(self, avail):
        self.move(avail.right() - W - 16, avail.top() + 92)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            self.c.exit_edit_mode()
        else:
            super().keyPressEvent(e)
