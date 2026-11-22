"""Your groups (layout.json), automatic backups, and the Undo history.

A group only stores the PATHS of its items. The items themselves never move.
"""
import copy
import datetime
import glob
import logging
import os
import shutil
import uuid

from . import desktop_files as df
from . import paths

log = logging.getLogger("cb")
MAX_BACKUPS = 20
MAX_UNDO = 100


# ------------------------------------------------------------------ tabs inside groups
def new_tab(name="All", view="icons"):
    return {"id": "t" + uuid.uuid4().hex[:7], "name": name, "view": view}


def ensure_tabs(g):
    """Every group has at least one tab; every item belongs to one of its tabs (unknown or
    missing -> the first tab); the remembered tab exists. Returns True if anything changed."""
    changed = False
    tabs = g.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        g["tabs"] = [new_tab()]
        changed = True
    for t in g["tabs"]:
        if t.get("view") not in ("icons", "list"):
            t["view"] = "icons"
            changed = True
    ids = [t["id"] for t in g["tabs"]]
    for it in g.get("items", []):
        if it.get("tab") not in ids:
            it["tab"] = ids[0]
            changed = True
    if g.get("tab") not in ids:
        g["tab"] = ids[0]
        changed = True
    return changed


def tab_of(g, tab_id):
    return next((t for t in g.get("tabs", []) if t["id"] == tab_id), None)


def current_tab(g):
    ensure_tabs(g)
    return tab_of(g, g["tab"])


def tab_indices(g, tab_id=None):
    """Indexes (into g["items"]) of the items in one tab (default: the selected tab)."""
    ensure_tabs(g)
    tid = tab_id or g["tab"]
    return [i for i, it in enumerate(g["items"]) if it.get("tab") == tid]


def new_group(name, x, y, accent=None, mode="tile"):
    t = new_tab()
    return {
        "tabs": [t],           # tabs inside the group (one tab = no tab bar)
        "tab": t["id"],        # the tab you looked at last
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "x": int(x), "y": int(y),
        "mode": mode,          # "tile" (small, iOS-like) or "panel" (big, Fences-like)
        "accent": accent,      # e.g. "#0A84FF"
        "tile_size": None,     # [w, h] after you resize the small tile
        "panel_size": None,    # [w, h] after you resize the big panel
        "badge": 0,            # how many new items since you last opened it
        "items": [],           # [{"path": ..., "added": ...}]
    }


class Layout:
    def __init__(self):
        data = paths.read_json(paths.layout_file(), {"version": 1, "groups": []})
        self.groups = data.get("groups", []) if isinstance(data, dict) else []
        self.extra = {k: v for k, v in (data.items() if isinstance(data, dict) else []) if k not in ("version", "groups")}
        self._migrate_tabs()

    def _migrate_tabs(self):
        """Groups from before tabs: keep a copy of layout.json first, then give each group one tab."""
        old = [g for g in self.groups if not g.get("tabs")]
        if not old:
            for g in self.groups:
                ensure_tabs(g)
            return
        src = paths.layout_file()
        if os.path.exists(src):
            try:
                os.makedirs(paths.backups_dir(), exist_ok=True)
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy2(src, os.path.join(paths.backups_dir(), f"before-tabs-{stamp}.json"))
            except OSError:
                log.exception("Could not back up layout.json before adding tabs - leaving it as it is")
                for g in self.groups:
                    ensure_tabs(g)     # in memory only
                return
        for g in self.groups:
            ensure_tabs(g)
        if os.path.exists(src):
            self.save()
            log.info("Added tabs to %d group(s) (copy of the old layout kept in backups)", len(old))

    def save(self):
        data = {"version": 1, "groups": self.groups}
        data.update(self.extra)
        paths.atomic_write_json(paths.layout_file(), data)
        self._backup()

    def _backup(self):
        try:
            os.makedirs(paths.backups_dir(), exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            shutil.copy2(paths.layout_file(), os.path.join(paths.backups_dir(), f"layout-{stamp}.json"))
            old = sorted(glob.glob(os.path.join(paths.backups_dir(), "layout-*.json")))
            for f in old[:-MAX_BACKUPS]:
                os.remove(f)  # only ever removes the app's OWN old backup copies
        except OSError:
            log.exception("Layout backup failed")

    def group(self, gid):
        return next((g for g in self.groups if g["id"] == gid), None)

    def group_of(self, p):
        key = df.norm(p)
        for g in self.groups:
            for it in g["items"]:
                if df.norm(it["path"]) == key:
                    return g
        return None

    def wanted_hidden(self):
        """{path: group_id} for every item that is in a group - plus its "twin": a shortcut with
        the very same name on your other desktop (your own vs the shared Public one). Windows
        shows both on one desktop, so hiding only one copy would leave it looking un-hidden."""
        out = {it["path"]: g["id"] for g in self.groups for it in g["items"] if not df.is_url(it["path"])}
        try:
            dirs = df.desktop_dirs()
        except Exception:
            dirs = []
        if len(dirs) > 1:
            dnorm = {df.norm(d): d for d in dirs}
            for p, gid in list(out.items()):
                home = df.norm(os.path.dirname(p))
                if home not in dnorm:
                    continue
                for d in dirs:
                    if df.norm(d) == home:
                        continue
                    twin = os.path.join(d, os.path.basename(p))
                    if twin not in out and os.path.lexists(twin):
                        out[twin] = gid
        return out

    @property
    def favorites(self):
        """Paths in the favorites dock. References only - favorites never hide anything."""
        return self.extra.setdefault("favorites", [])

    @favorites.setter
    def favorites(self, value):
        self.extra["favorites"] = list(value)

    @property
    def ui(self):
        """Layout look: bar/dock positions, popup size and the four sliders. Part of Undo."""
        return self.extra.setdefault("ui", {})

    @property
    def prefs(self):
        """Settings that are not part of Undo: theme choice, dock auto-hide, sounds."""
        p = self.extra.setdefault("prefs", {})
        for k, v in (("theme", "auto"), ("dock_autohide", False), ("sounds", True), ("volume", 50),
                     ("locked", False), ("groups_hidden", False), ("auto_fix_perms", True),
                     ("panel_labels", "auto"), ("snap_groups", True)):
            p.setdefault(k, v)
        if not p.get("dock_v5"):
            # v0.5: the dock stays visible now (Brian asked). Auto-hide is still in Settings > Dock.
            p["dock_autohide"] = False
            p["dock_v5"] = True
        return p

    @property
    def custom_themes(self):
        return self.extra.setdefault("custom_themes", [])

    def snapshot(self):
        return copy.deepcopy({"groups": self.groups, "favorites": self.favorites, "ui": self.ui,
                              "custom_themes": self.custom_themes, "theme": self.prefs.get("theme")})

    def restore(self, snap):
        if isinstance(snap, list):  # stage 1 style snapshot
            snap = {"groups": snap, "favorites": self.favorites}
        snap = copy.deepcopy(snap)
        self.groups = snap["groups"]
        for g in self.groups:
            ensure_tabs(g)
        self.favorites = snap.get("favorites", [])
        if "ui" in snap:
            self.extra["ui"] = snap["ui"]
        if "custom_themes" in snap:
            self.extra["custom_themes"] = snap["custom_themes"]
        if snap.get("theme"):
            self.prefs["theme"] = snap["theme"]


class UndoStack:
    def __init__(self):
        self._items = []

    def push(self, label, snap):
        self._items.append((label, snap))
        del self._items[:-MAX_UNDO]

    def pop(self):
        return self._items.pop() if self._items else None

    def can_undo(self):
        return bool(self._items)

    def next_label(self):
        return self._items[-1][0] if self._items else ""
