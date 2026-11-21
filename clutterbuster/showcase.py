"""--showcase: a safe demo for screenshots.

Uses a throw-away settings folder and pretend groups made of harmless built-in
Windows programs (Notepad, Calculator, ...). It never looks at or touches your
real desktop items, and nothing is launched. Windows are shown on top for the
screenshot only, then the demo closes itself.
"""
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
    desktop_layer.SHOWCASE[0] = True
    from .app import Controller
    from .tray import broom_icon
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(broom_icon())
    c = Controller(app, showcase=True)

    util = c.create_group("Utilities", edit=False, items=_sys_items(
        ["notepad.exe", "calc.exe", "mspaint.exe", "cmd.exe", "taskmgr.exe", "charmap.exe",
         "magnify.exe", "osk.exe", "SnippingTool.exe", "control.exe", "mstsc.exe", "WordPad.exe"]))
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
    for it in _sys_items(["notepad.exe", "calc.exe", "explorer.exe", "cmd.exe", "taskmgr.exe"]):
        c.add_favorite(it["path"])
    c.layout.save()
    c.rebuild_widgets()
    c.layer_timer.stop()       # demo windows are "on top"; don't re-stack them over the popup
    c.popup.stay_open = True   # the demo isn't the foreground app, so don't auto-close
    c.dock.pinned = True
    c.dock.show_dock()
    base, ext = os.path.splitext(out_png)

    def shot(path):
        QGuiApplication.primaryScreen().grabWindow(0).save(path)

    def step1():
        c.open_quick_search("no")

    def step2():
        shot(out_png)              # saving a 4K screenshot takes ~1s, so time the next step from here
        c.quick.close_search()
        c.open_group(util)
        QTimer.singleShot(1200, step3)

    def step3():
        import logging
        pp = c.popup
        logging.getLogger("cb").info("showcase popup: visible=%s gid=%s progress=%.2f geom=%s closing=%s",
                                     pp.isVisible(), pp.gid, pp.progress, pp.geometry().getRect(), pp.closing)
        shot(base + "-popup" + (ext or ".png"))
        c.popup.hide()
        app.quit()

    QTimer.singleShot(600, step1)
    QTimer.singleShot(1700, step2)
    QTimer.singleShot(15000, app.quit)  # safety net
    return app.exec()
