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


def new_group(name, x, y, accent=None, mode="tile"):
    return {
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
        """{path: group_id} for every item that is in a group."""
        return {it["path"]: g["id"] for g in self.groups for it in g["items"] if not df.is_url(it["path"])}

    @property
    def favorites(self):
        """Paths in the favorites dock. References only - favorites never hide anything."""
        return self.extra.setdefault("favorites", [])

    @favorites.setter
    def favorites(self, value):
        self.extra["favorites"] = list(value)

    def snapshot(self):
        return copy.deepcopy({"groups": self.groups, "favorites": self.favorites})

    def restore(self, snap):
        if isinstance(snap, list):  # stage 1 style snapshot
            snap = {"groups": snap, "favorites": self.favorites}
        snap = copy.deepcopy(snap)
        self.groups = snap["groups"]
        self.favorites = snap.get("favorites", [])


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
