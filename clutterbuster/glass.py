"""Painting helpers for the frosted-glass look, drag-and-drop safety helpers,
and the base desktop-layer window."""
import json

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QDrag, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QMessageBox, QWidget

from . import desktop_layer
from .theme import THEME, neon_gradient, qcolor, rgb_gradient


def rounded(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw_shadow(p, rect, radius, strength=1.0, layers=7):
    r, g, b, a = THEME["shadow"]
    p.save()
    # only paint the shadow OUTSIDE the glass, so see-through glass stays bright
    outside = QPainterPath()
    outside.addRect(rect.adjusted(-60, -60, 60, 60))
    p.setClipPath(outside.subtracted(rounded(rect, radius)), Qt.IntersectClip)
    p.setPen(Qt.NoPen)
    for i in range(layers, 0, -1):
        p.setBrush(QColor(r, g, b, int(a * strength * (1 - i / (layers + 1)))))
        p.drawRoundedRect(rect.adjusted(-i * 0.8, -i * 0.5, i * 0.8, i * 1.3), radius + i, radius + i)
    p.restore()


def draw_glass(p, rect, radius, fill_key="glass_fill", hover=False, glow=False, strip=True):
    """A frosted white rounded shape with a thin RGB strip along its top edge."""
    p.save()
    path = rounded(rect, radius)
    p.fillPath(path, qcolor("glass_fill_hover" if hover else fill_key))
    # a soft shine on the upper half
    shine = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() * 0.6)
    shine.setColorAt(0, qcolor("glass_shine"))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.setClipPath(path)
    p.fillRect(rect, shine)
    h = THEME["strip_height"]
    if strip and h:
        # Clean White: the thin RGB strip on top (a little brighter with more glow)
        alpha = int(150 + 105 * THEME.get("glow_strength", 0.6))
        p.fillRect(QRectF(rect.x(), rect.y(), rect.width(), h),
                   rgb_gradient(rect.left(), 0, rect.right(), 0, min(255, alpha)))
    p.setClipping(False)
    p.setPen(QPen(qcolor("glass_border"), 1.0))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    if glow:  # accent glow while something is dragged over
        r, g, b, _ = THEME["accent"]
        for i in range(1, 5):
            p.setPen(QPen(QColor(r, g, b, 150 // i), 1.6))
            p.drawRoundedRect(rect.adjusted(-i, -i, i, i), radius + i, radius + i)
    p.restore()


def draw_neon(p, rect, radius, accent=None, strength=None):
    """Neon Gamer: a glowing, slowly turning RGB edge around a rounded shape.
    Does nothing in themes without glow (Clean White) or with the glow slider at 0."""
    if not THEME.get("glow"):
        return
    s = THEME.get("glow_strength", 0.6) if strength is None else strength
    if s <= 0.01:
        return
    p.save()
    p.setBrush(Qt.NoBrush)
    c = rect.center()
    for grow, width, a in ((3.0, 7.0, 0.10), (1.6, 4.0, 0.22), (0.5, 2.2, 0.55), (0.0, 1.3, 1.0)):
        alpha = int(255 * min(1.0, a * (0.35 + 0.65 * s) * (1.0 if a >= 1 else 0.6 + 0.8 * s)))
        p.setPen(QPen(QBrush(neon_gradient(c, alpha, accent)), width))
        r = rect.adjusted(-grow, -grow, grow, grow)
        p.drawRoundedRect(r, radius + grow, radius + grow)
    p.restore()


def draw_edit_outline(p, rect, radius, color=None, handles=True):
    """Edit layout: a dashed outline with little round handles on the corners and edges."""
    col = QColor(color) if color is not None else QColor(THEME["default_accent"])
    p.save()
    p.setBrush(Qt.NoBrush)
    pen = QPen(col, 1.6, Qt.DashLine)
    pen.setDashPattern([4, 3])
    p.setPen(pen)
    p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), radius + 3, radius + 3)
    if handles:
        r = rect.adjusted(-3, -3, 3, 3)
        pts = [r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight(),
               QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()),
               QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y())]
        p.setPen(QPen(col, 1.4))
        p.setBrush(QColor(255, 255, 255))
        for pt in pts:
            p.drawEllipse(pt, 3.6, 3.6)
    p.restore()


def bring_to_top(widget):
    """Pop-up style windows (popup, search, Settings, edit toolbar) sit above everything."""
    def go():
        if widget.isVisible():
            desktop_layer.make_topmost(int(widget.winId()))
    QTimer.singleShot(0, go)
    QTimer.singleShot(250, go)


def safe_drop_action(event):
    """IMPORTANT SAFETY: never accept a drop as a MOVE.

    If we answered "move", Windows Explorer could delete the original file
    after the drop. We answer "link" (or "copy") - and then copy nothing,
    we only remember the path. Returns the action, or None to refuse."""
    acts = event.possibleActions()
    if acts & Qt.LinkAction:
        return Qt.LinkAction
    if acts & Qt.CopyAction:
        return Qt.CopyAction
    return None


ITEM_MIME = "application/x-clutterbuster-item"


def _text_urls(md):
    if not md.hasText():
        return []
    return [ln.strip() for ln in md.text().splitlines()
            if ln.strip().lower().startswith(("http://", "https://"))]


def parse_drop(md):
    """What was dropped? -> (local file paths, [(web address, title), ...])"""
    import re
    paths, webs = [], []
    if md.hasUrls():
        for u in md.urls():
            if u.isLocalFile():
                paths.append(u.toLocalFile())
            elif u.scheme().lower() in ("http", "https"):
                webs.append(u.toString())
    if not paths and not webs:
        webs = _text_urls(md)
    titles = {}
    if md.hasFormat("text/x-moz-url"):  # Firefox: "url\ntitle" in UTF-16
        try:
            parts = bytes(md.data("text/x-moz-url")).decode("utf-16").split("\n")
            for i in range(0, len(parts) - 1, 2):
                titles[parts[i].strip()] = parts[i + 1].strip()
        except Exception:
            pass
    if md.hasHtml():  # Chrome/Edge: <a href="url">Title</a>
        for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', md.html(), re.S | re.I):
            t = re.sub(r"<[^>]+>", "", inner).strip()
            if t and not t.lower().startswith(("http://", "https://")):
                titles.setdefault(href, t)
    if len(webs) == 1 and md.hasText():
        t = md.text().strip()
        if t and not t.lower().startswith(("http://", "https://")) and "\n" not in t:
            titles.setdefault(webs[0], t)
    return paths, [(w, titles.get(w, "")) for w in webs]


def is_acceptable_drag(event):
    md = event.mimeData()
    ok = md.hasFormat(ITEM_MIME) or md.hasUrls() or bool(_text_urls(md))
    return ok and safe_drop_action(event) is not None


def accept_drag(event):
    """Accept a drag safely (never as a move). Returns True if accepted."""
    if not is_acceptable_drag(event):
        event.ignore()
        return False
    event.setDropAction(safe_drop_action(event))
    event.accept()
    return True


def read_item(mime):
    """Our own in-app item drag -> (path, group_id) or None."""
    if not mime.hasFormat(ITEM_MIME):
        return None
    try:
        d = json.loads(bytes(mime.data(ITEM_MIME)).decode("utf-8"))
        return d["path"], d.get("group")
    except Exception:
        return None


def start_item_drag(source, path, group_id, icon):
    """Drag an item INSIDE Clutter Buster (onto another item, group or the dock).
    SAFETY: the drag carries only our private format - no file list - so if it is
    dropped on Explorer or the desktop, Windows ignores it. Nothing is copied or moved."""
    md = QMimeData()
    md.setData(ITEM_MIME, QByteArray(json.dumps({"path": path, "group": group_id}).encode("utf-8")))
    drag = QDrag(source)
    drag.setMimeData(md)
    drag.setPixmap(icon.pixmap(QSize(48, 48)))
    return drag.exec(Qt.LinkAction | Qt.CopyAction, Qt.LinkAction)


def draw_badge(p, center, count, color):
    """iOS-style count bubble in the group's accent color."""
    from PySide6.QtGui import QFont, QFontMetrics
    text = str(count) if count < 100 else "99+"
    f = QFont()
    f.setPointSizeF(8.5)
    f.setBold(True)
    fm = QFontMetrics(f)
    h = 19
    w = max(h, fm.horizontalAdvance(text) + 11)
    r = QRectF(center.x() - w / 2, center.y() - h / 2, w, h)
    p.save()
    p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
    p.setBrush(color)
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    p.drawText(r, Qt.AlignCenter, text)
    p.restore()


def ask(title, text, yes_text="Yes", no_text="Cancel", danger=False):
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    yes = box.addButton(yes_text, QMessageBox.AcceptRole)
    box.addButton(no_text, QMessageBox.RejectRole)
    if danger:
        yes.setStyleSheet("background:#e5293b;color:white;font-weight:bold;padding:4px 12px;border-radius:4px;")
    box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    box.exec()
    return box.clickedButton() is yes


class DesktopLayerWindow(QWidget):
    """A frameless, see-through window that lives on the desktop layer
    (behind all normal windows), with no taskbar button.

    Painting is split in two: paint_body() (cached - icons, glass, text) and
    paint_overlay() (the animated neon edge, badges, edit outlines). The glow animation
    only repaints the overlay on top of the cached picture, which keeps CPU use low."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._hwnd = None
        self._dirty = True
        self._cache = None
        self._cache_key = None
        self._emove = None   # edit-mode move: (press global pos, window pos)

    # ---------------------------------------------------------- cached painting
    def update(self, *a):
        self._dirty = True
        QWidget.update(self, *a)

    def glow_update(self):
        QWidget.update(self)

    def paint_body(self, p):
        pass

    def paint_overlay(self, p):
        pass

    def paintEvent(self, _e):
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if self._dirty or self._cache is None or self._cache_key != key:
            pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            bp = QPainter(pm)
            bp.setRenderHint(QPainter.Antialiasing)
            bp.setRenderHint(QPainter.SmoothPixmapTransform)
            self.paint_body(bp)
            bp.end()
            self._cache, self._cache_key, self._dirty = pm, key, False
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawPixmap(0, 0, self._cache)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        self.paint_overlay(p)
        p.end()

    # ---------------------------------------------------------- edit-mode moving
    def edit_press(self, e):
        self._emove = (e.globalPosition().toPoint(), self.pos())

    def edit_drag(self, e):
        if self._emove is None:
            return False
        self.move(self._emove[1] + (e.globalPosition().toPoint() - self._emove[0]))
        return True

    def edit_release(self):
        """Ends an edit-mode move; returns the window's new top-left snapped to a 16px grid."""
        if self._emove is None:
            return None
        self._emove = None
        return QPoint(round(self.x() / 16) * 16, round(self.y() / 16) * 16)

    def showEvent(self, e):
        super().showEvent(e)
        self._hwnd = int(self.winId())
        desktop_layer.register(self._hwnd)
        QTimer.singleShot(0, self.send_to_desktop_layer)
        QTimer.singleShot(150, self.send_to_desktop_layer)

    def hideEvent(self, e):
        super().hideEvent(e)

    def send_to_desktop_layer(self):
        if self.isVisible():
            desktop_layer.place_on_desktop_layer(int(self.winId()))

    def nativeEvent(self, event_type, message):
        hk = desktop_layer.handle_native(message)
        if hk is not None:
            self.on_hotkey(hk)
            return True, 0
        return False, 0

    def on_hotkey(self, hotkey_id):
        pass
