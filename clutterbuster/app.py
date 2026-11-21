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

from . import __version__, desktop_files as df, icons, paths, sounds
from .dock import Dock
from .glass import ask
from .group_widget import GroupWidget, first_free_left, group_size, min_size, snap_rect
from .ledger import Hider, Ledger
from .popup import GroupPopup
from .quicksearch import QuickSearch
from .searchbar import SearchBar
from .store import Layout, UndoStack, new_group
from .theme import ACCENTS
from .tray import SettingsDialog, Tray, broom_icon

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
        sounds.ensure()

        # 1) Make the desktop match the saved groups (un-hide leftovers, hide grouped items)
        self.sync_hidden()

        # 2) Windows
        self.search = SearchBar(self)
        self.search.place(self.avail())
        self.search.show()
        self.dock = Dock(self)
        self.place_dock()
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

    def place_dock(self):
        sr = self.search.search_rect()
        cx = self.search.x() + sr.center().x()
        self.dock.place(cx, self.search.y() + self.search.height() - 4)

    def group_rects(self, exclude=None):
        out = []
        for g in self.layout.groups:
            if g["id"] == exclude:
                continue
            w, h = group_size(g)
            out.append(QRect(g["x"], g["y"], w, h))
        # keep the search bar + dock area free too
        out.append(QRect(self.search.x(), self.search.y(), self.search.width(), self.search.height() + 90))
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
        return statuses, [p for p, s in statuses.items() if s == "failed"]

    def commit(self, undoable=True):
        """Save, back up, and refresh every window after a change."""
        self.layout.save()
        self.rebuild_widgets()
        self.popup.refresh()
        self.dock.refresh()
        self.update_undo_ui()

    def checkpoint(self, label):
        self.undo_stack.push(label, self.layout.snapshot())

    def update_undo_ui(self):
        en, label = self.undo_stack.can_undo(), self.undo_stack.next_label()
        self.search.update_undo(en, label)
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
        item = self.undo_stack.pop()
        if item is None:
            self.notify("Nothing to undo.")
            return
        label, snap = item
        self.layout.restore(snap)
        self.sync_hidden()
        self.commit()
        self.place_dock()
        log.info("Undid: %s", label)

    # ------------------------------------------------------------------ tray / lifecycle
    def show_settings(self):
        self._settings = SettingsDialog(self)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def edit_layout(self):
        box = QMessageBox(QMessageBox.Information, "Edit layout",
                          "Full edit mode (sliders, moving the search bar) arrives in stage 3.\n\n"
                          "Already working: drag a group to move it, drag its edges or corners to resize it, "
                          "and right-click it for colors and Small tile / Big panel.")
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.exec()

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
