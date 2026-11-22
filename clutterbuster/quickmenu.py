"""The gear menu next to "+ New Group": a compact glass menu with the everyday switches.

  Auto organize | Undo | Redo
  Theme chips + "Edit theme..."
  Hide all groups / Lock layout
  Sound + volume, Group transparency (live)
  Tidy up, All settings...

Everything it changes is saved in layout.json. It closes when you click somewhere else.
"""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import theme
from .glasswin import GlassPanel, SliderRow, qss
from .theme import THEME

W = 340


def _btn(text, tip="", primary=False):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    if primary:
        b.setObjectName("primary")
    return b


class QuickMenu(GlassPanel):
    def __init__(self, controller):
        super().__init__("Clutter Buster - Quick settings", closable=False)
        # a real popup: clicking anywhere else closes it
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.c = controller
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(7)

        row = QHBoxLayout()
        row.setSpacing(6)
        auto = _btn("\u2728 Auto organize", "Suggest groups for your desktop (nothing changes until you click Apply)",
                    primary=True)
        auto.clicked.connect(lambda: self._do(self.c.auto_organize))
        row.addWidget(auto, 1)
        self.undo_b = _btn("\u21B6", "Undo (Ctrl+Z)")
        self.undo_b.clicked.connect(lambda: (self.c.undo(), self.refresh()))
        self.redo_b = _btn("\u21B7", "Redo (Ctrl+Y)")
        self.redo_b.clicked.connect(lambda: (self.c.redo(), self.refresh()))
        for b in (self.undo_b, self.redo_b):
            b.setFixedWidth(46)
            row.addWidget(b)
        lay.addLayout(row)

        lay.addWidget(self._label("Theme"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.theme_btns = {}
        names = [theme.AUTO, *theme.BUILT_IN.keys(), *[t.get("name") for t in self.c.layout.custom_themes]]
        for i, n in enumerate(names):
            b = _btn("Auto (follow Windows)" if n == theme.AUTO else n)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=n: self._pick_theme(n))
            grid.addWidget(b, i // 2, i % 2)
            self.theme_btns[n] = b
        lay.addLayout(grid)
        edit = _btn("\u270E  Edit theme...", "Change the colors of the theme you're using "
                    "(a built-in theme is saved as your own copy)")
        edit.clicked.connect(lambda: self._do(self.c.edit_theme))
        lay.addWidget(edit)

        lay.addWidget(self._label("Groups"))
        self.hide_cb = QCheckBox("Hide all groups (their items stay hidden)")
        self.hide_cb.setCursor(Qt.PointingHandCursor)
        self.hide_cb.toggled.connect(lambda v: self.c.set_groups_hidden(bool(v)))
        lay.addWidget(self.hide_cb)
        self.lock_cb = QCheckBox("Lock layout (no moving/resizing)")
        self.lock_cb.setCursor(Qt.PointingHandCursor)
        self.lock_cb.setToolTip("Groups can't be moved, resized or rearranged. Clicking still opens things.")
        self.lock_cb.toggled.connect(lambda v: self.c.set_locked(bool(v)))
        lay.addWidget(self.lock_cb)
        self.trans = SliderRow("transparency", "Group transparency", 0, 100, " %",
                               self.c.ui.get("transparency", 35))
        self.trans.changed.connect(lambda k, v: self.c.set_ui(k, v))
        lay.addWidget(self.trans)
        self.name_size = SliderRow("name_size", "Name size (all groups)", 8, 36, " pt", self.c.default_name_size())
        self.name_size.setToolTip("Hover a group's name for A- / A+ to change just that group")
        self.name_size.changed.connect(lambda k, v: self.c.set_default_name_size(v))
        lay.addWidget(self.name_size)
        tidy = _btn("\u25A6  Tidy up (snap all groups to the grid)", "One Undo puts them back")
        tidy.clicked.connect(lambda: (self.c.tidy_up(), self.refresh()))
        lay.addWidget(tidy)

        lay.addWidget(self._label("Sound"))
        srow = QHBoxLayout()
        self.sound_cb = QCheckBox("On")
        self.sound_cb.setCursor(Qt.PointingHandCursor)
        self.sound_cb.toggled.connect(lambda v: (self.c.set_pref("sounds", bool(v)), self.vol.setEnabled(bool(v))))
        srow.addWidget(self.sound_cb)
        self.vol = SliderRow("volume", "Volume", 0, 100, " %", self.c.layout.prefs.get("volume", 50))
        self.vol.changed.connect(lambda k, v: self.c.set_pref(k, int(v)))
        srow.addWidget(self.vol, 1)
        lay.addLayout(srow)

        more = _btn("All settings...")
        more.clicked.connect(lambda: self._do(self.c.show_settings))
        lay.addWidget(more)
        self.refresh()
        from .glasswin import M
        self.restyle()
        lay.activate()
        self.setFixedSize(W + 2 * M + 12, self.body.sizeHint().height() + 2 * M + 12)

    def closeEvent(self, e):
        if self.c.quick_menu is self:
            self.c.quick_menu = None
        super().closeEvent(e)

    def _label(self, text):
        lb = QLabel(text.upper())
        lb.setObjectName("tag")
        return lb

    def _do(self, fn):
        self.close()
        fn()

    def _pick_theme(self, name):
        self.c.set_theme_choice(name)
        self.refresh()
        self.restyle()

    def restyle(self):
        acc = THEME["default_accent"]
        self.setStyleSheet(qss() + "QPushButton:checked{border:2px solid %s;}" % acc)
        self.update()

    def refresh(self):
        prefs = self.c.layout.prefs
        cur = prefs.get("theme", theme.AUTO)
        for n, b in self.theme_btns.items():
            b.setChecked(n == cur)
        for cb, val in ((self.hide_cb, prefs.get("groups_hidden")), (self.lock_cb, prefs.get("locked")),
                        (self.sound_cb, prefs.get("sounds", True))):
            cb.blockSignals(True)
            cb.setChecked(bool(val))
            cb.blockSignals(False)
        self.vol.setEnabled(bool(prefs.get("sounds", True)))
        self.vol.set_value(prefs.get("volume", 50))
        self.trans.set_value(self.c.ui.get("transparency", 35))
        self.name_size.set_value(self.c.default_name_size())
        self.undo_b.setEnabled(self.c.undo_stack.can_undo() or self.c.edit_mode)
        self.undo_b.setToolTip("Undo " + self.c.undo_stack.next_label() + " (Ctrl+Z)"
                               if self.c.undo_stack.can_undo() else "Nothing to undo")
        self.redo_b.setEnabled(self.c.can_redo())

    def open_at(self, anchor=None):
        """Drop down under the gear button (kept on screen)."""
        av = QGuiApplication.primaryScreen().availableGeometry()
        if anchor is None:
            anchor = QRect(av.center().x(), av.top() + 60, 1, 1)
        x = anchor.right() - self.width() + 24
        y = anchor.bottom() - 8
        x = max(av.left(), min(x, av.right() - self.width()))
        y = max(av.top(), min(y, av.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
