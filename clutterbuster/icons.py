"""Real Windows icons for shortcuts, files and folders (cached), a globe for websites,
and friendly names."""
import os
import sys
from urllib.parse import urlparse

from PySide6.QtCore import QFileInfo, QObject, QPointF, QRectF, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFileIconProvider, QStyle

from .desktop_files import is_url

_provider = None
_cache = {}
_globe = None
THUMB = 256          # thumbnails are made big so they stay sharp at 150-200 % scaling
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".jfif", ".ico"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".flv"}
_pending = set()


class _Notifier(QObject):
    """Tells the windows to repaint when a thumbnail is ready (always delivered on the UI thread)."""
    done = Signal(object, object)       # cache key, QImage or None
    changed = Signal()


notifier = None


def _ensure_notifier():
    global notifier
    if notifier is None:
        notifier = _Notifier()
        notifier.done.connect(_thumb_ready)
    return notifier


def is_media(p):
    return os.path.splitext(p)[1].lower() in IMAGE_EXT | VIDEO_EXT


def make_thumbnail(p, size=THUMB):
    """Picture/video thumbnail as a QImage: Windows' thumbnail first (also for hidden files and
    videos), else load the picture with Qt. None = keep the file-type icon. Safe off the UI thread."""
    img = None
    if sys.platform == "win32":
        try:
            from . import winicons
            img = winicons.shell_thumbnail(p, size)
        except Exception:
            img = None
    if (img is None or img.isNull()) and os.path.splitext(p)[1].lower() in IMAGE_EXT:
        r = QImageReader(p)
        r.setAutoTransform(True)
        s = r.size()
        if s.isValid() and s.width() > 0 and s.height() > 0:
            k = min(1.0, size / max(s.width(), s.height()))
            r.setScaledSize(QSize(max(1, int(s.width() * k)), max(1, int(s.height() * k))))
        img = r.read()
    return img if img is not None and not img.isNull() else None


class _ThumbJob(QRunnable):
    def __init__(self, key, path):
        super().__init__()
        self.key, self.path = key, path

    def run(self):
        try:
            img = make_thumbnail(self.path)
        except Exception:
            img = None
        notifier.done.emit(self.key, img)


def _thumb_ready(key, img):
    _pending.discard(key)
    if img is not None and not img.isNull():
        _cache[key] = QIcon(QPixmap.fromImage(img))
        notifier.changed.emit()


def _queue_thumbnail(key, p):
    if key in _pending:
        return
    _ensure_notifier()
    _pending.add(key)
    QThreadPool.globalInstance().start(_ThumbJob(key, p))


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
    if is_media(p):
        _queue_thumbnail(key, p)    # made in the background; the type icon shows until then
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
