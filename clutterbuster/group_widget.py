"""One group on the desktop. It can look like:

  * a SMALL TILE  - an icon-sized frosted square with a 3x3 mini preview (iOS folder).
                    Single click opens the big popup.
  * a BIG PANEL   - a Fences-style glass panel with a title bar and its items in a grid.
                    Click an item to open it; click the title to open the popup.

Both can be resized by dragging any edge or corner; icons scale with the size and are
never cut off (big panels get pages with dots when they're too small).
Hovering only highlights / shows labels - it NEVER opens a group.
"""
import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QLineEdit

from . import icons
from .glass import (DesktopLayerWindow, accept_drag, draw_badge, draw_edit_outline, draw_glass,
                    draw_neon, draw_shadow, read_item, start_item_drag)
from .theme import THEME, accent_color, qcolor, rad

DRAG_THRESHOLD = 6
EDGE = 7
TILE_DEFAULT, TILE_MIN, TILE_MAX = (96, 112), (56, 66), (320, 340)
PANEL_DEFAULT, PANEL_MIN = (340, 250), (150, 110)
TITLE_H = 34


def default_size(mode):
    return TILE_DEFAULT if mode == "tile" else PANEL_DEFAULT


def min_size(mode):
    return TILE_MIN if mode == "tile" else PANEL_MIN


def group_size(g):
    s = g.get("tile_size" if g.get("mode", "tile") == "tile" else "panel_size")
    return tuple(s) if s else default_size(g.get("mode", "tile"))


def grid_layout(w, h, n, max_cell=112):
    """Biggest square cell that fits n items in w x h. Pages only if even tiny cells don't fit.
    max_cell follows the Icon size slider (64 px icons -> 112 px cells)."""
    n = max(1, n)
    for c in range(int(max(30, max_cell)), 27, -2):
        cols, rows = int(w // c), int(h // c)
        if cols >= 1 and rows >= 1 and cols * rows >= n:
            return cols, rows, c, 1
    c = 28
    cols, rows = max(1, int(w // c)), max(1, int((h - 16) // c))
    return cols, rows, c, math.ceil(n / (cols * rows))


class GroupWidget(DesktopLayerWindow):
    def __init__(self, controller, group_id):
        super().__init__()
        self.c = controller
        self.gid = group_id
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._press = None          # global press position
        self._press_geom = None
        self._press_kind = None     # "move" | "resize" | "item" | "title" | "menu"
        self._press_item = None
        self._edges = 0
        self._active = False        # dragging/resizing in progress
        self._hover = False
        self._hover_item = None
        self._drop_hover = False
        self._drop_item = None
        self.page = 0
        self.editor = None

    @property
    def group(self):
        return self.c.layout.group(self.gid)

    @property
    def mode(self):
        g = self.group
        return g.get("mode", "tile") if g else "tile"

    # ------------------------------------------------------------ geometry
    def glass_rect(self):
        """Tile mode: the frosted square. Panel mode: the whole panel."""
        if self.mode == "tile":
            s = max(24.0, min(self.width() - 20.0, self.height() - 36.0))
            return QRectF((self.width() - s) / 2, 10, s, s)
        return QRectF(6, 9, self.width() - 12, self.height() - 15)

    def glass_rect_global(self):
        r = self.glass_rect().toRect()
        return QRect(self.mapToGlobal(r.topLeft()), r.size())

    def labels_visible(self):
        return self.glass_rect().width() >= 56 or self._hover

    def menu_rect(self):
        r = self.glass_rect()
        return QRectF(r.right() - 36, r.top() + 6, 28, 22)

    def title_rect(self):
        r = self.glass_rect()
        return QRectF(r.left(), r.top(), r.width(), TITLE_H)

    def content_rect(self):
        r = self.glass_rect()
        return QRectF(r.left() + 10, r.top() + TITLE_H, r.width() - 20, r.height() - TITLE_H - 10)

    def panel_layout(self):
        g = self.group
        cr = self.content_rect()
        n = len(g["items"]) if g else 0
        cols, rows, cell, pages = grid_layout(cr.width(), cr.height(), n, THEME["popup_icon"] + 48)
        self.page = min(self.page, pages - 1)
        return cr, cols, rows, cell, pages

    def panel_item_rects(self):
        """[(index, rect)] for the items on the current page of a big panel."""
        g = self.group
        if not g:
            return []
        cr, cols, rows, cell, pages = self.panel_layout()
        per = cols * rows
        cw = cr.width() / cols
        out = []
        start = self.page * per
        for k, idx in enumerate(range(start, min(len(g["items"]), start + per))):
            r, c = divmod(k, cols)
            out.append((idx, QRectF(cr.left() + c * cw + (cw - cell) / 2, cr.top() + r * cell, cell, cell)))
        return out

    def item_at(self, pos):
        if self.mode != "panel":
            return None
        for idx, r in self.panel_item_rects():
            if r.adjusted(3, 3, -3, -3).contains(QPointF(pos)):
                return idx
        return None

    def edges_at(self, pos):
        e = 0
        if pos.x() < EDGE:
            e |= 1
        if pos.x() > self.width() - EDGE:
            e |= 2
        if pos.y() < EDGE:
            e |= 4
        if pos.y() > self.height() - EDGE:
            e |= 8
        return e

    # ------------------------------------------------------------ painting
    def radius(self):
        if self.mode == "tile":
            return rad(max(8.0, self.glass_rect().width() * 0.25))
        return rad(16)

    def paint_body(self, p):
        g = self.group
        if g is None:
            return
        p.fillRect(self.rect(), QColor(255, 255, 255, 1))  # keeps edges grabbable for resizing
        if self.mode == "tile":
            self._paint_tile(p, g)
        else:
            self._paint_panel(p, g)

    def paint_overlay(self, p):
        """Drawn every frame on top of the cached picture: neon edge, badge, edit outline."""
        g = self.group
        if g is None:
            return
        r = self.glass_rect()
        acc = accent_color(g)
        draw_neon(p, r, self.radius(), accent=acc)
        if g.get("badge"):
            if self.mode == "tile":
                draw_badge(p, QPointF(r.right() - 2, r.top() + 2), g["badge"], acc)
            else:
                draw_badge(p, QPointF(self.menu_rect().left() - 14, self.menu_rect().center().y()), g["badge"], acc)
        if self.c.edit_mode:
            draw_edit_outline(p, r, self.radius(), acc)

    def _paint_tile(self, p, g):
        r = self.glass_rect()
        s = r.width()
        rr = self.radius()
        acc = accent_color(g)
        draw_shadow(p, r, rr, 0.9)
        draw_glass(p, r, rr, hover=self._hover or self._active, glow=self._drop_hover, strip=False)
        if not THEME.get("glow"):
            ring = QColor(acc)
            ring.setAlpha(min(255, int((60 + 90 * THEME.get("glow_strength", 0.6)) * (1.4 if self._hover else 1))))
            p.setPen(QPen(ring, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), rr - 1, rr - 1)
        pad = s * 0.13
        cell = (s - 2 * pad) / 3
        isz = cell * 0.84
        for i, it in enumerate(g["items"][:9]):
            row, col = divmod(i, 3)
            x = r.x() + pad + col * cell + (cell - isz) / 2
            y = r.y() + pad + row * cell + (cell - isz) / 2
            icons.icon_for(it["path"]).paint(p, QRect(round(x), round(y), round(isz), round(isz)))
        if self.labels_visible() and not (self.editor and self.editor.isVisible()):
            f = QFont(self.font())
            f.setPointSizeF(9)
            p.setFont(f)
            fm = QFontMetrics(f)
            text = fm.elidedText(g["name"], Qt.ElideRight, self.width() - 4)
            lr = QRectF(0, r.bottom() + 5, self.width(), fm.height() + 2)
            p.setPen(qcolor("label_shadow"))
            p.drawText(lr.translated(1, 1), Qt.AlignHCenter | Qt.AlignTop, text)
            p.setPen(qcolor("label_text"))
            p.drawText(lr, Qt.AlignHCenter | Qt.AlignTop, text)

    def _paint_panel(self, p, g):
        r = self.glass_rect()
        acc = accent_color(g)
        draw_shadow(p, r, self.radius(), 1.0)
        draw_glass(p, r, self.radius(), fill_key="panel_fill", glow=self._drop_hover, strip=True)
        # title bar: accent dot + name + "..." menu
        p.setPen(Qt.NoPen)
        p.setBrush(acc)
        p.drawEllipse(QPointF(r.left() + 17, r.top() + TITLE_H / 2 + 1), 5, 5)
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        mr = self.menu_rect()
        badge_w = 30 if g.get("badge") else 0
        if not (self.editor and self.editor.isVisible()):
            name = fm.elidedText(g["name"], Qt.ElideRight, int(mr.left() - r.left() - 34 - badge_w))
            p.setPen(qcolor("panel_title_text"))
            p.drawText(QRectF(r.left() + 30, r.top(), r.width(), TITLE_H + 2), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setPen(qcolor("hint_text"))
        p.drawText(mr, Qt.AlignCenter, "\u2022\u2022\u2022")
        # items
        cr, cols, rows, cell, pages = self.panel_layout()
        show_labels = cell >= 64
        nf = QFont(self.font())
        nf.setPointSizeF(8.5)
        p.setFont(nf)
        nfm = QFontMetrics(nf)
        for idx, ir in self.panel_item_rects():
            it = g["items"][idx]
            card = ir.adjusted(4, 4, -4, -4)
            hot = idx == self._hover_item or idx == self._drop_item
            p.setPen(QPen(acc if idx == self._drop_item else qcolor("card_border"), 1.5 if hot else 1))
            p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
            p.drawRoundedRect(card, rad(max(6, cell * 0.16)), rad(max(6, cell * 0.16)))
            if show_labels:
                isz = cell * 0.46
                icon_r = QRectF(card.center().x() - isz / 2, card.top() + card.height() * 0.12, isz, isz)
            else:
                isz = cell * 0.6
                icon_r = QRectF(card.center().x() - isz / 2, card.center().y() - isz / 2, isz, isz)
            icons.icon_for(it["path"]).paint(p, icon_r.toRect())
            if show_labels:
                p.setPen(qcolor("panel_text"))
                t = nfm.elidedText(icons.item_name(it), Qt.ElideRight, int(card.width() - 8))
                p.drawText(QRectF(card.left() + 2, icon_r.bottom() + 3, card.width() - 4, nfm.height() + 2),
                           Qt.AlignHCenter | Qt.AlignTop, t)
        if not g["items"]:
            p.setPen(qcolor("hint_text"))
            p.drawText(cr, Qt.AlignCenter | Qt.TextWordWrap, "Drop shortcuts, files, folders or links here")
        if pages > 1:
            p.setPen(Qt.NoPen)
            y = r.bottom() - 9
            x0 = r.center().x() - (pages - 1) * 7
            for i in range(pages):
                p.setBrush(qcolor("dot_on" if i == self.page else "dot_off"))
                p.drawEllipse(QPointF(x0 + i * 14, y), 3.2, 3.2)
        # tiny cells: show the hovered item's name in a bubble (hover never opens anything)
        if not show_labels and self._hover_item is not None and self._hover_item < len(g["items"]):
            rects = dict(self.panel_item_rects())
            if self._hover_item in rects:
                ir = rects[self._hover_item]
                t = nfm.elidedText(icons.item_name(g["items"][self._hover_item]), Qt.ElideRight, 220)
                w = nfm.horizontalAdvance(t) + 16
                b = QRectF(ir.center().x() - w / 2, ir.bottom() - 2, w, nfm.height() + 8)
                b.moveLeft(max(2, min(b.left(), self.width() - w - 2)))
                if b.bottom() > self.height() - 2:
                    b.moveBottom(ir.top() + 2)
                p.setPen(Qt.NoPen)
                p.setBrush(qcolor("bubble_fill"))
                p.drawRoundedRect(b, 7, 7)
                p.setPen(QColor(255, 255, 255))
                p.drawText(b, Qt.AlignCenter, t)

    # ------------------------------------------------------------ mouse
    def enterEvent(self, e):
        self._hover = True
        g = self.group
        if g and self.mode == "tile":
            n = len(g["items"])
            self.setToolTip(f"{g['name']} - {n} item{'s' if n != 1 else ''}\nClick to open")
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._hover_item = None
        self.unsetCursor()
        self.update()

    def _cursor_for(self, edges):
        if edges in (5, 10):
            return Qt.SizeFDiagCursor
        if edges in (6, 9):
            return Qt.SizeBDiagCursor
        if edges & 3:
            return Qt.SizeHorCursor
        if edges & 12:
            return Qt.SizeVerCursor
        return None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        self._press = e.globalPosition().toPoint()
        self._press_geom = self.geometry()
        self._active = False
        self._edges = self.edges_at(pos)
        self._press_item = None
        if self._edges:
            self._press_kind = "resize"
        elif self.mode == "panel" and self.menu_rect().contains(pos):
            self._press_kind = "menu"
        elif self.mode == "panel" and self.item_at(pos) is not None:
            self._press_kind = "item"
            self._press_item = self.item_at(pos)
        elif self.mode == "panel" and self.title_rect().contains(pos):
            self._press_kind = "title"
        else:
            self._press_kind = "move" if self.mode == "panel" else "tile"

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            cur = self._cursor_for(self.edges_at(pos))
            if cur is not None:
                self.setCursor(cur)
            elif self.c.edit_mode:
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.unsetCursor()
            hv = self.item_at(pos)
            if hv != self._hover_item:
                self._hover_item = hv
                self.update()
            return
        delta = e.globalPosition().toPoint() - self._press
        if not self._active and delta.manhattanLength() >= DRAG_THRESHOLD:
            self._active = True
            if self._press_kind == "item":
                g = self.group
                if g and self._press_item is not None and self._press_item < len(g["items"]):
                    path = g["items"][self._press_item]["path"]
                    self._press = None
                    self._active = False
                    start_item_drag(self, path, self.gid, icons.icon_for(path))
                return
        if not self._active:
            return
        if self._press_kind == "resize":
            self._do_resize(delta)
        elif self._press_kind in ("move", "title", "tile"):
            self.move(self._press_geom.topLeft() + delta)

    def _do_resize(self, d):
        g0 = QRect(self._press_geom)
        mw, mh = min_size(self.mode)
        mx = TILE_MAX if self.mode == "tile" else (4000, 4000)
        e = self._edges
        if e & 1:
            g0.setLeft(min(g0.left() + d.x(), g0.right() - mw))
        if e & 2:
            g0.setRight(max(g0.right() + d.x(), g0.left() + mw))
        if e & 4:
            g0.setTop(min(g0.top() + d.y(), g0.bottom() - mh))
        if e & 8:
            g0.setBottom(max(g0.bottom() + d.y(), g0.top() + mh))
        if g0.width() > mx[0]:
            if e & 1:
                g0.setLeft(g0.right() - mx[0])
            else:
                g0.setWidth(mx[0])
        if g0.height() > mx[1]:
            if e & 4:
                g0.setTop(g0.bottom() - mx[1])
            else:
                g0.setHeight(mx[1])
        self.setGeometry(g0)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press is None:
            return
        kind, active = self._press_kind, self._active
        self._press = None
        self._active = False
        if active and kind == "resize":
            gm = self.geometry()
            self.c.resize_group(self.gid, gm.x(), gm.y(), gm.width(), gm.height())
        elif active and kind in ("move", "title", "tile"):
            self.c.move_group(self.gid, self.x(), self.y())
        elif not active:
            if kind == "tile":
                self.c.open_group(self.gid)                 # single click opens a small tile
            elif kind == "title":
                self.c.open_group(self.gid)                 # big panel: click the title
            elif kind == "menu":
                self.c.group_menu(self.gid, self, self.mapToGlobal(self.menu_rect().bottomLeft().toPoint()))
            elif kind == "item" and not self.c.edit_mode:   # edit mode never launches things
                g = self.group
                if g and self._press_item is not None and self._press_item < len(g["items"]):
                    self.c.clear_badge(self.gid)
                    self.c.launch(g["items"][self._press_item]["path"])   # big panel: click an item
        self.update()

    def wheelEvent(self, e):
        if self.mode != "panel":
            return
        pages = self.panel_layout()[4]
        dy = e.angleDelta().y()
        if pages > 1 and dy:
            self.page = max(0, min(pages - 1, self.page + (1 if dy < 0 else -1)))
            self.update()

    def contextMenuEvent(self, e):
        idx = self.item_at(QPointF(e.pos()))
        g = self.group
        if idx is not None and g:
            self.c.item_menu(self.gid, g["items"][idx]["path"], e.globalPos())
        else:
            self.c.group_menu(self.gid, self, e.globalPos())

    # ------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, e):
        if accept_drag(e):
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
        target = None
        g = self.group
        if self._drop_item is not None and g and self._drop_item < len(g["items"]):
            target = g["items"][self._drop_item]["path"]
        self._drop_item = None
        if not accept_drag(e):  # sets a safe action: never "move"
            return
        md = e.mimeData()
        # handle after the drop finishes, so Windows isn't kept waiting
        from PySide6.QtCore import QTimer
        from .glass import parse_drop
        item = read_item(md)
        dropped = parse_drop(md) if item is None else None
        QTimer.singleShot(0, lambda: self.c.handle_drop(self.gid, item, dropped, target))
        self.update()

    # ------------------------------------------------------------ rename
    def start_rename(self):
        g = self.group
        if g is None:
            return
        if self.editor is None:
            self.editor = QLineEdit(self)
            self.editor.setAlignment(Qt.AlignCenter)
            self.editor.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,240);color:#1c1c22;border:1px solid #0A84FF;"
                "border-radius:6px;padding:1px 3px;font-size:9.5pt;}")
            self.editor.editingFinished.connect(self._finish_rename)
            self.editor.installEventFilter(self)
        r = self.glass_rect()
        if self.mode == "tile":
            self.editor.setGeometry(1, int(r.bottom() + 3), self.width() - 2, 24)
        else:
            self.editor.setGeometry(int(r.left() + 26), int(r.top() + 5), int(r.width() - 70), 24)
        self.editor.setText(g["name"])
        self.editor.selectAll()
        self.editor.show()
        self.activateWindow()
        self.editor.setFocus(Qt.OtherFocusReason)
        self.update()

    def _finish_rename(self):
        if self.editor is None or not self.editor.isVisible():
            return
        name = self.editor.text().strip()
        self.editor.hide()
        if name:
            self.c.rename_group(self.gid, name)
        self.update()

    def eventFilter(self, obj, ev):
        if obj is self.editor and ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.editor.hide()
            self.update()
            return True
        return super().eventFilter(obj, ev)


def snap_rect(x, y, w, h, avail, others, grid=16):
    """Snap the top-left corner to a 16px grid and avoid sitting on top of other groups."""
    ox, oy = avail.left() + 8, avail.top() + 8

    def fits(px, py):
        r = QRect(px, py, w, h)
        if r.left() < avail.left() or r.top() < avail.top() or r.right() > avail.right() or r.bottom() > avail.bottom():
            return False
        return not any(r.adjusted(-2, -2, 2, 2).intersects(o) for o in others)

    bx = ox + round((x - ox) / grid) * grid
    by = oy + round((y - oy) / grid) * grid
    best = None
    for radius in range(0, 60):
        cands = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                px, py = bx + dx * grid, by + dy * grid
                if fits(px, py):
                    cands.append(((px - x) ** 2 + (py - y) ** 2, px, py))
        if cands:
            best = min(cands)
            break
    if best is None:
        px = min(max(bx, avail.left()), avail.right() - w)
        py = min(max(by, avail.top()), avail.bottom() - h)
        return QPoint(px, py)
    return QPoint(best[1], best[2])


def first_free_left(avail, others, w, h, start_x=176):
    """Default spot for a new group: on the LEFT, top to bottom. Starts a little in from the
    edge so Brian's own first two columns of desktop icons stay uncovered."""
    step = 16
    x = avail.left() + start_x
    while x + w <= avail.right():
        y = avail.top() + 8
        while y + h <= avail.bottom():
            r = QRect(x, y, w, h)
            if not any(r.adjusted(-6, -6, 6, 6).intersects(o) for o in others):
                return QPoint(x, y)
            y += step
        x += step * 2
    return QPoint(avail.left() + start_x, avail.top() + 8)


def cursor_pos():
    return QCursor.pos()
