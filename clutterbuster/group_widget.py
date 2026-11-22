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
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLineEdit

from . import icons, namestyle, snapping, tabs as tabsmod
from .store import current_tab, tab_indices, tab_of
from PySide6.QtCore import QTimer as QTimerS
from .glass import (DesktopLayerWindow, accept_drag, draw_badge, draw_edit_outline, draw_glass,
                    draw_neon, draw_shadow, draw_warn, read_item)
from . import theme
from .theme import THEME, accent_color, is_dark, qcolor, rad

DRAG_THRESHOLD = 6
EDGE = 16          # resize zone along every edge (logical px - Windows scales it, ~24 px at 150%)
CORNER = 24        # bottom-right resize grip
LBL = 40      # room under a small tile for its name (bigger names, Brian asked)
TILE_DEFAULT, TILE_MIN, TILE_MAX = (96, 116), (56, 70), (320, 344)
TILE_PT, PANEL_PT = 11.0, 12.5   # default name sizes in points (Qt scales points with Windows DPI)
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
        self.tab_editor = None
        self._hover_tab = None
        self._hover_pencil = False
        self._hover_button = None
        self._drop_tab = None
        self._selected = None       # list view: clicked row (double-click opens)
        self._last_tab = None
        self._open_timer = QTimerS(self)
        self._open_timer.setSingleShot(True)
        self._open_timer.timeout.connect(lambda: self.c.open_group(self.gid))

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
            # the whole tile is glass now: name on top INSIDE it, then tabs, then icons
            # (nothing sticks out under it any more, so snapped tiles never overlap names)
            return QRectF(6, 6, max(24.0, self.width() - 12.0), max(24.0, self.height() - 12.0))
        return QRectF(6, 9, self.width() - 12, self.height() - 15)

    def tile_title_rect(self):
        r = self.glass_rect()
        h = QFontMetrics(self.name_font()).height() + 4
        return QRectF(r.left() + 8, r.top() + 5, r.width() - 16, h)

    def glass_rect_global(self):
        r = self.glass_rect().toRect()
        return QRect(self.mapToGlobal(r.topLeft()), r.size())

    def name_font(self):
        g = self.group
        st = namestyle.resolve(self.c.layout, g)
        if self.mode == "tile":
            return namestyle.font(self.font(), st, TILE_PT, False)
        return namestyle.font(self.font(), st, PANEL_PT, True)

    def name_size(self):
        """The name's current size in points (its own, else the default, else the theme's)."""
        return round(self.name_font().pointSizeF())

    def label_h(self):
        """Room under a small tile for its name - grows with bigger name sizes."""
        return max(LBL, QFontMetrics(self.name_font()).height() + 12)

    def name_buttons(self):
        """On hover: [A-] [A+] [pencil]. Panels: right after the name. Tiles: a little pill on the
        top edge of the square (there's no room beside a tile's name)."""
        g = self.group
        if g is None:
            return {}
        r = self.glass_rect()
        sz = 18
        if self.mode == "tile":
            tr = self.tile_title_rect()
            x0 = max(tr.left(), tr.right() - 4 * sz - 6)
            y = tr.center().y() - sz / 2
        else:
            tw = QFontMetrics(self.name_font()).horizontalAdvance(g["name"])
            x0 = min(r.left() + 30 + tw + 8, self.name_right() - 4 * sz - 10)
            y = r.top() + (TITLE_H - sz) / 2 + 1
        return {k: QRectF(x0 + i * (sz + 2), y, sz, sz) for i, k in enumerate(("smaller", "bigger", "pencil", "gear"))}

    def pencil_rect(self):
        return self.name_buttons().get("pencil")

    def button_at(self, pos):
        if not self._hover:
            return None
        if self.grip_rect().contains(QPointF(pos)):
            return None
        for k, br in self.name_buttons().items():
            if br.adjusted(-2, -2, 2, 2).contains(QPointF(pos)):
                return k
        return None

    def name_right(self):
        g = self.group
        segs, _t, plus = self.tab_bar()
        badge_w = 30 if g and g.get("badge") else 0
        return (plus.left() - 6) if (plus is not None and not segs) else (self.menu_rect().left() - 4 - badge_w)

    def labels_visible(self):
        return True

    def per_row(self):
        g = self.group
        return int((g or {}).get("per_row") or THEME.get("per_row", 3))

    def labels_mode(self):
        g = self.group
        return (g or {}).get("labels") or self.c.layout.prefs.get("panel_labels", "auto")

    def own_theme(self):
        return theme.group_theme(self.group, self.c.layout.prefs.get("theme", theme.AUTO), self.c.ui,
                                 self.c.layout.custom_themes)

    def paintEvent(self, e):
        with theme.swapped(self.own_theme()):        # a group can have its own theme / transparency
            super().paintEvent(e)

    def menu_rect(self):
        r = self.glass_rect()
        return QRectF(r.right() - 36, r.top() + 6, 28, 22)

    def title_rect(self):
        r = self.glass_rect()
        return QRectF(r.left(), r.top(), r.width(), TITLE_H)

    def multi_tab(self):
        g = self.group
        return bool(g) and len(g.get("tabs") or []) > 1

    def tab_bar(self):
        """(segments, track, plus rect). With one tab only a small '+' sits in the title bar."""
        g = self.group
        r = self.glass_rect()
        if not g:
            return [], QRectF(), None
        if not self.multi_tab():
            badge_w = 30 if g.get("badge") else 0
            mr = self.menu_rect()
            return [], QRectF(), tabsmod.plus_only(mr.left() - 26 - badge_w, r.top() + (TITLE_H - tabsmod.TAB_H) / 2 + 1)
        f = tabsmod.tab_font(self.font())
        return tabsmod.bar_layout(f, g["tabs"], r.left() + 10, r.top() + TITLE_H - 2, r.width() - 20,
                                  current=g.get("tab"))

    def tab_at(self, pos):
        if self.mode != "panel" or self.edges_at(pos):
            return None
        segs, _track, plus = self.tab_bar()
        return tabsmod.hit_bar(segs, plus, QPointF(pos))

    def content_rect(self):
        r = self.glass_rect()
        top = TITLE_H + (tabsmod.TAB_H + 6 if self.multi_tab() else 0)
        return QRectF(r.left() + 10, r.top() + top, r.width() - 20, r.height() - top - 10)

    def view(self):
        g = self.group
        return (current_tab(g) or {}).get("view", "icons") if g else "icons"

    def visible(self):
        g = self.group
        return tab_indices(g) if g else []

    def panel_layout(self):
        """(content rect, cols, rows, cell, pages). Icons per row follows the slider when it fits."""
        cr = self.content_rect()
        n = len(self.visible())
        if self.view() == "list":
            per = tabsmod.rows_per_page(cr.height() - (12 if n > tabsmod.rows_per_page(cr.height()) else 0))
            pages = max(1, math.ceil(n / per))
            self.page = min(self.page, pages - 1)
            return cr, 1, per, tabsmod.ROW_H, pages
        max_cell = THEME["popup_icon"] + 26          # compact, like desktop icons
        want = max(1, self.per_row())
        cell = min(max_cell, cr.width() / want)      # the columns share the width evenly
        if cell >= 44:
            cols = want
            rows = max(1, int((cr.height() - (14 if n > want else 0)) // cell)) if cr.height() >= cell else 0
            if rows >= 1:
                pages = max(1, math.ceil(n / (cols * rows)))
                self.page = min(self.page, pages - 1)
                return cr, cols, rows, cell, pages
        cols, rows, cell, pages = grid_layout(cr.width(), cr.height(), n, max_cell)
        self.page = min(self.page, pages - 1)
        return cr, cols, rows, cell, pages

    def panel_item_rects(self):
        """[(index, rect)] for the items on the current page of a big panel (current tab)."""
        g = self.group
        if not g:
            return []
        vis = self.visible()
        cr, cols, rows, cell, pages = self.panel_layout()
        per = cols * rows
        page_items = vis[self.page * per:(self.page + 1) * per]
        if self.view() == "list":
            return list(zip(page_items, tabsmod.row_rects(cr, len(page_items))))
        cw = cr.width() / cols
        out = []
        for k, idx in enumerate(page_items):
            r, c = divmod(k, cols)
            out.append((idx, QRectF(cr.left() + c * cw + (cw - cell) / 2, cr.top() + r * cell, cell, cell)))
        return out

    def item_at(self, pos):
        if self.mode != "panel" or self.edges_at(pos):
            return None
        pad = 0 if self.view() == "list" else 3
        for idx, r in self.panel_item_rects():
            if r.adjusted(pad, pad, -pad, -pad).contains(QPointF(pos)):
                return idx
        return None

    def edges_at(self, pos):
        """Which edges a point is on (1=left 2=right 4=top 8=bottom). The ONE test used for
        both the mouse cursor and the click, so what you see is what you get."""
        return edges_for(pos.x(), pos.y(), self.width(), self.height())

    def hit(self, pos):
        """(kind, edges) for a point: the hover buttons by the name, then resize, then the rest."""
        nb = self.button_at(pos)
        if nb is not None:
            return nb, 0
        e = 0 if self.c.layout_locked() else self.edges_at(pos)
        if e:
            return "resize", e
        if self.mode == "panel":
            if self.menu_rect().contains(pos):
                return "menu", 0
            t = self.tab_at(pos)
            if t is not None:
                return ("plus" if t == "+" else "tab:" + t), 0
            if self.item_at(pos) is not None:
                return "item", 0
            if self.title_rect().contains(pos):
                return "title", 0
            return "move", 0
        t = self.tile_tab_at(pos)
        if t is not None:
            return "tab:" + t, 0          # switch the tile's tab in place (doesn't open the popup)
        return "tile", 0

    def grip_rect(self):
        return QRectF(self.width() - CORNER, self.height() - CORNER, CORNER, CORNER)

    # ------------------------------------------------------------ painting
    def radius(self):
        if self.mode == "tile":
            return rad(max(8.0, min(22.0, self.glass_rect().width() * 0.12)))
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
        if (self.c.edit_mode or self._hover or self._active) and not self.c.layout_locked():
            self.paint_grip(p)
        n_fail = sum(1 for it in g["items"] if self.c.hide_failed(it["path"]))
        if n_fail and self.mode == "tile":
            draw_warn(p, QPointF(r.left() + 4, r.top() + 4), 8)

    def paint_name_buttons(self, p):
        for k, br in self.name_buttons().items():
            hot = self._hover_button == k
            if k == "pencil":
                draw_pencil(p, br, hot)
            elif k == "gear":
                draw_gear(p, br, hot)
            else:
                draw_size_button(p, br, k == "bigger", hot)

    def paint_warn(self, p, it, icon_r):
        """Small orange '!' on an item that couldn't be hidden (it's also still on the desktop)."""
        if self.c.hide_failed(it["path"]):
            draw_warn(p, QPointF(icon_r.right() - 2, icon_r.bottom() - 2), 7)

    def paint_grip(self, p):
        """Three short diagonal lines in the bottom-right corner: 'drag here to resize'."""
        gr = self.grip_rect()
        if self.mode == "panel":
            r = self.glass_rect()
            x2, y2 = r.right() - 5, r.bottom() - 5
        else:
            x2, y2 = gr.right() - 4, gr.bottom() - 4
        col = qcolor("panel_text" if self.mode == "panel" else "label_text")
        col.setAlpha(170)
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing)
        for k, n in enumerate((14, 9, 4)):
            pen = QPen(qcolor("label_shadow") if self.mode == "tile" else QColor(0, 0, 0, 0), 3.2)
            pen.setCapStyle(Qt.RoundCap)
            if self.mode == "tile":
                p.setPen(pen)
                p.drawLine(QPointF(x2 - n, y2), QPointF(x2, y2 - n))
            pen = QPen(col, 1.6)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x2 - n, y2), QPointF(x2, y2 - n))
        p.restore()

    # ---- small tiles: [ name ] [ tabs ] [ icons with names when there's room ]
    def tile_strip_area(self):
        if self.mode != "tile" or not self.multi_tab():
            return None
        tr = self.tile_title_rect()
        fm = QFontMetrics(self.strip_font())
        h = max(16.0, min(24.0, fm.height() + 8.0))
        return QRectF(tr.left(), tr.bottom() + 3, tr.width(), h)

    def strip_font(self, pt=8.5):
        return tabsmod.tab_font(self.font(), pt)

    def tile_bar(self):
        """(segments, track) of the tab pills at the top of a small tile; empty = use dots."""
        area = self.tile_strip_area()
        if area is None:
            return tabsmod.Segs(), QRectF()
        segs, track, _p = tabsmod.bar_layout(self.strip_font(), self.group["tabs"], area.left(), area.top(),
                                             area.width(), plus=False, current=self.group.get("tab"),
                                             h=area.height(), min_pt=6.5, dots_ok=True)
        if segs:      # centre the pill
            dx = (area.width() - track.width()) / 2
            if dx > 0:
                track = track.translated(dx, 0)
                moved = tabsmod.Segs((tid, rr.translated(dx, 0)) for tid, rr in segs)
                moved.font, moved.hidden, moved.names = segs.font, segs.hidden, segs.names
                segs = moved
        return segs, track

    def tile_strip(self):
        """[(tab id, rect)] - pills when they fit (names cut with '…', '▾' for the rest), else dots."""
        segs, _track = self.tile_bar()
        if segs:
            return list(segs)
        area = self.tile_strip_area()
        if area is None:
            return []
        tabs = self.group["tabs"]
        n = len(tabs)
        d = min(area.height() - 6, 10.0)
        step = min(d + 6, area.width() / n)
        x0 = area.center().x() - step * n / 2
        return [(t["id"], QRectF(x0 + i * step + (step - d) / 2, area.center().y() - d / 2, d, d))
                for i, t in enumerate(tabs)]

    def tile_tab_at(self, pos):
        for tid, rr in self.tile_strip():
            if rr.adjusted(-2, -3, 2, 3).contains(QPointF(pos)):
                return tid
        return None

    def paint_tile_strip(self, p, acc):
        segs, track = self.tile_bar()
        g = self.group
        if segs:
            tabsmod.paint_bar(p, self.strip_font(), g["tabs"], segs, track, None, g.get("tab"), acc,
                              hover=self._hover_tab)
            return
        strip = self.tile_strip()
        if not strip:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        for tid, rr in strip:
            if tid == g.get("tab"):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(acc))
            else:
                p.setPen(QPen(QColor(255, 255, 255, 110) if is_dark() else QColor(0, 0, 0, 80), 1))
                p.setBrush(Qt.NoBrush)
            p.drawEllipse(rr)
        p.restore()

    def tile_label_font(self):
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        return f

    def tile_layout(self):
        """-> (cells [(item index, icon rect, cell rect)], lines of name under each icon).
        Names show whenever a cell has room for the icon + a line of text (Settings can force
        Always / Never)."""
        g = self.group
        if g is None or self.mode != "tile":
            return [], 0
        r = self.glass_rect()
        n = max(2, min(6, self.per_row()))      # follows "Icons per row" (this group's own, if set)
        strip = self.tile_strip_area()
        top = (strip.bottom() if strip is not None else self.tile_title_rect().bottom()) + 5
        pad = max(6.0, r.width() * 0.06)
        area = QRectF(r.left() + pad, top, r.width() - 2 * pad, r.bottom() - pad * 0.8 - top)
        shown = (tab_indices(g) if g.get("tabs") else list(range(len(g["items"]))))[:n * n]
        lh = QFontMetrics(self.tile_label_font()).height()
        cw = area.width() / n
        rows = max(1, math.ceil(len(shown) / n))
        ch = min(area.height() / rows, cw + 2 * lh + 6)
        mode = self.labels_mode()
        lines = 0
        if mode != "never" and area.height() > 0:
            if ch - 2 * lh - 4 >= max(18.0, cw * 0.5):
                lines = 2
            elif ch - lh - 4 >= max(16.0, cw * 0.42) or mode == "always":
                lines = 1
        if lines:
            isz = max(10.0, min(cw * 0.74, ch - lines * lh - 6))
        else:
            isz = min(cw, ch) * 0.84
        out = []
        for i, idx in enumerate(shown):
            row, col = divmod(i, n)
            cell = QRectF(area.left() + col * cw, area.top() + row * ch, cw, ch)
            block = isz + (lines * lh + 2 if lines else 0)
            y = cell.top() + max(0.0, (ch - block) / 2) if not lines else cell.top() + 2
            out.append((idx, QRectF(cell.center().x() - isz / 2, y, isz, isz), cell))
        return out, lines

    def tile_preview_rects(self):
        """[(item index, icon rect)] of the icons inside a small tile (the selected tab)."""
        return [(idx, ir) for idx, ir, _c in self.tile_layout()[0]]

    def tile_item_at(self, pos):
        cells, lines = self.tile_layout()
        for idx, ir, cell in cells:
            hit = ir.adjusted(-2, -2, 2, 2)
            if lines:
                hit = hit.united(QRectF(cell.left() + 2, ir.bottom(), cell.width() - 4, cell.bottom() - ir.bottom()))
            if hit.contains(QPointF(pos)):
                return idx
        return None

    def _paint_tile(self, p, g):
        r = self.glass_rect()
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
        # the name, on top inside the tile
        if not (self.editor and self.editor.isVisible()):
            st = namestyle.resolve(self.c.layout, g)
            tr = self.tile_title_rect()
            if self._hover:            # leave room for the A- A+ pencil buttons on the right
                bw = 4 * 20 + 6
                tr = tr.adjusted(bw, 0, -bw, 0) if tr.width() > 2 * bw + 30 else tr.adjusted(0, 0, -bw, 0)
            namestyle.draw(p, tr, g["name"], Qt.AlignHCenter | Qt.AlignVCenter, st, self.font(), TILE_PT, False,
                           "panel_title_text", default_effect="shadow" if is_dark() else "none",
                           elide_w=tr.width())
            if self._hover:
                self.paint_name_buttons(p)
        self.paint_tile_strip(p, acc)
        cells, lines = self.tile_layout()
        lf = self.tile_label_font()
        lfm = QFontMetrics(lf)
        for idx, ir, cell in cells:
            it = g["items"][idx]
            if idx == self._hover_item:                      # hover: a soft highlight = clickable
                hl = (QRectF(cell.left() + 2, ir.top() - 3, cell.width() - 4,
                             (cell.bottom() if lines else ir.bottom() + 3) - ir.top() + 3) if lines
                      else ir.adjusted(-4, -4, 4, 4))
                p.setPen(QPen(QColor(255, 255, 255, 70) if is_dark() else QColor(0, 0, 0, 40), 1))
                p.setBrush(QColor(255, 255, 255, 40) if is_dark() else QColor(0, 0, 0, 22))
                p.drawRoundedRect(hl, 8, 8)
            icons.icon_for(it["path"]).paint(p, ir.toRect())
            if lines:
                y = ir.bottom() + 2
                p.setFont(lf)
                for line in two_lines(lfm, icons.item_name(it), cell.width() - 4)[:lines]:
                    draw_item_label(p, QRectF(cell.left() + 1, y, cell.width() - 2, lfm.height() + 1), line)
                    y += lfm.height()

    def _paint_panel(self, p, g):
        r = self.glass_rect()
        acc = accent_color(g)
        draw_shadow(p, r, self.radius(), 1.0)
        draw_glass(p, r, self.radius(), fill_key="panel_fill", glow=self._drop_hover, strip=True)
        # title bar: accent dot + name + "..." menu
        p.setPen(Qt.NoPen)
        p.setBrush(acc)
        p.drawEllipse(QPointF(r.left() + 17, r.top() + TITLE_H / 2 + 1), 5, 5)
        mr = self.menu_rect()
        badge_w = 30 if g.get("badge") else 0
        segs, track, plus = self.tab_bar()
        name_right = (plus.left() - 6) if (plus is not None and not segs) else (mr.left() - 4 - badge_w)
        if not (self.editor and self.editor.isVisible()):
            st = namestyle.resolve(self.c.layout, g)
            namestyle.draw(p, QRectF(r.left() + 30, r.top(), name_right - r.left() - 30, TITLE_H + 2),
                           g["name"], Qt.AlignLeft | Qt.AlignVCenter, st, self.font(), PANEL_PT, True,
                           "panel_title_text", elide_w=name_right - r.left() - 32 - 24)
            if self._hover:
                self.paint_name_buttons(p)
        p.setPen(qcolor("hint_text"))
        p.setFont(QFont(self.font()))
        p.drawText(mr, Qt.AlignCenter, "\u2022\u2022\u2022")
        if segs:
            tabsmod.paint_bar(p, tabsmod.tab_font(self.font()), g["tabs"], segs, track, plus, g.get("tab"), acc,
                              hover=self._hover_tab, drop=self._drop_tab)
        elif plus is not None and (self._hover or self.c.edit_mode):
            tabsmod.paint_plus(p, plus, self._hover_tab == "+")
        # items (current tab)
        cr, cols, rows, cell, pages = self.panel_layout()
        vis = self.visible()
        if self.view() == "list":
            page_items = [i for i, _r in self.panel_item_rects()]
            tabsmod.paint_list(p, cr, g, page_items, self.font(), hover=self._hover_item,
                               selected=self._selected, drop=self._drop_item, accent=acc)
            show_labels = True
            nf = QFont(self.font())
            nfm = QFontMetrics(nf)
        else:
            nf = QFont(self.font())
            nf.setPointSizeF(8.5)
            p.setFont(nf)
            nfm = QFontMetrics(nf)
            show_labels = labels_fit(cell, nfm.height(), self.labels_mode())
            for idx, ir in self.panel_item_rects():
                it = g["items"][idx]
                card = ir.adjusted(4, 4, -4, -4)
                hot = idx == self._hover_item or idx == self._drop_item
                p.setPen(QPen(acc if idx == self._drop_item else qcolor("card_border"), 1.5 if hot else 1))
                p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
                p.drawRoundedRect(card, rad(max(6, cell * 0.16)), rad(max(6, cell * 0.16)))
                if show_labels:
                    # icon on top, room for two lines of name under it
                    isz = max(14.0, min(cell * 0.55, card.height() - 2 * nfm.height() - 12))
                    if isz < cell * 0.38:          # only room for one line: a bigger icon
                        isz = max(14.0, min(cell * 0.55, card.height() - nfm.height() - 12))
                    icon_r = QRectF(card.center().x() - isz / 2, card.top() + 5, isz, isz)
                else:
                    isz = cell * 0.6
                    icon_r = QRectF(card.center().x() - isz / 2, card.center().y() - isz / 2, isz, isz)
                icons.icon_for(it["path"]).paint(p, icon_r.toRect())
                self.paint_warn(p, it, icon_r)
                if show_labels:
                    y = icon_r.bottom() + 3
                    for line in two_lines(nfm, icons.item_name(it), card.width() - 6):
                        if y + nfm.height() > card.bottom() + 3:
                            break
                        draw_item_label(p, QRectF(card.left() + 2, y, card.width() - 4, nfm.height() + 1), line)
                        y += nfm.height()
        if not vis:
            p.setPen(qcolor("hint_text"))
            p.setFont(QFont(self.font()))
            p.drawText(cr, Qt.AlignCenter | Qt.TextWordWrap,
                       "Drop shortcuts, files, folders or links here" if not g["items"] else "This tab is empty")
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
            tip = f"{g['name']} - {n} item{'s' if n != 1 else ''}\nClick to open"
            fails = [icons.item_name(it) for it in g["items"] if self.c.hide_failed(it["path"])]
            if fails:
                tip += ("\n\u26A0 Couldn't hide " + ", ".join(fails) +
                        " (shared Public desktop needs permission) - still visible on the desktop")
            self.setToolTip(tip)
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._hover_item = None
        self._hover_tab = None
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
        self._press_kind, self._edges = self.hit(pos)
        self._press_item = (self.item_at(pos) if self._press_kind == "item" else
                            self.tile_item_at(pos) if self._press_kind == "tile" else None)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            kind_, edges_ = self.hit(pos)
            cur = self._cursor_for(edges_)
            ht = kind_[4:] if kind_.startswith("tab:") else ("+" if kind_ == "plus" else None)
            hb = kind_ if kind_ in ("smaller", "bigger", "pencil", "gear") else None
            hp = hb is not None
            if hb != self._hover_button:
                self._hover_button = hb
                self._hover_pencil = hb == "pencil"
                tips = {"pencil": "Rename (or double-click the name)",
                        "gear": "Settings for this group",
                        "smaller": f"Smaller name ({self.name_size()} pt) - or Ctrl + mouse wheel over the name",
                        "bigger": f"Bigger name ({self.name_size()} pt) - or Ctrl + mouse wheel over the name"}
                self.setToolTip(tips.get(hb, ""))
            if self.mode == "tile" and ht != getattr(self, "_strip_tip", None):
                self._strip_tip = ht
                tb = tab_of(self.group, ht) if ht and self.group else None
                self.setToolTip(f"Show tab: {tb.get('name') or 'Tab'}" if tb else "")
                self.update()
            if ht != self._hover_tab:
                self._hover_tab = ht
                self.setToolTip("Add a tab" if ht == "+" else "")
                self.update()
            if cur is not None:
                self.setCursor(cur)
            elif hp:
                self.setCursor(Qt.PointingHandCursor)
            elif self.c.edit_mode:
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.unsetCursor()
            hv = self.item_at(pos) if self.mode == "panel" else (
                None if (hp or cur is not None) else self.tile_item_at(pos))
            if self.mode == "tile" and hv is not None and cur is None:
                self.setCursor(Qt.PointingHandCursor)        # icons on a tile are clickable
            if hv != self._hover_item:
                self._hover_item = hv
                g = self.group
                if g and hv is not None and hv < len(g["items"]):
                    self.setToolTip(icons.item_name(g["items"][hv]))     # the full name
                elif ht is None:
                    self.setToolTip("")
                self.update()
            return
        delta = e.globalPosition().toPoint() - self._press
        if not self._active and delta.manhattanLength() >= DRAG_THRESHOLD:
            self._active = True
            if self._press_kind == "item" or (self._press_kind == "tile" and self._press_item is not None):
                # an icon (big panel grid or a small tile's mini preview) dragged straight out:
                # onto the desktop = shown again, onto another group = moved there
                g = self.group
                if g and self._press_item is not None and self._press_item < len(g["items"]):
                    path = g["items"][self._press_item]["path"]
                    self._press = None
                    self._active = False
                    self.c.drag_item(self, path, self.gid)
                return
        if not self._active:
            return
        if self._press_kind == "resize":
            self._do_resize(delta)
        elif self._press_kind in ("move", "title", "tile") and not self.c.layout_locked():
            pos_ = self._press_geom.topLeft() + delta
            guides = []
            if self.c.snap_on():
                gr = QRectF(self.glass_rect()).translated(pos_.x(), pos_.y())
                dx, dy, guides = snapping.magnetic(gr, self.c.snap_targets(self.gid), self.c.avail())
                pos_ = QPoint(round(pos_.x() + dx), round(pos_.y() + dy))
            self.move(pos_)
            self.c.show_guides(guides, self)

    def _do_resize(self, d):
        rect = resize_rect(self._press_geom, d, self._edges, self.mode)
        guides = []
        if self.mode == "panel" and self.c.snap_on():
            # snap the glass edges being dragged (the window has a small shadow margin around it)
            gl = QRectF(rect).adjusted(6, 9, -6, -6)
            gl, guides = snapping.magnetic_edges(gl, self._edges, self.c.snap_targets(self.gid), self.c.avail())
            cand = snapping.to_rect(gl.adjusted(-6, -9, 6, 6))
            if cand.width() >= PANEL_MIN[0] and cand.height() >= PANEL_MIN[1]:
                rect = cand
        self.setGeometry(rect)
        self.c.show_guides(guides, self)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press is None:
            return
        kind, active = self._press_kind, self._active
        self._press = None
        self._active = False
        self.c.show_guides([], self)
        if active and kind == "resize":
            gm = self.geometry()
            self.c.resize_group(self.gid, gm.x(), gm.y(), gm.width(), gm.height())
        elif active and kind in ("move", "title", "tile") and not self.c.layout_locked():
            self.c.move_group(self.gid, self.x(), self.y())
        elif not active:
            if kind == "pencil":
                self.start_rename()
            elif kind == "gear":
                self.c.fence_settings(self.gid, self)
            elif kind in ("smaller", "bigger"):
                self.c.bump_name_size(self.gid, 1 if kind == "bigger" else -1)
                self.setToolTip(f"Name size: {self.name_size()} pt")
            elif kind in ("tile", "title") and self.on_name(e.position()):
                # the name: wait a moment - a double-click renames instead of opening
                self._open_timer.start(QApplication.doubleClickInterval())
            elif kind == "tile" and self._press_item is not None and not self.c.edit_mode:
                g = self.group                              # an icon on a small tile: launch it
                if g and self._press_item < len(g["items"]):
                    self.c.clear_badge(self.gid)
                    self.c.launch(g["items"][self._press_item]["path"])
            elif kind == "tile":
                self.c.open_group(self.gid)                 # empty space opens a small tile
            elif kind == "title":
                self.c.open_group(self.gid)                 # big panel: click the title
            elif kind.startswith("tab:"):
                self.c.select_tab(self.gid, kind[4:])
            elif kind == "plus":
                tid = self.c.add_tab(self.gid)
                if tid:
                    QTimerS.singleShot(60, lambda: self.start_tab_rename(tid))
            elif kind == "menu":
                self.c.group_menu(self.gid, self, self.mapToGlobal(self.menu_rect().bottomLeft().toPoint()))
            elif kind == "item" and self.view() == "list":    # list view: click selects, double-click opens
                self._selected = self._press_item
            elif kind == "item" and not self.c.edit_mode:   # edit mode never launches things
                g = self.group
                if g and self._press_item is not None and self._press_item < len(g["items"]):
                    self.c.clear_badge(self.gid)
                    self.c.launch(g["items"][self._press_item]["path"])   # big panel: click an item
        self.update()

    def on_name(self, pos):
        """Is pos on the group's name? (under a small tile, or the big panel's title text)"""
        r = self.glass_rect()
        pos = QPointF(pos)
        if self.mode == "tile":
            return self.tile_title_rect().adjusted(0, -3, 0, 2).contains(pos)
        return r.top() <= pos.y() <= r.top() + TITLE_H and r.left() + 24 <= pos.x() <= self.menu_rect().left() - 30

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and self.on_name(e.position()) and not self.tab_at(e.position()):
            self._open_timer.stop()
            self.start_rename()                          # Enter saves, Esc cancels (one undo step)
            return
        if e.button() != Qt.LeftButton or self.view() != "list" or self.c.edit_mode:
            return
        idx = self.item_at(e.position())
        g = self.group
        if idx is not None and g and idx < len(g["items"]):
            self.c.clear_badge(self.gid)
            self.c.launch(g["items"][idx]["path"])

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier and (self.on_name(e.position()) or self.button_at(e.position())):
            dy = e.angleDelta().y()
            if dy:
                self.c.bump_name_size(self.gid, 1 if dy > 0 else -1)     # Ctrl + wheel over the name
            e.accept()
            return
        self._wheel_page(e)

    def _wheel_page(self, e):
        if self.mode != "panel":
            return
        pages = self.panel_layout()[4]
        dy = e.angleDelta().y()
        if pages > 1 and dy:
            self.page = max(0, min(pages - 1, self.page + (1 if dy < 0 else -1)))
            self.update()

    def contextMenuEvent(self, e):
        t = self.tab_at(QPointF(e.pos()))
        if t and t != "+":
            self.c.tab_menu(self.gid, t, e.globalPos(), self)
            return
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
        t = self.tab_at(e.position())
        t = t if t and t != "+" else None
        di = None if t else (self.item_at(e.position()) if read_item(e.mimeData()) else None)
        if di != self._drop_item or t != self._drop_tab:
            self._drop_item = di
            self._drop_tab = t
            self.update()

    def dragLeaveEvent(self, e):
        self._drop_hover = False
        self._drop_item = None
        self._drop_tab = None
        self.update()

    def dropEvent(self, e):
        self._drop_hover = False
        target = None
        g = self.group
        if self._drop_item is not None and g and self._drop_item < len(g["items"]):
            target = g["items"][self._drop_item]["path"]
        self._drop_item = None
        tab = self._drop_tab
        self._drop_tab = None
        if not accept_drag(e):  # sets a safe action: never "move"
            return
        md = e.mimeData()
        # handle after the drop finishes, so Windows isn't kept waiting
        from PySide6.QtCore import QTimer
        from .glass import parse_drop
        item = read_item(md)
        dropped = parse_drop(md) if item is None else None
        QTimer.singleShot(0, lambda: self.c.handle_drop(self.gid, item, dropped, target, tab=tab))
        self.update()

    # ------------------------------------------------------------ rename
    def start_rename(self):
        g = self.group
        if g is None:
            return
        if self.editor is None:
            self.editor = QLineEdit(self)
            self.editor.setAlignment(Qt.AlignCenter)
            self.editor.setStyleSheet(rename_qss())
            self.editor.editingFinished.connect(self._finish_rename)
            self.editor.installEventFilter(self)
        r = self.glass_rect()
        st = namestyle.resolve(self.c.layout, g)
        ef = namestyle.font(self.font(), st, TILE_PT if self.mode == "tile" else PANEL_PT, self.mode != "tile")
        self.editor.setFont(ef)
        eh = QFontMetrics(ef).height() + 8
        if self.mode == "tile":
            tr = self.tile_title_rect()
            self.editor.setGeometry(int(tr.left()), int(tr.center().y() - eh / 2), int(tr.width()), eh)
        else:
            self.editor.setGeometry(int(r.left() + 26), int(r.top() + (TITLE_H - eh) / 2 + 1), int(r.width() - 70), eh)
        self.editor.setStyleSheet(rename_qss())
        self.editor.setText(g["name"])
        self.editor.selectAll()
        self.editor.show()
        self.activateWindow()
        self.editor.setFocus(Qt.OtherFocusReason)
        self.update()

    def start_tab_rename(self, tid):
        g = self.group
        if g is None or self.mode != "panel":
            return
        segs, _t, _p = self.tab_bar()
        rect = dict(segs).get(tid)
        t = next((x for x in g["tabs"] if x["id"] == tid), None)
        if rect is None or t is None:
            return
        if self.tab_editor is None:
            self.tab_editor = QLineEdit(self)
            self.tab_editor.setAlignment(Qt.AlignCenter)
            self.tab_editor.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,245);color:#1c1c22;border:1px solid #0A84FF;"
                "border-radius:9px;padding:0 4px;font-size:9pt;}")
            self.tab_editor.editingFinished.connect(self._finish_tab_rename)
            self.tab_editor.installEventFilter(self)
        self._editing_tab = tid
        w = max(90, int(rect.width()) + 20)
        self.tab_editor.setGeometry(int(rect.center().x() - w / 2), int(rect.top()), w, int(rect.height()))
        self.tab_editor.setText(t["name"])
        self.tab_editor.selectAll()
        self.tab_editor.show()
        self.activateWindow()
        self.tab_editor.setFocus(Qt.OtherFocusReason)

    def _finish_tab_rename(self):
        if self.tab_editor is None or not self.tab_editor.isVisible():
            return
        name = self.tab_editor.text().strip()
        self.tab_editor.hide()
        if name:
            self.c.rename_tab(self.gid, self._editing_tab, name)
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
        if obj is self.tab_editor and ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.tab_editor.hide()
            self.update()
            return True
        if obj is self.editor and ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.editor.hide()
            self.update()
            return True
        return super().eventFilter(obj, ev)


def rename_qss():
    """The in-place rename box: frosted glass in the theme's colours, accent outline."""
    from .theme import THEME, is_dark
    acc = THEME.get("default_accent", "#0A84FF")
    if is_dark():
        return (f"QLineEdit{{background:rgba(28,30,48,235);color:#F2F4FF;border:1.5px solid {acc};"
                f"border-radius:9px;padding:2px 8px;selection-background-color:{acc};}}")
    return (f"QLineEdit{{background:rgba(255,255,255,238);color:#1C1C22;border:1.5px solid {acc};"
            f"border-radius:9px;padding:2px 8px;selection-background-color:{acc};selection-color:white;}}")


def draw_size_button(p, r, bigger, hot=False):
    """A small round glass button with 'A-' or 'A+'."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(qcolor("card_border"), 1))
    p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
    p.drawEllipse(r)
    f = QFont()
    f.setPixelSize(int(r.height() * (0.62 if bigger else 0.5)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(qcolor("panel_text"))
    p.drawText(r.adjusted(-1, 0, -4, 0), Qt.AlignCenter, "A")
    p.drawText(r.adjusted(r.width() * 0.52, -r.height() * 0.18, 0, 0), Qt.AlignLeft | Qt.AlignVCenter,
               "+" if bigger else "\u2212")
    p.restore()


def draw_pencil(p, r, hot=False):
    """A small round glass button with a pencil in it."""
    if r is None:
        return
    from PySide6.QtGui import QPolygonF
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(qcolor("card_border"), 1))
    p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
    p.drawEllipse(r)
    c = r.center()
    k = r.width() / 17.0
    col = qcolor("panel_text")
    p.setPen(QPen(col, 1.1))
    p.setBrush(col)
    body = QPolygonF([QPointF(c.x() - 4.2 * k, c.y() + 2.6 * k), QPointF(c.x() + 2.6 * k, c.y() - 4.2 * k),
                      QPointF(c.x() + 4.2 * k, c.y() - 2.6 * k), QPointF(c.x() - 2.6 * k, c.y() + 4.2 * k)])
    p.drawPolygon(body)
    tip = QPolygonF([QPointF(c.x() - 4.2 * k, c.y() + 2.6 * k), QPointF(c.x() - 2.6 * k, c.y() + 4.2 * k),
                     QPointF(c.x() - 5.0 * k, c.y() + 5.0 * k)])
    p.drawPolygon(tip)
    p.restore()


def draw_gear(p, r, hot=False):
    """A small round glass button with a cog in it (this group's own settings)."""
    if r is None:
        return
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(qcolor("card_border"), 1))
    p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
    p.drawEllipse(r)
    c = r.center()
    k = r.width() / 18.0
    col = qcolor("panel_text")
    pen = QPen(col, 1.9 * k)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for i in range(8):
        a = math.pi / 4 * i
        p.drawLine(QPointF(c.x() + 3.6 * k * math.cos(a), c.y() + 3.6 * k * math.sin(a)),
                   QPointF(c.x() + 5.6 * k * math.cos(a), c.y() + 5.6 * k * math.sin(a)))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(col, 1.6 * k))
    p.drawEllipse(c, 3.4 * k, 3.4 * k)
    p.restore()


def labels_fit(cell, line_h, mode="auto"):
    """Names under big-panel icons: Always / Never / Auto = when a cell fits an icon + ~2 lines."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    return cell - 8 >= 18 + line_h + 8       # an icon + one line is enough (2 lines when there's room)


def draw_item_label(p, rect, text):
    """An item's name: small white text with a soft shadow on dark themes (like the mockup),
    the theme's text colour on light ones."""
    if is_dark():
        p.setPen(QColor(0, 0, 0, 150))
        p.drawText(rect.translated(0, 1), Qt.AlignHCenter | Qt.AlignTop, text)
        p.setPen(QColor(255, 255, 255, 240))
    else:
        p.setPen(qcolor("panel_text"))
    p.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, text)


def two_lines(fm, text, width):
    """Wrap a name onto at most two lines; the second ends with '…' if it's still too long."""
    width = int(max(10, width))
    if fm.horizontalAdvance(text) <= width:
        return [text]
    words, first = text.split(" "), ""
    for i in range(len(words), 0, -1):
        cand = " ".join(words[:i])
        if fm.horizontalAdvance(cand) <= width:
            first, rest = cand, " ".join(words[i:])
            break
    else:                                   # one long word: cut it by letters
        n = len(text)
        while n > 1 and fm.horizontalAdvance(text[:n]) > width:
            n -= 1
        if 0 < len(text) - n < 3:          # no lonely 1-2 letters on line 2 ("Monosna / p")
            n = max(1, (len(text) + 1) // 2)
        first, rest = text[:n], text[n:]
    return [first, fm.elidedText(rest.strip(), Qt.ElideRight, width)] if rest.strip() else [first]


def edges_for(x, y, w, h):
    """Resize hit-test shared by hover and press: 16 px along each edge, 24 px grip corner."""
    if x < 0 or y < 0 or x > w or y > h:
        return 0
    if x >= w - CORNER and y >= h - CORNER:
        return 2 | 8                      # the bottom-right grip
    e = 0
    if x < EDGE:
        e |= 1
    if x > w - EDGE:
        e |= 2
    if y < EDGE:
        e |= 4
    if y > h - EDGE:
        e |= 8
    return e


def resize_rect(g0, d, e, mode):
    """New window rect while resizing from press-time rect g0 by mouse delta d on edges e.
    Small tiles stay SQUARE (the glass square + its label): any edge or corner makes the whole
    tile bigger/smaller, anchored on the opposite side. (Before, dragging one edge of a tile
    only widened the transparent window and the square slid sideways - it looked like moving.)"""
    g0 = QRect(g0)
    if mode == "tile":
        s0 = min(g0.width() - 20, g0.height() - LBL)
        deltas = []
        if e & 1:
            deltas.append(-d.x())
        if e & 2:
            deltas.append(d.x())
        if e & 4:
            deltas.append(-d.y())
        if e & 8:
            deltas.append(d.y())
        ds = max(deltas, key=abs) if deltas else 0
        s = int(max(TILE_MIN[0] - 20, min(TILE_MAX[1] - LBL, s0 + ds)))
        w, h = s + 20, s + LBL
        x = g0.right() + 1 - w if e & 1 else g0.left()
        y = g0.bottom() + 1 - h if e & 4 else g0.top()
        if not (e & 1) and not (e & 2):            # top/bottom only: keep it centred
            x = g0.left() + (g0.width() - w) // 2
        return QRect(x, y, w, h)
    mw, mh = PANEL_MIN
    if e & 1:
        g0.setLeft(min(g0.left() + d.x(), g0.right() - mw))
    if e & 2:
        g0.setRight(max(g0.right() + d.x(), g0.left() + mw))
    if e & 4:
        g0.setTop(min(g0.top() + d.y(), g0.bottom() - mh))
    if e & 8:
        g0.setBottom(max(g0.bottom() + d.y(), g0.top() + mh))
    return g0


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
