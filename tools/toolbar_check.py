"""Developer check on a real Windows screen (real DPI + taskbar): drags the toolbar into each
corner with simulated mouse events and uses the gear menu's Dock toolbar to buttons.
SAFE: runs with a throw-away settings folder and an empty pretend desktop (never your real
desktop or your real groups), then closes itself.
Usage:  .venv\\Scripts\\python.exe tools\\toolbar_check.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["CLUTTERBUSTER_SHOWCASE"] = "1"      # never looks at / touches the real desktop
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="clutterbuster-tbcheck-")
os.environ["CLUTTERBUSTER_DEMO_DESKTOP"] = tempfile.mkdtemp(prefix="clutterbuster-tbcheck-desk-")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from clutterbuster import desktop_layer, paths  # noqa: E402

desktop_layer.SHOWCASE[0] = True
paths.ensure_dirs()
paths.setup_logging()
app = QApplication(sys.argv[:1])
app.setQuitOnLastWindowClosed(False)
from clutterbuster.app import Controller  # noqa: E402

c = Controller(app, showcase=True)
tb = c.search
av = c.avail()
print("screen", av.getRect(), "dpr", tb.devicePixelRatioF())
ok = True
targets = {"tl": av.topLeft(), "tr": av.topRight(), "bl": av.bottomLeft(), "br": av.bottomRight()}
for k, corner in targets.items():
    c.dock_toolbar("top")
    app.processEvents()
    g = tb.grip_rect().center().toPoint()
    QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, g)
    QTest.mouseMove(tb, g + QPoint(15, 0))
    app.processEvents()
    # push the bar into the corner (the mouse stays on the grip, like a real drag)
    gx = tb.mapToGlobal(tb.grip_rect().center().toPoint())
    if k[1] == "l":
        dx = corner.x() - tb.x() - 4
    else:
        dx = corner.x() - (tb.x() + tb.width()) + 4
    dy = (corner.y() - tb.y() - 4) if k[0] == "t" else (corner.y() - (tb.y() + tb.height()) + 4)
    QTest.mouseMove(tb, tb.mapFromGlobal(gx + QPoint(dx, dy)))
    app.processEvents()
    hint = tb._snap
    QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, tb.grip_rect().center().toPoint())
    app.processEvents()
    res = tb.corner
    print(f"drag {k}: hint={hint} result={res} at {tb.geometry().getRect()}")
    ok &= res == k
for k in ("tl", "tr", "bl", "br", "float", "top"):
    c.dock_toolbar(k)
    app.processEvents()
    print(f"menu {k}: corner={tb.corner} at {tb.geometry().getRect()}")
    ok &= (tb.corner == k) if k in targets else (tb.corner is None)
print("TOOLBAR CHECK", "PASSED" if ok else "FAILED")
sys.stdout.flush()
os._exit(0 if ok else 1)
