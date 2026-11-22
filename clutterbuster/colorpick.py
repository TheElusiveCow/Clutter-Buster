"""An inline colour picker that lives INSIDE the window that needs it (no separate dialog that
could open hidden behind an always-on-top window and block every click).

  [swatch grid]
  Hue        [=====rainbow=====o====]
  Brightness [=========o============]
  [preview]  #RRGGBB
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget

SWATCHES = ["#0A84FF", "#9B5CFF", "#FF3B7F", "#FF453A", "#FF9F0A", "#FFD60A", "#30D158", "#40C8E0", "#8E8E93",
            "#FFFFFF", "#D9D9DE", "#1C1C22", "#000000", "#7A4A2A", "#2E5E3A", "#1E3A8A", "#F4A6C1", "#B8E1FF"]


class InlineColorPicker(QWidget):
    changed = Signal(str)          # "#rrggbb"

    def __init__(self, color="#0A84FF", parent=None):
        super().__init__(parent)
        self._c = QColor(color if QColor(color).isValid() else "#0A84FF")
        self._sat = max(self._c.hsvSaturation(), 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.swatches = []
        for i, hx in enumerate(SWATCHES):
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(hx)
            b.setStyleSheet(f"QPushButton{{background:{hx};border:1px solid rgba(0,0,0,70);border-radius:10px;"
                            "min-width:20px;max-width:20px;min-height:20px;max-height:20px;padding:0;}"
                            "QPushButton:hover{border:2px solid white;}")
            b.clicked.connect(lambda _=False, h=hx: self.set_color(h, emit=True))
            grid.addWidget(b, i // 9, i % 9)
            self.swatches.append(b)
        lay.addLayout(grid)
        self.hue = self._slider(0, 359, "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f00, stop:0.17 #ff0, "
                                        "stop:0.33 #0f0, stop:0.5 #0ff, stop:0.67 #00f, stop:0.83 #f0f, stop:1 #f00)")
        self.val = self._slider(0, 255, "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #000, stop:1 #fff)")
        for label, s in (("Hue", self.hue), ("Brightness", self.val)):
            r = QHBoxLayout()
            lb = QLabel(label)
            lb.setFixedWidth(70)
            r.addWidget(lb)
            r.addWidget(s, 1)
            lay.addLayout(r)
        bottom = QHBoxLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(46, 24)
        bottom.addWidget(self.preview)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setFixedWidth(90)
        self.hex.setValidator(QRegularExpressionValidator(QRegularExpression("#?[0-9A-Fa-f]{0,6}")))
        self.hex.editingFinished.connect(self._hex_done)
        self.hex.textEdited.connect(self._hex_typing)
        bottom.addWidget(self.hex)
        bottom.addStretch(1)
        lay.addLayout(bottom)
        self.hue.valueChanged.connect(self._sliders)
        self.val.valueChanged.connect(self._sliders)
        self._sync()

    def _slider(self, lo, hi, groove):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setCursor(Qt.PointingHandCursor)
        s.setStyleSheet(f"QSlider::groove:horizontal{{height:8px;border-radius:4px;background:{groove};}}"
                        "QSlider::handle:horizontal{background:white;border:2px solid #555;width:14px;height:14px;"
                        "margin:-5px 0;border-radius:8px;}")
        return s

    def color(self):
        return self._c.name()

    def set_color(self, hx, emit=False):
        c = QColor(hx)
        if not c.isValid():
            return
        self._c = c
        if c.hsvSaturation() > 0:
            self._sat = c.hsvSaturation()
        self._sync()
        if emit:
            self.changed.emit(self._c.name())

    def _sync(self):
        for s, v in ((self.hue, max(0, self._c.hsvHue())), (self.val, self._c.value())):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
        if not self.hex.hasFocus():
            self.hex.setText(self._c.name().upper())
        self.preview.setStyleSheet(f"background:{self._c.name()};border:1px solid rgba(0,0,0,80);border-radius:6px;")

    def _sliders(self, _v):
        sat = self._sat if self._c.hsvSaturation() > 0 or self.hue.value() else self._sat
        self._c = QColor.fromHsv(self.hue.value(), max(sat, 60) if self._c.hsvSaturation() <= 0 else sat,
                                 self.val.value())
        self._sync()
        self.changed.emit(self._c.name())

    def _hex_typing(self, t):
        t = t.strip()
        if not t.startswith("#"):
            t = "#" + t
        if len(t) == 7 and QColor(t).isValid():
            self.set_color(t, emit=True)

    def _hex_done(self):
        self._hex_typing(self.hex.text())
        self.hex.setText(self._c.name().upper())
