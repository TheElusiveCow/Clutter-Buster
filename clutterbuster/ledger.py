"""The ledger: a written list of every desktop item Clutter Buster has hidden.

Rule: an item is written into the ledger BEFORE it gets hidden, and the app
only ever un-hides items that are in the ledger. Things you hid yourself are
never in the ledger, so the app never touches them.
"""
import datetime
import logging
import os

from . import desktop_files as df
from . import paths

log = logging.getLogger("cb")


class Ledger:
    def __init__(self):
        data = paths.read_json(paths.ledger_file(), {"version": 1, "hidden": {}})
        self.hidden = data.get("hidden", {}) if isinstance(data, dict) else {}

    def save(self):
        paths.atomic_write_json(paths.ledger_file(), {"version": 1, "hidden": self.hidden})

    def has(self, p):
        return df.norm(p) in self.hidden

    def add(self, p, group_id):
        self.hidden[df.norm(p)] = {"path": p, "group": group_id,
                                   "hidden_at": datetime.datetime.now().isoformat(timespec="seconds")}
        self.save()

    def remove(self, p):
        if self.hidden.pop(df.norm(p), None) is not None:
            self.save()

    def paths(self):
        return [v["path"] for v in self.hidden.values()]


class Hider:
    """Hides / un-hides desktop items, always keeping the ledger up to date."""

    def __init__(self, ledger):
        self.ledger = ledger
        self.failed = set()  # items we could not hide (e.g. Public Desktop needs admin)

    def hide(self, p, group_id):
        """Returns one of: hidden, pre-hidden, not-on-desktop, website, missing, failed."""
        if df.is_url(p):
            return "website"  # websites dragged from a browser aren't files: nothing to hide
        if not os.path.exists(p):
            return "missing"
        if not df.is_on_desktop(p):
            return "not-on-desktop"  # e.g. a file from Documents: grouped, but never hidden
        if self.ledger.has(p):
            if not df.is_hidden(p):
                # it came back visible (an app updater rewrote the shortcut, a sync tool, ...)
                if not df.set_hidden(p, True):
                    self.failed.add(df.norm(p))
                    log.info("Could not hide %s again (Windows error %s)", p, df.last_error(p))
                    return "failed"
                log.info("Hid %s again (it had become visible)", p)
            self.failed.discard(df.norm(p))
            return "hidden"
        if df.is_hidden(p):
            return "pre-hidden"  # you hid it yourself; we leave it exactly as it is
        self.ledger.add(p, group_id)  # write it down FIRST
        if df.set_hidden(p, True):
            self.failed.discard(df.norm(p))
            log.info("Hid %s", p)
            return "hidden"
        self.ledger.remove(p)
        self.failed.add(df.norm(p))
        log.info("Could not hide %s (it stays visible on the desktop, still in its group)", p)
        return "failed"

    def unhide(self, p):
        """Un-hide an item, but only if the ledger says we hid it."""
        self.failed.discard(df.norm(p))
        if not self.ledger.has(p):
            return False
        if not os.path.exists(p):
            self.ledger.remove(p)
            return False
        if df.set_hidden(p, False):
            self.ledger.remove(p)
            log.info("Showed %s again", p)
            return True
        log.error("Could not un-hide %s; will retry next start", p)
        return False

    def unhide_all(self):
        for p in self.ledger.paths():
            self.unhide(p)

    def sync(self, wanted):
        """wanted = {path: group_id} for every item that is in a group.
        Un-hides ledger items no longer in any group, hides grouped items."""
        wanted_norm = {df.norm(p): p for p in wanted}
        for p in self.ledger.paths():
            if df.norm(p) not in wanted_norm:
                self.unhide(p)
        statuses = {}
        for p, gid in wanted.items():
            statuses[p] = self.hide(p, gid)
        return statuses
