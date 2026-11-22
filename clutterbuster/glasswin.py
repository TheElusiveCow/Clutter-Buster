"""Glass dialog windows (Settings, theme maker, the Edit layout toolbar).

Frameless, see-through, painted in the current theme, draggable by any empty spot,
and kept on top while they are open (they're the only things besides the popup and
the quick search that sit above other windows)."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from .glass import bring_to_top, draw_glass, draw_neon, draw_shadow
from .theme import THEME, is_dark, rad

M = 18   # room for the soft shadow


_check_png = {}


def check_image(color="#FFFFFF"):
    """A crisp check mark picture for checked boxes (made once, at 4x so it's sharp at any scaling)."""
    if color in _check_png:
        return _check_png[color]
    import os
    import tempfile
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainterPath, QPen
    img = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath(QPointF(15, 33))
    path.lineTo(27, 45)
    path.lineTo(49, 19)
    p.drawPath(path)
    p.end()
    try:
        from . import paths
        d = paths.app_dir()
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = tempfile.gettempdir()
    fn = os.path.join(d, f"check-{color.strip('#')}.png")
    img.save(fn)
    _check_png[color] = fn.replace("\\", "/")
    return _check_png[color]


def checkbox_qss():
    """Easy-to-see checkboxes in every theme: a bordered box, filled with the accent when ticked,
    with a white check mark."""
    acc = THEME["default_accent"]
    if is_dark():
        box, line, hov = "rgba(255,255,255,26)", "rgba(255,255,255,170)", "rgba(255,255,255,235)"
    else:
        box, line, hov = "#FFFFFF", "rgba(0,0,0,120)", "rgba(0,0,0,200)"
    img = check_image()
    return f"""
    QCheckBox {{ spacing:9px; }}
    QCheckBox::indicator {{ width:18px; height:18px; border-radius:5px; border:2px solid {line};
                            background:{box}; }}
    QCheckBox::indicator:hover {{ border-color:{hov}; }}
    QCheckBox::indicator:checked {{ background:{acc}; border:2px solid {acc}; image:url({img}); }}
    QCheckBox::indicator:checked:hover {{ border-color:{hov}; }}
    QCheckBox::indicator:disabled {{ border-color:gray; background:transparent; }}
    QCheckBox::indicator:checked:disabled {{ background:gray; border-color:gray; }}
    """


def qss():
    """Qt style sheet for buttons, sliders, lists... matching the current theme."""
    acc = THEME["default_accent"]
    if is_dark():
        text, hint, btn, btnh, border, groove, sel, field = (
            "#E8ECFF", "#9AA0BE", "rgba(255,255,255,20)", "rgba(255,255,255,36)", "rgba(255,255,255,44)",
            "rgba(255,255,255,40)", "rgba(255,255,255,24)", "rgba(0,0,0,70)")
    else:
        text, hint, btn, btnh, border, groove, sel, field = (
            "#1C1C22", "#6B6E7A", "rgba(255,255,255,210)", "rgba(255,255,255,255)", "rgba(0,0,0,32)",
            "rgba(0,0,0,28)", "rgba(10,132,255,34)", "rgba(255,255,255,235)")
    return f"""
    QWidget {{ color:{text}; background:transparent; font-size:10pt; }}
    QLabel#h1 {{ font-size:15pt; font-weight:600; }}
    QLabel#h2 {{ font-size:11.5pt; font-weight:600; }}
    QLabel#hint {{ color:{hint}; }}
    QLabel#tag {{ color:{acc}; font-weight:700; letter-spacing:1px; font-size:9pt; }}
    QPushButton {{ background:{btn}; border:1px solid {border}; border-radius:9px; padding:6px 14px; }}
    QPushButton:hover {{ background:{btnh}; }}
    QPushButton:disabled {{ color:{hint}; }}
    QPushButton#primary {{ background:{acc}; color:white; border:none; font-weight:600; padding:7px 18px; }}
    QPushButton#danger {{ background:#E5293B; color:white; border:none; font-weight:bold; padding:8px 16px; }}
    QPushButton#danger:hover {{ background:#C81E2F; }}
    QPushButton#close {{ background:transparent; border:none; font-size:13pt; padding:2px 8px; color:{hint}; }}
    QPushButton#close:hover {{ color:#E5293B; }}
    QPushButton#swatch {{ border:2px solid {border}; border-radius:14px; min-width:28px; max-width:28px;
                          min-height:28px; max-height:28px; padding:0; }}
    QSlider::groove:horizontal {{ height:4px; background:{groove}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{acc}; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:white; border:2px solid {acc}; width:16px; height:16px;
                                  margin:-7px 0; border-radius:8px; }}
    QListWidget {{ background:transparent; border:none; outline:0; }}
    QListWidget::item {{ padding:8px 10px; border-radius:8px; }}
    QListWidget::item:selected {{ background:{sel}; color:{text}; }}
    QListWidget::item:hover {{ background:{sel}; }}
    QLineEdit {{ background:{field}; border:1px solid {border}; border-radius:7px; padding:5px 8px; }}
    QScrollArea#page {{ background:transparent; border:none; }}
    QScrollArea#page > QWidget > QWidget {{ background:transparent; }}
    QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
    QScrollBar::handle:vertical {{ background:{border}; border-radius:4px; min-height:30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    QFrame#card {{ background:{sel}; border-radius:12px; }}
    QToolTip {{ color:black; background:white; }}
    """ + checkbox_qss()


class GlassPanel(QWidget):
    """A frameless glass window. Put content in self.body (a QWidget)."""

    def __init__(self, title="", closable=True, parent=None):
        # parent = an owner window: an owned window always stays above its owner
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(title or "Clutter Buster")
        self._drag = None
        self.body = QWidget(self)
        self.close_btn = None
        if closable:
            self.close_btn = QPushButton("\u2715", self)
            self.close_btn.setObjectName("close")
            self.close_btn.setCursor(Qt.PointingHandCursor)
            self.close_btn.setToolTip("Close")
            self.close_btn.clicked.connect(self.close)
        self.restyle()

    def restyle(self):
        self.setStyleSheet(qss())
        self.update()

    def resizeEvent(self, e):
        self.body.setGeometry(M + 6, M + 6, self.width() - 2 * M - 12, self.height() - 2 * M - 12)
        if self.close_btn:
            self.close_btn.setGeometry(self.width() - M - 44, M + 8, 36, 30)
            self.close_btn.raise_()
        super().resizeEvent(e)

    def glass_rect(self):
        return QRectF(M, M, self.width() - 2 * M, self.height() - 2 * M)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.glass_rect()
        draw_shadow(p, r, rad(22), 1.5, layers=10)
        # dialogs are for reading: nearly solid glass, whatever the transparency slider says
        r_, g_, b_, a_ = THEME["popup_fill"]
        saved = THEME["popup_fill"]
        THEME["popup_fill"] = (r_, g_, b_, max(a_, 250))
        try:
            draw_glass(p, r, rad(22), fill_key="popup_fill")
        finally:
            THEME["popup_fill"] = saved
        draw_neon(p, r, rad(22), strength=THEME.get("glow_strength", 0.6) * 0.7)
        p.end()

    def glow_update(self):
        self.update()

    def show_on_top(self):
        self.show()
        self.raise_()
        self.activateWindow()
        bring_to_top(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = (e.globalPosition().toPoint(), self.pos())

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() & Qt.LeftButton:
            self.move(self._drag[1] + e.globalPosition().toPoint() - self._drag[0])

    def mouseReleaseEvent(self, e):
        self._drag = None


class SliderRow(QWidget):
    """  Label ............................ 64 px
         [==========o-----------------------]      """
    changed = Signal(str, int)

    def __init__(self, key, label, lo, hi, unit, value, parent=None):
        super().__init__(parent)
        self.key, self.unit = key, unit
        from PySide6.QtWidgets import QVBoxLayout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(3)
        top = QHBoxLayout()
        self.name = QLabel(label)
        self.val = QLabel()
        self.val.setObjectName("hint")
        top.addWidget(self.name)
        top.addStretch(1)
        top.addWidget(self.val)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(int(value))
        self.slider.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.slider)
        self._show(int(value))
        self.slider.valueChanged.connect(self._on)

    def _show(self, v):
        self.val.setText(f"{v}{self.unit}")

    def _on(self, v):
        self._show(v)
        self.changed.emit(self.key, v)

    def set_value(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(v))
        self.slider.blockSignals(False)
        self._show(int(v))


def color_button(hex_color):
    b = QPushButton()
    b.setObjectName("swatch")
    b.setCursor(Qt.PointingHandCursor)
    set_button_color(b, hex_color)
    return b


def set_button_color(b, hex_color):
    b.setProperty("hex", QColor(hex_color).name())
    b.setStyleSheet(f"QPushButton#swatch{{background:{QColor(hex_color).name()};}}")
