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

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
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
