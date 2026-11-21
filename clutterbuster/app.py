"""The brain of Clutter Buster: keeps groups, hiding, undo, favorites and all the windows in sync."""
import datetime
import logging
import os
import shutil
import sys
import time

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QColorDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, desktop_files as df, desktop_layer, icons, paths, sounds, theme
from .dock import Dock
from .glass import ask
from .group_widget import GroupWidget, first_free_left, group_size, min_size, snap_rect
from .ledger import Hider, Ledger
from .popup import GroupPopup
from .quicksearch import QuickSearch
from .searchbar import ActionBar, SearchBar
from .store import Layout, UndoStack, new_group
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
        self.widgets = {}
        self._told_about_show_hidden = False
        self.edit_mode = False
        self._edit_snap = None
        self._appearance_ckpt = False
        self._covered = False
        self._last_light = theme.windows_prefers_light()
        self.settings_win = None
        self.toolbar = None
        self.theme_name = ""
        prefs = self.layout.prefs
        sounds.SETTINGS.update(on=bool(prefs["sounds"]), volume=int(prefs["volume"]))
        sounds.ensure()
        self.apply_theme(repaint=False)

        # 1) Make the desktop match the saved groups (un-hide leftovers, hide grouped items)
        self.sync_hidden()

        # 2) Windows
        self.search = SearchBar(self)
        self.actions = ActionBar(self)
        self.dock = Dock(self)
        self.place_bars()
        self.search.show()
        self.actions.show()
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

        # 3) Ctrl+Space everywhere (no Windows key needed)
        if not showcase:
            if not self.search.register_hotkey():
                self.notify("Ctrl+Space is already used by another app, so that shortcut is off. "
                            "Click the search bar at the top instead.")
            self.search.update()

        # Re-check the desktop layer now and then (e.g. after "Show desktop").
        self.layer_timer = QTimer()
        self.layer_timer.timeout.connect(self.reassert_layer)
        self.layer_timer.start(2500)

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
        self.esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self.search)
        self.esc_shortcut.setContext(Qt.ApplicationShortcut)
        self.esc_shortcut.setEnabled(False)
        self.esc_shortcut.activated.connect(self._on_escape)
        self.apply_dock_mode()
        self.update_glow_timer()

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
        sr = self.search.search_rect()
        cx = self.search.x() + sr.center().x()
        self.dock.place(cx, self.search.y() + self.search.height() - 4)

    def _clamp_pos(self, w, pos):
        av = self.avail()
        x = min(max(int(pos[0]), av.left()), av.right() - w.width() + 1)
        y = min(max(int(pos[1]), av.top()), av.bottom() - w.height() + 1)
        return x, y

    def place_bars(self):
        """Search bar, New Group/Undo buttons and dock: saved spots, or the defaults."""
        av = self.avail()
        pos = self.ui.get("search_pos") or self.search.default_pos(av)
        self.search.move(*self._clamp_pos(self.search, pos))
        pos = self.ui.get("actions_pos") or (self.search.x() + self.search.width() - 10, self.search.y())
        self.actions.move(*self._clamp_pos(self.actions, pos))
        self.place_dock()

    def bar_moved(self, key, widget, pt):
        """Edit layout: the search bar, the buttons or the dock was dragged somewhere."""
        if key == "dock_pos":
            x, y = self._clamp_pos(widget, (pt.x(), pt.y()))
            self.ui[key] = [x + widget.width() // 2, y]
        else:
            self.ui[key] = list(self._clamp_pos(widget, (pt.x(), pt.y())))
        self.place_bars()
        self.schedule_save()

    def schedule_save(self):
        self.save_timer.start(600)

    # ------------------------------------------------------------------ look & themes
    def all_windows(self):
        out = [self.search, self.actions, self.dock, self.popup, self.quick, *self.widgets.values()]
        out += [w for w in (self.toolbar, self.settings_win) if w is not None]
        return [w for w in out if w is not None]

    def apply_theme(self, repaint=True):
        prefs = self.layout.prefs
        self.theme_name = theme.resolve(prefs.get("theme", theme.AUTO), self.layout.custom_themes)
        theme.apply(self.theme_name, self.ui, self.layout.custom_themes)
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
        self.apply_theme()
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
        if confirm and not ask("Delete theme?", f"Delete your theme \"{name}\"?\n\nThis can't be undone.",
                               yes_text="Delete theme", danger=True):
            return False
        self.layout.extra["custom_themes"] = [t for t in themes if t.get("name") != name]
        if self.layout.prefs.get("theme") == name:
            self.layout.prefs["theme"] = theme.AUTO
        self.layout.save()
        self.apply_theme()
        return True

    def set_pref(self, key, value):
        self.layout.prefs[key] = value
        if key == "dock_autohide":
            self.apply_dock_mode()
        elif key in ("sounds", "volume"):
            sounds.SETTINGS.update(on=bool(self.layout.prefs["sounds"]), volume=int(self.layout.prefs["volume"]))
            if key == "volume":
                sounds.ensure()
        self.schedule_save()

    def apply_dock_mode(self):
        pinned = self.edit_mode or not self.layout.prefs.get("dock_autohide", True) or self.showcase
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
        out.append(QRect(self.search.x(), self.search.y(), self.search.width(), self.search.height() + 90))
        out.append(self.actions.geometry())
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
            }
            paths.atomic_write_json(paths.status_file(), status)
        except Exception:
            log.exception("Could not write status.json")

    def reassert_layer(self):
        for w in [self.search, self.actions, self.dock, *self.widgets.values()]:
            w.send_to_desktop_layer()

    # ------------------------------------------------------------------ syncing
    def sync_hidden(self):
        statuses = self.hider.sync(self.layout.wanted_hidden())
        return statuses, [p for p, s in statuses.items() if s == "failed"]

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
        for g in self.layout.groups:
            w = self.widgets.get(g["id"])
            if w is None:
                w = GroupWidget(self, g["id"])
                self.widgets[g["id"]] = w
            gw, gh = group_size(g)
            gw, gh = min(gw, av.width()), min(gh, av.height())
            x = min(max(g["x"], av.left()), av.right() - gw)
            y = min(max(g["y"], av.top()), av.bottom() - gh)
            w.setGeometry(x, y, gw, gh)
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

    def move_group(self, gid, x, y):
        g = self.layout.group(gid)
        if g is None:
            return
        w, h = group_size(g)
        pt = snap_rect(x, y, w, h, self.avail(), self.group_rects(exclude=gid))
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
        c = QColorDialog.getColor(QColor(g.get("accent") or "#0A84FF"), None, f"Accent color for {g['name']}")
        if c.isValid():
            self.set_accent(gid, c.name())

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
    def handle_drop(self, gid, item, dropped, target=None):
        """Something was dropped on a group (tile, panel or popup)."""
        if item:
            path, src = item
            if target and df.norm(target) != df.norm(path):
                self.make_group_from(path, src, target, gid)
            elif src != gid:
                self.move_item(path, src, gid)
            return
        if dropped:
            files, webs = dropped
            self.add_items(gid, files, webs)

    def add_paths(self, gid, paths_):
        return self.add_items(gid, paths_, [])

    def add_items(self, gid, paths_, webs):
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
            for it in to_add:
                it["added"] = now
                g["items"].append(it)
            g["badge"] = int(g.get("badge") or 0) + len(to_add)
            failed, hid_any = [], False
            for it in to_add:
                st = self.hider.hide(it["path"], gid)
                if st == "failed":
                    failed.append(icons.item_name(it))
                hid_any = hid_any or st == "hidden"
            if hid_any and not self._told_about_show_hidden and df.explorer_shows_hidden_files():
                self._told_about_show_hidden = True
                notes.append("Heads-up: your PC shows hidden items, so grouped items stay on the "
                             "desktop but look faded. That's normal!")
            if failed:
                notes.append(", ".join(failed) + " is on the shared Public desktop, which needs admin rights "
                             "to hide, so it's in the group and also stays on the desktop.")
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

    def move_item(self, path, src, dst):
        if self.layout.group(dst) is None or self.layout.group(src) is None:
            return
        self.checkpoint("move item")
        it = self._take_item(src, path)
        if it is None:
            self.undo_stack.pop()
            return
        g = self.layout.group(dst)
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

    # ------------------------------------------------------------------ menus
    def group_menu(self, gid, widget, gpos):
        g = self.layout.group(gid)
        if g is None:
            return
        m = QMenu()
        m.addAction("Open", lambda: self.open_group(gid))
        m.addAction("Rename...", widget.start_rename)
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
        self.layout.restore(snap)
        self._after_restore()
        log.info("Undid: %s", label)

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

    def rehide(self):
        """Try again to hide grouped items that could not be hidden before
        (e.g. Public Desktop shortcuts after you were given permission)."""
        self.hider.failed.clear()
        statuses, failed = self.sync_hidden()
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
        if not ask("Remove Clutter Buster?",
                   "This will:\n\n"
                   "\u2022 show every grouped item on your desktop again\n"
                   "\u2022 turn off start-with-Windows\n"
                   "\u2022 delete Clutter Buster's settings and groups\n"
                   "\u2022 close the app\n\n"
                   "None of your files, shortcuts or folders are deleted or moved.",
                   yes_text="Remove Clutter Buster", danger=True):
            return
        self.remove_everything()

    def remove_everything(self):
        self.restore_desktop()
        if self.ledger.hidden:
            QMessageBox.warning(None, "Clutter Buster",
                                "Some items could not be shown again, so I stopped before deleting anything.\n"
                                "Details are in " + paths.error_log())
            return
        remove_startup_entry()
        self.removed = True
        log.info("Remove Clutter Buster: desktop restored, deleting app data")
        paths.close_logging()
        shutil.rmtree(paths.app_dir(), ignore_errors=True)
        self.tray.hide()
        self.app.quit()


def remove_startup_entry():
    """Turn off start-with-Windows (not added until a later stage, but be thorough)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
            try:
                winreg.DeleteValue(k, "ClutterBuster")
            except FileNotFoundError:
                pass
    except OSError:
        pass


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
    if "--rehide" in argv:
        # ask the running copy to try hiding grouped items that failed before
        ok = send_command("rehide")
        log.info("--rehide: %s", "sent" if ok else "Clutter Buster was not running")
        return 0 if ok else 3
    if send_command("search", wait_ms=300):
        log.info("Second copy started; Clutter Buster is already running, so this one exits.")
        return 0
    server = start_server()
    controller = Controller(app)
    controller.attach_server(server)
    app._cb_controller = controller
    return app.exec()
