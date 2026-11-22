"""The little gear by a group's name: this group's own settings in a compact glass panel,
anchored to the group. Changes show live; each is one Undo step (slider drags merge into one).
Closes when you click anywhere else."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from . import theme
from .glasswin import GlassPanel, SliderRow

LABELS = [("Auto", "auto"), ("Always", "always"), ("Never", "never")]


class FenceSettings(GlassPanel):
    def __init__(self, controller, gid):
        super().__init__("Group settings", closable=True)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.c, self.gid = controller, gid
        g = self.group
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(8, 4, 8, 6)
        lay.setSpacing(8)
        self.title = QLabel(g["name"])
        self.title.setObjectName("h2")
        lay.addWidget(self.title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        row = 0
        # accent colour
        grid.addWidget(QLabel("Accent"), row, 0)
        sw = QHBoxLayout()
        sw.setSpacing(4)
        self.swatches = {}
        for name, col in theme.ACCENTS:
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(22, 22)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(name)
            b.clicked.connect(lambda _=False, c_=col: self.c.set_accent(self.gid, c_))
            self.swatches[col] = b
            sw.addWidget(b)
        more = QPushButton("\u2026")
        more.setFixedSize(26, 22)
        more.setToolTip("Any colour...")
        more.setCursor(Qt.PointingHandCursor)
        more.clicked.connect(self.toggle_picker)
        sw.addWidget(more)
        sw.addStretch(1)
        grid.addLayout(sw, row, 1)
        row += 1
        from .colorpick import InlineColorPicker
        self.picker = InlineColorPicker(g.get("accent") or theme.THEME.get("default_accent", "#0A84FF"))
        self.picker.changed.connect(
            lambda hx: self.c.set_group_prop(self.gid, "accent", hx, "accent color", burst=True))
        self.picker.hide()
        grid.addWidget(self.picker, row, 0, 1, 2)
        row += 1
        # theme override
        grid.addWidget(QLabel("Theme"), row, 0)
        self.theme = QComboBox()
        self.theme.addItem("Theme default", None)
        for n in list(theme.BUILT_IN) + [ct.get("name") for ct in self.c.layout.custom_themes if ct.get("name")]:
            self.theme.addItem(n, n)
        self.theme.currentIndexChanged.connect(
            lambda _i: self.c.set_group_prop(self.gid, "theme", self.theme.currentData(), "group theme"))
        grid.addWidget(self.theme, row, 1)
        row += 1
        self.corner_row = row       # the corner picture row is added by the themes module (if present)
        if hasattr(self.c, "corner_choices"):
            grid.addWidget(QLabel("Corner picture"), row, 0)
            self.corner = QComboBox()
            for text, val in self.c.corner_choices():
                self.corner.addItem(text, val)
            self.corner.activated.connect(self._corner)
            grid.addWidget(self.corner, row, 1)
            row += 1
        # name style
        grid.addWidget(QLabel("Name"), row, 0)
        nr = QHBoxLayout()
        for text, d in (("A\u2212", -1), ("A+", 1)):
            b = QPushButton(text)
            b.setFixedWidth(46)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, d_=d: (self.c.bump_name_size(self.gid, d_), self.refresh()))
            nr.addWidget(b)
        self.size_lbl = QLabel()
        self.size_lbl.setObjectName("hint")
        nr.addWidget(self.size_lbl)
        fb = QPushButton("Font && colour...")
        fb.setCursor(Qt.PointingHandCursor)
        fb.clicked.connect(lambda: (self.close(), self.c.name_style_dialog(self.gid)))
        nr.addWidget(fb)
        nr.addStretch(1)
        grid.addLayout(nr, row, 1)
        row += 1
        # small tile / big panel
        grid.addWidget(QLabel("Look"), row, 0)
        mr = QHBoxLayout()
        self.mode_btns = {}
        for text, m in (("Small tile", "tile"), ("Big panel", "panel")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, m_=m: self._mode(m_))
            self.mode_btns[m] = b
            mr.addWidget(b)
        mr.addStretch(1)
        grid.addLayout(mr, row, 1)
        row += 1
        # show names
        grid.addWidget(QLabel("Show names"), row, 0)
        self.labels = QComboBox()
        self.labels.addItem("Like Settings", None)
        for text, v in LABELS:
            self.labels.addItem(text, v)
        self.labels.currentIndexChanged.connect(
            lambda _i: self.c.set_group_prop(self.gid, "labels", self.labels.currentData(), "show names"))
        grid.addWidget(self.labels, row, 1)
        row += 1
        lay.addLayout(grid)
        # sliders
        self.per_row = SliderRow("per_row", "Icons per row (this group)", 2, 6, "",
                                 g.get("per_row") or theme.THEME.get("per_row", 3))
        self.per_row.changed.connect(lambda _k, v: self.c.set_group_prop(self.gid, "per_row", v, "icons per row",
                                                                          burst=True))
        lay.addWidget(self.per_row)
        tr = g.get("transparency")
        self.transp = SliderRow("transparency", "Transparency (this group)", 0, 100, " %",
                                tr if tr is not None else self.c.ui.get("transparency", 35))
        self.transp.changed.connect(lambda _k, v: self.c.set_group_prop(self.gid, "transparency", v,
                                                                         "group transparency", burst=True))
        lay.addWidget(self.transp)
        bottom = QHBoxLayout()
        reset = QPushButton("Use defaults")
        reset.setToolTip("Theme, icons per row, names and transparency follow the main settings again")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset)
        bottom.addWidget(reset)
        bottom.addStretch(1)
        dele = QPushButton("Delete group")
        dele.setObjectName("danger")
        dele.setCursor(Qt.PointingHandCursor)
        dele.clicked.connect(lambda: (self.close(), self.c.request_delete_group(self.gid)))
        bottom.addWidget(dele)
        lay.addLayout(bottom)
        self.refresh()
        self.fit()

    @property
    def group(self):
        return self.c.layout.group(self.gid)

    def refresh(self):
        g = self.group
        if g is None:
            return self.close()
        self.title.setText(g["name"])
        acc = (g.get("accent") or "").lower()
        for col, b in self.swatches.items():
            ring = "3px solid white" if col.lower() == acc else "1px solid rgba(0,0,0,60)"
            b.setStyleSheet(f"QPushButton#swatch{{background:{col};border:{ring};border-radius:11px;"
                            "min-width:22px;max-width:22px;min-height:22px;max-height:22px;padding:0;}")
        for w, key in ((self.theme, "theme"), (self.labels, "labels")):
            w.blockSignals(True)
            i = w.findData(g.get(key))
            w.setCurrentIndex(i if i >= 0 else 0)
            w.blockSignals(False)
        if hasattr(self, "corner"):
            self.corner.blockSignals(True)
            i = self.corner.findData(g.get("corner", "theme"))
            self.corner.setCurrentIndex(i if i >= 0 else 0)
            self.corner.blockSignals(False)
        for m, b in self.mode_btns.items():
            b.setChecked(g.get("mode", "tile") == m)
        w = self.c.widgets.get(self.gid)
        self.size_lbl.setText(f"{w.name_size()} pt" if w else "")
        self.per_row.set_value(g.get("per_row") or theme.THEME.get("per_row", 3))
        tr = g.get("transparency")
        self.transp.set_value(tr if tr is not None else self.c.ui.get("transparency", 35))

    def fit(self):
        from .glasswin import M
        self.body.layout().activate()
        self.resize(440, self.body.layout().sizeHint().height() + 2 * M + 16)

    def toggle_picker(self, show=None):
        g = self.group
        self.picker.set_color((g or {}).get("accent") or theme.THEME.get("default_accent", "#0A84FF"))
        self.picker.setVisible(not self.picker.isVisible() if show is None else show)
        self.fit()
        self.anchor()

    def _mode(self, m):
        self.c.set_mode(self.gid, m)
        self.refresh()
        self.anchor()

    def _corner(self, _i):
        val = self.corner.currentData()
        if val == "choose":
            self.close()
            self.c.choose_corner_picture(self.gid)
        else:
            self.c.set_group_prop(self.gid, "corner", None if val == "theme" else val, "corner picture")

    def _reset(self):
        self.c.reset_group_look(self.gid)
        self.refresh()

    def anchor(self):
        """Next to the group: to its right if there's room, else to its left; kept on screen."""
        w = self.c.widgets.get(self.gid)
        av = self.c.avail()
        if w is None:
            self.move(av.center() - QPoint(self.width() // 2, self.height() // 2))
            return
        gr = w.glass_rect_global()
        x = gr.right() - 10
        if x + self.width() > av.right():
            x = gr.left() - self.width() + 10
        y = min(max(av.top(), gr.top() - 18), av.bottom() - self.height())
        self.move(max(av.left(), x), y)
