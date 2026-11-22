"""--showcase: a safe demo for screenshots.

Uses a throw-away settings folder, pretend groups made of harmless built-in Windows
programs (Notepad, Calculator, ...) and a pretend desktop folder in %TEMP%. It never
looks at or touches your real desktop items, and nothing is launched or applied. Windows are shown on top for the
screenshot only, then the demo closes itself.
"""
import logging
import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from . import desktop_layer


def _sys_items(names):
    root = os.environ.get("SystemRoot", r"C:\Windows")
    out = []
    for n in names:
        for base in (os.path.join(root, "System32"), root):
            p = os.path.join(base, n)
            if os.path.exists(p):
                out.append({"path": p})
                break
    return out


def make_demo_desktop():
    """A pretend desktop in %TEMP%: shortcuts to harmless built-in Windows programs plus a few
    empty demo files/folders. Your real desktop is never read or touched."""
    import tempfile
    d = tempfile.mkdtemp(prefix="clutterbuster-demo-desktop-")
    root = os.environ.get("SystemRoot", r"C:\Windows")
    s32 = os.path.join(root, "System32")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    links = [
        ("Game Controllers", os.path.join(s32, "joy.cpl")),
        ("Steam (demo)", os.path.join(s32, "joy.cpl")),
        ("LM Studio (demo)", os.path.join(s32, "cmd.exe")),
        ("Ollama (demo)", os.path.join(s32, "WindowsPowerShell", "v1.0", "powershell.exe")),
        ("Microsoft Edge", os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe")),
        ("Notepad", os.path.join(s32, "notepad.exe")),
        ("Calculator", os.path.join(s32, "calc.exe")),
        ("Task Manager", os.path.join(s32, "Taskmgr.exe")),
        ("Control Panel", os.path.join(s32, "control.exe")),
        ("Paint", os.path.join(s32, "mspaint.exe")),
        ("Windows Media Player", os.path.join(pf, "Windows Media Player", "wmplayer.exe")),
        ("Character Map", os.path.join(s32, "charmap.exe")),
        ("Magnifier", os.path.join(s32, "Magnify.exe")),
    ]
    made_links = False
    if sys.platform == "win32":
        import subprocess
        lines = ["$s = New-Object -ComObject WScript.Shell"]
        for name, target in links:
            if os.path.exists(target):
                lp = os.path.join(d, name + ".lnk").replace("'", "''")
                lines.append(f"$l = $s.CreateShortcut('{lp}'); $l.TargetPath = '{target}'; $l.Save()")
        try:
            subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                            "; ".join(lines)], timeout=30, creationflags=0x08000000)
            made_links = True
        except Exception:
            logging.getLogger("cb").exception("showcase: could not make demo shortcuts")
    if not made_links:
        for name, _t in links:
            open(os.path.join(d, name + ".lnk"), "wb").close()
    for name in ("Budget 2026.xlsx", "Notes.txt", "Recipe.pdf", "Holiday photo.jpg"):
        open(os.path.join(d, name), "wb").close()
    for name in ("Old Projects", "Screenshots"):
        os.makedirs(os.path.join(d, name), exist_ok=True)
    with open(os.path.join(d, "YouTube.url"), "w", encoding="utf-8") as f:
        f.write("[InternetShortcut]\nURL=https://www.youtube.com/\n")
    return d


class Backdrop(QWidget):
    """A plain full-screen 'wallpaper' behind the demo windows, so the demo pictures show only
    pretend items - never your real desktop icons, groups or open windows."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setGeometry(QApplication.primaryScreen().geometry())

    PALETTES = {   # pretend wallpapers for the fun-theme pictures (top, middle, bottom)
        "Space": ((6, 6, 22), (30, 16, 70), (4, 10, 30)),
        "Holiday": ((40, 10, 12), (70, 22, 18), (20, 8, 8)),
        "Winter": ((120, 160, 205), (170, 200, 230), (80, 110, 150)),
        "Springfield": ((90, 170, 245), (150, 205, 250), (110, 180, 90)),
        "Doghouse": ((150, 200, 235), (190, 225, 245), (110, 170, 80)),
        "Cozy Cabin": ((60, 50, 30), (120, 90, 50), (30, 40, 25)),
    }

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        pal = self.PALETTES.get(os.environ.get("CLUTTERBUSTER_SHOWCASE_THEME", ""))
        if pal:
            for k, col in zip((0, 0.6, 1), pal):
                g.setColorAt(k, QColor(*col))
            p.fillRect(self.rect(), g)
            if os.environ.get("CLUTTERBUSTER_SHOWCASE_THEME") == "Space":
                import random
                rnd = random.Random(7)
                for _ in range(500):
                    a = rnd.randint(60, 220)
                    p.fillRect(int(rnd.random() * w), int(rnd.random() * h), 2, 2, QColor(255, 255, 255, a))
            p.end()
            return
        g.setColorAt(0, QColor(14, 12, 40))
        g.setColorAt(0.6, QColor(45, 20, 85))
        g.setColorAt(1, QColor(8, 22, 40))
        p.fillRect(self.rect(), g)
        rg = QRadialGradient(w * 0.7, h * 0.2, w * 0.4)
        rg.setColorAt(0, QColor(0, 255, 160, 70))
        rg.setColorAt(1, QColor(0, 255, 160, 0))
        p.fillRect(self.rect(), rg)
        p.end()


def run_showcase(out_png):
    """Makes two pictures from a pretend desktop: OUT.png (the 'Automatically do it' review
    window) and OUT-settings.png (Settings > General with Start with Windows)."""
    import shutil
    desktop_layer.SHOWCASE[0] = True
    demo = make_demo_desktop()
    os.environ["CLUTTERBUSTER_DEMO_DESKTOP"] = demo
    from .app import Controller
    from .tray import broom_icon
    from .store import Layout
    lay = Layout()
    lay.prefs["theme"] = os.environ.get("CLUTTERBUSTER_SHOWCASE_THEME", "Neon Gamer")
    lay.prefs["autostart"] = True
    lay.save()
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(broom_icon())
    backdrop = Backdrop()
    backdrop.show()            # first, so every demo window stacks above it
    c = Controller(app, showcase=True)
    log = logging.getLogger("cb")

    util = c.create_group("Utilities", edit=False, items=_sys_items(
        ["notepad.exe", "calc.exe", "mspaint.exe", "cmd.exe", "taskmgr.exe", "charmap.exe"]))
    c.set_accent(util, "#00D2FF")
    c.clear_badge(util)
    tools = c.create_group("Windows Tools", edit=False, mode="panel", items=_sys_items(
        ["explorer.exe", "regedit.exe", "msinfo32.exe", "cleanmgr.exe", "dxdiag.exe", "perfmon.exe"]))
    c.set_accent(tools, "#9B5CFF")
    c.clear_badge(tools)
    ai = c.create_group("AI", edit=False, items=[
        {"path": "https://huggingface.co/", "title": "Hugging Face"}])
    c.set_accent(ai, "#BF5AF2")
    c.clear_badge(ai)
    web = c.create_group("Websites", edit=False, items=[
        {"path": "https://github.com/", "title": "GitHub"}])
    c.set_accent(web, "#30D158")
    c.clear_badge(web)
    for it in _sys_items(["notepad.exe", "calc.exe", "explorer.exe", "cmd.exe", "taskmgr.exe"]):
        c.add_favorite(it["path"])
    c.undo_stack._items.clear()
    c.update_undo_ui()
    c.layout.save()
    c.rebuild_widgets()
    c.layer_timer.stop()       # demo windows are "on top"; don't re-stack them
    c.dock.pinned = True
    c.dock.show_dock()
    base, ext = os.path.splitext(out_png)
    ext = ext or ".png"

    def shot(path):
        QGuiApplication.primaryScreen().grabWindow(0).save(path)
        log.info("showcase: saved %s", path)

    if os.environ.get("CLUTTERBUSTER_SHOWCASE_SCENE") == "tabs":
        return _tabs_scene(app, c, demo, out_png, shot, log, shutil)
    if os.environ.get("CLUTTERBUSTER_SHOWCASE_SCENE") == "fun":
        return _fun_scene(app, c, demo, out_png, shot, log, shutil)

    def step1():
        for w in [c.search, c.actions, c.dock, *c.widgets.values()]:
            desktop_layer.make_topmost(int(w.winId()))   # re-stack the demo windows above the backdrop
        c.auto_organize()
        QTimer.singleShot(1000, step2)

    def step2():
        shot(out_png)
        log.info("showcase: suggestions %s",
                 [(s["name"], len(s["items"]), bool(s.get("gid"))) for s in c.organize_win.plan])
        c.organize_win.close()     # Cancel: nothing changes
        win = c.show_settings(0)   # General
        win.autostart.blockSignals(True)
        win.autostart.setChecked(True)   # demo: show it as on (no registry in demo mode)
        win.autostart.blockSignals(False)
        QTimer.singleShot(900, step3)

    def step3():
        shot(base + "-settings" + ext)
        log.info("showcase: done (theme %s)", c.theme_name)
        app.quit()

    QTimer.singleShot(700, step1)
    QTimer.singleShot(20000, app.quit)  # safety net
    rc = app.exec()
    shutil.rmtree(demo, ignore_errors=True)   # our own pretend desktop in %TEMP%
    return rc


def _tabs_scene(app, c, demo, out_png, shot, log, shutil):
    """v0.5 demo: big panels with tabs (icons + list view), bigger names, and the gear menu open.
    Pretend items only (built-in Windows programs and empty files in the %TEMP% demo desktop)."""
    from .store import new_tab
    av = c.avail()
    files = [{"path": os.path.join(demo, n)} for n in
             ("Budget 2026.xlsx", "Notes.txt", "Recipe.pdf", "Holiday photo.jpg", "Old Projects", "Screenshots")]

    def tabbed(name, x, y, w, h, accent, tabs, current, view=None):
        gid = c.create_group(name, edit=False, mode="panel")
        g = c.layout.group(gid)
        g["tabs"], g["items"] = [], []
        for tname, items in tabs:
            t = new_tab(tname)
            g["tabs"].append(t)
            for it in items:
                g["items"].append(dict(it, tab=t["id"]))
        g["tab"] = g["tabs"][current]["id"]
        if view:
            g["tabs"][current]["view"] = view
        g["x"], g["y"], g["panel_size"] = av.left() + x, av.top() + y, [w, h]
        g["accent"], g["badge"] = accent, 0
        return gid

    tabbed("My Stuff", 330, 110, 460, 300, "#00D2FF",
           [("Apps", _sys_items(["notepad.exe", "calc.exe", "mspaint.exe", "charmap.exe", "magnify.exe"])),
            ("Tools", _sys_items(["cmd.exe", "taskmgr.exe", "regedit.exe", "msinfo32.exe", "dxdiag.exe",
                                  "cleanmgr.exe", "perfmon.exe"])),
            ("Files", files)], current=1)
    tabbed("Documents", 330, 440, 540, 250, "#FF9F0A",
           [("Files", files), ("Apps", _sys_items(["notepad.exe", "write.exe"]))], current=0, view="list")
    for gid in list(c.widgets):
        g = c.layout.group(gid)
        if g and g["name"] in ("Windows Tools",):
            g["x"], g["y"] = av.left() + 900, av.top() + 150
    c.undo_stack._items.clear()
    c.commit()

    def step1():
        for w in [c.search, c.actions, c.dock, *c.widgets.values()]:
            desktop_layer.make_topmost(int(w.winId()))
        r = c.actions.gear_rect()
        from PySide6.QtCore import QRect
        c.show_quick_menu(QRect(c.actions.mapToGlobal(r.topLeft().toPoint()), r.size().toSize()))
        QTimer.singleShot(900, step2)

    def step2():
        shot(out_png)
        if c.quick_menu is not None:
            c.quick_menu.close()
        log.info("showcase: tabs scene done (theme %s)", c.theme_name)
        app.quit()

    QTimer.singleShot(900, step1)
    QTimer.singleShot(20000, app.quit)
    rc = app.exec()
    shutil.rmtree(demo, ignore_errors=True)
    return rc


def _fun_scene(app, c, demo, out_png, shot, log, shutil):
    """v0.6 demo: a fun theme with corner pictures on tiles and a panel with tabs, and the toolbar
    as a pill or tucked into a corner (CLUTTERBUSTER_SHOWCASE_CORNER=tr). Pretend items only."""
    from .store import new_tab
    av = c.avail()
    for gid in list(c.widgets):            # start from just our own demo groups
        c.delete_group(gid)
    files = [{"path": os.path.join(demo, n)} for n in
             ("Budget 2026.xlsx", "Notes.txt", "Recipe.pdf", "Holiday photo.jpg", "Old Projects", "Screenshots")]

    def group(name, x, y, w, h, mode, tabs, accent):
        gid = c.create_group(name, edit=False, mode=mode)
        g = c.layout.group(gid)
        g["tabs"], g["items"] = [], []
        for tname, items in tabs:
            t = new_tab(tname)
            g["tabs"].append(t)
            for it in items:
                g["items"].append(dict(it, tab=t["id"]))
        g["tab"] = g["tabs"][0]["id"]
        g["x"], g["y"] = av.left() + x, av.top() + y
        if mode == "panel":
            g["panel_size"] = [w, h]
        else:
            g["tile_size"] = [w, h]
        g["accent"], g["badge"] = accent, 0
        g["per_row"] = 3
        return gid

    group("Games", 170, 130, 520, 380, "panel",
          [("Games", _sys_items(["joy.cpl", "mspaint.exe", "calc.exe", "notepad.exe", "charmap.exe", "magnify.exe"])),
           ("AI", _sys_items(["cmd.exe", "WindowsPowerShell/v1.0/powershell.exe"])), ("Tools", files)], None)
    group("Work", 730, 130, 324, 300, "tile",
          [("Work", files[:5])], None)
    group("Windows", 1090, 130, 324, 300, "tile",
          [("Main", _sys_items(["taskmgr.exe", "control.exe", "regedit.exe", "msinfo32.exe", "dxdiag.exe"])),
           ("More", _sys_items(["cleanmgr.exe"]))], None)
    corner = os.environ.get("CLUTTERBUSTER_SHOWCASE_CORNER")
    if corner:
        c.ui["toolbar_corner"] = corner
    c.undo_stack._items.clear()
    c.commit()
    c.place_bars()
    c.dock.hide()

    def step1():
        for w in [c.search, *c.widgets.values()]:
            desktop_layer.make_topmost(int(w.winId()))
        QTimer.singleShot(900, step2)

    def step2():
        shot(out_png)
        log.info("showcase: fun scene done (theme %s, corner %s)", c.theme_name, corner)
        app.quit()

    QTimer.singleShot(900, step1)
    QTimer.singleShot(20000, app.quit)
    rc = app.exec()
    shutil.rmtree(demo, ignore_errors=True)
    return rc
