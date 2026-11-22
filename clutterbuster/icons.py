"""Real Windows icons for shortcuts, files and folders (cached), a globe for websites,
and friendly names."""
import os
import sys
from urllib.parse import urlparse

from PySide6.QtCore import QFileInfo, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFileIconProvider, QStyle

from .desktop_files import is_url

_provider = None
_cache = {}
_globe = None


def globe_icon():
    """A simple blue globe, drawn by hand (no internet needed)."""
    global _globe
    if _globe is None:
        pm = QPixmap(128, 128)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(10, 10, 108, 108)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 132, 255))
        p.drawEllipse(r)
        p.setPen(QPen(QColor(255, 255, 255, 235), 6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(40, 12, 48, 104))
        p.drawLine(QPointF(64, 12), QPointF(64, 116))
        p.drawLine(QPointF(12, 64), QPointF(116, 64))
        p.drawArc(QRectF(20, 22, 88, 30), 200 * 16, 140 * 16)
        p.drawArc(QRectF(20, 76, 88, 30), 20 * 16, 140 * 16)
        p.end()
        _globe = QIcon(pm)
    return _globe


def _cache_key(p):
    try:
        st = os.stat(p)
        return (os.path.normcase(os.path.abspath(p)), int(st.st_mtime), st.st_size)
    except OSError:
        return None


def icon_for(p):
    """The item's real icon, cached per item (not per file type)."""
    global _provider
    if is_url(p):
        return globe_icon()
    key = _cache_key(p)
    if key is None:
        return QApplication.style().standardIcon(QStyle.SP_MessageBoxWarning)
    if key in _cache:
        return _cache[key]
    icon = None
    if sys.platform == "win32":
        try:
            from . import winicons
            icon, _how = winicons.resolve(p)
        except Exception:
            icon = None
    if icon is None:
        if _provider is None:
            _provider = QFileIconProvider()
        icon = _provider.icon(QFileInfo(p))
    if icon is None or icon.isNull():
        icon = QApplication.style().standardIcon(QStyle.SP_FileIcon)
    _cache[key] = icon
    return icon


def forget(p=None):
    """Drop cached icons (all, or one item)."""
    if p is None:
        _cache.clear()
        return
    for k in [k for k in _cache if k[0] == os.path.normcase(os.path.abspath(p))]:
        _cache.pop(k, None)


def domain_of(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or url


def display_name(p):
    if is_url(p):
        return domain_of(p)
    base = os.path.basename(p.rstrip("\\/")) or p
    stem, ext = os.path.splitext(base)
    return stem if ext.lower() in (".lnk", ".exe", ".appref-ms", ".url") else base


def item_name(item):
    """Name to show for a group item (websites use their saved title)."""
    return item.get("title") or display_name(item["path"])
