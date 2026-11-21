"""--showcase: a safe demo for screenshots.

Uses a throw-away settings folder and pretend groups made of harmless built-in
Windows programs (Notepad, Calculator, ...). It never looks at or touches your
real desktop items, and nothing is launched. Windows are shown on top for the
screenshot only, then the demo closes itself.
"""
import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

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


def run_showcase(out_png):
    """Makes three pictures: OUT.png (Neon Gamer + Edit layout), OUT-popup.png (an open
    group) and OUT-settings.png (Settings with the theme maker open)."""
    desktop_layer.SHOWCASE[0] = True
    from .app import Controller
    from .tray import broom_icon
    from .store import Layout
    lay = Layout()
    lay.prefs["theme"] = os.environ.get("CLUTTERBUSTER_SHOWCASE_THEME", "Neon Gamer")
    lay.save()
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(broom_icon())
    c = Controller(app, showcase=True)
    log = logging.getLogger("cb")

    util = c.create_group("Utilities", edit=False, items=_sys_items(
        ["notepad.exe", "calc.exe", "mspaint.exe", "cmd.exe", "taskmgr.exe", "charmap.exe",
         "magnify.exe", "osk.exe", "SnippingTool.exe", "control.exe", "mstsc.exe", "WordPad.exe"]))
    c.set_accent(util, "#00D2FF")
    c.layout.group(util)["badge"] = 2
    tools = c.create_group("Windows Tools", edit=False, mode="panel", items=_sys_items(
        ["explorer.exe", "regedit.exe", "msinfo32.exe", "cleanmgr.exe", "dxdiag.exe",
         "perfmon.exe", "resmon.exe", "mmc.exe"]))
    c.set_accent(tools, "#9B5CFF")
    web = c.create_group("Websites", edit=False, items=[
        {"path": "https://www.youtube.com/", "title": "YouTube"},
        {"path": "https://github.com/", "title": "GitHub"},
        {"path": "https://huggingface.co/", "title": "Hugging Face"}])
    c.set_accent(web, "#30D158")
    c.clear_badge(web)
    sysg = c.create_group("System", edit=False, mode="panel", items=_sys_items(
        ["control.exe", "taskmgr.exe", "msconfig.exe", "services.msc", "devmgmt.msc", "diskmgmt.msc"]))
    c.set_accent(sysg, "#FF9F0A")
    c.clear_badge(sysg)
    for it in _sys_items(["notepad.exe", "calc.exe", "explorer.exe", "cmd.exe", "taskmgr.exe"]):
        c.add_favorite(it["path"])
    c.layout.save()
    c.rebuild_widgets()
    c.layer_timer.stop()       # demo windows are "on top"; don't re-stack them over the popup
    c.popup.stay_open = True   # the demo isn't the foreground app, so don't auto-close
    c.dock.pinned = True
    c.dock.show_dock()
    base, ext = os.path.splitext(out_png)
    ext = ext or ".png"

    def shot(path):
        QGuiApplication.primaryScreen().grabWindow(0).save(path)
        log.info("showcase: saved %s", path)

    def step1():
        c.enter_edit_mode()
        QTimer.singleShot(900, step2)

    def step2():
        shot(out_png)              # saving a 4K screenshot takes ~1s, so time the next step from here
        c.exit_edit_mode()
        c.open_group(util)
        QTimer.singleShot(1000, step3)

    def step3():
        shot(base + "-popup" + ext)
        c.popup.hide()
        win = c.show_settings(0)
        win.open_maker()
        win.maker.name.setText("Purple Night")
        QTimer.singleShot(900, step4)

    def step4():
        shot(base + "-settings" + ext)
        log.info("showcase: done (theme %s, glow animating %s)", c.theme_name, c.glow_timer.isActive())
        app.quit()

    QTimer.singleShot(700, step1)
    QTimer.singleShot(20000, app.quit)  # safety net
    return app.exec()
