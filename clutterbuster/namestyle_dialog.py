"""Right-click a group > Name style...  (or Settings > Appearance > Group names... for all groups)

Font (any font on your PC), size, bold/italic, color and a shadow or outline, with a live
preview. Empty choices follow the theme. Apply = one Undo step."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from . import namestyle
from .glass import draw_glass
from .glasswin import GlassPanel, set_button_color
from .theme import THEME, rad

TILE_PT, PANEL_PT = 11.0, 12.5


class Preview(QWidget):
    def __init__(self, get_style, name, parent=None):
        super().__init__(parent)
        self.get_style, self.name = get_style, name
        self.setMinimumHeight(120)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        st = self.get_style()
        # a small tile with its name under it ...
        t = QRectF(18, 10, 70, 70)
        draw_glass(p, t, rad(16))
        namestyle.draw(p, QRectF(0, t.bottom() + 4, 106, 40), self.name, Qt.AlignHCenter | Qt.AlignTop, st,
                       self.font(), TILE_PT, False, "label_text", default_effect="shadow", elide_w=104)
        # ... and a big panel title bar
        pr = QRectF(124, 10, self.width() - 134, self.height() - 20)
        draw_glass(p, pr, rad(14), fill_key="panel_fill")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(THEME["default_accent"]))
        p.drawEllipse(pr.left() + 12, pr.top() + 13, 10, 10)
        namestyle.draw(p, QRectF(pr.left() + 30, pr.top(), pr.width() - 40, 36), self.name,
                       Qt.AlignLeft | Qt.AlignVCenter, st, self.font(), PANEL_PT, True, "panel_title_text",
                       elide_w=pr.width() - 44)
        p.end()


class NameStyleDialog(GlassPanel):
    def __init__(self, controller, gid=None):
        super().__init__("Clutter Buster - Name style")
        self.c, self.gid = controller, gid
        self.setAttribute(Qt.WA_DeleteOnClose, True)    # frees the font list when closed
        g = controller.layout.group(gid) if gid else None
        self.own = dict((g.get("name_style") if g else controller.ui.get("name_style")) or {})
        base = namestyle.resolve(controller.layout) if g else dict(namestyle.DEFAULT)
        self.setFixedSize(560, 520)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(14, 8, 14, 12)
        lay.setSpacing(10)
        h = QLabel(f"Name style: {g['name']}" if g else "Group names (all groups)")
        h.setObjectName("h1")
        lay.addWidget(h)
        hint = QLabel("Anything left on \"Default\" follows " + ("your default (Settings > Appearance) and the theme."
                                                              if g else "the theme."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        cur = dict(base)
        cur.update(self.own)

        self.use_font = QCheckBox("Font")
        self.family = QComboBox()        # every font installed on this PC, each shown in its own look
        self.family.setMaxVisibleItems(16)
        for fam in QFontDatabase.families():
            if QFontDatabase.isPrivateFamily(fam):
                continue
            self.family.addItem(fam)
            self.family.setItemData(self.family.count() - 1, QFont(fam, 10), Qt.FontRole)
        want = cur.get("family") or QFont().family()
        i = self.family.findText(want)
        if i >= 0:
            self.family.setCurrentIndex(i)
        self.use_font.setChecked(bool(self.own.get("family")))
        self.family.setEnabled(self.use_font.isChecked())
        self.use_font.toggled.connect(lambda v: (self.family.setEnabled(v), self.changed()))
        self.family.currentIndexChanged.connect(lambda _i: self.changed())
        grid.addWidget(self.use_font, 0, 0)
        grid.addWidget(self.family, 0, 1, 1, 2)

        grid.addWidget(QLabel("Size"), 1, 0)
        self.size = QSpinBox()
        self.size.setRange(0, 40)
        self.size.setSpecialValueText("Default")
        self.size.setSuffix(" pt")
        self.size.setValue(int(self.own.get("size") or 0))
        self.size.valueChanged.connect(lambda _v: self.changed())
        grid.addWidget(self.size, 1, 1)

        grid.addWidget(QLabel("Weight"), 2, 0)
        self.bold = QComboBox()
        self.bold.addItems(["Default", "Bold", "Regular"])
        b = self.own.get("bold")
        self.bold.setCurrentIndex(0 if b is None else (1 if b else 2))
        self.bold.currentIndexChanged.connect(lambda _i: self.changed())
        grid.addWidget(self.bold, 2, 1)
        self.italic = QCheckBox("Italic")
        self.italic.setChecked(bool(self.own.get("italic")))
        self.italic.toggled.connect(lambda _v: self.changed())
        grid.addWidget(self.italic, 2, 2)

        grid.addWidget(QLabel("Color"), 3, 0)
        crow = QHBoxLayout()
        self.color_hex = self.own.get("color") or ""
        self.color_btn = QPushButton()
        self.color_btn.setObjectName("swatch")
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self.color_btn.clicked.connect(self.pick_color)
        crow.addWidget(self.color_btn)
        theme_c = QPushButton("Theme color")
        theme_c.setCursor(Qt.PointingHandCursor)
        theme_c.clicked.connect(lambda: self.set_color(""))
        crow.addWidget(theme_c)
        crow.addStretch(1)
        grid.addLayout(crow, 3, 1, 1, 2)
        self.set_color(self.color_hex, notify=False)

        grid.addWidget(QLabel("Readability"), 4, 0)
        self.effect = QComboBox()
        for _k, label in namestyle.EFFECTS:
            self.effect.addItem(label)
        keys = [k for k, _l in namestyle.EFFECTS]
        self.effect.setCurrentIndex(keys.index(self.own.get("effect", "auto")) if self.own.get("effect", "auto") in keys else 0)
        self.effect.currentIndexChanged.connect(lambda _i: self.changed())
        grid.addWidget(self.effect, 4, 1)
        lay.addLayout(grid)

        self.preview = Preview(self.style_now, g["name"] if g else "Computer Software")
        lay.addWidget(self.preview, 1)

        bottom = QHBoxLayout()
        reset = QPushButton("Use default" if g else "Reset to theme")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self.reset)
        bottom.addWidget(reset)
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        bottom.addWidget(cancel)
        ok = QPushButton("Apply")
        ok.setObjectName("primary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.apply)
        bottom.addWidget(ok)
        lay.addLayout(bottom)
        av = controller.avail()
        self.move(av.center().x() - self.width() // 2, av.center().y() - self.height() // 2)

    def overrides(self):
        o = {}
        if self.use_font.isChecked():
            o["family"] = self.family.currentText()
        if self.size.value():
            o["size"] = int(self.size.value())
        if self.bold.currentIndex():
            o["bold"] = self.bold.currentIndex() == 1
        if self.italic.isChecked():
            o["italic"] = True
        if self.color_hex:
            o["color"] = self.color_hex
        k = namestyle.EFFECTS[self.effect.currentIndex()][0]
        if k != "auto":
            o["effect"] = k
        return o

    def style_now(self):
        st = namestyle.resolve(self.c.layout) if self.gid else dict(namestyle.DEFAULT)
        st.update(self.overrides())
        return st

    def changed(self):
        self.preview.update()

    def set_color(self, hexc, notify=True):
        self.color_hex = hexc
        set_button_color(self.color_btn, hexc or namestyle.color({}, "panel_title_text").name())
        self.color_btn.setToolTip(hexc or "Theme color")
        if notify:
            self.changed()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.color_hex or "#FFFFFF"), self, "Name color")
        if c.isValid():
            self.set_color(c.name())

    def reset(self):
        self.use_font.setChecked(False)
        self.size.setValue(0)
        self.bold.setCurrentIndex(0)
        self.italic.setChecked(False)
        self.effect.setCurrentIndex(0)
        self.set_color("")

    def apply(self):
        self.c.set_name_style(self.gid, self.overrides())
        self.close()
