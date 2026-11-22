"""The brain of Clutter Buster: keeps groups, hiding, undo, favorites and all the windows in sync."""
import datetime
import logging
import os
import sys
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, desktop_files as df, desktop_layer, icons, integration, organize, paths, permfix, removal, sounds, theme
from .dock import Dock
from .glass import ask
from .group_widget import GroupWidget, first_free_left, group_size, min_size, snap_rect
from .ledger import Hider, Ledger
from .popup import GroupPopup
from .quicksearch import QuickSearch
from .searchbar import CORNERS as TOOLBAR_CORNERS, SNAP as TOOLBAR_SNAP, SearchBar
from .store import Layout, UndoStack, new_group, new_tab, tab_of
from .theme import ACCENTS, DEFAULT_UI
from .tray import Tray, broom_icon

log = logging.getLogger("cb")


def server_name(showcase=False):
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "me"
    return f"ClutterBuster-{user}" + ("-showcase" if showcase else "")


def swatch(hex_color):
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(hex_color))
    p.setPen(QColor(255, 255, 255))
    p.drawEllipse(1, 1, 14, 14)
    p.end()
    return QIcon(pm)


class Controller:
    def __init__(self, app, showcase=False):
        self.app = app
        self.showcase = showcase
        self.removed = False
        self.layout = Layout()
        self.ledger = Ledger()
        self.hider = Hider(self.ledger)
        self.undo_stack = UndoStack()
        self.redo_stack = []
        self.failed_hides = set()     # norm paths Windows wouldn't let us hide (shown with an orange "!")
        self.quick_menu = None
        self._permfix_declined = set()   # shared shortcuts you said "Not now" / "No" to (this session)
        self._permfix_job = None         # (process handle, files, started) while the helper runs
        self._perm_toast = None
        self.widgets = {}
        self._told_about_show_hidden = False
        self.edit_mode = False
        self._edit_snap = None
        self._appearance_ckpt = False
        self._covered = False
        self._last_light = theme.windows_prefers_light()
        self.settings_win = None
        self.organize_win = None
        self.toolbar = None
        self.theme_name = ""
        prefs = self.layout.prefs
        sounds.SETTINGS.update(on=bool(prefs["sounds"]), volume=int(prefs["volume"]))
        sounds.ensure()
        self.apply_theme(repaint=False)

        # 1) Make the desktop match the saved groups (un-hide leftovers, hide grouped items)
        self.sync_hidden()

        # 2) Windows
        self.search = SearchBar(self)       # the whole toolbar: search, + New Group, gear
        self.actions = self.search          # (they used to be two windows)
        self.dock = Dock(self)
        self.place_bars()
        self.search.show()
        self.dock.show()
        self.popup = GroupPopup(self)
        self.quick = QuickSearch(self)
        self.tray = Tray(self)
        self.tray.show()
        self.rebuild_widgets()
        self.update_undo_ui()

        self.undo_shortcut = QShortcut(QKeySequence.Undo, self.search)
        self.undo_shortcut.setContext(Qt.ApplicationShortcut)
        self.undo_shortcut.activated.connect(self.undo)
        self.redo_shortcuts = []
        for seq in (QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")):
            sc = QShortcut(seq, self.search)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(self.redo)
            self.redo_shortcuts.append(sc)

        # 3) Ctrl+Space everywhere (no Windows key needed)
        if not showcase:
            if not self.search.register_hotkey():
                self.notify(f"{self.search_hotkey()['text']} is already used by another app, so that shortcut is off. "
                            "Click the search bar at the top instead.")
            self.search.update()

        # Re-check the desktop layer now and then (e.g. after "Show desktop").
        self.layer_timer = QTimer()
        self.layer_timer.timeout.connect(self.reassert_layer)
        self.layer_timer.start(2500)
        self.beat_timer = QTimer()                  # tells the freeze watchdog we're alive
        self.beat_timer.timeout.connect(paths.heartbeat)
        self.beat_timer.start(2000)

        # Stage 3: neon glow animation (max 25 fps, paused while a game / full-screen or
        # maximized window covers the desktop), Auto theme watcher, and delayed saving.
        self.glow_timer = QTimer()
        self.glow_timer.timeout.connect(self._glow_tick)
        self._glow_last = time.monotonic()
        self.cover_timer = QTimer()
        self.cover_timer.timeout.connect(self._check_covered)
        self.cover_timer.start(1000)
        self.theme_timer = QTimer()
        self.theme_timer.timeout.connect(self._check_windows_theme)
        self.theme_timer.start(2000)
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.layout.save)
        self._icons_timer = QTimer()
        self._icons_timer.setSingleShot(True)
        self._icons_timer.timeout.connect(self._repaint_all)
        icons._ensure_notifier().changed.connect(lambda: self._icons_timer.start(80))   # thumbnails ready
        # Grouped items that come back visible (an updater recreating its shortcut, a restore,
        # ...) are hidden again: right away when a desktop folder changes, and every 30 s.
        self._recheck_timer = QTimer()
        self._recheck_timer.setSingleShot(True)
        self._recheck_timer.timeout.connect(self.recheck_hidden)
        self.recheck_timer = QTimer()
        self.recheck_timer.timeout.connect(self.recheck_hidden)
        if not self.showcase:
            from PySide6.QtCore import QFileSystemWatcher
            self.desk_watch = QFileSystemWatcher([d for d in df.desktop_dirs() if os.path.isdir(d)])
            self.desk_watch.directoryChanged.connect(lambda *_: self._recheck_timer.start(1500))
            self.recheck_timer.start(30000)
            QTimer.singleShot(4000, self.refresh_explorer)     # make sure Explorer redrew after start-up
        self.permfix_timer = QTimer()
        self.permfix_timer.setSingleShot(True)
        self.permfix_timer.timeout.connect(self.check_permfix)
        self.permfix_poll = QTimer()
        self.permfix_poll.timeout.connect(self._poll_permfix)
        if self.failed_hides and not showcase:
            self.permfix_timer.start(2500)
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self.search)
        self.esc_shortcut.setContext(Qt.ApplicationShortcut)
        self.esc_shortcut.setEnabled(False)
        self.esc_shortcut.activated.connect(self._on_escape)
        self.apply_dock_mode()
        self.update_glow_timer()

        # Stage 4: Start with Windows (on unless you turned it off) + the Settings > Apps entry
        if not showcase:
            self.setup_windows_integration()

        app.aboutToQuit.connect(self.on_about_to_quit)
        app.commitDataRequest.connect(lambda *_: self.restore_desktop())
        self.write_status()
        try:
            with open(paths.path("app.pid"), "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
        log.info("Clutter Buster %s started with %d group(s)%s", __version__, len(self.layout.groups),
                 " [showcase]" if showcase else "")

    # ------------------------------------------------------------------ helpers
    def avail(self):
        return QGuiApplication.primaryScreen().availableGeometry()

    @property
    def ui(self):
        return self.layout.ui

    def place_dock(self):
        pos = self.ui.get("dock_pos")
        if pos:
            av = self.avail()
            cx = min(max(int(pos[0]), av.left() + 120), av.right() - 120)
            top = min(max(int(pos[1]), av.top()), av.bottom() - 100)
            self.dock.place(cx, top)
            return
        if self.search.wedge:            # toolbar tucked in a corner: the dock keeps its usual spot
            av = self.avail()
            self.dock.place(av.center().x(), av.top() + 12)
            return
        sr = self.search.search_rect()
        cx = self.search.x() + sr.center().x()
        self.dock.place(cx, self.search.y() + self.search.height() - 4)

    def _clamp_pos(self, w, pos):
        av = self.avail()
        x = min(max(int(pos[0]), av.left()), av.right() - w.width() + 1)
        y = min(max(int(pos[1]), av.top()), av.bottom() - w.height() + 1)
        return x, y

    def place_bars(self):
        """Toolbar (floating pill or tucked into a corner) and dock: saved spots, or the defaults."""
        av = self.avail()
        corner = self.ui.get("toolbar_corner")
        if corner in TOOLBAR_CORNERS:
            self.search.set_corner(corner)
            w, h = self.search.width(), self.search.height()
            x = av.left() if corner[1] == "l" else av.right() - w + 1
            y = av.top() if corner[0] == "t" else av.bottom() - h + 1
            self.search.move(x, y)
        else:
            self.search.set_corner(None)
            pos = self.ui.get("search_pos") or self.search.default_pos(av)
            self.search.move(*self._clamp_pos(self.search, pos))
        self.place_dock()

    def bar_moved(self, key, widget, pt):
        """Edit layout: the toolbar or the dock was dragged somewhere."""
        if key == "dock_pos":
            x, y = self._clamp_pos(widget, (pt.x(), pt.y()))
            self.ui[key] = [x + widget.width() // 2, y]
        else:
            self.search.set_corner(None)
            self.ui.pop("toolbar_corner", None)
            self.ui["search_pos"] = list(self._clamp_pos(self.search, (pt.x(), pt.y())))
        self.place_bars()
        self.schedule_save()

    def toolbar_snap_corner(self, geo, cursor=None):
        """While the toolbar is dragged: the screen corner it would tuck into (or None).

        Everything is in Qt's logical pixels (Windows' 150 % scaling is already applied) and
        measured against the primary screen's work area (above the taskbar). It snaps when
        EITHER the mouse is near a corner OR the toolbar is pushed into one - the toolbar is
        clamped onto the screen first, because the grip is at the bar's far left: pushing the
        bar against the top-right corner leaves the mouse ~700 px away (v0.6.0 only looked at
        the unclamped window, so on Brian's PC it never snapped)."""
        av = self.avail()
        m = 10      # the toolbar's transparent margin
        w, h = geo.width(), geo.height()
        x = min(max(geo.left(), av.left() - m), av.right() - w + 1 + m)
        y = min(max(geo.top(), av.top() - m), av.bottom() - h + 1 + m)
        g = QRect(x, y, w, h).adjusted(m, m, -m, -m)
        pts = {"tl": (g.topLeft(), av.topLeft()), "tr": (g.topRight(), av.topRight()),
               "bl": (g.bottomLeft(), av.bottomLeft()), "br": (g.bottomRight(), av.bottomRight())}
        best = None
        for k, (mine, scr) in pts.items():
            dx, dy = abs(mine.x() - scr.x()), abs(mine.y() - scr.y())
            hit = dx <= TOOLBAR_SNAP and dy <= TOOLBAR_SNAP
            d = dx + dy
            if cursor is not None:
                cx, cy = abs(cursor.x() - scr.x()), abs(cursor.y() - scr.y())
                if cx <= TOOLBAR_SNAP and cy <= TOOLBAR_SNAP:
                    hit, d = True, min(d, cx + cy)
            if hit and (best is None or d < best[0]):
                best = (d, k)
        return best[1] if best else None

    def dock_toolbar(self, where):
        """Gear menu > Dock toolbar to: "tl"/"tr"/"bl"/"br", "top" (top centre) or "float"
        (a floating bar at its last spot). Works even when dragging is awkward."""
        if where == "top":
            return self.reset_toolbar()
        cur = self.ui.get("toolbar_corner")
        if (where in TOOLBAR_CORNERS and cur == where) or (where == "float" and not cur):
            return
        self.checkpoint("dock toolbar")
        if where in TOOLBAR_CORNERS:
            self.ui["toolbar_corner"] = where
        else:
            self.ui.pop("toolbar_corner", None)
        self.place_bars()
        self.search.send_to_desktop_layer()
        log.info("Toolbar docked: %s", where)
        self.commit()

    def toolbar_moved(self, corner, pos):
        """The toolbar was dragged by its grip (or in Edit layout) and dropped."""
        if self.layout_locked():
            self.place_bars()
            return
        self.checkpoint("move toolbar")
        log.info("Toolbar dropped: %s", corner or f"floating at {pos.x()},{pos.y()}")
        if corner in TOOLBAR_CORNERS:
            self.ui["toolbar_corner"] = corner
        else:
            self.ui.pop("toolbar_corner", None)
            x, y = pos.x(), pos.y()
            if self.edit_mode:
                x, y = round(x / 16) * 16, round(y / 16) * 16
            self.search.set_corner(None)
            self.ui["search_pos"] = list(self._clamp_pos(self.search, (x, y)))
        self.place_bars()
        self.search.send_to_desktop_layer()
        self.commit() if not self.edit_mode else self.schedule_save()

    def reset_toolbar(self):
        """Gear menu > Reset toolbar position: back to the middle of the top edge."""
        if "toolbar_corner" not in self.ui and "search_pos" not in self.ui:
            self.place_bars()
            return
        self.checkpoint("reset toolbar")
        self.ui.pop("toolbar_corner", None)
        self.ui.pop("search_pos", None)
        self.place_bars()
        self.search.send_to_desktop_layer()
        self.commit()

    def schedule_save(self):
        self.save_timer.start(600)

    # ------------------------------------------------------------------ look & themes
    def all_windows(self):
        out = [self.search, self.dock, self.popup, self.quick, *self.widgets.values()]
        out += [w for w in (self.toolbar, self.settings_win) if w is not None]
        return [w for w in out if w is not None]

    def style_menus(self):
        """Every QMenu / drop-down in the app: readable colours from the current theme."""
        from .glasswin import menu_qss
        try:
            self.app.setStyleSheet(menu_qss())
        except Exception:
            log.exception("Could not style menus")

    def apply_theme(self, repaint=True):
        prefs = self.layout.prefs
        self.theme_name = theme.resolve(prefs.get("theme", theme.AUTO), self.layout.custom_themes)
        theme.apply(self.theme_name, self.ui, self.layout.custom_themes)
        self.style_menus()
        if not repaint:
            return
        for w in self.all_windows():
            if hasattr(w, "restyle"):
                w.restyle()
            w.update()
        if self.popup.isVisible():
            self.popup.page = min(self.popup.page, self.popup.pages() - 1)
            self.popup.page_pos = float(self.popup.page)
            if self.ui.get("popup_size") is None:
                g = self.popup.geometry()
                pw, ph = self.popup.panel_size()
                self.popup.resize(pw + 44, ph + 44)
                self.popup.move(g.topLeft())
        if self.settings_win is not None:
            self.settings_win.refresh_from_ui()
        self.update_glow_timer()

    def set_ui(self, key, value):
        """A look slider moved (Edit layout toolbar or Settings) - applies live."""
        self._appearance_checkpoint()
        self.ui[key] = int(value)
        if key == "per_row":
            self.ui["popup_size"] = None     # the popup re-fits to the new number of columns
        self.apply_theme()
        if key in ("per_row", "icon_size"):
            self.rebuild_widgets()           # small tile previews + big panels follow live
        if self.toolbar is not None and self.toolbar.isVisible():
            self.toolbar.refresh_from_ui()
        self.schedule_save()

    def ui_changed(self, key):
        """Something in the look changed directly (e.g. the popup was resized)."""
        self._appearance_checkpoint()
        self.schedule_save()

    def reset_look(self):
        self._appearance_checkpoint()
        for k, v in DEFAULT_UI.items():
            self.ui[k] = v
        self.ui["popup_size"] = None
        self.apply_theme()
        if self.toolbar is not None:
            self.toolbar.refresh_from_ui()
        self.schedule_save()

    def _appearance_checkpoint(self):
        # Edit layout already saved one undo step for the whole session
        if self.edit_mode or self._appearance_ckpt:
            return
        self.undo_stack.push("appearance change", self.layout.snapshot())
        self._appearance_ckpt = True
        self.update_undo_ui()

    def settings_closed(self):
        self._appearance_ckpt = False
        self.settings_win = None

    def set_theme_choice(self, name):
        self.layout.prefs["theme"] = name or theme.AUTO
        self.layout.save()
        self.apply_theme()
        log.info("Theme: %s (showing %s)", self.layout.prefs["theme"], self.theme_name)

    def save_custom_theme(self, ct):
        themes = self.layout.custom_themes
        old = next((i for i, t in enumerate(themes) if t.get("name") == ct["name"]), None)
        if old is not None:
            if not ask("Replace theme?", f"You already have a theme called \"{ct['name']}\". Replace it?",
                       yes_text="Replace"):
                return False
            themes[old] = ct
        else:
            themes.append(ct)
        self.set_theme_choice(ct["name"])
        return True

    def delete_custom_theme(self, name, confirm=True):
        themes = self.layout.custom_themes
        if not any(t.get("name") == name for t in themes):
            return False
        if confirm and not ask("Delete theme?", f"Delete your theme \"{name}\"?\n\nYou can Undo this (Ctrl+Z).",
                               yes_text="Delete theme", danger=True):
            return False
        self.checkpoint("delete theme")
        self.layout.extra["custom_themes"] = [t for t in themes if t.get("name") != name]
        if self.layout.prefs.get("theme") == name:
            self.layout.prefs["theme"] = theme.AUTO
        for g in self.layout.groups:                     # groups that used it follow the main theme again
            if g.get("theme") == name:
                g.pop("theme", None)
        self.layout.save()
        self.apply_theme()
        self.update_undo_ui()
        log.info("Deleted custom theme %s", name)
        if self.quick_menu is not None:
            try:
                self.quick_menu.close()
            except RuntimeError:
                pass
        return True

    def set_pref(self, key, value):
        self.layout.prefs[key] = value
        if key == "dock_autohide":
            self.apply_dock_mode()
        elif key == "panel_labels":
            for w in self.widgets.values():
                w.update()
        elif key in ("sounds", "volume"):
            sounds.SETTINGS.update(on=bool(self.layout.prefs["sounds"]), volume=int(self.layout.prefs["volume"]))
            if key == "volume":
                sounds.ensure()
        self.schedule_save()

    def apply_dock_mode(self):
        pinned = self.edit_mode or not self.layout.prefs.get("dock_autohide", False) or self.showcase
        self.dock.pinned = pinned
        if pinned:
            self.dock.show_dock()
        else:
            self.dock.hide_dock()

    # neon glow animation
    def update_glow_timer(self):
        want = bool(theme.THEME.get("glow")) and theme.THEME.get("glow_strength", 0) > 0.01 and not self._covered
        if want and not self.glow_timer.isActive():
            self._glow_last = time.monotonic()
            self.glow_timer.start(40)      # 25 frames a second at most
        elif not want and self.glow_timer.isActive():
            self.glow_timer.stop()

    def _glow_tick(self):
        now = time.monotonic()
        dt = min(0.2, now - self._glow_last)
        self._glow_last = now
        theme.PHASE[0] = (theme.PHASE[0] + dt / 6.0) % 1.0   # one lap every 6 seconds
        from .glasswin import GlassPanel
        for w in self.all_windows():
            if w.isVisible() and not isinstance(w, GlassPanel):   # dialogs keep a still glow (saves CPU)
                w.glow_update() if hasattr(w, "glow_update") else w.update()

    def _check_covered(self):
        cov = bool(desktop_layer.desktop_covered()) and not self.showcase
        if cov != self._covered:
            self._covered = cov
            self.update_glow_timer()

    def _check_windows_theme(self):
        light = theme.windows_prefers_light()
        if light != self._last_light:
            self._last_light = light
            if self.layout.prefs.get("theme", theme.AUTO) == theme.AUTO:
                log.info("Windows switched to %s mode - following it", "light" if light else "dark")
                self.apply_theme()

    # ------------------------------------------------------------------ edit layout
    def enter_edit_mode(self):
        if self.edit_mode:
            if self.toolbar is not None:
                self.toolbar.show_on_top()
            return
        from .edit_toolbar import EditToolbar
        self._edit_snap = self.layout.snapshot()
        self.undo_stack.push("edit layout", self.layout.snapshot())   # one undo step per session
        self.edit_mode = True
        self.esc_shortcut.setEnabled(True)
        self.apply_dock_mode()
        if self.toolbar is None:
            self.toolbar = EditToolbar(self)
        self.toolbar.restyle()
        self.toolbar.refresh_from_ui()
        self.toolbar.place(self.avail())
        self.toolbar.show_on_top()
        for w in self.all_windows():
            w.update()
        self.update_undo_ui()
        log.info("Edit layout: on")

    def exit_edit_mode(self):
        if not self.edit_mode:
            return
        self.edit_mode = False
        self.esc_shortcut.setEnabled(False)
        if self.toolbar is not None:
            self.toolbar.hide()
        if self.layout.snapshot() == self._edit_snap and self.undo_stack.next_label() == "edit layout":
            self.undo_stack.pop()          # nothing changed: no empty undo step
        self._edit_snap = None
        self.save_timer.stop()
        self.layout.save()
        self.apply_dock_mode()
        for w in self.all_windows():
            w.update()
        self.update_undo_ui()
        log.info("Edit layout: off (saved)")

    def _on_escape(self):
        if self.quick.isVisible():
            self.quick.close_search()
        elif self.popup.isVisible():
            self.popup.close_animated()
        else:
            self.exit_edit_mode()

    def group_rects(self, exclude=None):
        out = []
        for g in self.layout.groups:
            if g["id"] == exclude:
                continue
            w, h = group_size(g)
            out.append(QRect(g["x"], g["y"], w, h))
        # keep the search bar, the buttons and the dock area free too
        if self.search.wedge:
            out.append(self.search.geometry())
        else:
            out.append(QRect(self.search.x(), self.search.y(), self.search.width(), self.search.height() + 90))
        if self.ui.get("dock_pos"):
            out.append(self.dock.geometry().adjusted(0, 0, 0, 90))
        return out

    def notify(self, text):
        log.info("Notice: %s", text)
        if self.showcase:
            return
        if QSystemTrayIcon.isSystemTrayAvailable() and self.tray.isVisible():
            self.tray.showMessage("Clutter Buster", text, broom_icon(), 5000)

    def write_status(self):
        try:
            import PySide6
            status = {
                "version": __version__,
                "started": datetime.datetime.now().isoformat(timespec="seconds"),
                "pid": os.getpid(),
                "python": sys.version.split()[0],
                "pyside6": PySide6.__version__,
                "desktop_dirs": df.desktop_dirs(),
                "explorer_shows_hidden_files": df.explorer_shows_hidden_files(),
                "popup_style": "compact frosted panel (no full-screen blur)",
                "hotkey_ctrl_space": self.search.hotkey_ok,
                "search_shortcut": self.search_hotkey()["text"],
                "groups": len(self.layout.groups),
                "favorites": len(self.layout.favorites),
                "ledger_hidden_items": len(self.ledger.hidden),
                "could_not_hide": sorted(self.hider.failed),
                "screen": [self.avail().x(), self.avail().y(), self.avail().width(), self.avail().height()],
                "dpr": QGuiApplication.primaryScreen().devicePixelRatio(),
                "search_bar_visible": self.search.isVisible(),
                "dock_visible": self.dock.isVisible(),
                "tray_visible": self.tray.isVisible(),
                "showcase": self.showcase,
                "theme_choice": self.layout.prefs.get("theme"),
                "theme_shown": self.theme_name,
                "windows_light_mode": theme.windows_prefers_light(),
                "glow_animating": self.glow_timer.isActive(),
                "edit_mode": self.edit_mode,
                "custom_themes": [t.get("name") for t in self.layout.custom_themes],
                "start_with_windows": integration.autostart_enabled(),
                "start_with_windows_command": integration._get(integration.RUN_KEY, integration.RUN_NAME),
                "in_settings_apps": integration.uninstall_registered(),
                "uninstall_command": integration._get(integration.UNINSTALL_KEY, "UninstallString"),
            }
            paths.atomic_write_json(paths.status_file(), status)
        except Exception:
            log.exception("Could not write status.json")

    def reassert_layer(self):
        for w in [self.search, self.dock, *self.widgets.values()]:
            w.send_to_desktop_layer()

    # ------------------------------------------------------------------ syncing
    def sync_hidden(self):
        statuses = self.hider.sync(self.layout.wanted_hidden())
        failed = [p for p, s in statuses.items() if s == "failed"]
        before = getattr(self, "failed_hides", set())
        self.failed_hides = {df.norm(p) for p in failed}
        if self.failed_hides != before:                # keep the orange ! in step
            for w in getattr(self, "widgets", {}).values():
                w.update()
        if failed and not self.showcase and hasattr(self, "permfix_timer"):
            self.permfix_timer.start(1200)        # offer the shared-desktop permission fix
        return statuses, failed

    def visible_grouped(self):
        """Grouped desktop items that are NOT hidden right now (should be none, except failed ones)."""
        out = []
        for p in self.layout.wanted_hidden():
            if df.is_url(p) or not os.path.exists(p) or not df.is_on_desktop(p):
                continue
            if not df.is_hidden(p):
                out.append(p)
        return out

    def recheck_hidden(self):
        """Hide again anything grouped that became visible; returns how many were found."""
        if getattr(self, "removed", False):
            return 0
        vis = [p for p in self.visible_grouped() if df.norm(p) not in self.failed_hides]
        if vis:
            log.info("Re-check: %d grouped item(s) visible again: %s", len(vis),
                     ", ".join(os.path.basename(p) for p in vis))
            self.sync_hidden()
            self.hider.ledger.save()
            for p in vis:
                df.notify_changed(p)
        return len(vis)

    def refresh_explorer(self):
        """Nudge Explorer to redraw every hidden grouped item (it sometimes keeps a stale icon
        after a quick show/hide, e.g. around a restart)."""
        for p in self.layout.wanted_hidden():
            if not df.is_url(p) and os.path.exists(p) and df.is_hidden(p):
                df.notify_changed(p)

    # ------------------------------------------------------------------ shared-desktop permission fix
    def permfix_candidates(self, gid=None):
        """Grouped items on the Public Desktop that Windows refused to hide with 'access denied'."""
        wanted = self.layout.wanted_hidden()
        paths_ = [p for p, g in wanted.items() if df.norm(p) in self.failed_hides and (gid is None or g == gid)]
        return permfix.candidates(paths_)

    def check_permfix(self):
        """After hiding: if shared shortcuts failed, ask once (glass toast), then one UAC prompt."""
        if self.showcase or self._permfix_job is not None or not self.layout.prefs.get("auto_fix_perms", True):
            return
        files = [p for p in self.permfix_candidates() if df.norm(p) not in self._permfix_declined]
        if not files or self._perm_toast is not None:
            return
        from .glass_toast import GlassToast
        n = len(files)
        self._perm_toast = GlassToast(
            f"Windows will ask for permission to hide {n} shared shortcut{'s' if n != 1 else ''}",
            "They're on the shared Public desktop: " + ", ".join(os.path.splitext(os.path.basename(p))[0]
                                                                  for p in files[:4]) + (" ..." if n > 4 else ""),
            ok_text="OK", cancel_text="Not now")
        self._perm_toast.accepted.connect(lambda: self.fix_permissions(files))
        self._perm_toast.rejected.connect(lambda: self._decline_permfix(files, "Not now"))
        self._perm_toast.destroyed.connect(lambda *_: setattr(self, "_perm_toast", None))
        self._perm_toast.show_corner(self.avail())

    def _decline_permfix(self, files, why):
        self._permfix_declined |= {df.norm(p) for p in files}
        log.info("Shared-desktop permission fix: %s (%d file(s)) - they stay visible, marked with !", why, len(files))
        self.notify("Those shared shortcuts stay on the desktop for now (orange !). Use \"Fix hiding "
                    "permission...\" in the broom menu or the group's menu whenever you like.")

    def fix_permissions(self, files=None, gid=None):
        """Run ONE elevated icacls helper for exactly these files, wait, then hide them again.
        Only the helper asks for admin rights - Clutter Buster itself never does."""
        if self._permfix_job is not None:
            return False
        files = files if files is not None else self.permfix_candidates(gid)
        if not files:
            self.notify("Nothing to fix - everything in your groups is hidden.")
            return False
        log.info("Shared-desktop permission fix: asking Windows to let %s change: %s",
                 permfix.current_user(), "; ".join(files))
        try:
            handle, used = permfix.launch(files)
        except permfix.Cancelled:
            self._decline_permfix(files, "the Windows permission prompt was cancelled")
            self.update_permfix_ui()
            return False
        except OSError as e:
            log.error("Shared-desktop permission fix could not start: %s", e)
            self.notify(f"Couldn't ask Windows for permission ({e}). The shortcuts stay visible.")
            return False
        self._permfix_job = (handle, used, time.monotonic())
        self.permfix_poll.start(300)
        return True

    def _poll_permfix(self):
        if self._permfix_job is None:
            self.permfix_poll.stop()
            return
        handle, used, t0 = self._permfix_job
        code = permfix.poll(handle)
        if code is None and time.monotonic() - t0 < 120:
            return
        self.permfix_poll.stop()
        self._permfix_job = None
        log.info("Shared-desktop permission helper finished (exit code %s); hiding again", code)
        self.hider.failed.clear()
        statuses, failed = self.sync_hidden()
        still = [p for p in used if df.norm(p) in self.failed_hides]
        fixed = len(used) - len(still)
        log.info("Shared-desktop permission fix: %d hidden now, %d still visible", fixed, len(still))
        if still:
            self._permfix_declined |= {df.norm(p) for p in still}
            self.notify(f"{len(still)} shared shortcut(s) still couldn't be hidden (orange !).")
        elif fixed:
            self.notify(f"Done - {fixed} shared shortcut{'s' if fixed != 1 else ''} hidden.")
        self.commit()
        self.write_status()
        self.update_permfix_ui()

    def update_permfix_ui(self):
        if hasattr(self.tray, "refresh_toggles"):
            self.tray.refresh_toggles()

    def _repaint_all(self):
        for w in self.all_windows():
            if w.isVisible():
                w.update()

    def hide_failed(self, path):
        """True if this grouped item (or its same-named twin on the other desktop) is still visible
        because Windows refused to hide it (usually the shared Public desktop)."""
        if not self.failed_hides or df.is_url(path):
            return False
        n = df.norm(path)
        if n in self.failed_hides:
            return True
        base = os.path.basename(n)
        return any(os.path.basename(f) == base for f in self.failed_hides)

    def commit(self, undoable=True):
        """Save, back up, and refresh every window after a change."""
        self.layout.save()
        self.rebuild_widgets()
        self.popup.refresh()
        self.dock.refresh()
        self.update_undo_ui()

    def checkpoint(self, label):
        if self.edit_mode:
            return      # Edit layout keeps ONE undo step for the whole session
        self.undo_stack.push(label, self.layout.snapshot())
        self.redo_stack.clear()

    def update_undo_ui(self):
        en, label = self.undo_stack.can_undo(), self.undo_stack.next_label()
        self.actions.update_undo(en, label)
        self.tray.update_undo(en, label)

    def rebuild_widgets(self):
        ids = {g["id"] for g in self.layout.groups}
        for gid in list(self.widgets):
            if gid not in ids:
                w = self.widgets.pop(gid)
                w.hide()
                w.deleteLater()
        av = self.avail()
        hide_all = bool(self.layout.prefs.get("groups_hidden"))
        for g in self.layout.groups:
            w = self.widgets.get(g["id"])
            if w is None:
                w = GroupWidget(self, g["id"])
                self.widgets[g["id"]] = w
            if w._last_tab != g.get("tab"):
                w._last_tab = g.get("tab")
                w.page = 0
                w._selected = None
            gw, gh = group_size(g)
            gw, gh = min(gw, av.width()), min(gh, av.height())
            x = min(max(g["x"], av.left()), av.right() - gw)
            y = min(max(g["y"], av.top()), av.bottom() - gh)
            w.setGeometry(x, y, gw, gh)
            if hide_all:
                w.hide()          # "Hide all groups": the groups go away, their items stay hidden
                continue
            if not w.isVisible():
                w.show()
            w.update()

    # ------------------------------------------------------------------ groups
    def create_group(self, name="New Group", edit=True, mode="tile", items=None, label="new group"):
        self.checkpoint(label)
        accent = ACCENTS[len(self.layout.groups) % len(ACCENTS)][1]
        w, h = group_size({"mode": mode})
        pos = first_free_left(self.avail(), self.group_rects(), w, h)
        g = new_group(name, pos.x(), pos.y(), accent=accent, mode=mode)
        if items:
            g["items"] = items
            g["badge"] = len(items)
        self.layout.groups.append(g)
        self.sync_hidden()
        self.commit()
        if edit and not self.showcase:
            QTimer.singleShot(60, self.widgets[g["id"]].start_rename)
        return g["id"]

    def rename_group(self, gid, name):
        g = self.layout.group(gid)
        if g and name and name != g["name"]:
            self.checkpoint("rename")
            g["name"] = name[:60]
            self.commit()

    # ------------------------------------------------------------------ magnetic snapping
    def snap_on(self):
        """Snap while dragging: the Settings toggle, and not while Alt is held."""
        from . import snapping
        return bool(self.layout.prefs.get("snap_groups", True)) and not snapping.alt_held()

    def snap_targets(self, exclude=None):
        return [w.glass_rect_global() for gid, w in self.widgets.items() if gid != exclude and w.isVisible()]

    def show_guides(self, lines, widget=None):
        from . import snapping
        if not lines:
            if getattr(self, "_guides", None) is not None:
                self._guides.clear()
            return
        if getattr(self, "_guides", None) is None:
            self._guides = snapping.GuideOverlay()
        g = self.layout.group(widget.gid) if widget is not None else None
        self._guides.show_lines(lines, (g or {}).get("accent") or theme.THEME.get("default_accent"))

    def move_group(self, gid, x, y):
        """Free placement (magnetic snapping already happened while dragging); kept on screen."""
        g = self.layout.group(gid)
        if g is None:
            return
        w, h = group_size(g)
        av = self.avail()
        pt = QPoint(min(max(int(x), av.left()), av.right() - w), min(max(int(y), av.top()), av.bottom() - h))
        if (pt.x(), pt.y()) == (g["x"], g["y"]):
            self.widgets[gid].move(pt)
            return
        self.checkpoint("move group")
        g["x"], g["y"] = pt.x(), pt.y()
        self.commit()

    def resize_group(self, gid, x, y, w, h):
        g = self.layout.group(gid)
        if g is None:
            return
        mw, mh = min_size(g.get("mode", "tile"))
        self.checkpoint("resize group")
        g["x"], g["y"] = int(x), int(y)
        g["tile_size" if g.get("mode", "tile") == "tile" else "panel_size"] = [max(mw, int(w)), max(mh, int(h))]
        self.commit()

    def set_accent(self, gid, color):
        g = self.layout.group(gid)
        if g is None:
            return
        self.checkpoint("accent color")
        g["accent"] = color
        self.commit()

    def pick_custom_accent(self, gid):
        g = self.layout.group(gid)
        if g is None:
            return
        # the colour picker lives inside the group's settings panel (no separate dialog)
        self.fence_settings(gid, self.widgets.get(gid)).toggle_picker(True)

    def set_mode(self, gid, mode):
        g = self.layout.group(gid)
        if g is None or g.get("mode", "tile") == mode:
            return
        self.checkpoint("small/big switch")
        g["mode"] = mode
        w, h = group_size(g)
        pt = snap_rect(g["x"], g["y"], w, h, self.avail(), self.group_rects(exclude=gid))
        g["x"], g["y"] = pt.x(), pt.y()
        self.commit()

    def clear_badge(self, gid):
        g = self.layout.group(gid)
        if g and g.get("badge"):
            g["badge"] = 0
            self.layout.save()
            if gid in self.widgets:
                self.widgets[gid].update()

    def request_delete_group(self, gid):
        g = self.layout.group(gid)
        if g is None:
            return
        n = len(g["items"])
        if ask("Delete group?",
               f"Delete the group \"{g['name']}\"?\n\n"
               f"Its {n} item{'s' if n != 1 else ''} will show up on your desktop again, right where "
               "they were. Nothing is deleted from your PC. You can Undo this.",
               yes_text="Delete group", danger=True):
            self.delete_group(gid)

    def delete_group(self, gid):
        g = self.layout.group(gid)
        if g is None:
            return
        self.checkpoint("delete group")
        self.layout.groups.remove(g)
        if self.popup.gid == gid:
            self.popup.hide()
            self.popup.gid = None
        self.sync_hidden()
        self.commit()

    def open_group(self, gid):
        # clicking the same group again while its popup is open (or just closed) = toggle closed
        last_gid, last_t = self.popup.last_closed
        if self.popup.isVisible() and self.popup.gid == gid:
            self.popup.close_animated()
            return
        if last_gid == gid and time.monotonic() - last_t < 0.35:
            return
        w = self.widgets.get(gid)
        anchor = w.glass_rect_global() if w else QRect()
        self.clear_badge(gid)
        self.popup.open_group(gid, anchor)

    # ------------------------------------------------------------------ items
    def handle_drop(self, gid, item, dropped, target=None, tab=None):
        """Something was dropped on a group (tile, panel or popup), maybe right on one of its tabs."""
        if item:
            path, src = item
            if self.layout_locked() and src:
                self.notify("The layout is locked - unlock it in the \u2699 menu to move things around.")
                return
            if tab and src == gid:
                self.move_item_to_tab(gid, path, tab)
            elif target and df.norm(target) != df.norm(path):
                self.make_group_from(path, src, target, gid)
            elif src != gid:
                self.move_item(path, src, gid, tab=tab)
            return
        if dropped:
            files, webs = dropped
            self.add_items(gid, files, webs, tab=tab)

    def add_paths(self, gid, paths_):
        return self.add_items(gid, paths_, [])

    def add_items(self, gid, paths_, webs, tab=None):
        g = self.layout.group(gid)
        if g is None:
            return []
        notes, to_add = [], []
        seen = set()
        for p in paths_:
            p = os.path.normpath(p)
            if not os.path.exists(p):
                notes.append(f"Couldn't find {os.path.basename(p)}.")
                continue
            other = self.layout.group_of(p)
            if other is not None:
                if other["id"] != gid:
                    notes.append(f"\"{icons.display_name(p)}\" is already in \"{other['name']}\".")
                continue
            if df.norm(p) in seen:
                continue
            seen.add(df.norm(p))
            to_add.append({"path": p})
        for url, title in webs:
            other = self.layout.group_of(url)
            if other is not None:
                if other["id"] != gid:
                    notes.append(f"That website is already in \"{other['name']}\".")
                continue
            if df.norm(url) in seen:
                continue
            seen.add(df.norm(url))
            to_add.append({"path": url, "title": (title or icons.domain_of(url))[:80]})
        if to_add:
            self.checkpoint("add items")
            now = datetime.datetime.now().isoformat(timespec="seconds")
            dest_tab = tab if tab and tab_of(g, tab) else g["tab"]     # new things go to the tab you're on
            for it in to_add:
                it["added"] = now
                it["tab"] = dest_tab
                g["items"].append(it)
            g["badge"] = int(g.get("badge") or 0) + len(to_add)
            failed, hid_any = [], False
            statuses, _f = self.sync_hidden()       # also hides a same-named twin on the other desktop
            for it in to_add:
                st = statuses.get(it["path"])
                if self.hide_failed(it["path"]):
                    failed.append(icons.item_name(it))
                hid_any = hid_any or st == "hidden"
            if hid_any and not self._told_about_show_hidden and df.explorer_shows_hidden_files():
                self._told_about_show_hidden = True
                notes.append("Heads-up: your PC shows hidden items, so grouped items stay on the "
                             "desktop but look faded. That's normal!")
            if failed:
                notes.append(", ".join(failed) + " is on the shared Public desktop, which needs admin rights "
                             "to hide, so it's in the group and also stays on the desktop (marked with an "
                             "orange !).")
                log.warning("Could not hide (still on the desktop): %s", ", ".join(failed))
            self.commit()
        if notes:
            self.notify("\n".join(notes))
        return [it["path"] for it in to_add]

    def _take_item(self, gid, path):
        g = self.layout.group(gid)
        if g is None:
            return None
        for i, it in enumerate(g["items"]):
            if df.norm(it["path"]) == df.norm(path):
                return g["items"].pop(i)
        return None

    def move_item(self, path, src, dst, tab=None):
        if self.layout.group(dst) is None or self.layout.group(src) is None:
            return
        self.checkpoint("move item")
        it = self._take_item(src, path)
        if it is None:
            self.undo_stack.pop()
            return
        g = self.layout.group(dst)
        it["tab"] = tab if tab and tab_of(g, tab) else g["tab"]
        g["items"].append(it)
        g["badge"] = int(g.get("badge") or 0) + 1
        self.sync_hidden()
        self.commit()

    def make_group_from(self, a_path, a_gid, b_path, b_gid):
        """Dropped item A onto item B: make a new group holding both (like iOS)."""
        self.checkpoint("make group from two items")
        a = self._take_item(a_gid, a_path) if a_gid else None
        b = self._take_item(b_gid, b_path)
        if a is None or b is None:
            snap = self.undo_stack.pop()
            if snap:
                self.layout.restore(snap[1])
            return
        accent = ACCENTS[len(self.layout.groups) % len(ACCENTS)][1]
        w, h = group_size({"mode": "tile"})
        pos = first_free_left(self.avail(), self.group_rects(), w, h)
        g = new_group("New Group", pos.x(), pos.y(), accent=accent)
        for it in (a, b):
            it["tab"] = g["tab"]
        g["items"] = [b, a]
        g["badge"] = 2
        self.layout.groups.append(g)
        self.sync_hidden()
        self.commit()
        if self.popup.isVisible():
            self.popup.close_animated()
        QTimer.singleShot(60, self.widgets[g["id"]].start_rename)

    def remove_item(self, gid, p):
        g = self.layout.group(gid)
        if g is None:
            return
        if not any(df.norm(it["path"]) == df.norm(p) for it in g["items"]):
            return
        self.checkpoint("remove item")
        self._take_item(gid, p)
        self.sync_hidden()
        self.commit()

    def drag_item(self, source, path, gid):
        """Drag one item. Dropped on a group/tab/dock: handled there. Dropped on the bare
        desktop: it leaves its group and shows on the desktop again (one Undo step)."""
        from .glass import start_item_drag
        if self.layout_locked():
            self.notify("The layout is locked - unlock it in the \u2699 menu to move things around. "
                        "Clicking still opens things.")
            return False
        action, cancelled = start_item_drag(source, path, gid, icons.icon_for(path))
        if action != Qt.IgnoreAction or cancelled:
            return False
        if self._over_our_windows(QCursor.pos()) or not desktop_layer.cursor_over_desktop():
            return False
        return self.drag_out(gid, path)

    def _over_our_windows(self, pt):
        for w in self.all_windows():
            if w is not None and w.isVisible() and w.frameGeometry().contains(pt):
                return True
        return False

    def drag_out(self, gid, path):
        """Take an item out of its group because it was dragged onto the desktop.
        The file stays exactly where it is; only its Hidden flag is cleared (via the ledger)."""
        g = self.layout.group(gid)
        if g is None or not any(df.norm(it["path"]) == df.norm(path) for it in g["items"]):
            return False
        self.checkpoint("drag out of group")
        self._take_item(gid, path)
        self.sync_hidden()
        self.commit()
        log.info("Dragged out of %s: %s", g["name"], path)
        return True

    def launch(self, p):
        if df.is_url(p):
            try:
                if sys.platform == "win32":
                    os.startfile(p)
                else:
                    import webbrowser
                    webbrowser.open(p)
                log.info("Opened website %s", p)
            except OSError as e:
                self.notify(f"Couldn't open that website: {e}")
            return
        if not os.path.exists(p):
            self.notify(f"Couldn't find {p}. It may have been moved or deleted outside Clutter Buster.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(p)
            log.info("Opened %s", p)
        except OSError as e:
            self.notify(f"Windows couldn't open {icons.display_name(p)}: {e.strerror or e}")

    # ------------------------------------------------------------------ favorites
    def favorite_name(self, p):
        g = self.layout.group_of(p)
        if g:
            for it in g["items"]:
                if df.norm(it["path"]) == df.norm(p):
                    return icons.item_name(it)
        return icons.display_name(p)

    def add_favorite(self, p):
        if any(df.norm(f) == df.norm(p) for f in self.layout.favorites):
            self.dock.show_dock()
            return False
        self.checkpoint("add favorite")
        self.layout.favorites = self.layout.favorites + [p]
        self.commit()
        self.place_dock()
        self.dock.show_dock()
        self.dock.hide_timer.start(1500)
        return True

    def remove_favorite(self, p):
        favs = [f for f in self.layout.favorites if df.norm(f) != df.norm(p)]
        if len(favs) == len(self.layout.favorites):
            return
        self.checkpoint("remove favorite")
        self.layout.favorites = favs
        self.commit()
        self.place_dock()

    def handle_favorite_drop(self, item, dropped):
        if item:
            self.add_favorite(item[0])
            return
        if dropped:
            files, webs = dropped
            for p in files:
                if os.path.exists(p):
                    self.add_favorite(os.path.normpath(p))
            for url, _title in webs:
                self.add_favorite(url)

    # ------------------------------------------------------------------ tabs inside groups
    def _refresh_group(self, gid):
        w = self.widgets.get(gid)
        if w is not None:
            w.update()
        if self.popup.isVisible() and self.popup.gid == gid:
            self.popup.refresh()

    def more_tabs_menu(self, gid, widget=None):
        """The '▾' button when a group has more tabs than fit: every tab, pick one."""
        g = self.layout.group(gid)
        if g is None:
            return
        m = QMenu(widget)
        for t in g.get("tabs") or []:
            a = m.addAction(t.get("name") or "Tab")
            a.setCheckable(True)
            a.setChecked(t["id"] == g.get("tab"))
            a.triggered.connect(lambda _=False, tid=t["id"]: self.select_tab(gid, tid))
        m.exec(QCursor.pos())

    def select_tab(self, gid, tid):
        """Switch tab (remembered, not an undo step)."""
        if tid == "more":
            QTimer.singleShot(0, lambda: self.more_tabs_menu(gid, self.widgets.get(gid)))
            return
        g = self.layout.group(gid)
        if g is None or not tab_of(g, tid) or g.get("tab") == tid:
            return
        g["tab"] = tid
        w = self.widgets.get(gid)
        if w is not None:
            w._last_tab, w.page, w._selected = tid, 0, None
        if self.popup.gid == gid:
            self.popup.tab_changed()
        self._refresh_group(gid)
        self.schedule_save()

    def add_tab(self, gid, name=None):
        g = self.layout.group(gid)
        if g is None:
            return None
        self.checkpoint("add tab")
        existing = {t["name"] for t in g["tabs"]}
        if len(g["tabs"]) == 1 and g["tabs"][0]["name"] == "All":
            g["tabs"][0]["name"] = "Main"       # "All" would be confusing once there are two
            existing = {"Main"}
        n = len(g["tabs"]) + 1
        name = name or f"Tab {n}"
        while name in existing:
            n += 1
            name = f"Tab {n}"
        t = new_tab(name)
        g["tabs"].append(t)
        g["tab"] = t["id"]
        self.commit()
        if self.popup.gid == gid:
            self.popup.tab_changed()
        return t["id"]

    def rename_tab(self, gid, tid, name):
        g = self.layout.group(gid)
        t = tab_of(g, tid) if g else None
        name = (name or "").strip()[:40]
        if t is None or not name or name == t["name"]:
            return
        self.checkpoint("rename tab")
        t["name"] = name
        self.commit()

    def move_tab(self, gid, tid, delta):
        g = self.layout.group(gid)
        if g is None:
            return
        ids = [t["id"] for t in g["tabs"]]
        if tid not in ids:
            return
        i = ids.index(tid)
        j = i + delta
        if not 0 <= j < len(ids):
            return
        self.checkpoint("move tab")
        g["tabs"][i], g["tabs"][j] = g["tabs"][j], g["tabs"][i]
        self.commit()

    def set_tab_view(self, gid, tid, view):
        g = self.layout.group(gid)
        t = tab_of(g, tid) if g else None
        if t is None or t.get("view") == view:
            return
        self.checkpoint("tab view")
        t["view"] = view
        w = self.widgets.get(gid)
        if w is not None:
            w.page = 0
        self.commit()
        if self.popup.gid == gid:
            self.popup.tab_changed()

    def delete_tab(self, gid, tid, confirm=True):
        g = self.layout.group(gid)
        t = tab_of(g, tid) if g else None
        if t is None or len(g["tabs"]) < 2:
            return
        rest = [x for x in g["tabs"] if x["id"] != tid]
        n = sum(1 for it in g["items"] if it.get("tab") == tid)
        if confirm and n and not ask("Delete tab?", f"Delete the tab \"{t['name']}\"?\n\nIts {n} item"
                                     f"{'s' if n != 1 else ''} move to \"{rest[0]['name']}\". Nothing is "
                                     "deleted from your PC. You can Undo this.", yes_text="Delete tab"):
            return
        self.checkpoint("delete tab")
        for it in g["items"]:
            if it.get("tab") == tid:
                it["tab"] = rest[0]["id"]
        g["tabs"] = rest
        if g.get("tab") == tid:
            g["tab"] = rest[0]["id"]
        self.commit()
        if self.popup.gid == gid:
            self.popup.tab_changed()

    def move_item_to_tab(self, gid, path, tid):
        g = self.layout.group(gid)
        if g is None or not tab_of(g, tid):
            return
        it = next((x for x in g["items"] if df.norm(x["path"]) == df.norm(path)), None)
        if it is None or it.get("tab") == tid:
            return
        self.checkpoint("move to tab")
        it["tab"] = tid
        self.commit()

    def tab_menu(self, gid, tid, gpos, widget):
        if tid == "more":
            return self.more_tabs_menu(gid, widget)
        g = self.layout.group(gid)
        t = tab_of(g, tid) if g else None
        if t is None:
            return
        ids = [x["id"] for x in g["tabs"]]
        i = ids.index(tid)
        m = QMenu()
        m.addAction("Rename...", lambda: widget.start_tab_rename(tid))
        left = m.addAction("Move left", lambda: self.move_tab(gid, tid, -1))
        left.setEnabled(i > 0)
        right = m.addAction("Move right", lambda: self.move_tab(gid, tid, 1))
        right.setEnabled(i < len(ids) - 1)
        view = m.addMenu("View")
        for key, label in (("icons", "Icons"), ("list", "List (name, date, type)")):
            a = view.addAction(label, lambda k=key: self.set_tab_view(gid, tid, k))
            a.setCheckable(True)
            a.setChecked(t.get("view", "icons") == key)
        m.addAction("+  New tab", lambda: self._new_tab_and_rename(gid, widget))
        m.addSeparator()
        d = m.addAction("Delete tab (items move to the first tab)...", lambda: self.delete_tab(gid, tid))
        d.setEnabled(len(ids) > 1)
        m.exec(gpos)

    def add_tab_from_menu(self, gid, widget):
        g = self.layout.group(gid)
        if g is None:
            return
        if g.get("mode") == "panel":
            self._new_tab_and_rename(gid, widget)
        else:                       # small tile: tabs live in its popup
            if not (self.popup.isVisible() and self.popup.gid == gid):
                self.open_group(gid)
            self._new_tab_and_rename(gid, self.popup)

    def _new_tab_and_rename(self, gid, widget):
        tid = self.add_tab(gid)
        if tid and hasattr(widget, "start_tab_rename"):
            QTimer.singleShot(60, lambda: widget.start_tab_rename(tid))

    # ------------------------------------------------------------------ one group's own settings (gear)
    def fence_settings(self, gid, widget=None):
        from .fence_settings import FenceSettings
        old = getattr(self, "fence_panel", None)
        if old is not None:
            try:
                old.close()
            except RuntimeError:
                pass
        self.fence_panel = FenceSettings(self, gid)
        self.fence_panel.destroyed.connect(lambda *_: setattr(self, "fence_panel", None))
        self.fence_panel.anchor()
        self.fence_panel.show()
        return self.fence_panel

    def set_group_prop(self, gid, key, value, label, burst=False):
        """Set (or clear, with None) one of a group's own settings. One Undo step; slider drags
        merge into one step."""
        g = self.layout.group(gid)
        if g is None or g.get(key) == value:
            return
        if burst:
            self._name_burst(("prop", gid, key), label)
        else:
            self.checkpoint(label)
        if value is None:
            g.pop(key, None)
        else:
            g[key] = value
        self.commit()
        p = getattr(self, "fence_panel", None)
        if p is not None:
            try:
                p.refresh()
            except RuntimeError:
                pass

    # ------------------------------------------------------------------ corner pictures
    def corner_choices(self):
        from . import corners
        return corners.choices()

    def set_corner_picture(self, gid, value):
        """value: "theme" (or None) = the theme's picture, "none", "asset:<name>" or a file path."""
        self.set_group_prop(gid, "corner", None if value in (None, "theme") else value, "corner picture")

    def choose_corner_picture(self, gid, src=None):
        """Right-click > Corner picture > Choose image...: copies the picture into
        %APPDATA%/ClutterBuster/pictures, so moving/deleting the original doesn't matter."""
        from PySide6.QtWidgets import QFileDialog
        from . import corners
        from .glass import info
        if self.layout.group(gid) is None:
            return None
        if src is None:
            dlg = QFileDialog(None, "Choose a corner picture",
                              os.path.join(os.path.expanduser("~"), "Pictures"), corners.IMAGE_FILTER)
            dlg.setFileMode(QFileDialog.ExistingFile)
            dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            if not dlg.exec() or not dlg.selectedFiles():
                return None
            src = dlg.selectedFiles()[0]
        try:
            dest = corners.import_picture(src)
        except OSError as e:
            log.warning("Corner picture %s: %s", src, e)
            info(None, "Corner picture", f"Couldn't use that picture:\n{e}")
            return None
        self.set_group_prop(gid, "corner", dest, "corner picture")
        log.info("Corner picture for %s: %s", gid, dest)
        return dest

    def reset_group_look(self, gid):
        g = self.layout.group(gid)
        keys = ("theme", "per_row", "labels", "transparency", "corner")
        if g is None or not any(k in g for k in keys):
            return
        self.checkpoint("group defaults")
        for k in keys:
            g.pop(k, None)
        self.commit()

    # ------------------------------------------------------------------ name style
    def name_style_dialog(self, gid=None):
        """gid=None: the default for all groups (Settings > Appearance)."""
        from .namestyle_dialog import NameStyleDialog
        dlg = NameStyleDialog(self, gid)
        dlg.show_on_top()
        return dlg

    def set_name_style(self, gid, style):
        """style = dict of overrides, or None/{} to follow the default. One undo step."""
        style = {k: v for k, v in (style or {}).items() if v not in (None, "", 0, "auto") or k == "bold" and v is False}
        if gid is None:
            if (self.ui.get("name_style") or {}) == style:
                return
            self.checkpoint("name style (all groups)")
            self.ui["name_style"] = style
        else:
            g = self.layout.group(gid)
            if g is None or (g.get("name_style") or {}) == style:
                return
            self.checkpoint("name style")
            if style:
                g["name_style"] = style
            else:
                g.pop("name_style", None)
        self.commit()

    NAME_MIN, NAME_MAX = 8, 36

    def _name_burst(self, key, label):
        """Several quick size clicks / wheel steps = ONE undo step."""
        t = getattr(self, "_name_burst_timer", None)
        if t is None:
            t = self._name_burst_timer = QTimer()
            t.setSingleShot(True)
            t.timeout.connect(lambda: setattr(self, "_name_burst_key", None))
        if getattr(self, "_name_burst_key", None) != key:
            self.checkpoint(label)
            self._name_burst_key = key
            self.update_undo_ui()
        t.start(1500)

    def bump_name_size(self, gid, delta):
        """A-/A+ by a group's name, or Ctrl+wheel over it: +-1 pt for this group, live."""
        g = self.layout.group(gid)
        w = self.widgets.get(gid)
        if g is None or w is None:
            return None
        new = max(self.NAME_MIN, min(self.NAME_MAX, w.name_size() + int(delta)))
        if new == (g.get("name_style") or {}).get("size"):
            return new
        self._name_burst(("group", gid), "name size")
        st = dict(g.get("name_style") or {})
        st["size"] = new
        g["name_style"] = st
        w.update()
        if self.popup.gid == gid:
            self.popup.update()
        self.schedule_save()
        return new

    def default_name_size(self):
        return int((self.ui.get("name_style") or {}).get("size") or 11)

    def set_default_name_size(self, size):
        """Gear menu > Name size: the default for every group (a group's own size still wins)."""
        size = max(self.NAME_MIN, min(self.NAME_MAX, int(size)))
        st = dict(self.ui.get("name_style") or {})
        if st.get("size") == size:
            return
        self._name_burst(("default",), "name size (all groups)")
        st["size"] = size
        self.ui["name_style"] = st
        for w in self.widgets.values():
            w.update()
        self.schedule_save()

    # ------------------------------------------------------------------ quick search shortcut
    def search_hotkey(self):
        from . import hotkey
        hk = self.layout.prefs.get("hotkey")
        if isinstance(hk, dict) and hk.get("vk") and hk.get("mods"):
            return {"mods": int(hk["mods"]), "vk": int(hk["vk"]),
                    "text": hk.get("text") or hotkey.describe(hk["mods"], hk["vk"])}
        return dict(hotkey.DEFAULT)

    def pause_hotkey(self, paused):
        """While you record a new shortcut in Settings, the old one is switched off."""
        from . import hotkey
        if self.showcase:
            return
        hotkey.unregister(int(self.search.winId()))
        if not paused:
            self.search.register_hotkey()

    def set_search_hotkey(self, mods, vk, text=None):
        """Use a new quick-search shortcut right away. Returns (ok, message). If Windows says
        another app has it, the old shortcut stays."""
        from . import hotkey
        new = {"mods": int(mods), "vk": int(vk), "text": text or hotkey.describe(mods, vk)}
        old = self.search_hotkey()
        hwnd = int(self.search.winId())
        hotkey.unregister(hwnd)
        if hotkey.register(hwnd, new["mods"], new["vk"]):
            self.layout.prefs["hotkey"] = new
            self.layout.save()
            self.search.hotkey_ok = True
            self.search.update()
            log.info("Quick search shortcut is now %s", new["text"])
            return True, f"Done - press {new['text']} anywhere to search."
        self.search.hotkey_ok = hotkey.register(hwnd, old["mods"], old["vk"])
        self.search.update()
        return False, (f"{new['text']} is already used by another app, so I kept {old['text']}. "
                       "Try another combination.")

    # ------------------------------------------------------------------ the gear menu
    def layout_locked(self):
        return bool(self.layout.prefs.get("locked")) and not self.edit_mode

    def set_locked(self, on):
        self.layout.prefs["locked"] = bool(on)
        self.layout.save()
        for w in self.widgets.values():
            w.update()
        self.tray.refresh_toggles()
        log.info("Layout %s", "locked" if on else "unlocked")

    def set_groups_hidden(self, on):
        """Hide/show every group window. Items inside groups stay hidden on the desktop either way."""
        self.layout.prefs["groups_hidden"] = bool(on)
        self.layout.save()
        if on and self.popup.isVisible():
            self.popup.close_animated()
        self.rebuild_widgets()
        self.tray.refresh_toggles()
        log.info("Groups %s", "hidden" if on else "shown")

    def toggle_groups_hidden(self):
        self.set_groups_hidden(not self.layout.prefs.get("groups_hidden"))

    def tidy_up(self):
        """Snap every group to the 16 px grid without overlaps (one undo step)."""
        if not self.layout.groups:
            return
        self.checkpoint("tidy up")
        placed = []
        av = self.avail()
        for g in sorted(self.layout.groups, key=lambda g: (g["y"], g["x"])):
            w, h = group_size(g)
            pt = snap_rect(g["x"], g["y"], w, h, av, placed)
            g["x"], g["y"] = pt.x(), pt.y()
            placed.append(QRect(pt.x(), pt.y(), w, h))
        self.commit()
        log.info("Tidied up %d group(s)", len(self.layout.groups))

    def show_quick_menu(self, anchor=None):
        from .quickmenu import QuickMenu
        if self.quick_menu is not None and self.quick_menu.isVisible():
            self.quick_menu.close()
            return
        self.quick_menu = QuickMenu(self)
        self.quick_menu.open_at(anchor)
        return self.quick_menu

    def edit_theme(self, name=None):
        """Edit any theme: your own ones in place; a built-in one as a copy."""
        from .theme_maker import ThemeMaker
        name = name or self.theme_name
        start = next((t for t in self.layout.custom_themes if t.get("name") == name), None)
        if start is None:
            start = theme.custom_from_builtin(name)
        self._maker = ThemeMaker(self, start=start)
        av = self.avail()
        self._maker.move(av.center().x() - self._maker.width() // 2, av.center().y() - self._maker.height() // 2)
        self._maker.show_on_top()
        return self._maker

    # ------------------------------------------------------------------ menus
    def group_menu(self, gid, widget, gpos):
        g = self.layout.group(gid)
        if g is None:
            return
        m = QMenu()
        m.addAction("Open", lambda: self.open_group(gid))
        m.addAction("\u270E  Rename", widget.start_rename)          # the same in-place box as the pencil
        if self.permfix_candidates(gid):
            m.addAction("\u26A0  Fix hiding permission...", lambda: self.fix_permissions(gid=gid))
        m.addAction("\u2699  Group settings...", lambda: self.fence_settings(gid, widget))
        m.addAction("Name style...", lambda: self.name_style_dialog(gid))
        m.addAction("+  Add a tab", lambda: self.add_tab_from_menu(gid, widget))
        if self.edit_mode:
            m.addAction("\u2713  Done editing layout", self.exit_edit_mode)
        else:
            m.addAction("\u270E  Edit layout", self.enter_edit_mode)
        acc = m.addMenu("Accent color")
        for name, hexc in ACCENTS:
            a = acc.addAction(swatch(hexc), name, lambda h=hexc: self.set_accent(gid, h))
            a.setCheckable(True)
            a.setChecked((g.get("accent") or "").lower() == hexc.lower())
        acc.addSeparator()
        acc.addAction("Custom color...", lambda: self.pick_custom_accent(gid))
        from . import corners
        cm = m.addMenu("Corner picture")
        cur = g.get("corner") or "theme"
        for label, val in corners.choices():
            if val == "choose":
                cm.addSeparator()
                cm.addAction(label, lambda: self.choose_corner_picture(gid))
                continue
            a = cm.addAction(label, lambda v=val: self.set_corner_picture(gid, v))
            a.setCheckable(True)
            a.setChecked(cur == val)
        if cur not in [v for _l, v in corners.choices()]:
            a = cm.addAction(corners.label_for(cur))
            a.setCheckable(True)
            a.setChecked(True)
        show = m.addMenu("Show as")
        mode = g.get("mode", "tile")
        a1 = show.addAction("Small tile", lambda: self.set_mode(gid, "tile"))
        a1.setCheckable(True)
        a1.setChecked(mode == "tile")
        a2 = show.addAction("Big panel", lambda: self.set_mode(gid, "panel"))
        a2.setCheckable(True)
        a2.setChecked(mode == "panel")
        m.addSeparator()
        m.addAction("Delete group...", lambda: self.request_delete_group(gid))
        m.addSeparator()
        u = m.addAction("Undo " + self.undo_stack.next_label(), self.undo)
        u.setEnabled(self.undo_stack.can_undo())
        m.exec(gpos)

    def item_menu(self, gid, path, gpos, in_popup=False):
        m = QMenu()

        def open_it():
            if in_popup:
                self.popup.close_animated()
            self.launch(path)

        m.addAction("Open", open_it)
        if any(df.norm(f) == df.norm(path) for f in self.layout.favorites):
            m.addAction("Remove from favorites", lambda: self.remove_favorite(path))
        else:
            m.addAction("\u2605  Add to favorites", lambda: self.add_favorite(path))
        m.addSeparator()
        label = "Remove from group" if df.is_url(path) else "Remove from group (show on desktop again)"
        m.addAction(label, lambda: self.remove_item(gid, path))
        m.exec(gpos)

    # ------------------------------------------------------------------ search
    def open_quick_search(self, text=""):
        if self.quick.isVisible():
            self.quick.activateWindow()
            return
        if self.search.wedge:             # tucked in a corner: quick search opens top-centre
            av = self.avail()
            self.quick.open(av.center().x(), av.top() + 18, text)
            return
        sr = self.search.search_rect()
        top = self.search.mapToGlobal(sr.topLeft().toPoint()).y()
        self.quick.open(self.search.search_global_center_x(), top, text)

    def search_entries(self):
        """(name, path, icon, where) for group items, favorites and desktop items. No web results."""
        out, seen = [], set()
        for g in self.layout.groups:
            for it in g["items"]:
                p = it["path"]
                seen.add(df.norm(p))
                out.append((icons.item_name(it), p, icons.icon_for(p),
                            ("Website \u00B7 " if df.is_url(p) else "") + g["name"]))
        for p in self.layout.favorites:
            if df.norm(p) not in seen:
                seen.add(df.norm(p))
                out.append((self.favorite_name(p), p, icons.icon_for(p), "Favorites"))
        for p in df.list_desktop_items():
            if df.norm(p) in seen:
                continue
            if df.is_hidden(p):  # hidden by you, leave it out
                continue
            out.append((icons.display_name(p), p, icons.icon_for(p), "Desktop"))
        out.sort(key=lambda e: e[0].lower())
        return out

    # ------------------------------------------------------------------ Windows integration (stage 4)
    def setup_windows_integration(self):
        prefs = self.layout.prefs
        if "autostart" not in prefs:          # first run of stage 4: on by default
            prefs["autostart"] = True
            self.layout.save()
        integration.set_autostart(bool(prefs["autostart"]))   # also refreshes the path if the folder moved
        icon = paths.path("broom.ico")
        try:
            if not os.path.exists(icon):
                broom_icon().pixmap(64, 64).save(icon, "ICO")
        except Exception:
            log.exception("Could not save broom.ico")
        integration.register_uninstall(__version__, icon)

    def set_autostart(self, on):
        self.layout.prefs["autostart"] = bool(on)
        self.layout.save()
        ok = integration.set_autostart(bool(on))
        log.info("Start with Windows: %s%s", "on" if on else "off", "" if ok else " (registry write failed)")
        if self.settings_win is not None:
            self.settings_win.refresh_autostart()

    # ------------------------------------------------------------------ automatically do it (stage 4)
    def auto_organize(self):
        """Open the review window with suggestions. Nothing changes until Apply."""
        from .organize_dialog import OrganizeDialog
        if self.edit_mode:
            self.exit_edit_mode()
        if self.organize_win is not None:
            self.organize_win.close()
        plan = organize.suggest(self.layout)
        log.info("Automatically do it: %d suggested group(s), %d item(s)",
                 len(plan), sum(len(s["items"]) for s in plan))
        self.organize_win = OrganizeDialog(self, plan)
        av = self.avail()
        w = self.organize_win
        w.move(av.center().x() - w.width() // 2, max(av.top(), av.center().y() - w.height() // 2))
        w.show_on_top()
        return w

    def apply_organize(self, plan):
        """Do what the review window says - as ONE undo step. Returns how many items were grouped."""
        chosen = []
        for s in plan:
            if not s.get("enabled"):
                continue
            ps = [it["path"] for it in s.get("items", []) if it.get("on")]
            if ps:
                chosen.append((s, ps))
        if not chosen:
            return 0
        self.checkpoint("automatically do it")
        now = datetime.datetime.now().isoformat(timespec="seconds")
        total, failed, made = 0, [], []
        for s, ps in chosen:
            g = self.layout.group(s["gid"]) if s.get("gid") else None
            if g is None:
                w, h = group_size({"mode": "tile"})
                pos = first_free_left(self.avail(), self.group_rects(), w, h)
                g = new_group((s.get("name") or "New Group")[:60], pos.x(), pos.y(),
                              accent=s.get("accent"), mode="tile")
                self.layout.groups.append(g)
                made.append(g["name"])
            added = []
            for p in ps:
                if not os.path.exists(p) or self.layout.group_of(p) is not None:
                    continue
                g["items"].append({"path": p, "added": now})
                added.append(p)
            g["badge"] = int(g.get("badge") or 0) + len(added)
            for p in added:
                if self.hider.hide(p, g["id"]) == "failed":   # ledger is written before hiding
                    failed.append(icons.display_name(p))
            total += len(added)
        self.sync_hidden()
        self.commit()
        log.info("Automatically do it: grouped %d item(s); new groups: %s", total, ", ".join(made) or "none")
        msg = f"Grouped {total} item{'s' if total != 1 else ''}. Click Undo to put it all back."
        if failed:
            msg += "\n" + ", ".join(failed) + " couldn't be hidden, so they're in a group and also stay on the desktop."
        self.notify(msg)
        return total

    # ------------------------------------------------------------------ undo
    def undo(self):
        if self.edit_mode:
            # undo inside Edit layout = put everything back the way it was when editing started
            snap = self._edit_snap
            self.layout.restore(snap)
            self._after_restore()
            log.info("Undid the changes of this Edit layout session")
            return
        item = self.undo_stack.pop()
        if item is None:
            self.notify("Nothing to undo.")
            return
        label, snap = item
        self.redo_stack.append((label, self.layout.snapshot()))
        self.layout.restore(snap)
        self._after_restore()
        log.info("Undid: %s", label)

    def can_redo(self):
        return bool(self.redo_stack) and not self.edit_mode

    def redo(self):
        if not self.can_redo():
            self.notify("Nothing to redo.")
            return
        label, snap = self.redo_stack.pop()
        self.undo_stack.push(label, self.layout.snapshot())
        self.layout.restore(snap)
        self._after_restore()
        log.info("Redid: %s", label)

    def _after_restore(self):
        self.sync_hidden()
        self.commit()
        self.place_bars()
        self.apply_theme()
        if self.toolbar is not None:
            self.toolbar.refresh_from_ui()

    # ------------------------------------------------------------------ tray / lifecycle
    def show_settings(self, section=0):
        from .settings import SettingsWindow
        if self.settings_win is None:
            self.settings_win = SettingsWindow(self)
            av = self.avail()
            self.settings_win.move(av.center().x() - self.settings_win.width() // 2 - 260,
                                   av.center().y() - self.settings_win.height() // 2)
        self.settings_win.nav.setCurrentRow(section)
        self.settings_win.show_on_top()
        return self.settings_win

    def edit_layout(self):
        self.enter_edit_mode()

    def attach_server(self, server):
        self._server = server
        server.newConnection.connect(self._on_ipc)

    def _on_ipc(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            sock.waitForReadyRead(500)
            cmd = bytes(sock.readAll()).decode("utf-8", "ignore").strip()
            log.info("Message from another copy: %r", cmd)
            sock.write(b"ok\n")
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            if cmd == "quit":
                QTimer.singleShot(50, self.quit)
            elif cmd == "search":
                QTimer.singleShot(0, self.open_quick_search)
            elif cmd == "rehide":
                QTimer.singleShot(0, self.rehide)
            elif cmd == "uninstall":
                QTimer.singleShot(0, self.request_remove)
            elif cmd.startswith("open:"):
                name = cmd[5:].strip().lower()
                g = next((x for x in self.layout.groups if x["name"].strip().lower() == name), None)
                if g is not None:
                    QTimer.singleShot(0, lambda gid=g["id"]: self.open_group(gid))
            elif cmd == "closepopup":
                QTimer.singleShot(0, self.popup.close_animated)

    def rehide(self):
        """Try again to hide grouped items that could not be hidden before
        (e.g. Public Desktop shortcuts after you were given permission)."""
        self.hider.failed.clear()
        statuses, failed = self.sync_hidden()
        self.commit()
        log.info("Re-hide: %d hidden, %d still could not be hidden",
                 sum(1 for s in statuses.values() if s == "hidden"), len(failed))
        self.write_status()

    def restore_desktop(self):
        """Show every item the app hid. Safe to call many times."""
        self.hider.unhide_all()

    def quit(self):
        self.restore_desktop()
        log.info("Quit: desktop restored")
        self.app.quit()

    def on_about_to_quit(self):
        from . import hotkey
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.layout.save()
        hotkey.unregister(int(self.search.winId()))
        if not self.removed:
            self.restore_desktop()
            try:
                os.remove(paths.path("app.pid"))
            except OSError:
                pass
        self.tray.hide()

    def request_remove(self):
        """The one confirmation (with the unticked 'also delete the program folder' box)."""
        if self.edit_mode:
            self.exit_edit_mode()
        go, delete_folder = removal.confirm()
        if go:
            self.remove_everything(delete_folder)

    def remove_everything(self, delete_folder=False, wait_pid=None):
        if self.save_timer.isActive():
            self.save_timer.stop()
        ok, msg = removal.remove_all(self.hider, delete_folder, wait_pid)
        if not ok:
            QMessageBox.warning(None, "Clutter Buster", msg)
            return False
        self.removed = True
        self.tray.hide()
        self.app.quit()
        return True


def standalone_uninstall(app):
    """main.py --uninstall when the app isn't running (e.g. from Settings > Apps)."""
    go, delete_folder = removal.confirm()
    if not go:
        return 1
    hider = Hider(Ledger())
    ok, msg = removal.remove_all(hider, delete_folder)
    if not ok:
        QMessageBox.warning(None, "Clutter Buster", msg)
        return 2
    return 0


def send_command(cmd, showcase=False, wait_ms=1500):
    """Talk to an already-running Clutter Buster. Returns True if one answered."""
    sock = QLocalSocket()
    sock.connectToServer(server_name(showcase))
    if not sock.waitForConnected(wait_ms):
        return False
    sock.write((cmd + "\n").encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(wait_ms)
    sock.waitForReadyRead(wait_ms)
    sock.disconnectFromServer()
    return True


def start_server(showcase=False):
    name = server_name(showcase)
    server = QLocalServer()
    if not server.listen(name):
        QLocalServer.removeServer(name)
        server.listen(name)
    return server


def run(argv):
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName("Clutter Buster")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(broom_icon())
    if "--quit" in argv:
        # ask the running copy to quit nicely (it shows everything on the desktop again)
        ok = send_command("quit")
        log.info("--quit: %s", "sent" if ok else "Clutter Buster was not running")
        return 0 if ok else 3
    if "--open-group" in argv:
        # open one group's popup (used for screenshots); nothing else changes
        i = argv.index("--open-group")
        ok = len(argv) > i + 1 and send_command("open:" + argv[i + 1])
        return 0 if ok else 3
    if "--close-popup" in argv:
        return 0 if send_command("closepopup") else 3
    if "--rehide" in argv:
        # ask the running copy to try hiding grouped items that failed before
        ok = send_command("rehide")
        log.info("--rehide: %s", "sent" if ok else "Clutter Buster was not running")
        return 0 if ok else 3
    if "--uninstall" in argv:
        # from Windows Settings > Apps (or by hand): let the running copy handle it, else do it here
        if send_command("uninstall"):
            log.info("--uninstall: handed to the running copy")
            return 0
        return standalone_uninstall(app)
    if send_command("search", wait_ms=300):
        log.info("Second copy started; Clutter Buster is already running, so this one exits.")
        return 0
    server = start_server()
    controller = Controller(app)
    controller.attach_server(server)
    app._cb_controller = controller
    rc = app.exec()
    # Everything is saved and the desktop restored by now (aboutToQuit). Leave right away instead
    # of letting Python tear the Qt windows down one by one, which can crash on the way out.
    logging.shutdown()
    os._exit(rc)
