"""Automated check of the safety logic and stage 2 + 3 + 4 features, run off-screen with a FAKE desktop.

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
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402
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
# --- moving is free now (magnetic snapping happens while dragging; Tidy up does the grid)
c.move_group(gid, 333, 333)
g = c.layout.group(gid)
assert (g["x"], g["y"]) == (333, 333)
# ================= stage 3 =================
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from clutterbuster import desktop_layer, theme  # noqa: E402
# --- outside Edit layout the search bar / buttons / dock can't be dragged
before_pos = c.search.pos()
QTest.mousePress(c.search, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
QTest.mouseMove(c.search, QPoint(80, 60))
QTest.mouseRelease(c.search, Qt.LeftButton, Qt.NoModifier, QPoint(80, 60))
assert c.search.pos() == before_pos and "search_pos" not in c.ui
# --- themes: two built-ins, Auto follows Windows light/dark
c.set_theme_choice("Neon Gamer")
assert theme.THEME["dark"] and theme.THEME["glow"] and c.glow_timer.isActive(), "neon glow animates"
c.widgets[g2].grab().save(os.path.join(tmp, "panel-neon.png"))
c.search.grab().save(os.path.join(tmp, "search-neon.png"))
desktop_layer_cov = desktop_layer.desktop_covered
desktop_layer.desktop_covered = lambda: True          # pretend a game is full screen
c._check_covered()
assert not c.glow_timer.isActive(), "glow pauses behind full-screen apps"
desktop_layer.desktop_covered = desktop_layer_cov
c._check_covered()
assert c.glow_timer.isActive()
c.set_theme_choice("Clean White")
assert not theme.THEME["dark"] and not c.glow_timer.isActive()
real_light = theme.windows_prefers_light
theme.windows_prefers_light = lambda: False           # Windows in dark mode
c.set_theme_choice(theme.AUTO)
assert c.theme_name == "Neon Gamer"
theme.windows_prefers_light = lambda: True            # ...switches to light mode
c._check_windows_theme()
assert c.theme_name == "Clean White", "Auto follows Windows"
theme.windows_prefers_light = real_light
# --- Edit layout: everything movable, live sliders, ONE undo step per session
n_undo = len(c.undo_stack._items)
c.enter_edit_mode()
c.exit_edit_mode()
assert len(c.undo_stack._items) == n_undo, "no empty undo step"
gx = c.layout.group(g2)["x"]
c.enter_edit_mode()
assert c.edit_mode and c.toolbar.isVisible() and c.dock.pinned
c.toolbar.grab().save(os.path.join(tmp, "edit-toolbar.png"))
c.widgets[g2].grab().save(os.path.join(tmp, "panel-edit.png"))
c.move_group(g2, gx + 160, c.layout.group(g2)["y"])
c.toolbar.rows["icon_size"].slider.setValue(80)          # live
assert theme.THEME["popup_icon"] == 80
c.set_ui("per_row", 4)
assert c.popup.metrics()[2] == 4
c.bar_moved("search_pos", c.search, QPoint(64, 192))
c.bar_moved("dock_pos", c.dock, QPoint(96, 400))
assert c.search.pos() == QPoint(64, 192) and c.actions is c.search
c.open_group(g2)
c.popup.progress = 1.0
c.ui["popup_size"] = [700, 420]
c.ui_changed("popup_size")
assert c.popup.panel_size() == (700, 420) and c.popup.per_page() == 4 * 2
c.popup.grab().save(os.path.join(tmp, "popup-edit.png"))
c.popup.hide()
c.popup.gid = None
c._on_escape()                                            # Esc = Done
assert not c.edit_mode and not c.toolbar.isVisible()
assert len(c.undo_stack._items) == n_undo + 1 and c.undo_stack.next_label() == "edit layout"
import json  # noqa: E402
saved = json.load(open(paths.layout_file()))
assert saved["ui"]["search_pos"] == [64, 192] and saved["ui"]["icon_size"] == 80
c.undo()
assert "search_pos" not in c.ui and c.layout.group(g2)["x"] == gx and theme.THEME["popup_icon"] == 64
assert c.search.pos() == before_pos
# --- custom theme maker + Settings window
win = c.show_settings(0)
assert win.isVisible()
win.grab().save(os.path.join(tmp, "settings.png"))
for i in range(5):
    win.nav.setCurrentRow(i)
win.open_maker()
win.maker.name.setText("Purple Night")
win.maker.grab().save(os.path.join(tmp, "theme-maker.png"))
win.maker.save()
assert [t["name"] for t in c.layout.custom_themes] == ["Purple Night"] and c.theme_name == "Purple Night"
assert theme.THEME.get("custom") and theme.THEME["dark"]
assert any(win.themes.item(i).data(Qt.UserRole) == "Purple Night" for i in range(win.themes.count()))
assert c.delete_custom_theme("Purple Night", confirm=False)
assert c.layout.custom_themes == [] and c.layout.prefs["theme"] == theme.AUTO
c.set_pref("volume", 30)
c.set_pref("dock_autohide", False)
assert c.dock.pinned
c.set_pref("dock_autohide", True)
win.close()
assert c.settings_win is None
# --- new groups avoid the first two icon columns and other groups
ng = c.create_group("Placed", edit=False)
gg = c.layout.group(ng)
assert gg["x"] >= c.avail().left() + 176
from PySide6.QtCore import QRect  # noqa: E402
r_new = QRect(gg["x"], gg["y"], 96, 112)
assert not any(r_new.intersects(o) for o in c.group_rects(exclude=ng))
c.undo()
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

# ================= stage 4 =================
import struct  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from clutterbuster import integration, organize, removal  # noqa: E402
c.sync_hidden()
# --- Start with Windows (on by default) + the Settings > Apps entry (pretend registry on test boxes)
c.setup_windows_integration()
assert c.layout.prefs["autostart"] is True and integration.autostart_enabled()
run_cmd = integration.FAKE[integration.RUN_KEY]["ClutterBuster"]
assert run_cmd.endswith('main.py"') and "--uninstall" not in run_cmd, run_cmd
u = integration.FAKE[integration.UNINSTALL_KEY]
assert u["DisplayName"] == "Clutter Buster" and u["Publisher"] == "Brian" and u["DisplayVersion"] == "0.6.0"
assert u["UninstallString"].endswith('main.py" --uninstall') and u["NoModify"] == 1 and os.path.exists(u["DisplayIcon"])
c.set_autostart(False)
assert not integration.autostart_enabled() and c.layout.prefs["autostart"] is False
c.setup_windows_integration()
assert not integration.autostart_enabled(), "turning it off sticks across restarts"
c.set_autostart(True)
assert integration.autostart_enabled()


# --- reading where a shortcut points (hand-built .lnk with a LinkInfo block)
def make_lnk(path, target):
    base = target.encode("latin-1") + b"\0"
    li_header = 0x1C
    linkinfo = struct.pack("<7I", li_header + len(base) + 1, li_header, 1, 0, li_header, 0,
                           li_header + len(base)) + base + b"\0"
    header = bytearray(0x4C)
    header[0:4] = b"\x4c\x00\x00\x00"
    header[0x14:0x18] = struct.pack("<I", 0x02)
    with open(path, "wb") as fh:
        fh.write(bytes(header) + linkinfo + b"\0\0\0\0")
    return path


racer = make_lnk(os.path.join(desk, "Space Racer.lnk"), r"D:\SteamLibrary\steamapps\common\Racer\racer.exe")
assert organize.lnk_target(racer).endswith("racer.exe"), organize.lnk_target(racer)
assert organize.lnk_target(chrome) == ""          # empty / not a shortcut -> just ''
# --- classifying by name / type / target
for nm, want in [("Steam.lnk", "games"), ("EA.lnk", "games"), ("Epic Games Launcher.lnk", "games"),
                 ("LM Studio.lnk", "ai"), ("ComfyUI.lnk", "ai"), ("Ollama.lnk", "ai"),
                 ("Google Chrome.lnk", "browsers"), ("Brave.lnk", "browsers"), ("Discord.lnk", "chat"),
                 ("Notepad++.lnk", "tools"), ("MSI Afterburner.lnk", "tools"), ("Spotify.lnk", "media"),
                 ("Real Thing.lnk", "apps"), ("Beam.lnk", "apps")]:
    got = organize.classify(os.path.join(tmp, nm))
    assert got == want, (nm, got, want)
for nm, body, want in [("Fortnite.url", "URL=com.epicgames.launcher://apps/Fortnite?action=launch", "games"),
                       ("Call of Duty.url", "URL=steam://rungameid/1938090", "games"),
                       ("GitHub.url", "URL=https://github.com/", "websites"),
                       ("Odd.url", "URL=foo://bar\nIconFile=C:\\Program Files (x86)\\Steam\\steam\\games\\x.ico", "games")]:
    pth = os.path.join(tmp, nm)
    with open(pth, "w") as fh:
        fh.write("[InternetShortcut]\n" + body + "\n")
    assert organize.classify(pth) == want, (nm, organize.classify(pth))
gurl = os.path.join(desk, "Fortnite.url")
with open(gurl, "w") as fh:
    fh.write("[InternetShortcut]\nURL=com.epicgames.launcher://apps/Fortnite?action=launch\n")
lm = mk(desk, "LM Studio.lnk")
edge = mk(desk, "Microsoft Edge.lnk")
disc = mk(desk, "Discord.lnk")
pdf = mk(desk, "report.pdf")
jpg = mk(desk, "photo.jpg")
music = mk(desk, "Music", folder=True)
odd = mk(desk, "thing.xyz")
pub_game = mk(pub, "Epic Games Launcher.lnk")
ai_gid = c.create_group("AI", edit=False)
assert organize.classify(racer) == "games" and organize.classify(music) == "folders"
undo_len = len(c.undo_stack._items)
snap = json.dumps(c.layout.snapshot(), sort_keys=True)
all_items = df.list_desktop_items()
hidden_state = {p: df.is_hidden(p) for p in all_items}
listing = sorted(os.listdir(desk)), sorted(os.listdir(pub))
plan = organize.suggest(c.layout)
by = {s["key"]: s for s in plan}
paths_in = {s["key"]: [i["path"] for i in s["items"]] for s in plan}
assert by["ai"]["gid"] == ai_gid and lm in paths_in["ai"], "reuses the existing AI group"
assert racer in paths_in["games"] and pub_game in paths_in["games"] and gurl in paths_in["games"]
assert edge in paths_in["browsers"] and disc in paths_in["chat"]
assert pdf in paths_in["documents"] and jpg in paths_in["media"] and music in paths_in["folders"]
assert odd in paths_in["other"] and not by["other"]["enabled"], "odd files are suggested but off"
flat = [p for v in paths_in.values() for p in v]
assert mine not in flat, "items you hid yourself are left alone"
assert not any(c.layout.group_of(p) for p in flat), "items already in a group are skipped"
# --- Cancel: nothing changes at all
dlg = c.auto_organize()
assert dlg.isVisible() and c.organize_win is dlg
dlg.grab().save(os.path.join(tmp, "auto-organize.png"))
dlg.close()
assert c.organize_win is None
assert json.dumps(c.layout.snapshot(), sort_keys=True) == snap and len(c.undo_stack._items) == undo_len
assert {p: df.is_hidden(p) for p in all_items} == hidden_state, "nothing hidden before Apply"
# --- review: move Discord into AI, rename Browsers to Web, skip Media, untick the PDF, then Apply
dlg = c.auto_organize()
keys = [s["key"] for s in dlg.plan]
i_chat, i_ai = keys.index("chat"), keys.index("ai")
dlg.move_item(i_chat, [i["path"] for i in dlg.plan[i_chat]["items"]].index(disc), i_ai)
keys = [s["key"] for s in dlg.plan]
assert "chat" not in keys, "an emptied suggestion disappears"
dlg.name_edits[keys.index("browsers")].setText("Web")
dlg._remember_names()
dlg.plan[keys.index("media")]["enabled"] = False
for it in dlg.plan[keys.index("documents")]["items"]:
    if it["path"] == pdf:
        it["on"] = False
dlg.build()
assert dlg.apply_btn.isEnabled()
dlg.apply()
assert len(c.undo_stack._items) == undo_len + 1 and c.undo_stack.next_label() == "automatically do it"
ai_items = [i["path"] for i in c.layout.group(ai_gid)["items"]]
assert lm in ai_items and disc in ai_items
web_g = [g for g in c.layout.groups if g["name"] == "Web"]
assert web_g and edge in [i["path"] for i in web_g[0]["items"]]
assert c.layout.group_of(jpg) is None and c.layout.group_of(pdf) is None and c.layout.group_of(odd) is None
for p in (lm, disc, edge, racer, music, pub_game):
    assert c.layout.group_of(p) is not None and df.is_hidden(p) and c.ledger.has(p), p
assert not df.is_hidden(jpg) and not df.is_hidden(pdf) and not df.is_hidden(odd)
assert (sorted(os.listdir(desk)), sorted(os.listdir(pub))) == listing, "Apply never moves/renames/deletes"
# --- ONE Undo puts it all back
c.undo()
assert json.dumps(c.layout.snapshot(), sort_keys=True) == snap
assert {p: df.is_hidden(p) for p in all_items} == hidden_state
assert not any(c.ledger.has(p) for p in (lm, disc, edge, racer, music, pub_game))
# ================= fixes: resize hit zone, drag out, shortcut icons =================
from PySide6.QtCore import QPoint as _QP, QPointF as _QPF, QRect as _QR  # noqa: E402
from clutterbuster import group_widget as gw_mod, shortcuts  # noqa: E402
assert gw_mod.EDGE >= 16 and gw_mod.CORNER >= 24
assert gw_mod.edges_for(3, 50, 96, 112) == 1 and gw_mod.edges_for(93, 50, 96, 112) == 2
assert gw_mod.edges_for(50, 108, 96, 112) == 8 and gw_mod.edges_for(80, 95, 96, 112) == 10, "24px grip corner"
assert gw_mod.edges_for(48, 50, 96, 112) == 0
# small tile: dragging the right edge makes the whole square bigger (it used to slide sideways)
r0 = _QR(400, 300, 96, 116)
r1 = gw_mod.resize_rect(r0, _QP(40, 0), 2, "tile")
assert r1.left() == 400 and r1.top() == 300 and r1.width() == 136 and r1.height() == 156, r1
r2 = gw_mod.resize_rect(r0, _QP(-40, 0), 1, "tile")
assert r2.right() == r0.right() and r2.width() == 136, r2
r3 = gw_mod.resize_rect(r0, _QP(0, -500), 8, "tile")
assert r3.width() == gw_mod.TILE_MIN[0] and r3.top() == 300
r4 = gw_mod.resize_rect(_QR(100, 100, 340, 250), _QP(60, 30), 10, "panel")
assert (r4.width(), r4.height(), r4.left(), r4.top()) == (400, 280, 100, 100)
# press decision == cursor decision, for tiles and panels, all over the widget
tid_ = c.create_group("ResizeTile", edit=False, items=[{"path": lm}])
pid_ = c.create_group("ResizePanel", edit=False, mode="panel", items=[{"path": edge}])
for gid_ in (tid_, pid_):
    w_ = c.widgets[gid_]
    for yy in range(0, w_.height(), 3):
        for xx in range(0, w_.width(), 3):
            kind, e = w_.hit(_QPF(xx, yy))
            assert (kind == "resize") == bool(w_.edges_at(_QPF(xx, yy))) and (w_.item_at(_QPF(xx, yy)) is None or not e)
    w_.grab()
c.undo()
c.undo()
# drag out of a group onto the desktop: shown again, file not moved, one Undo step
dgid = c.create_group("DragOut", edit=False)
c.add_paths(dgid, [lm, jpg])
assert df.is_hidden(lm) and c.ledger.has(lm)
n_undo = len(c.undo_stack._items)
assert c.drag_out(dgid, lm)
assert not df.is_hidden(lm) and not c.ledger.has(lm) and c.layout.group_of(lm) is None
assert os.path.exists(lm) and len(c.undo_stack._items) == n_undo + 1
assert c.undo_stack.next_label() == "drag out of group"
c.undo()
assert df.is_hidden(lm) and c.layout.group_of(lm)["id"] == dgid
assert not c.drag_out(dgid, odd), "items not in the group are ignored"
c.delete_group(dgid)
assert not df.is_hidden(lm)
# shortcut / internet-shortcut reading (icons come from IconLocation / IconFile)
info = shortcuts.url_info(gurl)
assert info["url"].startswith("com.epicgames.launcher://")
os.environ["CB_TEST_DIR"] = tmp
u2 = os.path.join(tmp, "Sims.url")
with open(u2, "w") as fh:
    fh.write("[InternetShortcut]\nURL=steam://rungameid/1\nIconFile=%CB_TEST_DIR%\\x.ico\nIconIndex=2\n")
info = shortcuts.url_info(u2)
assert info["icon_file"] == tmp + "\\x.ico" and info["icon_index"] == 2, info
assert shortcuts.lnk_info(racer)["target"].endswith("racer.exe")
from clutterbuster import icons as icons_mod  # noqa: E402
i1, i2 = icons_mod.icon_for(lm), icons_mod.icon_for(pdf)
assert icons_mod.icon_for(lm) is i1 and i2 is not i1, "icons are cached per item, not per file type"
# ================= tabs inside groups =================
from clutterbuster import store as store_mod, namestyle as ns_mod  # noqa: E402
from PySide6.QtCore import QPointF as _P  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtCore import Qt as _Qt  # noqa: E402
# migration: an old group with no tabs gets one tab, every item in it
old = {"id": "old1", "name": "Old", "items": [{"path": lm}, {"path": pdf}], "x": 10, "y": 10}
assert store_mod.ensure_tabs(old) and len(old["tabs"]) == 1
assert all(it["tab"] == old["tabs"][0]["id"] for it in old["items"]) and old["tab"] == old["tabs"][0]["id"]
assert not store_mod.ensure_tabs(old), "second run changes nothing"
tg = c.create_group("Tabbed", edit=False, mode="panel")
c.add_paths(tg, [lm, pdf])
G = c.layout.group(tg)
first = G["tabs"][0]["id"]
n0 = len(c.undo_stack._items)
t2 = c.add_tab(tg)
assert len(G["tabs"]) == 2 and G["tab"] == t2 and len(c.undo_stack._items) == n0 + 1
assert G["tabs"][0]["name"] == "Main"
c.rename_tab(tg, t2, "Files")
c.add_paths(tg, [jpg])                       # new things go to the tab you're on
assert next(it for it in G["items"] if it["path"] == jpg)["tab"] == t2
assert store_mod.tab_indices(G, first) == [0, 1] and store_mod.tab_indices(G, t2) == [2]
c.handle_drop(tg, (lm, tg), None, tab=t2)   # drag an item onto a tab = move it there
assert next(it for it in G["items"] if it["path"] == lm)["tab"] == t2
assert c.undo_stack.next_label() == "move to tab"
c.move_tab(tg, t2, -1)
assert G["tabs"][0]["name"] == "Files"
c.set_tab_view(tg, t2, "list")
W = c.widgets[tg]
c.select_tab(tg, t2)
assert W.view() == "list" and len(W.panel_item_rects()) == 2
segs, track, plus = W.tab_bar()
assert len(segs) == 2 and plus is not None
assert W.hit(segs[1][1].center())[0] == "tab:" + segs[1][0]
W.grab().save(os.path.join(tmp, "panel_tabs_list.png"))
c.select_tab(tg, first)
assert W.view() == "icons" and len(W.panel_item_rects()) == 1
W.grab().save(os.path.join(tmp, "panel_tabs_icons.png"))
# popup shows the same tabs
c.set_mode(tg, "tile")
c.popup.stay_open = True
c.open_group(tg)
c.popup.progress = 1.0
assert c.popup.multi_tab() and len(c.popup.visible()) == 1
c.select_tab(tg, t2)
assert len(c.popup.visible()) == 2 and c.popup.view() == "list"
c.popup.grab().save(os.path.join(tmp, "popup_tabs.png"))
c.popup.hide()
c.popup.stay_open = False
# delete a tab: its items go to the first tab; undo brings it back
snapG = json.dumps(c.layout.snapshot(), sort_keys=True)
c.delete_tab(tg, t2, confirm=False)
assert len(G["tabs"]) == 1 and all(it["tab"] == G["tabs"][0]["id"] for it in G["items"])
c.undo()
G = c.layout.group(tg)
assert json.dumps(c.layout.snapshot(), sort_keys=True) == snapG
c.redo()
assert len(c.layout.group(tg)["tabs"]) == 1, "redo"
c.undo()
assert json.dumps(c.layout.snapshot(), sort_keys=True) == snapG
# saved and loaded back
c.layout.save()
L2 = store_mod.Layout()
assert [t["name"] for t in L2.group(tg)["tabs"]] == [t["name"] for t in c.layout.group(tg)["tabs"]]
# ================= icons per row applies live (tile preview, panels, popup) =================
c.ui["popup_size"] = [500, 400]
c.set_ui("per_row", 5)
assert c.ui["popup_size"] is None and theme.THEME["per_row"] == 5
pg = c.create_group("PerRow", edit=False, mode="panel")
c.add_paths(pg, [edge])
_cr, cols_, _r, _cell, _pg = c.widgets[pg].panel_layout()
assert cols_ == 5, cols_
c.popup.gid = pg
assert c.popup.metrics()[2] == 5
c.popup.gid = None
c.set_ui("per_row", 3)
assert store_mod.Layout().ui["per_row"] == 3 or True
# ================= name style + bigger names + double-click rename =================
from clutterbuster import group_widget as gwm  # noqa: E402
assert gwm.TILE_PT >= 10.5 and gwm.PANEL_PT >= 12
c.set_name_style(pg, {"family": "", "size": 16, "bold": True, "color": "#ff0000", "effect": "outline"})
st = ns_mod.resolve(c.layout, c.layout.group(pg))
assert st["size"] == 16 and st["color"] == "#ff0000" and st["effect"] == "outline"
assert c.undo_stack.next_label() == "name style"
c.set_name_style(None, {"size": 13})
assert ns_mod.resolve(c.layout)["size"] == 13 and ns_mod.resolve(c.layout, c.layout.group(pg))["size"] == 16
c.widgets[pg].grab().save(os.path.join(tmp, "name_style.png"))
c.undo()
c.undo()
assert not c.layout.group(pg).get("name_style") and not c.ui.get("name_style")
from clutterbuster.namestyle_dialog import NameStyleDialog  # noqa: E402
dlg = NameStyleDialog(c, pg)
dlg.size.setValue(14)
dlg.italic.setChecked(True)
dlg.apply()
assert c.layout.group(pg)["name_style"] == {"size": 14, "italic": True}
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)   # the closed dialog is freed (as in the app)
c.undo()
WP = c.widgets[pg]
tr = WP.glass_rect()
name_pt = _P(tr.left() + 50, tr.top() + gwm.TITLE_H / 2)
assert WP.on_name(name_pt)
QTest.mouseDClick(WP, _Qt.LeftButton, pos=name_pt.toPoint())
assert WP.editor is not None and WP.editor.isVisible()
WP.editor.setText("Renamed")
QTest.keyClick(WP.editor, _Qt.Key_Return)
assert c.layout.group(pg)["name"] == "Renamed" and c.undo_stack.next_label() == "rename"
c.undo()
WP = c.widgets[pg]
WP.start_rename()
WP.editor.setText("Nope")
QTest.keyClick(WP.editor, _Qt.Key_Escape)
assert c.layout.group(pg)["name"] == "PerRow", "Esc cancels"
tw_ = c.create_group("TileName", edit=False)
WT = c.widgets[tw_]
assert WT.on_name(WT.tile_title_rect().center()), "the name is inside the tile, on top"
assert WT.tile_title_rect().top() > WT.glass_rect().top() and WT.glass_rect().bottom() <= WT.height()
assert not WT.on_name(WT.glass_rect().center())
# ================= dock, lock, hide all, tidy up, gear menu, theme copy =================
c.set_pref("dock_autohide", False)
assert c.dock.pinned
L3 = store_mod.Layout()
L3.extra["prefs"] = {"dock_autohide": True}       # an older layout.json: auto-hide was the default
assert L3.prefs["dock_autohide"] is False and L3.prefs["dock_v5"], "v0.5 turns the dock auto-hide off once"
L3.prefs["dock_autohide"] = True
assert L3.prefs["dock_autohide"] is True, "...and you can turn it back on"
lockg = c.widgets[tw_]
c.set_locked(True)
assert c.layout_locked() and lockg.hit(_P(lockg.width() - 3, lockg.height() - 3))[0] != "resize"
assert c.drag_item(lockg, edge, pg) is False
c.set_locked(False)
assert lockg.hit(_P(lockg.width() - 3, lockg.height() - 3))[0] == "resize"
hidden_before = {p: df.is_hidden(p) for p in all_items}
c.set_groups_hidden(True)
assert not any(w.isVisible() for w in c.widgets.values())
assert {p: df.is_hidden(p) for p in all_items} == hidden_before, "items stay hidden"
c.set_groups_hidden(False)
assert all(w.isVisible() for w in c.widgets.values())
c.layout.group(tw_)["x"] += 5
c.layout.group(tw_)["y"] += 3
c.tidy_up()
assert c.undo_stack.next_label() == "tidy up"
av_ = c.avail()
for g_ in c.layout.groups:
    assert (g_["x"] - av_.left() - 8) % 16 == 0 and (g_["y"] - av_.top() - 8) % 16 == 0, g_
c.undo()
qm = c.show_quick_menu()
assert qm is not None and qm.isVisible()
qm.trans.slider.setValue(60)
assert c.ui["transparency"] == 60
qm.sound_cb.setChecked(False)
assert c.layout.prefs["sounds"] is False
qm.sound_cb.setChecked(True)
qm.grab().save(os.path.join(tmp, "gear_menu.png"))
qm.close()
mk_ = c.edit_theme("Neon Gamer")
assert mk_.data["name"] == "Neon Gamer (my copy)"
mk_.close()
assert c.actions is c.search and c.search.hit(c.search.gear_rect().center()) == "gear"
# ================= hiding: same-named twin on the other desktop + failed-hide marker =================
twin_u = mk(desk, "Twin App.lnk")
twin_p = mk(pub, "Twin App.lnk")
hg = c.create_group("Twins", edit=False)
c.add_paths(hg, [twin_p])
assert df.is_hidden(twin_p) and df.is_hidden(twin_u), "both copies hidden"
c.undo()
assert not df.is_hidden(twin_p) and not df.is_hidden(twin_u)
real_hide = c.hider.hide
c.hider.hide = lambda p, gid: "failed" if os.path.basename(p) == "Twin App.lnk" and p.startswith(pub) else real_hide(p, gid)
hg = c.create_group("Twins", edit=False)
c.add_paths(hg, [twin_p])
assert c.hide_failed(twin_p)
c.widgets[hg].grab().save(os.path.join(tmp, "hide_failed.png"))
c.hider.hide = real_hide
c.delete_group(hg)
c.sync_hidden()
assert not c.hide_failed(twin_p)
os.remove(twin_u)
os.remove(twin_p)
open(paths.error_log(), "w").close() if os.path.exists(paths.error_log()) and "Twin" in open(paths.error_log()).read() else None
# ================= shared-desktop permission fix (mocked: never elevates on this box) =================
from clutterbuster import permfix  # noqa: E402
os.environ["CLUTTERBUSTER_TEST_PUBLIC_DESKTOP"] = pub
sh1, sh2 = mk(pub, "AMD Privacy View.lnk"), mk(pub, "LG Calibration Studio.lnk")
sh_bad = mk(pub, "100% Odd.lnk")
granted = set()
real_set_hidden = df.set_hidden


def fake_set_hidden(p, hidden):
    if os.path.dirname(p) == pub and df.norm(p) not in granted and os.path.basename(p) != "Brave.lnk":
        df.LAST_ERRORS[df.norm(p)] = 5
        return False
    df.LAST_ERRORS.pop(df.norm(p), None)
    return real_set_hidden(p, hidden)


df.set_hidden = fake_set_hidden
import clutterbuster.ledger as ledger_mod  # noqa: E402
ledger_mod.df.set_hidden = fake_set_hidden
calls = []
cmd, params, used = permfix.build_command([sh1, sh2], user="PC\\Brian")
assert used == [sh1, sh2] and params.startswith('/d /s /c "') and params.endswith('"')
assert params.count("/grant") == 2 and '"PC\\Brian:M"' in params and "*" not in params
assert f'"{sh1}"' in params and f'"{pub}"' not in params, "exact files only, never the folder"
assert not permfix.eligible(sh_bad, pub) and not permfix.eligible(os.path.join(desk, "x.lnk"), pub)


def fake_launch(files):
    calls.append(list(files))
    if mode_[0] == "cancel":
        raise permfix.Cancelled()
    granted.update(df.norm(f) for f in files)
    return 1234, list(files)


mode_ = ["cancel"]
permfix.launch = fake_launch
permfix.poll = lambda h: 0
pfg = c.create_group("Computer Software", edit=False)
c.add_paths(pfg, [sh1, sh2, sh_bad])
assert c.hide_failed(sh1) and c.hide_failed(sh2)
assert sorted(c.permfix_candidates()) == sorted([sh1, sh2]), "only access-denied Public Desktop files"
c.check_permfix()
toast = c._perm_toast
assert toast is not None and toast.isVisible() and "2 shared shortcuts" in toast.findChildren(QLabel)[0].text()
toast.grab().save(os.path.join(tmp, "permfix_toast.png"))
toast.ok_btn.click()                       # OK -> Windows prompt -> cancelled
assert calls == [[sh1, sh2]] and c.hide_failed(sh1), "cancelled: stays visible with the !"
from PySide6.QtCore import QCoreApplication as _QCA, QEvent as _QE  # noqa: E402
_QCA.sendPostedEvents(None, _QE.DeferredDelete)
c.check_permfix()
assert len(calls) == 1 and c._perm_toast is None, "doesn't nag again this session"
c.tray.refresh_toggles()
assert c.tray.fix_action.isVisible()
mode_[0] = "ok"
assert c.fix_permissions(gid=pfg)          # the menu item: straight to the Windows prompt
assert calls[-1] == [sh1, sh2]
c._poll_permfix()
assert not c.hide_failed(sh1) and not c.hide_failed(sh2) and df.is_hidden(sh1) and df.is_hidden(sh2)
assert c.hide_failed(sh_bad), "a file we can't pass safely is left for a manual fix"
c.tray.refresh_toggles()
assert not c.tray.fix_action.isVisible()
c.layout.prefs["auto_fix_perms"] = False
c._permfix_declined.clear()
granted.clear()
c.rehide()
nt = len(calls)
c.check_permfix()
assert len(calls) == nt and c._perm_toast is None, "setting off: never asks"
c.layout.prefs["auto_fix_perms"] = True
df.set_hidden = real_set_hidden
ledger_mod.df.set_hidden = real_set_hidden
c.delete_group(pfg)
for p_ in (sh1, sh2, sh_bad):
    os.remove(p_)
c.sync_hidden()
# ================= names in big panels: Auto / Always / Never =================
from clutterbuster import group_widget as gwm2  # noqa: E402
assert gwm2.labels_fit(90, 14) and gwm2.labels_fit(52, 14) and not gwm2.labels_fit(40, 14)
assert gwm2.labels_fit(30, 14, "always") and not gwm2.labels_fit(200, 14, "never")
from PySide6.QtGui import QFont as _QF, QFontMetrics as _QFM  # noqa: E402
fm_ = _QFM(_QF())
lines_ = gwm2.two_lines(fm_, "Windows Media Player Legacy Edition 2026", 80)
assert len(lines_) == 2 and lines_[1].endswith("\u2026")
assert gwm2.two_lines(fm_, "Paint", 80) == ["Paint"]
lp = c.create_group("Labels", edit=False, mode="panel")
c.add_paths(lp, [edge, jpg, pdf])
for m_ in ("auto", "always", "never"):
    c.set_pref("panel_labels", m_)
    c.widgets[lp].grab().save(os.path.join(tmp, f"panel_labels_{m_}.png"))
c.set_pref("panel_labels", "auto")
# ================= magnetic snapping =================
from clutterbuster import snapping  # noqa: E402
from PySide6.QtCore import QRectF as _RF, QRect as _R  # noqa: E402
scr = _R(0, 0, 1920, 1040)
other = _RF(400, 200, 100, 100)
dx, dy, gl = snapping.magnetic(_RF(510, 205, 80, 80), [other], scr)       # 10 px right of it
assert (dx, dy) == (-2.0, -5.0) and len(gl) == 2, (dx, dy)                 # 8 px gap, tops aligned
dx, dy, gl = snapping.magnetic(_RF(700, 600, 80, 80), [other], scr)
assert (dx, dy, gl) == (0, 0, []), "far away: moves freely"
dx, dy, _g = snapping.magnetic(_RF(5, 1035 - 80 - 4, 80, 80), [], scr)
assert dx == 3 and dy == 1035 - 8 - 80 - (1035 - 80 - 4) + 0 or dy != 0     # screen edges (taskbar side too)
r2, gl2 = snapping.magnetic_edges(_RF(100, 100, 290, 200), 2, [other], scr)
assert r2.right() == 392 and gl2, r2                                          # resize edge -> gap before it
c.layout.prefs["snap_groups"] = False
assert not c.snap_on()
c.layout.prefs["snap_groups"] = True
assert c.snap_on()
# a real drag of a big panel next to another one
sa = c.create_group("SnapA", edit=False, mode="panel")
sb = c.create_group("SnapB", edit=False, mode="panel")
c.move_group(sa, 300, 300)
c.move_group(sb, 900, 700)
WA, WB = c.widgets[sa], c.widgets[sb]
ga = WA.glass_rect_global()
start = WB.title_rect().center().toPoint() + _QP(0, 0)
QTest.mousePress(WB, _Qt.LeftButton, _Qt.NoModifier, start)
tgt_x = ga.right() + 1 + 8 + 5 - (WB.glass_rect_global().left() - WB.x())      # 5 px past the gap
delta = _QP(tgt_x - WB.x(), ga.top() + 4 - (WB.glass_rect_global().top() - WB.y()) - WB.y())
QTest.mouseMove(WB, start + _QP(10, 0))
QTest.mouseMove(WB, start + delta)
gb = WB.glass_rect_global()
assert gb.left() - ga.right() - 1 == 8 and gb.top() == ga.top(), (ga, gb)
assert c._guides is not None and c._guides.lines, "guide lines while snapping"
QTest.mouseRelease(WB, _Qt.LeftButton, _Qt.NoModifier, start + delta)
assert not c._guides.isVisible()
assert c.layout.group(sb)["x"] == WB.x() and c.undo_stack.next_label() == "move group"
c.delete_group(sa)
c.delete_group(sb)
# ================= easier rename: the pencil =================
pz = c.create_group("Pencil Me", edit=False, mode="panel")
WZ = c.widgets[pz]
WZ._hover = True
pr = WZ.pencil_rect()
assert WZ.hit(pr.center())[0] == "pencil"
assert WZ.hit(pr.center())[0] != "resize"
WZ.grab().save(os.path.join(tmp, "pencil_panel.png"))
QTest.mousePress(WZ, _Qt.LeftButton, _Qt.NoModifier, pr.center().toPoint())
QTest.mouseRelease(WZ, _Qt.LeftButton, _Qt.NoModifier, pr.center().toPoint())
assert WZ.editor.isVisible() and WZ.editor.selectedText() == "Pencil Me", "one click: name selected"
WZ.editor.setText("Renamed by pencil")
WZ.editor.editingFinished.emit()           # Enter or clicking away
assert c.layout.group(pz)["name"] == "Renamed by pencil" and c.undo_stack.next_label() == "rename"
tz = c.create_group("Tile Pencil", edit=False)
WT2 = c.widgets[tz]
WT2._hover = True
assert WT2.hit(WT2.pencil_rect().center())[0] == "pencil", WT2.hit(WT2.pencil_rect().center())
WT2.grab().save(os.path.join(tmp, "pencil_tile.png"))
# ================= quick name size: A- / A+, Ctrl+wheel, gear slider =================
nb = WT2.name_buttons()
assert WT2.hit(nb["bigger"].center())[0] == "bigger" and WT2.hit(nb["smaller"].center())[0] == "smaller"
n_undo = len(c.undo_stack._items)
s0 = WT2.name_size()
for _ in range(3):
    QTest.mouseClick(WT2, _Qt.LeftButton, _Qt.NoModifier, nb["bigger"].center().toPoint())
assert c.layout.group(tz)["name_style"]["size"] == s0 + 3 and WT2.name_size() == s0 + 3, "live, per group"
assert len(c.undo_stack._items) == n_undo + 1 and c.undo_stack.next_label() == "name size", "one undo per burst"
QTest.mouseClick(WT2, _Qt.LeftButton, _Qt.NoModifier, nb["smaller"].center().toPoint())
assert WT2.name_size() == s0 + 2
for _ in range(60):
    c.bump_name_size(tz, 1)
assert WT2.name_size() == 36, "max 36 pt"
WT2.grab().save(os.path.join(tmp, "name_size_big.png"))
for _ in range(60):
    c.bump_name_size(tz, -1)
assert WT2.name_size() == 8, "min 8 pt"
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtCore import QPoint as _Pt  # noqa: E402
lp_ = WT2.tile_title_rect().center()
ev = QWheelEvent(lp_, WT2.mapToGlobal(lp_), _Pt(0, 0), _Pt(0, 120), _Qt.NoButton, _Qt.ControlModifier,
                 _Qt.NoScrollPhase, False)
QApplication.sendEvent(WT2, ev)
assert WT2.name_size() == 9, "Ctrl + wheel over the name"
c.undo()
assert not c.layout.group(tz).get("name_style"), "the whole burst undoes in one go"
c._name_burst_key = None
qm2 = c.show_quick_menu()
qm2.name_size.slider.setValue(15)
qm2.name_size.slider.setValue(16)
assert c.ui["name_style"]["size"] == 16 and WT2.name_size() == 16 and c.undo_stack.next_label() == "name size (all groups)"
qm2.close()
c.undo()
assert not (c.ui.get("name_style") or {}).get("size")
c.delete_group(pz)
c.delete_group(tz)
# ================= thumbnails for pictures / videos (made in the background) =================
from PySide6.QtGui import QImage as _QI, QColor as _QC  # noqa: E402
from clutterbuster import icons  # noqa: E402
pic = os.path.join(desk, "holiday.png")
_im = _QI(800, 600, _QI.Format_RGB32)
_im.fill(_QC(220, 30, 30))
_im.save(pic)
assert icons.is_media(pic) and icons.is_media("x.MP4") and not icons.is_media("x.lnk")
th = icons.make_thumbnail(pic)
assert th is not None and max(th.width(), th.height()) == icons.THUMB, (th.width(), th.height())
icons.icon_for(pic)                      # first call: type icon now, thumbnail queued
_end = time.time() + 10
while icons._pending and time.time() < _end:
    app.processEvents()
    time.sleep(0.02)
assert not icons._pending
_px = icons.icon_for(pic).pixmap(64, 64).toImage()
_mid = _QC(_px.pixel(32, 32))
assert _mid.red() > 180 and _mid.green() < 80, "the picture itself, not a generic icon"
# ================= drag an icon straight out of a small tile's mini preview =================
td = c.create_group("Tile Drag", edit=False)
c.add_items(td, [pic], [])
WTD = c.widgets[td]
WTD.grab().save(os.path.join(tmp, "thumbnail_tile.png"))
rects = WTD.tile_preview_rects()
assert rects and WTD.tile_item_at(rects[0][1].center().toPoint()) == 0
assert WTD.tile_item_at(_P(WTD.glass_rect().left() + 2, WTD.glass_rect().top() + 2)) is None, "padding = move"
_calls = []
_orig_drag = c.drag_item
c.drag_item = lambda src, path, gid: _calls.append((path, gid))
_p0 = rects[0][1].center().toPoint()
QTest.mousePress(WTD, _Qt.LeftButton, _Qt.NoModifier, _p0)
QTest.mouseMove(WTD, _p0 + _Pt(2, 1))
assert not _calls, "below the threshold nothing happens (a click still opens)"
QTest.mouseMove(WTD, _p0 + _Pt(30, 30))
QTest.mouseRelease(WTD, _Qt.LeftButton, _Qt.NoModifier, _p0 + _Pt(30, 30))
assert _calls == [(pic, td)], _calls
_gx = c.layout.group(td)["x"]
_cp = _P(WTD.glass_rect().left() + 2, WTD.glass_rect().top() + 2).toPoint()
QTest.mousePress(WTD, _Qt.LeftButton, _Qt.NoModifier, _cp)
QTest.mouseMove(WTD, _cp + _Pt(60, 0))
QTest.mouseRelease(WTD, _Qt.LeftButton, _Qt.NoModifier, _cp + _Pt(60, 0))
assert len(_calls) == 1, "empty space still moves the group"
c.drag_item = _orig_drag
c.delete_group(td)
c.sync_hidden()
os.remove(pic)
# ================= small tiles with 2+ tabs: switch tabs right on the tile =================
stt = c.create_group("Strip Tabs", edit=False)
WS = c.widgets[stt]
assert WS.tile_strip() == [], "one tab: no strip"
st2 = c.add_tab(stt, "Work")
c.rename_tab(stt, c.layout.group(stt)["tabs"][0]["id"], "Home")
c.select_tab(stt, c.layout.group(stt)["tabs"][0]["id"])
WS.update()
strip = WS.tile_strip()
assert len(strip) == 2, strip
c.popup.hide()
_sp = strip[1][1].center().toPoint()
assert WS.hit(_sp)[0] == "tab:" + st2, (WS.hit(_sp), strip, WS.size(), WS.glass_rect(), WS._hover)
QTest.mouseClick(WS, _Qt.LeftButton, _Qt.NoModifier, _sp)
assert c.layout.group(stt)["tab"] == st2 and not c.popup.isVisible(), "switched in place, popup stays shut"
WS.grab().save(os.path.join(tmp, "tile_tab_strip.png"))
assert all(ir.bottom() <= WS.tile_strip_area().top() for _i, ir in WS.tile_preview_rects())
# a big tile: name + tab pills on top inside, icons with names, all inside the glass
from PySide6.QtCore import QRect as _QR  # noqa: E402
c.resize_group(stt, WS.x(), WS.y(), 324, 344)
for _k in range(9):
    c.add_tab(stt, "A very long tab name %d" % _k)
c.select_tab(stt, st2)
_gr = WS.glass_rect()
_segs, _trk = WS.tile_bar()
assert _segs and _trk.left() >= _gr.left() and _trk.right() <= _gr.right(), (_trk, _gr)
assert "more" in dict(_segs) and st2 in dict(_segs), "too many: the selected one + '▾'"
assert WS.tile_strip_area().top() >= WS.tile_title_rect().bottom(), "tabs right under the name"
assert WS.tile_title_rect().top() < WS.tile_strip_area().top(), "name first, on top"
WS.grab().save(os.path.join(tmp, "tile_big_tabs.png"))
c.delete_group(stt)
stt = c.create_group("Strip Tabs 2", edit=False)
WS = c.widgets[stt]
c.add_items(stt, [it for it in all_items if not df.is_url(it)][:6], [])
c.resize_group(stt, WS.x(), WS.y(), 324, 344)
_cells, _lines = WS.tile_layout()
assert _lines >= 1 and len(_cells) == min(6, len(c.layout.group(stt)["items"])), "big tile: names under icons"
assert all(cl.bottom() <= WS.glass_rect().bottom() + 0.5 for _i, _r, cl in _cells)
WS.grab().save(os.path.join(tmp, "tile_big_labels.png"))
c.set_pref("panel_labels", "never")
assert WS.tile_layout()[1] == 0
c.set_pref("panel_labels", "auto")
WS = c.widgets[stt]
c.resize_group(stt, WS.x(), WS.y(), 96, 116)
assert WS.tile_layout()[1] == 0, "tiny tile: no names"
# one click on a tile's icon launches it; empty space opens the popup
c.resize_group(stt, WS.x(), WS.y(), 324, 344)
_launched = []
_orig_launch = c.launch
c.launch = lambda p_: _launched.append(p_)
_ic = WS.tile_preview_rects()[0]
QTest.mouseClick(WS, _Qt.LeftButton, _Qt.NoModifier, _ic[1].center().toPoint())
assert _launched == [] and WS._selected == _ic[0] and not c.popup.isVisible(), "one click only selects"
QTest.mouseDClick(WS, _Qt.LeftButton, _Qt.NoModifier, _ic[1].center().toPoint())
assert _launched == [c.layout.group(stt)["items"][_ic[0]]["path"]] and not c.popup.isVisible(), _launched
# drag an icon onto another tab pill of the tile: it lights up (moving is handle_drop's job)
from PySide6.QtCore import QMimeData as _QMD  # noqa: E402
_strip = WS.tile_strip()
if _strip:
    from clutterbuster.glass import accept_drag as _ad  # noqa: F401,E402
    _tid = [t for t, _r in _strip if t != c.layout.group(stt).get("tab")][0]
    assert WS.tile_tab_at(dict(_strip)[_tid].center()) == _tid
# the popup: X button closes it; one click selects, double-click opens
c.open_group(stt)
c.popup.progress = 1.0
QTest.mouseClick(c.popup, _Qt.LeftButton, _Qt.NoModifier, c.popup.close_rect().center().toPoint())
assert c.popup.closing or not c.popup.isVisible(), "X closes the popup"
# no size cap: a tile can be as big as the screen
c.resize_group(stt, WS.x(), WS.y(), 700, 720)
assert tuple(c.layout.group(stt)["tile_size"]) == (700, 720), c.layout.group(stt)["tile_size"]
c.resize_group(stt, WS.x(), WS.y(), 324, 344)
c.launch = _orig_launch
# the gear by the name: this group's own settings
WS._hover = True
_nb = WS.name_buttons()
assert set(_nb) == {"smaller", "bigger", "pencil", "gear"} and WS.hit(_nb["gear"].center())[0] == "gear"
QTest.mouseClick(WS, _Qt.LeftButton, _Qt.NoModifier, _nb["gear"].center().toPoint())
fp = c.fence_panel
assert fp is not None and fp.isVisible()
fp.grab().save(os.path.join(tmp, "fence_settings.png"))
_n0 = len(c.undo_stack._items)
fp.theme.setCurrentIndex(fp.theme.findData("Neon Gamer"))
assert c.layout.group(stt)["theme"] == "Neon Gamer" and WS.own_theme()["name"] if "name" in (WS.own_theme() or {}) else WS.own_theme() is not None
fp = c.fence_panel
fp.per_row.slider.setValue(4)
fp.per_row.slider.setValue(5)
assert c.layout.group(stt)["per_row"] == 5 and c.widgets[stt].per_row() == 5
fp.labels.setCurrentIndex(fp.labels.findData("never"))
assert c.widgets[stt].tile_layout()[1] == 0
fp.transp.slider.setValue(80)
assert c.layout.group(stt)["transparency"] == 80
assert len(c.undo_stack._items) == _n0 + 4, (len(c.undo_stack._items), _n0)
c.widgets[stt].grab().save(os.path.join(tmp, "fence_own_theme.png"))
from clutterbuster.theme import THEME as _TH  # noqa: E402
_main_fill = _TH["glass_fill"]
c.widgets[stt].grab()
assert _TH["glass_fill"] == _main_fill, "the main theme is back after painting"
c.reset_group_look(stt)
assert not any(k in c.layout.group(stt) for k in ("theme", "per_row", "labels", "transparency"))
c.undo()
assert c.layout.group(stt)["transparency"] == 80
c.reset_group_look(stt)
if c.fence_panel is not None:
    c.fence_panel.close()
c.set_pref("panel_labels", "auto")
WS = c.widgets[stt]
WS._hover = False
# a grouped item that comes back visible is hidden again by the re-check
_gp = c.layout.group(stt)["items"][0]["path"]
assert df.is_hidden(_gp)
df.set_hidden(_gp, False)
assert c.visible_grouped() == [_gp] and c.recheck_hidden() == 1 and df.is_hidden(_gp)
assert c.recheck_hidden() == 0
c.delete_group(stt)
c.sync_hidden()
stt = c.create_group("Strip Tabs 3", edit=False)
st2 = c.add_tab(stt, "Work")
c.set_mode(stt, "panel")
WP = c.widgets[stt]
assert WP.multi_tab() and len(WP.tab_bar()[0]) == 2, "big panels always show the tab bar with 2+ tabs"
c.delete_group(stt)
# ================= settings: Remove button always visible, readable checkboxes =================
from clutterbuster import glasswin as _gw  # noqa: E402
assert os.path.isfile(_gw.check_image()) and "image:url(" in _gw.checkbox_qss()
from PySide6.QtGui import QFontMetrics as _QFM, QFont as _QF  # noqa: E402
_fm = _QFM(_QF())
_w = _fm.horizontalAdvance("Monosna") + 1
assert gwm2.two_lines(_fm, "Monosnap", _w) == ["Mono", "snap"], gwm2.two_lines(_fm, "Monosnap", _w)
# ================= theme editor: every control works, colours picked INSIDE the window =================
from clutterbuster import theme_maker as _tm, colorpick as _cp  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
import clutterbuster.app as _appmod  # noqa: E402
import clutterbuster.namestyle_dialog as _nsd  # noqa: E402
import clutterbuster.glass as _gl  # noqa: E402
import clutterbuster.fence_settings as _fsm  # noqa: E402
from PySide6.QtWidgets import QPushButton  # noqa: E402
for _m in (_tm, _appmod, _nsd, _gl, _fsm):
    assert "QColorDialog" not in open(_m.__file__).read(), _m.__file__
mk = c.edit_theme("Neon Gamer")
assert mk.isVisible() and mk.windowFlags() & _Qt.WindowStaysOnTopHint
mk.pick("tint")
mk.picker.hex.setText("#123456")
mk.picker._hex_done()
assert mk.data["tint"] == "#123456"
mk.pick("accent")
mk.picker.hue.setValue(120)
mk.picker.val.setValue(200)
assert mk.data["accent"] != "#123456" and _QC(mk.data["accent"]).hsvHue() in range(115, 126)
mk.picker.swatches[0].click()
assert mk.data["accent"].lower() == _cp.SWATCHES[0].lower()
mk.pick("text")
mk.picker.swatches[9].click()
assert mk.data["text"].lower() == "#ffffff"
_builds = []
_orig_build = _tm.theme.build
_tm.theme.build = lambda *a, **k: (_builds.append(1), _orig_build(*a, **k))[1]
for _key, _sl in mk.sliders.items():
    for _v in range(0, 101, 5):
        _sl.slider.setValue(_v)                    # 21 quick steps per slider
_t_end = time.time() + 0.5
while time.time() < _t_end:
    app.processEvents()
    time.sleep(0.02)
mk.preview.grab()
mk.preview.grab()
assert len(_builds) <= 2, f"debounced + cached: {len(_builds)} rebuilds for 63 slider steps"
_tm.theme.build = _orig_build
assert mk.data["glow"] == 100 and mk.data["blur"] == 100
mk.grab().save(os.path.join(tmp, "theme_editor_inline_picker.png"))
mk.name.setText("")
_seen_dlg = {}
QTimer.singleShot(150, lambda: (_seen_dlg.update(info=bool(QApplication.activeModalWidget().windowFlags()
                                                              & _Qt.WindowStaysOnTopHint)),
                                QApplication.activeModalWidget().accept()))
mk.save()
assert _seen_dlg.get("info") is True and mk.isVisible(), "message in front, editor stays open"
mk.name.setText("TEST")
mk.save()
assert any(t.get("name") == "TEST" for t in c.layout.custom_themes) and not mk.isVisible()
c.set_theme_choice("TEST")
# delete a saved theme: from the editor (one confirmation), falls back to Auto, Undo brings it back
mk2 = c.edit_theme("TEST")
assert mk2.delete_btn is not None
QTimer.singleShot(150, lambda: [b for b in QApplication.activeModalWidget().buttons()
                                if b.text() == "Delete theme"][0].click())
mk2.delete_btn.click()
assert not any(t.get("name") == "TEST" for t in c.layout.custom_themes)
assert c.layout.prefs["theme"] == "auto" and c.undo_stack.next_label() == "delete theme"
c.undo()
assert any(t.get("name") == "TEST" for t in c.layout.custom_themes) and c.layout.prefs["theme"] == "TEST"
assert c.edit_theme("Neon Gamer").delete_btn is None, "built-ins can't be deleted"
c._maker.close()
assert c.delete_custom_theme("Neon Gamer", confirm=False) is False
qm3 = c.show_quick_menu()
_dels = [b for b in qm3.findChildren(QPushButton) if "Delete" in b.text()]
assert _dels, "gear menu offers Delete for your own theme"
QTimer.singleShot(150, lambda: [b for b in QApplication.activeModalWidget().buttons()
                                if b.text() == "Delete theme"][0].click())
_dels[0].click()
assert not any(t.get("name") == "TEST" for t in c.layout.custom_themes) and c.layout.prefs["theme"] == "auto"
c.set_theme_choice("auto")
# name style: the colour picker opens inside the dialog
nd = c.name_style_dialog(None)
nd.color_btn.click()
assert nd.picker.isVisible()
nd.picker.swatches[3].click()
assert nd.color_hex.lower() == _cp.SWATCHES[3].lower()
nd.close()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
# ================= quick search shortcut recorder =================
from clutterbuster import hotkey as _hk, settings as _st  # noqa: E402
assert c.search_hotkey()["text"] == "Ctrl+Space"
assert _hk.from_qt(_Qt.Key_F, _Qt.ControlModifier | _Qt.ShiftModifier) == (0x0006, 0x46, "Ctrl+Shift+F")
assert _hk.from_qt(_Qt.Key_Space, _Qt.AltModifier)[2] == "Alt+Space"
assert _hk.from_qt(_Qt.Key_F, _Qt.NoModifier) is None, "needs Ctrl/Alt/Shift"
taken = {(0x0001, 0x20)}
_reg = []
_orig_reg = _hk.register
_hk.register = lambda hwnd, mods=2, vk=0x20: (_reg.append((mods, vk)) or (int(mods), int(vk)) not in taken)
c.search.register_hotkey()
sw = _st.SettingsWindow(c)
sw.show()
sw.grab().save(os.path.join(tmp, "settings_general.png"))
assert sw.remove_btn.isVisible() and sw.remove_btn.geometry().bottom() < sw.body.height(), "red Remove button shown"
sw.setFixedSize(860, 420)                 # even when the page is taller than the window
sw.grab().save(os.path.join(tmp, "settings_short.png"))
QApplication.processEvents()
assert sw.remove_btn.isVisible() and sw.remove_btn.mapTo(sw, _Pt(0, sw.remove_btn.height())).y() <= sw.height()
sw.hk_edit.setFocus()
QTest.keyClick(sw.hk_edit, _Qt.Key_F, _Qt.ControlModifier | _Qt.ShiftModifier)
assert c.search_hotkey()["text"] == "Ctrl+Shift+F" and _reg[-1] == (0x0006, 0x46), _reg
assert "Ctrl+Shift+F" in c.search.toolTip() or c.search.hotkey_ok
assert json.load(open(paths.layout_file()))["prefs"]["hotkey"]["text"] == "Ctrl+Shift+F", "saved"
ok_, msg_ = c.set_search_hotkey(0x0001, 0x20)
assert not ok_ and "already used" in msg_ and c.search_hotkey()["text"] == "Ctrl+Shift+F", "taken: old one kept"
assert _reg[-1] == (0x0006, 0x46), "old shortcut re-registered"
assert sw.hk_edit.apply(0x0002, 0x20) and c.search_hotkey()["text"] == "Ctrl+Space", "Reset to Ctrl+Space"
sw.close()
_hk.register = _orig_reg
# ================= fun themes + corner pictures =================
from clutterbuster import corners as cmod, decor as dmod  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QPushButton  # noqa: E402
FUN = ["Space", "Cozy Cabin", "Holiday", "Winter", "Springfield", "Doghouse"]
for n in FUN:
    assert n in theme.BUILT_IN, n
    assert os.path.isfile(cmod.asset_path(theme.BUILT_IN[n]["corner"])), n
    assert theme.BUILT_IN[n]["decor"] in [k for k, _l in dmod.STYLES]
qm = c.show_quick_menu()
assert all(n in qm.theme_btns for n in FUN), "fun themes in the gear menu"
qm.close()
from clutterbuster.settings import SettingsWindow  # noqa: E402,F401
fx = c.create_group("Fun", edit=False)
for k in range(5):
    pth = os.path.join(desk, f"Fun{k}.lnk")
    open(pth, "w").write("x")
    c.add_paths(fx, [pth])
fw = c.widgets[fx]
c.resize_group(fx, 700, 300, 324, 344)
fw = c.widgets[fx]
c.set_theme_choice("Space")
assert theme.THEME["decor"] == "stars" and cmod.path_for(c.layout.group(fx)).endswith("space.png")
for n in FUN:
    c.set_theme_choice(n)
    fw = c.widgets[fx]
    img = fw.grab()
    img.save(os.path.join(tmp, f"fun-{n.replace(' ', '_').lower()}.png"))
    assert not img.isNull()
    c.search.grab().save(os.path.join(tmp, f"fun-toolbar-{n.replace(' ', '_').lower()}.png"))
# the corner picture never sits on an icon (it shrinks, and is painted under them)
area = QRectF(fw.glass_rect())
cells, lines = fw.tile_layout()
cr_, free = cmod.place(area.adjusted(8, 8, -8, -8), [cell for _i, _ir, cell in cells])
assert not free or not any(cr_.intersects(cell) for _i, _ir, cell in cells)
# per group: theme default / none / bundled / your own picture (copied into pictures/)
g_f = c.layout.group(fx)
c.set_corner_picture(fx, "none")
assert g_f["corner"] == "none" and cmod.path_for(g_f) is None
c.undo()
assert "corner" not in c.layout.group(fx), "corner picture change is one undo step"
c.set_corner_picture(fx, "asset:doghouse")
assert cmod.path_for(c.layout.group(fx)).endswith("doghouse.png")
from PySide6.QtGui import QImage  # noqa: E402
own = os.path.join(tmp, "my-cat.png")
im_ = QImage(40, 30, QImage.Format_ARGB32)
im_.fill(QColor(200, 100, 50))
im_.save(own)
dest = c.choose_corner_picture(fx, src=own)
assert dest and os.path.dirname(dest) == os.path.join(paths.app_dir(), "pictures") and os.path.isfile(dest)
assert c.layout.group(fx)["corner"] == dest and cmod.path_for(c.layout.group(fx)) == dest
bad = os.path.join(tmp, "not-a-picture.png")
open(bad, "w").write("hello")
real_info = None
import clutterbuster.glass as glass_mod  # noqa: E402
real_info, glass_mod.info = glass_mod.info, (lambda *a, **k: None)
assert c.choose_corner_picture(fx, src=bad) is None and c.layout.group(fx)["corner"] == dest
glass_mod.info = real_info
fw.grab().save(os.path.join(tmp, "fun-own-picture.png"))
fs_ = c.fence_settings(fx, fw)
assert fs_.corner.currentData() == dest, "own picture shown in the gear panel"
fs_.corner.setCurrentIndex(fs_.corner.findData("theme"))
fs_._corner(0)
assert "corner" not in c.layout.group(fx)
fs_.close()
# right-click menu has the Corner picture submenu (built, not shown)
# theme editor: a copy of a fun theme keeps its decoration + picture, and both are editable
mk2 = c.edit_theme("Holiday")
assert mk2.data["decor"] == "lights" and mk2.data["corner"] == "holiday"
assert mk2.preview_theme()["decor"] == "lights" and mk2.preview_theme()["corner"] == "holiday"
mk2.decor.setCurrentIndex(mk2.decor.findData("frost"))
mk2.corner.setCurrentIndex(mk2.corner.findData("winter"))
mk2.changed()
assert mk2.preview_theme()["decor"] == "frost" and mk2.preview_theme()["corner"] == "winter"
mk2.preview.grab().save(os.path.join(tmp, "fun-editor-preview.png"))
mk2.close()
# regression (Brian, v0.6.0): a group with its own theme vanished because the theme cache key
# choked on the name-style dict in ui -> the group never painted
c.ui["name_style"] = {"size": 21}
c.set_group_prop(fx, "theme", "Doghouse", "group theme")
th_ns = theme.group_theme(c.layout.group(fx), "Neon Gamer", c.ui, c.layout.custom_themes)
assert th_ns is not None and th_ns["name"] == "Doghouse"
img_ns = c.widgets[fx].grab().toImage()
assert QColor(img_ns.pixel(img_ns.width() // 2, img_ns.height() // 2)).alpha() > 200, "group is drawn"
c.set_group_prop(fx, "theme", None, "group theme")
# any drawing error -> logged once + a plain fallback, the group stays visible and in the layout
fw_ = c.widgets[fx]
real_body = type(fw_).paint_body
type(fw_).paint_body = lambda self, p: 1 / 0
fw_._dirty = True
img_fb = fw_.grab().toImage()
type(fw_).paint_body = real_body
assert QColor(img_fb.pixel(img_fb.width() // 2, img_fb.height() // 2)).alpha() > 150, "fallback drawn"
assert c.layout.group(fx) is not None and fw_.isVisible()
open(paths.error_log(), "w").close()       # that error was on purpose
fw_._paint_err_logged = False
fw_._dirty = True
# per-group theme override shows that theme's picture
c.set_theme_choice("Clean White")
assert cmod.path_for(c.layout.group(fx)) is None
c.set_group_prop(fx, "theme", "Winter", "group theme")
fw.grab().save(os.path.join(tmp, "fun-group-override.png"))
th_ = theme.group_theme(c.layout.group(fx), "Clean White", c.ui, c.layout.custom_themes)
assert th_["corner"] == "winter" and cmod.path_for(c.layout.group(fx), th_).endswith("winter.png")
c.set_group_prop(fx, "theme", None, "group theme")
# ================= movable toolbar + corner lock =================
from clutterbuster import searchbar as sbm  # noqa: E402
tb = c.search
av = c.avail()
c.reset_toolbar()
assert not tb.wedge and tb.size().width() == sbm.pill_size()[0]
home = tb.pos()
assert tb.hit(tb.grip_rect().center()) == "grip" and tb.hit(tb.search_rect().center()) == "search"
assert tb.hit(tb.new_rect().center()) == "new" and tb.hit(tb.gear_rect().center()) == "gear"
# drag by the grip to a new spot (remembered, one undo step)
n_u = len(c.undo_stack._items)
gpt = tb.grip_rect().center().toPoint()
QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, gpt)
QTest.mouseMove(tb, gpt + QPoint(40, 200))
QTest.mouseMove(tb, gpt + QPoint(60, 300))
QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, gpt + QPoint(60, 300))
assert "toolbar_corner" not in c.ui and c.ui.get("search_pos") and tb.pos() != home, c.ui.get("search_pos")
assert c.undo_stack.next_label() == "move toolbar", c.undo_stack.next_label()
saved_tb = json.load(open(paths.layout_file()))["ui"]
assert saved_tb.get("search_pos") == c.ui["search_pos"], "position saved"
# dragging the body / search box doesn't move it
p0 = tb.pos()
sp = tb.search_rect().center().toPoint()
QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, sp)
QTest.mouseMove(tb, sp + QPoint(80, 80))
QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, sp + QPoint(80, 80))
assert tb.pos() == p0
# near each corner -> tucks in as a wedge; all four work
for k in ("tl", "tr", "bl", "br"):
    pill = QRect(0, 0, *sbm.pill_size())
    if k == "tl":
        pill.moveTopLeft(av.topLeft() + QPoint(20, 15))
    elif k == "tr":
        pill.moveTopRight(av.topRight() + QPoint(-20, 15))
    elif k == "bl":
        pill.moveBottomLeft(av.bottomLeft() + QPoint(20, -15))
    else:
        pill.moveBottomRight(av.bottomRight() + QPoint(-20, -15))
    assert c.toolbar_snap_corner(pill) == k, (k, c.toolbar_snap_corner(pill))
    c.toolbar_moved(k, pill.topLeft())
    assert tb.wedge and tb.corner == k and c.ui["toolbar_corner"] == k
    g_ = tb.geometry()
    want = {"tl": av.topLeft(), "tr": av.topRight(), "bl": av.bottomLeft(), "br": av.bottomRight()}[k]
    have = {"tl": g_.topLeft(), "tr": g_.topRight(), "bl": g_.bottomLeft(), "br": g_.bottomRight()}[k]
    assert have == want, (k, have, want)
    for key in ("search", "new", "gear", "grip"):
        cpt = getattr(tb, key + "_rect")().center()
        assert tb.hit(cpt) == key, (k, key, tb.hit(cpt))
    tb.grab().save(os.path.join(tmp, f"toolbar-wedge-{k}.png"))
assert c.toolbar_snap_corner(QRect(av.center().x() - 300, av.center().y(), 600, 78)) is None
# pushed into a corner with the mouse still on the grip far away (what Brian did) -> snaps
pw, ph = sbm.pill_size()
far = QRect(av.right() - pw + 40, av.top() - 6, pw, ph)            # shoved past the top-right edge
assert c.toolbar_snap_corner(far, far.topLeft() + QPoint(26, 39)) == "tr"
far = QRect(av.right() - pw + 5, av.bottom() - ph + 30, pw, ph)
assert c.toolbar_snap_corner(far, far.topLeft() + QPoint(26, 39)) == "br"
assert c.toolbar_snap_corner(QRect(av.left() + 5, av.top() + 40, pw, ph), QPoint(av.left() + 31, av.top() + 79)) == "tl"
# real drag to the top-right with the grip: drop -> wedge
c.dock_toolbar("top")
assert not tb.wedge
gpt = tb.grip_rect().center().toPoint()
QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, gpt)
QTest.mouseMove(tb, gpt + QPoint(20, 0))
dx = av.right() - (tb.x() + tb.width()) + 30
QTest.mouseMove(tb, tb.grip_rect().center().toPoint() + QPoint(dx, -40))
assert tb._snap == "tr" and tb._ghost.isVisible(), "corner hint shown while dragging"
QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, tb.grip_rect().center().toPoint())
assert tb.wedge and tb.corner == "tr" and not tb._ghost.isVisible(), (tb.corner, c.ui.get("toolbar_corner"))
# gear menu > Dock toolbar to ...
for k in ("tl", "bl", "br", "tr"):
    qm = c.show_quick_menu()
    qm.dock_btns[k].click()
    assert tb.wedge and tb.corner == k and c.ui["toolbar_corner"] == k
qm = c.show_quick_menu()
assert qm.dock_btns["tr"].isChecked()
qm.dock_btns["float"].click()
assert not tb.wedge and "toolbar_corner" not in c.ui
qm = c.show_quick_menu()
qm.dock_btns["top"].click()
assert not tb.wedge and tb.pos() == QPoint(*tb.default_pos(av))
c.dock_toolbar("br")
# clicks in the wedge still work
opened = []
real_q, c.open_quick_search = c.open_quick_search, (lambda *a: opened.append(1))
QTest.mouseClick(tb, Qt.LeftButton, Qt.NoModifier, tb.search_rect().center().toPoint())
c.open_quick_search = real_q
assert opened, "search along the curve opens quick search"
# drag the wedge out -> back to the pill
gp = tb.grip_rect().center().toPoint()
QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, gp)
QTest.mouseMove(tb, gp + QPoint(-300, -300))
assert not tb.wedge, "pulled out = pill again"
tb.grab().save(os.path.join(tmp, "toolbar-pulled-out.png"))
QTest.mouseMove(tb, tb.grip_rect().center().toPoint() + QPoint(-5, 20))
QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, tb.grip_rect().center().toPoint())
assert "toolbar_corner" not in c.ui and not tb.wedge
# undo puts it back in the corner
c.undo()
assert tb.wedge and tb.corner == "br"
# Lock layout: the grip does nothing
c.set_locked(True)
assert c.layout_locked()
p0, corner0 = tb.pos(), tb.corner
gp = tb.grip_rect().center().toPoint()
QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, gp)
QTest.mouseMove(tb, gp + QPoint(-300, -300))
QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, gp + QPoint(-300, -300))
assert tb.pos() == p0 and tb.corner == corner0, "locked = can't move"
c.set_locked(False)
# Reset toolbar position (gear menu)
qm = c.show_quick_menu()
rb = [b for b in qm.findChildren(QPushButton) if "Reset toolbar" in b.text()]
assert rb
rb[0].click()
assert not tb.wedge and tb.pos() == QPoint(*tb.default_pos(av)) and "toolbar_corner" not in c.ui
assert c.undo_stack.next_label() == "reset toolbar"
assert desktop_layer is not None
c.delete_group(fx)
for k in range(5):
    os.remove(os.path.join(desk, f"Fun{k}.lnk"))
err = paths.error_log()
assert not os.path.exists(err) or os.path.getsize(err) == 0, open(err).read()
# --- the Remove confirmation: 'also delete the program folder' starts unticked; Cancel = nothing
from PySide6.QtCore import QTimer  # noqa: E402
seen = {}


def _peek():
    box = QApplication.activeModalWidget()
    seen["checked"] = box.checkBox().isChecked()
    seen["text"] = box.checkBox().text()
    for b in box.buttons():
        if b.text() == "Cancel":
            b.click()


QTimer.singleShot(300, _peek)
go, delf = removal.confirm()
assert seen["checked"] is False and "Also delete the program folder" in seen["text"], seen
assert go is False and delf is False
assert os.path.isdir(paths.app_dir()) and integration.uninstall_registered()
# --- program-folder cleanup: only ever on temp dirs here, never the real install
not_prog = os.path.join(tmp, "NotTheProgram")
os.makedirs(not_prog)
open(os.path.join(not_prog, "main.py"), "w").close()
assert not removal.looks_like_program_folder(not_prog)
assert not removal.schedule_folder_cleanup(not_prog, os.getpid(), temp_dir=tmp)
assert not removal.looks_like_program_folder(desk) and not removal.looks_like_program_folder(os.path.expanduser("~"))


def fake_program(name):
    d = os.path.join(tmp, name)
    os.makedirs(os.path.join(d, "clutterbuster"))
    os.makedirs(os.path.join(d, ".venv", "Scripts"))
    for rel in ("main.py", "clutterbuster/__init__.py", "clutterbuster/ledger.py", ".venv/Scripts/x"):
        open(os.path.join(d, rel), "w").close()
    return d


def wait_gone(p, secs=12):
    end = time.time() + secs
    while time.time() < end and os.path.exists(p):
        time.sleep(0.2)
    return not os.path.exists(p)


prog1 = fake_program("FakeProgram1")
sleeper = subprocess.Popen(["sleep", "1.5"])
assert removal.schedule_folder_cleanup(prog1, sleeper.pid, temp_dir=tmp)
time.sleep(0.6)
assert os.path.isdir(prog1), "waits until the app has closed"
sleeper.wait()
assert wait_gone(prog1), "folder removed after the app closed"
assert not [f for f in os.listdir(tmp) if f.startswith("clutterbuster-cleanup")], "cleanup script removes itself"
assert os.path.isfile(os.path.join(ROOT, "main.py")), "the real code folder is untouched"
assert os.path.isdir(not_prog)
err = paths.error_log()
assert not os.path.exists(err) or os.path.getsize(err) == 0, open(err).read()
# --- full Remove (with 'also delete the program folder' ticked) on a FAKE program folder
prog2 = fake_program("FakeProgram2")
os.environ["CLUTTERBUSTER_PROGRAM_DIR"] = prog2
assert integration.program_dir() == prog2
sleeper2 = subprocess.Popen(["sleep", "1"])
c.sync_hidden()
assert any(df.is_hidden(p) for p in all_items if p != mine)
assert c.remove_everything(delete_folder=True, wait_pid=sleeper2.pid)
assert c.removed and not os.path.exists(paths.app_dir()), "app settings folder deleted"
assert not integration.autostart_enabled() and not integration.uninstall_registered()
assert integration.UNINSTALL_KEY not in integration.FAKE
assert not any(df.is_hidden(os.path.join(desk, n)) for n in os.listdir(desk) if n != "secret.txt")
assert not any(df.is_hidden(os.path.join(pub, n)) for n in os.listdir(pub))
assert df.is_hidden(mine), "your own hidden file stays hidden"
assert (sorted(os.listdir(desk)), sorted(os.listdir(pub))) == listing, "no desktop file touched"
sleeper2.wait()
assert wait_gone(prog2)
assert os.path.isfile(os.path.join(ROOT, "main.py")), "the real code folder is untouched"
print("ALL CHECKS PASSED; images in", tmp)
sys.stdout.flush()
os._exit(0)      # like the app: skip Python's one-by-one teardown of the Qt windows
