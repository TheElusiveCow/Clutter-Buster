"""The Settings window (tray > Settings...): a glass window with sections

  General     - Start with Windows, "Automatically do it", how to uninstall
  Appearance  - theme (Auto / Clean White / Neon Gamer / your own), theme maker, the 4 sliders
  Search      - the quick search shortcut (Ctrl+Space, read-only for now)
  Dock        - auto-hide on/off
  Sounds      - on/off and volume
  About       - version, GitHub link, where your settings live
  ...and the red "Remove Clutter Buster" button (same as in the tray menu).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
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
        left.addWidget(self.nav, 1)
        remove = QPushButton("Remove Clutter Buster")
        remove.setObjectName("danger")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Shows everything on your desktop again, then removes the app's settings")
        remove.clicked.connect(lambda: (self.close(), self.c.request_remove()))
        left.addWidget(remove)
        outer.addLayout(left)
        # right: pages
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.pages.addWidget(self._general())
        self.pages.addWidget(self._appearance())
        self.pages.addWidget(self._search())
        self.pages.addWidget(self._dock())
        self.pages.addWidget(self._sounds())
        self.pages.addWidget(self._about())
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
        card = QHBoxLayout()
        card.addWidget(QLabel("Quick search shortcut"))
        card.addStretch(1)
        key = QLabel("  Ctrl + Space  ")
        key.setObjectName("tag")
        card.addWidget(key)
        lay.addLayout(card)
        ok = self.c.search.hotkey_ok
        lay.addWidget(_hint(
            "Press Ctrl+Space anywhere to search your desktop items, your groups, your favorites and "
            "saved websites. Changing the shortcut comes in a later version." +
            ("" if ok is not False else "\n\nRight now another app is using Ctrl+Space, so the shortcut is off - "
                                        "click the search bar instead.")))
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
