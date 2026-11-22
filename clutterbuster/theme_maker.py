"""Custom theme maker (Settings > Appearance > Make a custom theme).

Pick an accent, a glass tint and a text color, set frost (blur), glow and corner
roundness, watch the live preview (a mini tile, popup and search bar), then save it
with a name. Saved themes show up in the theme list.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from . import theme
from .colorpick import InlineColorPicker
from .glass import draw_glass, draw_neon, draw_shadow, info
from .glasswin import GlassPanel, SliderRow, color_button, set_button_color
from .theme import THEME, qcolor, rad

DEFAULT_CUSTOM = {"name": "", "accent": "#00D2FF", "tint": "#1A1240", "text": "#F2F0FF",
                  "blur": 55, "glow": 70, "roundness": 55}
ICON_COLORS = ["#FF3B7F", "#0A84FF", "#30D158", "#FF9F0A", "#9B5CFF", "#40C8E0", "#FFD60A", "#FF453A", "#8E8E93"]


class ThemePreview(QWidget):
    """Paints a mini desktop with the theme being made - without changing the real one."""

    def __init__(self, get_theme, parent=None):
        super().__init__(parent)
        self.get_theme = get_theme
        self.setMinimumSize(400, 300)
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)   # 25 fps while the theme maker is open

    def _tick(self):
        self.phase = (self.phase + 0.04 / 6) % 1.0
        if self.isVisible():
            self.update()

    def paintEvent(self, _e):
        saved, saved_phase = dict(THEME), theme.PHASE[0]
        THEME.clear()
        THEME.update(self.get_theme())
        theme.PHASE[0] = self.phase
        try:
            self._paint()
        finally:
            THEME.clear()
            THEME.update(saved)
            theme.PHASE[0] = saved_phase

    def _paint(self):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        bg = QRectF(0, 0, W, H)
        # a pretend wallpaper so the glass has something to show through
        g = QLinearGradient(0, 0, 0, H)
        if THEME.get("dark"):
            g.setColorAt(0, QColor(18, 14, 48))
            g.setColorAt(0.6, QColor(40, 22, 80))
            g.setColorAt(1, QColor(10, 30, 50))
        else:
            g.setColorAt(0, QColor(150, 196, 232))
            g.setColorAt(0.6, QColor(196, 222, 240))
            g.setColorAt(1, QColor(120, 160, 150))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(bg, 14, 14)
        aur = QRadialGradient(QPointF(W * 0.75, H * 0.25), W * 0.45)
        aur.setColorAt(0, QColor(0, 255, 170, 70 if THEME.get("dark") else 40))
        aur.setColorAt(1, QColor(0, 255, 170, 0))
        p.setBrush(aur)
        p.drawRoundedRect(bg, 14, 14)
        acc = QColor(THEME["default_accent"])
        # search bar
        sb = QRectF(W * 0.18, 14, W * 0.64, 30)
        draw_shadow(p, sb, rad(10), 0.8)
        draw_glass(p, sb, rad(10), fill_key="glass_fill_hover", strip=True)
        draw_neon(p, sb, rad(10))
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(qcolor("hint_text"))
        p.drawText(sb.adjusted(26, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, "Search shortcuts and files...")
        p.setPen(QPen(qcolor("icon_glyph"), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(sb.left() + 14, sb.center().y() - 1), 4.5, 4.5)
        # tile
        tr = QRectF(22, 78, 74, 74)
        trad = rad(18)
        draw_shadow(p, tr, trad, 0.9)
        draw_glass(p, tr, trad, strip=False)
        draw_neon(p, tr, trad, accent=acc)
        if not THEME.get("glow"):
            p.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), 120), 1.5))
            p.drawRoundedRect(tr.adjusted(1, 1, -1, -1), trad - 1, trad - 1)
        for i in range(9):
            r_, c_ = divmod(i, 3)
            ir = QRectF(tr.left() + 11 + c_ * 18, tr.top() + 11 + r_ * 18, 14, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ICON_COLORS[i]))
            p.drawRoundedRect(ir, 4, 4)
        p.setPen(qcolor("label_shadow"))
        p.drawText(QRectF(tr.left() - 10, tr.bottom() + 5, tr.width() + 20, 18).translated(1, 1), Qt.AlignHCenter, "Games")
        p.setPen(qcolor("label_text"))
        p.drawText(QRectF(tr.left() - 10, tr.bottom() + 5, tr.width() + 20, 18), Qt.AlignHCenter, "Games")
        # popup
        pr = QRectF(W * 0.36, 70, W * 0.58, H - 86)
        prad = rad(22)
        draw_shadow(p, pr, prad, 1.2)
        draw_glass(p, pr, prad, fill_key="popup_fill")
        draw_neon(p, pr, prad, accent=acc)
        tf = QFont(self.font())
        tf.setPointSizeF(12)
        tf.setBold(True)
        p.setFont(tf)
        p.setPen(Qt.NoPen)
        p.setBrush(acc)
        p.drawEllipse(QPointF(pr.left() + 18, pr.top() + 22), 4.5, 4.5)
        p.setPen(qcolor("title_text"))
        p.drawText(QRectF(pr.left() + 30, pr.top() + 8, pr.width(), 28), Qt.AlignVCenter | Qt.AlignLeft, "Games")
        nf = QFont(self.font())
        nf.setPointSizeF(7.5)
        p.setFont(nf)
        cw = (pr.width() - 24) / 3
        ch = min(64.0, (pr.height() - 50) / 2)
        names = ["Steam", "Discord", "Xbox", "Epic", "Battle", "GOG"]
        for k in range(6):
            r_, c_ = divmod(k, 3)
            card = QRectF(pr.left() + 12 + c_ * cw + 3, pr.top() + 42 + r_ * ch + 3, cw - 6, ch - 6)
            p.setPen(QPen(qcolor("card_border"), 1))
            p.setBrush(qcolor("card_fill"))
            p.drawRoundedRect(card, rad(10), rad(10))
            isz = min(30.0, card.height() - 22)
            ir = QRectF(card.center().x() - isz / 2, card.top() + 6, isz, isz)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ICON_COLORS[k]))
            p.drawRoundedRect(ir, rad(7), rad(7))
            p.setPen(qcolor("panel_text"))
            p.drawText(QRectF(card.left(), ir.bottom() + 2, card.width(), 14), Qt.AlignHCenter, names[k])
        p.end()


class ThemeMaker(GlassPanel):
    def __init__(self, controller, start=None, parent=None):
        super().__init__("Clutter Buster - Make a theme", parent=parent)
        self.c = controller
        self.original = dict(start) if start else None
        self.data = dict(DEFAULT_CUSTOM)
        if start:
            self.data.update(start)
        self.setFixedSize(880, 640)
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(18, 10, 18, 14)
        outer.setSpacing(10)
        h1 = QLabel(("Edit theme: " + start.get("name", "")) if start else "Make a custom theme")
        h1.setObjectName("h1")
        outer.addWidget(h1)
        row = QHBoxLayout()
        row.setSpacing(18)
        outer.addLayout(row, 1)
        left = QVBoxLayout()
        left.setSpacing(8)
        row.addLayout(left, 0)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.colors = {}
        self.color_key = "accent"
        for i, (key, label) in enumerate((("accent", "Accent"), ("tint", "Glass tint"), ("text", "Text"))):
            grid.addWidget(QLabel(label), 0, 2 * i)
            b = color_button(self.data[key])
            b.setToolTip(f"Change the {label.lower()} colour below")
            b.clicked.connect(lambda _=False, k=key: self.pick(k))
            grid.addWidget(b, 0, 2 * i + 1)
            self.colors[key] = b
        left.addLayout(grid)
        # the colour picker is part of this window (a separate dialog could hide behind it)
        self.picker_label = QLabel()
        self.picker_label.setObjectName("hint")
        left.addWidget(self.picker_label)
        self.picker = InlineColorPicker(self.data["accent"])
        self.picker.changed.connect(self.on_color)
        left.addWidget(self.picker)
        left.addSpacing(4)
        self.sliders = {}
        for key, label in (("blur", "Frost (blur)"), ("glow", "Glow"), ("roundness", "Corner roundness")):
            s = SliderRow(key, label, 0, 100, " %", self.data[key])
            s.setMinimumWidth(260)
            s.changed.connect(self.on_slider)
            self.sliders[key] = s
            left.addWidget(s)
        left.addStretch(1)
        nl = QLabel("Name")
        left.addWidget(nl)
        self.name = QLineEdit(self.data.get("name") or "")
        self.name.setPlaceholderText("e.g. Purple Night")
        self.name.setMaxLength(40)
        left.addWidget(self.name)
        self._preview_cache = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self.changed)
        self.preview = ThemePreview(self.preview_theme)
        row.addWidget(self.preview, 1)
        bottom = QHBoxLayout()
        hint = QLabel("Saved themes appear in Settings > Appearance.")
        hint.setObjectName("hint")
        bottom.addWidget(hint)
        bottom.addStretch(1)
        self.delete_btn = None
        if start and any(t.get("name") == start.get("name") for t in self.c.layout.custom_themes):
            self.delete_btn = QPushButton("Delete theme")
            self.delete_btn.setObjectName("danger")
            self.delete_btn.setCursor(Qt.PointingHandCursor)
            self.delete_btn.clicked.connect(self.delete_theme)
            bottom.addWidget(self.delete_btn)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        bottom.addWidget(cancel)
        save = QPushButton("Save theme")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self.save)
        bottom.addWidget(save)
        outer.addLayout(bottom)
        self.pick("accent")

    def preview_theme(self):
        if getattr(self, "_preview_cache", None) is None:      # built once per change, not per frame
            d = dict(self.data)
            self._preview_cache = theme.build("__preview__", self.c.ui, [dict(d, name="__preview__")])
        return self._preview_cache

    def pick(self, key):
        """Choose which colour the picker below changes."""
        self.color_key = key
        names = {"accent": "Accent", "tint": "Glass tint", "text": "Text"}
        self.picker_label.setText(f"Changing: {names[key]}")
        for k, b in self.colors.items():
            ring = ("3px solid " + THEME["default_accent"]) if k == key else "1px solid rgba(0,0,0,60)"
            b.setStyleSheet(f"QPushButton#swatch{{background:{self.data[k]};border:{ring};}}")
        self.picker.set_color(self.data[key])

    def on_color(self, hx):
        self.data[self.color_key] = hx
        set_button_color(self.colors[self.color_key], hx)
        self.pick(self.color_key)
        self._debounce.start(100)

    def on_slider(self, key, v):
        self.data[key] = int(v)
        self._debounce.start(100)                     # redraw once the slider settles a little

    def changed(self):
        self._preview_cache = None
        self.preview.update()

    def save(self):
        name = self.name.text().strip()
        if not name:
            info(self, "Theme name", "Give your theme a name first.")
            self.name.setFocus()
            return
        if name in theme.BUILT_IN or name.lower() == "auto":
            info(self, "Theme name", f"\"{name}\" is a built-in name - pick another one.")
            return
        self.data["name"] = name
        self.c.save_custom_theme(dict(self.data))
        self.close()

    def delete_theme(self):
        name = (self.original or {}).get("name")
        if name and self.c.delete_custom_theme(name):
            self.close()

    def closeEvent(self, e):
        self.preview.timer.stop()
        super().closeEvent(e)
