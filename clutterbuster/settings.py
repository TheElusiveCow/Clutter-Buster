"""The Settings window (tray > Settings...): a glass window with sections

  General     - Start with Windows, "Automatically do it", how to uninstall
  Appearance  - theme (Auto / Clean White / Neon Gamer / your own), theme maker, the 4 sliders
  Search      - the quick search shortcut (record a new one, or reset to Ctrl+Space)
  Dock        - auto-hide on/off
  Sounds      - on/off and volume
  About       - version, GitHub link, where your settings live
  ...and the red "Remove Clutter Buster" button (same as in the tray menu).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QLineEdit, QScrollArea, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import __version__, integration, paths, sounds
from .glasswin import GlassPanel, SliderRow
from .theme import AUTO, BUILT_IN, DEFAULT_UI, SLIDERS

GITHUB = "https://github.com/TheElusiveCow/Clutter-Buster"
SECTIONS = ["General", "Appearance", "Search", "Dock", "Sounds", "About"]


def _h(text, kind="h2"):
    lab = QLabel(text)
    lab.setObjectName(kind)
    return lab


def _hint(text):
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


class SettingsWindow(GlassPanel):
    def __init__(self, controller):
        super().__init__("Clutter Buster - Settings")
        self.c = controller
        self.maker = None
        self.setFixedSize(860, 600)
        outer = QHBoxLayout(self.body)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(14)
        # left: title + section list + Remove button
        left = QVBoxLayout()
        left.setSpacing(8)
        t = _h("Clutter Buster", "h1")
        left.addWidget(t)
        left.addWidget(_hint("Settings"))
        left.addSpacing(6)
        self.nav = QListWidget()
        self.nav.setFixedWidth(190)
        for s in SECTIONS:
            QListWidgetItem(s, self.nav)
        self.nav.setCursor(Qt.PointingHandCursor)
        self.nav.setMinimumHeight(60)
        left.addWidget(self.nav, 1)
        left.addSpacing(6)
        remove = QPushButton("Remove Clutter Buster")
        remove.setObjectName("danger")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Shows everything on your desktop again, then removes the app's settings")
        remove.clicked.connect(lambda: (self.close(), self.c.request_remove()))
        remove.setMinimumHeight(38)
        left.addWidget(remove)
        self.remove_btn = remove
        outer.addLayout(left)
        # right: pages
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        # every page scrolls, so a tall page (big fonts / 150 % scaling) can never push the
        # red Remove button off the bottom of the window
        for page in (self._general(), self._appearance(), self._search(), self._dock(), self._sounds(),
                     self._about()):
            self.pages.addWidget(_scroll(page))
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

    # ------------------------------------------------------------ sections
    def _page(self, title):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 4, 30, 6)
        lay.setSpacing(10)
        lay.addWidget(_h(title, "h1"))
        return w, lay

    def _general(self):
        w, lay = self._page("General")
        lay.addWidget(_h("Start up"))
        self.autostart = QCheckBox("Start Clutter Buster when Windows starts")
        self.autostart.setCursor(Qt.PointingHandCursor)
        self.autostart.setChecked(integration.autostart_enabled())
        self.autostart.toggled.connect(lambda v: self.c.set_autostart(bool(v)))
        lay.addWidget(self.autostart)
        lay.addWidget(_hint("Your groups appear by themselves after you sign in. Turn this off and "
                            "you start the app yourself (it then won't run until you do)."))
        lay.addSpacing(8)
        lay.addWidget(_h("Shared desktop shortcuts"))
        self.autofix = QCheckBox("Fix shared-desktop permissions automatically")
        self.autofix.setCursor(Qt.PointingHandCursor)
        self.autofix.setChecked(bool(self.c.layout.prefs.get("auto_fix_perms", True)))
        self.autofix.toggled.connect(lambda v: self.c.set_pref("auto_fix_perms", bool(v)))
        lay.addWidget(self.autofix)
        lay.addWidget(_hint("Shortcuts on the shared Public desktop need admin permission to hide. When one "
                            "can't be hidden, Clutter Buster asks first, then Windows shows ONE permission "
                            "prompt for exactly those shortcuts. Clutter Buster itself never runs as admin."))
        lay.addSpacing(8)
        lay.addWidget(_h("Tidy up"))
        row = QHBoxLayout()
        auto = QPushButton("\u2728  Automatically do it...")
        auto.setObjectName("primary")
        auto.setCursor(Qt.PointingHandCursor)
        auto.clicked.connect(self.c.auto_organize)
        row.addWidget(auto)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(_hint("Looks at what's on your desktop and suggests groups - Games, AI, Browsers, "
                            "Tools, Documents and so on, reusing groups you already have. You check "
                            "everything first: nothing changes until you click Apply, and one Undo puts it "
                            "all back. It only runs when you click it."))
        lay.addSpacing(8)
        lay.addWidget(_h("Uninstall"))
        lay.addWidget(_hint("Use the red button on the left, or Windows Settings > Apps > Installed apps > "
                            "Clutter Buster > Uninstall. Either way every grouped item is shown on your "
                            "desktop again first."))
        lay.addStretch(1)
        return w

    def refresh_autostart(self):
        self.autostart.blockSignals(True)
        self.autostart.setChecked(integration.autostart_enabled())
        self.autostart.blockSignals(False)

    def _appearance(self):
        w, lay = self._page("Appearance")
        lay.addWidget(_h("Theme"))
        self.themes = QListWidget()
        self.themes.setMaximumHeight(170)
        self.themes.setCursor(Qt.PointingHandCursor)
        self.themes.itemClicked.connect(self._pick_theme)
        lay.addWidget(self.themes)
        row = QHBoxLayout()
        make = QPushButton("\u2728  Make a custom theme...")
        make.setCursor(Qt.PointingHandCursor)
        make.clicked.connect(self.open_maker)
        row.addWidget(make)
        self.delete_btn = QPushButton("Delete theme...")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._delete_theme)
        row.addWidget(self.delete_btn)
        self.themes.currentItemChanged.connect(lambda *_: self._update_delete())
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(6)
        lay.addWidget(_h("Look"))
        self.rows = {}
        for key, label, lo, hi, unit in SLIDERS:
            r = SliderRow(key, label, lo, hi, unit, self.c.ui.get(key, DEFAULT_UI[key]))
            r.changed.connect(self.c.set_ui)
            self.rows[key] = r
            lay.addWidget(r)
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Show names in big panels"))
        self.panel_labels = QComboBox()
        for key, label in (("auto", "Auto (when there's room)"), ("always", "Always"), ("never", "Never")):
            self.panel_labels.addItem(label, key)
        keys = ["auto", "always", "never"]
        cur = self.c.layout.prefs.get("panel_labels", "auto")
        self.panel_labels.setCurrentIndex(keys.index(cur) if cur in keys else 0)
        self.panel_labels.currentIndexChanged.connect(
            lambda i: self.c.set_pref("panel_labels", self.panel_labels.itemData(i)))
        lrow.addWidget(self.panel_labels)
        lrow.addStretch(1)
        lay.addLayout(lrow)
        self.snap = QCheckBox("Snap groups to each other (hold Alt while dragging to place freely)")
        self.snap.setCursor(Qt.PointingHandCursor)
        self.snap.setChecked(bool(self.c.layout.prefs.get("snap_groups", True)))
        self.snap.toggled.connect(lambda v: self.c.set_pref("snap_groups", bool(v)))
        lay.addWidget(self.snap)
        nrow = QHBoxLayout()
        names = QPushButton("Aa  Group names...")
        names.setCursor(Qt.PointingHandCursor)
        names.setToolTip("Font, size, color and shadow/outline for every group's name "
                         "(right-click a group > Name style... to change just one)")
        names.clicked.connect(lambda: self.c.name_style_dialog(None))
        nrow.addWidget(names)
        nrow.addStretch(1)
        lay.addLayout(nrow)
        lay.addStretch(1)
        self.fill_themes()
        return w

    def _search(self):
        w, lay = self._page("Search")
        lay.addWidget(_h("Quick search shortcut"))
        row = QHBoxLayout()
        self.hk_edit = HotkeyEdit(self.c, self)
        row.addWidget(self.hk_edit, 1)
        reset = QPushButton("Reset to Ctrl+Space")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(lambda: self.hk_edit.apply(0x0002, 0x20))
        row.addWidget(reset)
        lay.addLayout(row)
        self.hk_msg = _hint("Click the box, then press the keys you want - at least one of Ctrl, Alt or "
                            "Shift plus a key (for example Ctrl+Shift+F or Alt+Space). It works right away.")
        lay.addWidget(self.hk_msg)
        ok = self.c.search.hotkey_ok
        lay.addWidget(_hint(
            "The shortcut searches your desktop items, your groups, your favorites and saved websites from "
            "anywhere." + ("" if ok is not False else "\n\nRight now another app is using it, so it's off - "
                                                    "pick another one, or click the search bar instead.")))
        lay.addStretch(1)
        return w

    def _dock(self):
        w, lay = self._page("Dock")
        self.autohide = QCheckBox("Auto-hide the favorites dock (show it when the mouse comes near)")
        self.autohide.setChecked(bool(self.c.layout.prefs["dock_autohide"]))
        self.autohide.toggled.connect(lambda v: self.c.set_pref("dock_autohide", bool(v)))
        lay.addWidget(self.autohide)
        lay.addWidget(_hint("Off (the default): the dock is always there, on the desktop behind your windows. "
                            "On: it tucks away and a thin handle under the search bar shows where it is. "
                            "Drag shortcuts or links onto the dock to add favorites; right-click to remove."))
        lay.addStretch(1)
        return w

    def _sounds(self):
        w, lay = self._page("Sounds")
        self.sound_on = QCheckBox("Play a soft sound when a group opens and closes")
        self.sound_on.setChecked(bool(self.c.layout.prefs["sounds"]))
        self.sound_on.toggled.connect(lambda v: self.c.set_pref("sounds", bool(v)))
        lay.addWidget(self.sound_on)
        self.volume = SliderRow("volume", "Volume", 0, 100, " %", self.c.layout.prefs["volume"])
        self.volume.slider.sliderReleased.connect(lambda: self.c.set_pref("volume", self.volume.slider.value()))
        self.volume.slider.valueChanged.connect(
            lambda v: None if self.volume.slider.isSliderDown() else self.c.set_pref("volume", v))
        lay.addWidget(self.volume)
        test = QPushButton("\u25B6  Test sound")
        test.setCursor(Qt.PointingHandCursor)
        test.clicked.connect(lambda: sounds.play("open"))
        row = QHBoxLayout()
        row.addWidget(test)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _about(self):
        w, lay = self._page("About")
        lay.addWidget(QLabel(f"Clutter Buster {__version__}"))
        link = QLabel(f'<a href="{GITHUB}" style="color:#0A84FF;">{GITHUB}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        lay.addWidget(link)
        lay.addWidget(_hint("iOS-style groups for your desktop. Grouped items are only hidden (the Windows "
                            "'Hidden' flag) - nothing is ever moved, renamed or deleted."))
        lay.addWidget(_hint(f"Your groups and settings are saved in:\n{paths.app_dir()}"))
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------ theme list
    def fill_themes(self):
        cur = self.c.layout.prefs.get("theme", AUTO)
        self.themes.clear()
        from .theme import resolve
        names = [(AUTO, f"Auto - follow Windows light/dark (now: {resolve(AUTO, [])})")]
        names += [(n, n) for n in BUILT_IN]
        names += [(ct["name"], f"{ct['name']}   (custom)") for ct in self.c.layout.custom_themes]
        for key, label in names:
            it = QListWidgetItem(("\u25CF  " if key == cur else "\u25CB  ") + label, self.themes)
            it.setData(Qt.UserRole, key)
            if key == cur:
                self.themes.setCurrentItem(it)
        self._update_delete()

    def _update_delete(self):
        it = self.themes.currentItem()
        key = it.data(Qt.UserRole) if it else None
        self.delete_btn.setEnabled(bool(key) and key != AUTO and key not in BUILT_IN)

    def _pick_theme(self, it):
        self.c.set_theme_choice(it.data(Qt.UserRole))

    def _delete_theme(self):
        it = self.themes.currentItem()
        if it:
            self.c.delete_custom_theme(it.data(Qt.UserRole))

    def open_maker(self):
        from .theme_maker import ThemeMaker
        self.maker = ThemeMaker(self.c, parent=self)   # owned by Settings, so always in front of it
        from PySide6.QtGui import QGuiApplication
        g, av = self.geometry(), QGuiApplication.primaryScreen().availableGeometry()
        # beside Settings when there's room, so both stay visible
        x = min(g.right() - 40, av.right() - self.maker.width() - 8)
        y = min(g.top() + 70, av.bottom() - self.maker.height() - 8)
        self.maker.move(max(av.left(), x), max(av.top(), y))
        self.maker.show_on_top()

    # ------------------------------------------------------------ sync
    def refresh_from_ui(self):
        for key, row in self.rows.items():
            row.set_value(self.c.ui.get(key, DEFAULT_UI[key]))
        self.fill_themes()

    def restyle(self):
        super().restyle()
        if getattr(self, "maker", None) is not None and self.maker.isVisible():
            self.maker.restyle()

    def closeEvent(self, e):
        if self.maker is not None:
            self.maker.close()
        self.c.settings_closed()
        super().closeEvent(e)


def _scroll(page):
    sa = QScrollArea()
    sa.setObjectName("page")
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setWidget(page)
    sa.viewport().setAutoFillBackground(False)
    page.setAutoFillBackground(False)
    return sa


class HotkeyEdit(QLineEdit):
    """Click, then press a key combination: it's used right away (or you're told it's taken)."""

    def __init__(self, controller, settings):
        super().__init__()
        self.c, self.s = controller, settings
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click, then press the new shortcut")
        self.show_current()

    def show_current(self):
        self.setText(self.c.search_hotkey()["text"])

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.c.pause_hotkey(True)
        self.setText("Press the keys now...")

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.c.pause_hotkey(False)
        self.show_current()

    def keyPressEvent(self, e):
        from . import hotkey
        if e.key() in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr):
            return                                   # wait for the actual key
        if e.key() == Qt.Key_Escape and not e.modifiers():
            self.clearFocus()
            return
        combo = hotkey.from_qt(e.key(), e.modifiers())
        if combo is None:
            self.s.hk_msg.setText("That needs Ctrl, Alt or Shift plus a key - try again.")
            return
        self.apply(combo[0], combo[1], combo[2])

    def apply(self, mods, vk, text=None):
        ok, msg = self.c.set_search_hotkey(mods, vk, text)
        self.s.hk_msg.setText(msg)
        self.blockSignals(True)
        self.clearFocus()
        self.blockSignals(False)
        self.show_current()
        return ok
