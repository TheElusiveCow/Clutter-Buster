"""Developer check (READ-ONLY): for every item in every group, show what kind of item it is,
where a shortcut points / takes its picture from, whether it's hidden, and which icon the
old (Qt) lookup and the new lookup return. Saves a picture sheet to %TEMP%\\cb-icon-diag.png.
Run:  .venv\\Scripts\\python.exe tools\\icon_diag.py
"""
import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QFileInfo, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileIconProvider  # noqa: E402

app = QApplication(sys.argv[:1])
from clutterbuster import desktop_files as df  # noqa: E402
from clutterbuster.shortcuts import lnk_info, url_info  # noqa: E402
from clutterbuster.store import Layout  # noqa: E402

try:
    from clutterbuster import winicons
except Exception as e:  # noqa: BLE001
    winicons = None
    print("new lookup unavailable:", e)
prov = QFileIconProvider()


def h(icon, size=48):
    if icon is None or icon.isNull():
        return "null"
    img = icon.pixmap(size, size).toImage().convertToFormat(QImage.Format_ARGB32)
    return hashlib.md5(bytes(img.constBits())).hexdigest()[:8]


rows = []
lay = Layout()
for g in lay.groups:
    for it in g.get("items", []):
        p = it["path"]
        if df.is_url(p):
            continue
        ext = os.path.splitext(p)[1].lower()
        old = prov.icon(QFileInfo(p))
        new, how = (winicons.resolve(p) if winicons else (None, "n/a"))
        extra = ""
        if ext == ".lnk":
            i = lnk_info(p)
            extra = (f"target={i['target']!r} exists={os.path.exists(i['target']) if i['target'] else None} "
                     f"IconLocation={i['icon_location']!r},{i['icon_index']}")
        elif ext == ".url":
            i = url_info(p)
            extra = f"URL={i['url'][:60]!r} IconFile={i['icon_file']!r},{i['icon_index']}"
        print(f"[{g['name']}] {os.path.basename(p)} | exists={os.path.exists(p)} hidden={df.is_hidden(p)} "
              f"| {extra}\n     Qt sizes={[s.width() for s in old.availableSizes()]} Qt48={h(old)} "
              f"| new: {how} sizes={[s.width() for s in new.availableSizes()] if new else []} new48={h(new)}")
        rows.append((g["name"], os.path.basename(p), old, new))
old_hashes = [h(r[2]) for r in rows]
dups = {x for x in old_hashes if old_hashes.count(x) > 1}
print("Qt icons shared by several different items (= generic):", sorted(dups))
W, RH = 900, 110
img = QImage(W, max(RH, RH * len(rows)), QImage.Format_ARGB32)
img.fill(QColor(235, 238, 245))
p = QPainter(img)
for n, (gname, name, old, new) in enumerate(rows):
    y = n * RH
    p.drawText(QRect(10, y, 360, RH), Qt.AlignVCenter, f"{gname}: {name}")
    p.drawText(QRect(380, y, 80, 20), 0, "old (Qt)")
    p.drawPixmap(380, y + 20, old.pixmap(72, 72))
    p.drawText(QRect(520, y, 80, 20), 0, "new")
    if new:
        p.drawPixmap(520, y + 20, new.pixmap(72, 72))
p.end()
out = os.path.join(tempfile.gettempdir(), "cb-icon-diag.png")
img.save(out)
print("sheet:", out)
