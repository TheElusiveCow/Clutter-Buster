"""The iOS-style group popup - a COMPACT frosted panel (no full-screen overlay).

It grows out of the clicked group (quick scale + fade), sits next to it, and the
rest of the desktop stays visible and usable. Big title, 3x3 grid of items with
names, page dots after 9 items. Click an item to open it. Click anywhere else
(or press Esc) to close - it shrinks back into the group. Drag empty space to move it.
Drag an item onto another item to make a new group with both.
"""
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QApplication, QWidget

from . import icons, sounds
from .glass import accept_drag, draw_glass, draw_shadow, parse_drop, read_item, rounded, start_item_drag
from .theme import THEME, accent_color, qcolor

PER_PAGE = 9
MARGIN = 22        # room around the panel for its soft shadow
PAD = 20
HEADER_H = 58
DOTS_H = 26


def cell_size():
    isz = THEME["popup_icon"]
    return isz + 54, isz + 50     # ~118 x 114 with 64px icons


class GroupPopup(QWidget):
    def __init__(self, controller):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.c = controller
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.gid = None
        self.origin = QPointF()
        self.progress = 0.0
        self.page = 0
        self.page_pos = 0.0
        self.closing = False
        self.blur_mode = ""   # compact popup paints its own frosted glass
        self._press = None
        self._press_item = None
        self._press_win = None
        self._dragging = False
        self._hover_item = None
        self._drop_hover = False
        self._drop_item = None
        self.last_closed = (None, 0)
        self.stay_open = False   # showcase screenshots only
        self.anim = QVariantAnimation(self)
        self.anim.valueChanged.connect(self._on_progress)
        self.anim.finished.connect(self._on_anim_done)
        self.page_anim = QVariantAnimation(self)
        self.page_anim.setDuration(220)
        self.page_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.page_anim.valueChanged.connect(self._on_page_pos)

    def apply_blur(self):
        return ""

    @property
    def group(self):
        return self.c.layout.group(self.gid) if self.gid else None

    # ------------------------------------------------------------ size & place
    def panel_size(self):
        cw, ch = cell_size()
        return 3 * cw + 2 * PAD, HEADER_H + 3 * ch + DOTS_H + PAD

    def panel_rect(self):
        w, h = self.panel_size()
        return QRectF(MARGIN, MARGIN, w, h)

    def place_next_to(self, anchor):
        """Put the popup beside the group (right side if it fits, else left), on screen."""
        av = QGuiApplication.primaryScreen().availableGeometry()
        w, h = self.panel_size()
        W, H = w + 2 * MARGIN, h + 2 * MARGIN
        if anchor.isValid():
            x = anchor.right() + 10 - MARGIN
            if x + W > av.right():
                x = anchor.left() - 10 - W + MARGIN
            y = anchor.top() - 30 - MARGIN
        else:
            x, y = av.center().x() - W // 2, av.center().y() - H // 2
        x = max(av.left(), min(x, av.right() - W))
        y = max(av.top(), min(y, av.bottom() - H))
        self.setGeometry(x, y, W, H)
        if anchor.isValid():
            c = QPointF(self.mapFromGlobal(anchor.center()))
            pr = self.panel_rect()
            self.origin = QPointF(min(max(c.x(), pr.left()), pr.right()), min(max(c.y(), pr.top()), pr.bottom()))
        else:
            self.origin = self.panel_rect().center()

    # ------------------------------------------------------------ open / close
    def open_group(self, gid, anchor_rect):
        self.gid = gid
        self.page = 0
        self.page_pos = 0.0
        self.closing = False
        self._hover_item = None
        self.progress = 0.0
        self.place_next_to(anchor_rect)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        sounds.play("open")
        self._animate(1.0, 170, QEasingCurve.OutCubic)

    def close_animated(self):
        if not self.isVisible() or self.closing:
            return
        self.closing = True
        sounds.play("close")
        self._animate(0.0, 150, QEasingCurve.InCubic)

    def _animate(self, end, ms, curve):
        self.anim.stop()
        self.anim.setStartValue(float(self.progress))
        self.anim.setEndValue(float(end))
        self.anim.setDuration(ms)
        self.anim.setEasingCurve(curve)
        self.anim.start()

    def _on_progress(self, v):
        self.progress = float(v)
        self.update()

    def _on_anim_done(self):
        if self.closing:
            self.hide()
            self.closing = False
            from time import monotonic
            self.last_closed = (self.gid, monotonic())
            self.gid = None

    def _on_page_pos(self, v):
        self.page_pos = float(v)
        self.update()

    def refresh(self):
        if self.isVisible() and self.group is None:
            self.hide()
            self.gid = None
            return
        if self.group is not None:
            self.page = min(self.page, self.pages() - 1)
            self.page_pos = float(self.page)
        self.update()

    # ------------------------------------------------------------ geometry
    def pages(self):
        g = self.group
        return max(1, math.ceil((len(g["items"]) if g else 0) / PER_PAGE))

    def item_rect(self, k, shift=0.0):
        pr = self.panel_rect()
        cw, ch = cell_size()
        row, col = divmod(k, 3)
        return QRectF(pr.left() + PAD + col * cw + shift, pr.top() + HEADER_H + row * ch, cw, ch)

    def dot_rects(self):
        n = self.pages()
        pr = self.panel_rect()
        x0 = pr.center().x() - (n - 1) * 9
        y = pr.bottom() - PAD / 2 - DOTS_H / 2 + 2
        return [QRectF(x0 + i * 18 - 8, y - 8, 16, 16) for i in range(n)]

    # ------------------------------------------------------------ painting
    def paintEvent(self, _e):
        g = self.group
        if g is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        t = max(0.0, min(1.0, self.progress))
        pr = self.panel_rect()
        # grow out of the group: scale around the point nearest the group
        s = 0.25 + 0.75 * t
        p.translate(self.origin)
        p.scale(s, s)
        p.translate(-self.origin)
        p.setOpacity(t)
        rad = 28
        draw_shadow(p, pr, rad, 1.3, layers=10)
        draw_glass(p, pr, rad, fill_key="popup_fill", glow=self._drop_hover)
        acc = accent_color(g)
        # header: accent dot + big title + item count
        f = QFont(self.font())
        f.setPointSizeF(17)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(Qt.NoPen)
        p.setBrush(acc)
        p.drawEllipse(QPointF(pr.left() + PAD + 6, pr.top() + 31), 6, 6)
        p.setPen(qcolor("title_text"))
        title = fm.elidedText(g["name"], Qt.ElideRight, int(pr.width() - 2 * PAD - 90))
        p.drawText(QRectF(pr.left() + PAD + 20, pr.top() + 8, pr.width(), 46), Qt.AlignLeft | Qt.AlignVCenter, title)
        sf = QFont(self.font())
        sf.setPointSizeF(9)
        p.setFont(sf)
        p.setPen(qcolor("hint_text"))
        n = len(g["items"])
        p.drawText(QRectF(pr.left(), pr.top() + 8, pr.width() - PAD, 46), Qt.AlignRight | Qt.AlignVCenter,
                   f"{n} item{'s' if n != 1 else ''}")
        # items as soft white cards (clipped so sliding pages look right)
        p.save()
        p.setClipPath(rounded(pr, rad))
        nf = QFont(self.font())
        nf.setPointSizeF(9.5)
        p.setFont(nf)
        nfm = QFontMetrics(nf)
        isz = THEME["popup_icon"]
        opt = QTextOption(Qt.AlignHCenter | Qt.AlignTop)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        for page in range(self.pages()):
            shift = (page - self.page_pos) * (pr.width())
            if abs(shift) >= pr.width():
                continue
            for k, it in enumerate(g["items"][page * PER_PAGE:(page + 1) * PER_PAGE]):
                idx = page * PER_PAGE + k
                cell = self.item_rect(k, shift)
                card = cell.adjusted(5, 4, -5, -4)
                hot = (idx == self._hover_item and t >= 1) or idx == self._drop_item
                p.setPen(QPen(acc if idx == self._drop_item else qcolor("card_border"), 1.6 if hot else 1))
                p.setBrush(qcolor("card_fill") if not hot else QColor(255, 255, 255, 250))
                p.drawRoundedRect(card, 16, 16)
                ir = QRectF(card.center().x() - isz / 2, card.top() + 10, isz, isz)
                icons.icon_for(it["path"]).paint(p, ir.toRect())
                name = icons.item_name(it)
                nr = QRectF(card.left() + 5, ir.bottom() + 5, card.width() - 10, nfm.height() * 2 + 2)
                if nfm.horizontalAdvance(name) > nr.width() * 2 - 12:
                    name = nfm.elidedText(name, Qt.ElideRight, int(nr.width() * 2 - 12))
                p.setPen(qcolor("panel_text"))
                p.drawText(nr, name, opt)
        if not g["items"]:
            p.setPen(qcolor("panel_subtext"))
            f2 = QFont(self.font())
            f2.setPointSizeF(11)
            p.setFont(f2)
            p.drawText(pr.adjusted(30, HEADER_H, -30, -DOTS_H), Qt.AlignCenter | Qt.TextWordWrap,
                       "This group is empty.\nDrag shortcuts, files, folders or website links onto it.")
        p.restore()
        if self.pages() > 1:
            p.setPen(Qt.NoPen)
            for i, dr in enumerate(self.dot_rects()):
                p.setBrush(qcolor("dot_on" if i == self.page else "dot_off"))
                p.drawEllipse(dr.center(), 4, 4)
        p.end()

    # ------------------------------------------------------------ hit testing
    def item_at(self, pos):
        g = self.group
        if g is None or self.progress < 1:
            return None
        for k in range(PER_PAGE):
            idx = self.page * PER_PAGE + k
            if idx >= len(g["items"]):
                break
            if self.item_rect(k).adjusted(5, 4, -5, -4).contains(QPointF(pos)):
                return idx
        return None

    # ------------------------------------------------------------ mouse / keys
    def mousePressEvent(self, e):
        pos = e.position()
        if self.closing:
            return
        if not self.panel_rect().contains(pos):
            self.close_animated()  # the shadow margin counts as "outside"
            return
        if e.button() == Qt.LeftButton:
            for i, dr in enumerate(self.dot_rects() if self.pages() > 1 else []):
                if dr.contains(pos):
                    self.go_page(i)
                    return
            self._press = e.globalPosition().toPoint()
            self._press_item = self.item_at(pos)
            self._press_win = self.pos()
            self._dragging = False

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._press is not None and (e.buttons() & Qt.LeftButton):
            d = e.globalPosition().toPoint() - self._press
            if not self._dragging and d.manhattanLength() >= 6:
                self._dragging = True
                g = self.group
                if self._press_item is not None and g and self._press_item < len(g["items"]):
                    path = g["items"][self._press_item]["path"]
                    self._press = None
                    self._dragging = False
                    start_item_drag(self, path, self.gid, icons.icon_for(path))
                    return
            if self._dragging:
                self.move(self._press_win + d)   # drag the popup around
            return
        hv = self.item_at(pos)
        if hv != self._hover_item:
            self._hover_item = hv
            g = self.group
            self.setToolTip(g["items"][hv]["path"] if (g and hv is not None) else "")
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press is None:
            return
        was_drag, pressed = self._dragging, self._press_item
        self._press = None
        self._dragging = False
        if not was_drag and pressed is not None and pressed == self.item_at(e.position()):
            g = self.group
            if g and pressed < len(g["items"]):
                path = g["items"][pressed]["path"]
                self.close_animated()
                self.c.launch(path)

    def contextMenuEvent(self, e):
        idx = self.item_at(QPointF(e.pos()))
        g = self.group
        if idx is None or g is None:
            return
        self.c.item_menu(self.gid, g["items"][idx]["path"], e.globalPos(), in_popup=True)

    def wheelEvent(self, e):
        dy = e.angleDelta().y() or e.angleDelta().x()
        if dy:
            self.go_page(self.page + (1 if dy < 0 else -1))

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self.close_animated()
        elif k in (Qt.Key_Right, Qt.Key_PageDown):
            self.go_page(self.page + 1)
        elif k in (Qt.Key_Left, Qt.Key_PageUp):
            self.go_page(self.page - 1)
        elif k == Qt.Key_Z and e.modifiers() & Qt.ControlModifier:
            self.c.undo()
        else:
            super().keyPressEvent(e)

    def go_page(self, n):
        n = max(0, min(self.pages() - 1, n))
        if n == self.page:
            return
        self.page = n
        self.page_anim.stop()
        self.page_anim.setStartValue(float(self.page_pos))
        self.page_anim.setEndValue(float(n))
        self.page_anim.start()

    # ------------------------------------------------------------ click elsewhere closes
    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange and self.isVisible() and not self.isActiveWindow():
            QTimer.singleShot(80, self._maybe_close)

    def _maybe_close(self):
        if not self.isVisible() or self.isActiveWindow() or self.stay_open:
            return
        if QApplication.activePopupWidget() or QApplication.activeModalWidget():
            return
        self.close_animated()

    # ------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, e):
        if self.group is not None and accept_drag(e):
            self._drop_hover = True
            self.update()

    def dragMoveEvent(self, e):
        if not accept_drag(e):
            return
        di = self.item_at(e.position()) if read_item(e.mimeData()) else None
        if di != self._drop_item:
            self._drop_item = di
            self.update()

    def dragLeaveEvent(self, e):
        self._drop_hover = False
        self._drop_item = None
        self.update()

    def dropEvent(self, e):
        self._drop_hover = False
        g = self.group
        target = None
        if self._drop_item is not None and g and self._drop_item < len(g["items"]):
            target = g["items"][self._drop_item]["path"]
        self._drop_item = None
        if g is None or not accept_drag(e):
            return
        item = read_item(e.mimeData())
        dropped = parse_drop(e.mimeData()) if item is None else None
        gid = self.gid
        QTimer.singleShot(0, lambda: self.c.handle_drop(gid, item, dropped, target))
        self.update()


