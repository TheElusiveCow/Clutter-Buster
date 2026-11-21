"""Automated check of the safety logic and stage 2 features, run off-screen with a FAKE desktop.

It never touches real files: it builds a temporary pretend desktop and a
temporary app-data folder, and (on non-Windows) the Hidden flag is simulated.
Run:  python tests/smoke_test.py      (meant for Linux/macOS dev boxes)
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if sys.platform == "win32":
    sys.exit("smoke_test uses a simulated desktop and is meant for Linux/macOS dev boxes only.")

tmp = tempfile.mkdtemp(prefix="cb-test-")
desk = os.path.join(tmp, "Desktop")
pub = os.path.join(tmp, "PublicDesktop")
os.makedirs(desk)
os.makedirs(pub)
os.environ["APPDATA"] = os.path.join(tmp, "AppData")
os.environ["CLUTTERBUSTER_TEST_DESKTOPS"] = os.pathsep.join([desk, pub])

from clutterbuster import paths  # noqa: E402
paths.ensure_dirs()
paths.setup_logging()
paths.install_excepthook()

from PySide6.QtCore import QMimeData, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from clutterbuster import desktop_files as df, fuzzy  # noqa: E402
from clutterbuster.app import Controller  # noqa: E402
from clutterbuster.glass import parse_drop  # noqa: E402
from clutterbuster.group_widget import grid_layout  # noqa: E402


def mk(d, name, folder=False):
    p = os.path.join(d, name)
    if folder:
        os.makedirs(p)
    else:
        open(p, "w").close()
    return p


chrome = mk(desk, "Chrome.lnk")
steam = mk(desk, "Steam.lnk")
notes = mk(desk, "notes.txt")
folder = mk(desk, "Projects", folder=True)
site_file = mk(desk, "YouTube.url")
mine = mk(desk, "secret.txt")
df.set_hidden(mine, True)          # Brian hid this one himself
before = sorted(os.listdir(desk))

app = QApplication(sys.argv)
c = Controller(app)
assert c.layout.groups == [], "must start with no groups"
assert c.search.isVisible() and c.dock.isVisible()

# --- adding: files, folders, .url files (hidden like files), websites (never hidden)
gid = c.create_group("Games", edit=False)
added = c.add_paths(gid, [chrome, steam, notes, folder, site_file, mine])
assert site_file in added, ".url files are allowed now"
assert all(df.is_hidden(p) for p in (chrome, steam, notes, folder, site_file)), "grouped items hidden"
assert not c.ledger.has(mine), "pre-hidden item never recorded as ours"
md = QMimeData()
md.setUrls([QUrl("https://www.example.com/page")])
md.setHtml('<a href="https://www.example.com/page">Example Page</a>')
files, webs = parse_drop(md)
assert files == [] and webs == [("https://www.example.com/page", "Example Page")], webs
c.handle_drop(gid, None, (files, webs))
md2 = QMimeData()
md2.setText("https://github.com/")
c.handle_drop(gid, None, parse_drop(md2))
g = c.layout.group(gid)
urls = [it for it in g["items"] if df.is_url(it["path"])]
assert [u.get("title") for u in urls] == ["Example Page", "github.com"], urls
assert not c.ledger.has("https://github.com/"), "websites are never hidden"
assert g["badge"] == 8, g["badge"]
c.open_group(gid)
assert c.layout.group(gid)["badge"] == 0, "opening clears the badge"
c.popup.hide()
c.popup.gid = None
# duplicates / one group per item
g2 = c.create_group("Work", edit=False)
assert c.add_paths(g2, [chrome]) == []
for i in range(12):
    c.add_paths(g2, [mk(desk, f"doc{i}.txt")])
c.open_group(g2)
assert c.popup.pages() == 2
c.popup.progress = 1.0
c.popup.grab().save(os.path.join(tmp, "popup.png"))
c.popup.hide()
c.popup.gid = None
# --- big panel + resizing + accent
c.set_mode(g2, "panel")
c.set_accent(g2, "#FF3B7F")
c.resize_group(g2, 300, 200, 360, 260)
w2 = c.widgets[g2]
assert (w2.width(), w2.height()) == (360, 260)
w2.grab().save(os.path.join(tmp, "panel.png"))
c.resize_group(g2, 300, 200, 150, 110)  # tiny: still no clipping -> pages
cr, cols, rows, cell, pages = w2.panel_layout()
assert cell >= 28 and cols * rows * pages >= 12
for _i, r in w2.panel_item_rects():
    assert cr.adjusted(-1, -1, 1, 1).contains(r), "icon cut off"
assert grid_layout(400, 300, 12)[3] == 1
c.resize_group(g2, 300, 200, 360, 260)
c.widgets[gid].grab().save(os.path.join(tmp, "tile.png"))
c.search.grab().save(os.path.join(tmp, "search.png"))
# --- favorites never hide, undo works
c.add_favorite(notes)
c.add_favorite("https://github.com/")
assert c.layout.favorites == [notes, "https://github.com/"]
c.dock.pinned = True
c.dock.reveal = 1.0
c.dock._apply_geometry()
c.dock.grab().save(os.path.join(tmp, "dock.png"))
c.remove_favorite(notes)
c.undo()
assert notes in c.layout.favorites
# --- quick search
c.open_quick_search("doc1")
assert c.quick.results and c.quick.results[0][0].startswith("doc1"), c.quick.results[:2]
c.quick.grab().save(os.path.join(tmp, "quick.png"))
c.quick.close_search()
assert fuzzy.score("clc", "Calculator") is not None
# --- move item between groups, item-onto-item makes a new group
d0 = os.path.join(desk, "doc0.txt")
c.handle_drop(gid, (d0, g2), None)
assert c.layout.group_of(d0)["id"] == gid and df.is_hidden(d0)
c.handle_drop(g2, (d0, gid), None, target=os.path.join(desk, "doc1.txt"))
newg = c.layout.group_of(d0)
assert newg["id"] not in (gid, g2) and len(newg["items"]) == 2 and df.is_hidden(d0)
c.undo()
assert c.layout.group_of(d0)["id"] == gid
# --- remove item -> unhidden; undo -> hidden again
c.remove_item(gid, notes)
assert not df.is_hidden(notes) and not c.ledger.has(notes)
c.undo()
assert df.is_hidden(notes)
# --- move snaps to grid
c.move_group(gid, 333, 333)
g = c.layout.group(gid)
assert (g["x"] - c.avail().left() - 8) % 16 == 0
# --- delete group -> items visible again; Brian's own hidden file stays hidden
c.delete_group(gid)
assert not df.is_hidden(chrome) and df.is_hidden(mine)
c.undo()
assert df.is_hidden(chrome)
# --- crash recovery: ledger items with no group get un-hidden on start
c.layout.groups = [x for x in c.layout.groups if x["id"] != gid]
c.layout.save()
from clutterbuster.ledger import Hider, Ledger  # noqa: E402
from clutterbuster.store import Layout  # noqa: E402
c2 = Controller.__new__(Controller)
c2.layout, c2.ledger = Layout(), Ledger()
c2.hider = Hider(c2.ledger)
Controller.sync_hidden(c2)
assert not df.is_hidden(chrome), "orphan ledger item unhidden on restart"
assert df.is_hidden(os.path.join(desk, "doc2.txt")), "still-grouped item stays hidden"
# --- quit restores everything we hid, but not Brian's own hidden file
c.restore_desktop()
c2.hider.unhide_all()
assert not any(df.is_hidden(os.path.join(desk, n)) for n in os.listdir(desk) if n != "secret.txt")
assert df.is_hidden(mine)
assert sorted(os.listdir(desk)) == sorted(before + [f"doc{i}.txt" for i in range(12)]), "no file moved/renamed/deleted"
assert 0 < len(os.listdir(paths.backups_dir())) <= 20
err = paths.error_log()
assert not os.path.exists(err) or os.path.getsize(err) == 0, open(err).read()
print("ALL CHECKS PASSED; images in", tmp)
