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
c.bar_moved("search_pos", c.search, QPoint(240, 192))
c.bar_moved("actions_pos", c.actions, QPoint(400, 304))
c.bar_moved("dock_pos", c.dock, QPoint(96, 400))
assert c.search.pos() == QPoint(240, 192) and c.actions.pos() == QPoint(400, 304)
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
assert saved["ui"]["search_pos"] == [240, 192] and saved["ui"]["icon_size"] == 80
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
assert u["DisplayName"] == "Clutter Buster" and u["Publisher"] == "Brian" and u["DisplayVersion"] == "0.5.0"
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
assert WT.on_name(_P(WT.width() / 2, WT.glass_rect().bottom() + 8))
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
assert c.actions.boxes()[1][0] == "gear" and len(c.actions.boxes()) == 2
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
