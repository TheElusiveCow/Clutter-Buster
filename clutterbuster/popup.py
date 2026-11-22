"""The iOS-style group popup - a COMPACT frosted panel (no full-screen overlay).

It grows out of the clicked group (quick scale + fade), sits next to it, and the
rest of the desktop stays visible and usable. Big title, 3x3 grid of items with
names, page dots after 9 items. Click an item to open it. Click anywhere else
(or press Esc) to close - it shrinks back into the group. Drag empty space to move it.
Drag an item onto another item to make a new group with both.
"""
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from . import icons, sounds, tabs as tabsmod
from .store import current_tab, tab_indices
from .glass import (accept_drag, bring_to_top, draw_edit_outline, draw_glass, draw_neon, draw_shadow,
                    parse_drop, read_item, rounded)
from .theme import THEME, accent_color, qcolor, rad

MARGIN = 22        # room around the panel for its soft shadow
PAD = 20
HEADER_H = 58
DOTS_H = 26
EDGE = 9           # Edit layout: grab this close to the panel edge to resize it
MIN_ICON = 32


def cell_size(isz=None):
    isz = THEME["popup_icon"] if isz is None else isz
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
        self._resize = None      # Edit layout: (press pos, panel rect, edges)
        self._hover_tab = None
        self._drop_tab = None
        self._selected = None
        self.tab_editor = None
        self._editing_tab = None
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
    def metrics(self):
        """(panel w, panel h, cols, rows, cell w, cell h, icon size).
        Columns follow the "Icons per row" slider and icons the "Icon size" slider.
        After you resize the popup in Edit layout its size is kept and icons/rows fit into it."""
        cols = max(1, int((self.group or {}).get("per_row") or THEME.get("per_row", 3)))
        isz = int(THEME["popup_icon"])
        size = self.c.ui.get("popup_size") if hasattr(self.c, "ui") else None
        if size:
            w, h = size
            cw = (w - 2 * PAD) / cols
            isz = int(max(MIN_ICON, min(isz, cw - 54)))
            ch = isz + 50
            rows = max(1, int((h - self.header_h() - DOTS_H - PAD) // ch))
            if self.view() == "list":
                rows = tabsmod.rows_per_page(h - self.header_h() - DOTS_H - PAD)
            return w, h, cols, rows, cw, ch, isz
        cw, ch = cell_size(isz)
        w, h = cols * cw + 2 * PAD, self.header_h() + 3 * ch + DOTS_H + PAD
        if self.view() == "list":
            return w, h, 1, tabsmod.rows_per_page(3 * ch), w - 2 * PAD, tabsmod.ROW_H, isz
        return w, h, cols, 3, cw, ch, isz

    # ------------------------------------------------------------ tabs
    def multi_tab(self):
        g = self.group
        return bool(g) and len(g.get("tabs") or []) > 1

    def header_h(self):
        return HEADER_H + (tabsmod.TAB_H + 8 if self.multi_tab() else 0)

    def view(self):
        g = self.group
        return (current_tab(g) or {}).get("view", "icons") if g else "icons"

    def visible(self):
        g = self.group
        return tab_indices(g) if g else []

    def tab_bar(self):
        g = self.group
        pr = self.panel_rect()
        if g is None:
            return [], QRectF(), None
        if not self.multi_tab():
            return [], QRectF(), tabsmod.plus_only(pr.right() - PAD - 92, pr.top() + 8 + (46 - tabsmod.TAB_H) / 2)
        return tabsmod.bar_layout(tabsmod.tab_font(self.font(), 9.5), g["tabs"], pr.left() + PAD,
                                  pr.top() + HEADER_H - 6, pr.width() - 2 * PAD, current=g.get("tab"))

    def tab_at(self, pos):
        if self.progress < 1:
            return None
        segs, _t, plus = self.tab_bar()
        return tabsmod.hit_bar(segs, plus, QPointF(pos))

    def content_rect(self):
        pr = self.panel_rect()
        return QRectF(pr.left() + PAD, pr.top() + self.header_h(), pr.width() - 2 * PAD,
                      pr.height() - self.header_h() - DOTS_H - PAD / 2)

    def tab_changed(self):
        """Another tab was picked (or tabs were added/removed): back to page 1, keep the top-left."""
        self.page = 0
        self.page_pos = 0.0
        self._selected = None
        if self.isVisible():
            tl = self.geometry().topLeft()
            w, h = self.panel_size()
            self.setGeometry(tl.x(), tl.y(), w + 2 * MARGIN, h + 2 * MARGIN)
        self.update()

    def start_tab_rename(self, tid):
        g = self.group
        if g is None:
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
                "border-radius:9px;padding:0 4px;font-size:9.5pt;}")
            self.tab_editor.editingFinished.connect(self._finish_tab_rename)
            self.tab_editor.installEventFilter(self)
        self._editing_tab = tid
        w = max(100, int(rect.width()) + 24)
        self.tab_editor.setGeometry(int(rect.center().x() - w / 2), int(rect.top()), w, int(rect.height()))
        self.tab_editor.setText(t["name"])
        self.tab_editor.selectAll()
        self.tab_editor.show()
        self.tab_editor.setFocus(Qt.OtherFocusReason)

    def _finish_tab_rename(self):
        if self.tab_editor is None or not self.tab_editor.isVisible():
            return
        name = self.tab_editor.text().strip()
        self.tab_editor.hide()
        self.setFocus()
        if name:
            self.c.rename_tab(self.gid, self._editing_tab, name)
        self.update()

    def eventFilter(self, obj, ev):
        if obj is self.tab_editor and ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.tab_editor.hide()
            self.setFocus()
            self.update()
            return True
        return super().eventFilter(obj, ev)

    def min_panel_size(self):
        cols = max(1, int((self.group or {}).get("per_row") or THEME.get("per_row", 3)))
        cw, ch = cell_size(MIN_ICON)
        return cols * cw + 2 * PAD, HEADER_H + ch + DOTS_H + PAD

    def per_page(self):
        m = self.metrics()
        return m[2] * m[3]

    def panel_size(self):
        m = self.metrics()
        return int(m[0]), int(m[1])

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
        self._selected = None
        if self.tab_editor is not None:
            self.tab_editor.hide()
        self.progress = 0.0
        self.place_next_to(anchor_rect)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        bring_to_top(self)
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
        return max(1, math.ceil((len(self.visible()) if g else 0) / self.per_page()))

    def item_rect(self, k, shift=0.0):
        pr = self.panel_rect()
        _w, _h, cols, _rows, cw, ch, _isz = self.metrics()
        if self.view() == "list":
            cr = self.content_rect()
            return QRectF(cr.left() + shift, cr.top() + tabsmod.HEAD_H + k * tabsmod.ROW_H, cr.width(), tabsmod.ROW_H)
        row, col = divmod(k, cols)
        return QRectF(pr.left() + PAD + col * cw + shift, pr.top() + self.header_h() + row * ch, cw, ch)

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
        rr = rad(28)
        acc = accent_color(g)
        draw_shadow(p, pr, rr, 1.3, layers=10)
        draw_glass(p, pr, rr, fill_key="popup_fill", glow=self._drop_hover)
        draw_neon(p, pr, rr, accent=acc)
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
        segs, track, plus = self.tab_bar()
        title = fm.elidedText(g["name"], Qt.ElideRight, int(pr.width() - 2 * PAD - 130))
        p.drawText(QRectF(pr.left() + PAD + 20, pr.top() + 8, pr.width(), 46), Qt.AlignLeft | Qt.AlignVCenter, title)
        sf = QFont(self.font())
        sf.setPointSizeF(9)
        p.setFont(sf)
        p.setPen(qcolor("hint_text"))
        n = len(g["items"])
        p.drawText(QRectF(pr.left(), pr.top() + 8, pr.width() - PAD, 46), Qt.AlignRight | Qt.AlignVCenter,
                   f"{n} item{'s' if n != 1 else ''}")
        if segs:
            tabsmod.paint_bar(p, tabsmod.tab_font(self.font(), 9.5), g["tabs"], segs, track, plus, g.get("tab"),
                              acc, hover=self._hover_tab, drop=self._drop_tab)
        elif plus is not None:
            tabsmod.paint_plus(p, plus, self._hover_tab == "+")
        # items as soft white cards (clipped so sliding pages look right)
        p.save()
        p.setClipPath(rounded(pr, rr))
        nf = QFont(self.font())
        nf.setPointSizeF(9.5)
        p.setFont(nf)
        nfm = QFontMetrics(nf)
        isz = self.metrics()[6]
        per = self.per_page()
        opt = QTextOption(Qt.AlignHCenter | Qt.AlignTop)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        vis = self.visible()
        for page in range(self.pages()):
            shift = (page - self.page_pos) * (pr.width())
            if abs(shift) >= pr.width():
                continue
            if self.view() == "list":
                tabsmod.paint_list(p, self.content_rect().translated(shift, 0), g, vis[page * per:(page + 1) * per],
                                   self.font(), hover=self._hover_item if t >= 1 else None, selected=self._selected,
                                   drop=self._drop_item, accent=acc)
                p.setFont(nf)
                continue
            for k, idx in enumerate(vis[page * per:(page + 1) * per]):
                it = g["items"][idx]
                cell = self.item_rect(k, shift)
                card = cell.adjusted(5, 4, -5, -4)
                hot = (idx == self._hover_item and t >= 1) or idx == self._drop_item
                p.setPen(QPen(acc if idx == self._drop_item else qcolor("card_border"), 1.6 if hot else 1))
                p.setBrush(qcolor("card_fill_hot" if hot else "card_fill"))
                p.drawRoundedRect(card, rad(16), rad(16))
                ir = QRectF(card.center().x() - isz / 2, card.top() + 10, isz, isz)
                icons.icon_for(it["path"]).paint(p, ir.toRect())
                if self.c.hide_failed(it["path"]):
                    from .glass import draw_warn
                    draw_warn(p, QPointF(ir.right(), ir.bottom()), 8)
                name = icons.item_name(it)
                nr = QRectF(card.left() + 5, ir.bottom() + 5, card.width() - 10, nfm.height() * 2 + 2)
                if nfm.horizontalAdvance(name) > nr.width() * 2 - 12:
                    name = nfm.elidedText(name, Qt.ElideRight, int(nr.width() * 2 - 12))
                p.setPen(qcolor("panel_text"))
                p.drawText(nr, name, opt)
        if not vis:
            p.setPen(qcolor("panel_subtext"))
            f2 = QFont(self.font())
            f2.setPointSizeF(11)
            p.setFont(f2)
            p.drawText(pr.adjusted(30, self.header_h(), -30, -DOTS_H), Qt.AlignCenter | Qt.TextWordWrap,
                       "This group is empty.\nDrag shortcuts, files, folders or website links onto it."
                       if not g["items"] else "This tab is empty.\nDrag items onto the tab's name to move them here.")
        p.restore()
        if self.pages() > 1:
            p.setPen(Qt.NoPen)
            for i, dr in enumerate(self.dot_rects()):
                p.setBrush(qcolor("dot_on" if i == self.page else "dot_off"))
                p.drawEllipse(dr.center(), 4, 4)
        if self.c.edit_mode and t >= 1:
            draw_edit_outline(p, pr, rr, acc)
        p.end()

    # ------------------------------------------------------------ hit testing
    def item_at(self, pos):
        g = self.group
        if g is None or self.progress < 1:
            return None
        per = self.per_page()
        vis = self.visible()
        lst = self.view() == "list"
        for k, idx in enumerate(vis[self.page * per:(self.page + 1) * per]):
            r = self.item_rect(k)
            if (r if lst else r.adjusted(5, 4, -5, -4)).contains(QPointF(pos)):
                return idx
        return None

    # ------------------------------------------------------------ mouse / keys
    def edges_at(self, pos):
        """Edit layout only: which panel edges are under the mouse (1=L, 2=R, 4=T, 8=B)."""
        if not self.c.edit_mode:
            return 0
        pr = self.panel_rect()
        if not pr.adjusted(-EDGE, -EDGE, EDGE, EDGE).contains(pos):
            return 0
        e = 0
        if abs(pos.x() - pr.left()) < EDGE:
            e |= 1
        if abs(pos.x() - pr.right()) < EDGE:
            e |= 2
        if abs(pos.y() - pr.top()) < EDGE:
            e |= 4
        if abs(pos.y() - pr.bottom()) < EDGE:
            e |= 8
        return e

    def _do_resize(self, gpos):
        d = gpos - self._resize[0]
        g0 = QRect(self._resize[1])          # global panel rect at press time
        mw, mh = self.min_panel_size()
        e = self._resize[2]
        if e & 1:
            g0.setLeft(min(g0.left() + d.x(), g0.right() - mw))
        if e & 2:
            g0.setRight(max(g0.right() + d.x(), g0.left() + mw))
        if e & 4:
            g0.setTop(min(g0.top() + d.y(), g0.bottom() - mh))
        if e & 8:
            g0.setBottom(max(g0.bottom() + d.y(), g0.top() + mh))
        av = QGuiApplication.primaryScreen().availableGeometry()
        g0 = g0.intersected(av.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN))
        self.c.ui["popup_size"] = [g0.width(), g0.height()]
        self.setGeometry(g0.left() - MARGIN, g0.top() - MARGIN, g0.width() + 2 * MARGIN, g0.height() + 2 * MARGIN)
        self.page = min(self.page, self.pages() - 1)
        self.page_pos = float(self.page)
        self.update()

    def mousePressEvent(self, e):
        pos = e.position()
        if self.closing:
            return
        edges = self.edges_at(pos)
        if edges and e.button() == Qt.LeftButton:
            pr = self.panel_rect()
            self._resize = (e.globalPosition().toPoint(),
                            QRect(self.mapToGlobal(pr.topLeft().toPoint()), pr.size().toSize()), edges)
            return
        if not self.panel_rect().contains(pos):
            self.close_animated()  # the shadow margin counts as "outside"
            return
        t = self.tab_at(pos)
        if t is not None and e.button() == Qt.LeftButton:
            if t == "+":
                tid = self.c.add_tab(self.gid)
                if tid:
                    QTimer.singleShot(60, lambda: self.start_tab_rename(tid))
            else:
                self.c.select_tab(self.gid, t)
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
        if self._resize is not None and (e.buttons() & Qt.LeftButton):
            self._do_resize(e.globalPosition().toPoint())
            return
        cur = {5: Qt.SizeFDiagCursor, 10: Qt.SizeFDiagCursor, 6: Qt.SizeBDiagCursor, 9: Qt.SizeBDiagCursor}
        edges = self.edges_at(pos)
        if edges:
            self.setCursor(cur.get(edges, Qt.SizeHorCursor if edges & 3 else Qt.SizeVerCursor))
        else:
            self.unsetCursor()
        if self._press is not None and (e.buttons() & Qt.LeftButton):
            d = e.globalPosition().toPoint() - self._press
            if not self._dragging and d.manhattanLength() >= 6:
                self._dragging = True
                g = self.group
                if self._press_item is not None and g and self._press_item < len(g["items"]):
                    path = g["items"][self._press_item]["path"]
                    self._press = None
                    self._dragging = False
                    self.c.drag_item(self, path, self.gid)
                    return
            if self._dragging:
                self.move(self._press_win + d)   # drag the popup around
            return
        ht = self.tab_at(pos)
        if ht != self._hover_tab:
            self._hover_tab = ht
            self.setCursor(Qt.PointingHandCursor) if ht else self.unsetCursor()
            self.update()
        hv = self.item_at(pos)
        if hv != self._hover_item:
            self._hover_item = hv
            g = self.group
            self.setToolTip(g["items"][hv]["path"] if (g and hv is not None) else "")
            self.update()

    def mouseReleaseEvent(self, e):
        if self._resize is not None:
            self._resize = None
            self.c.ui_changed("popup_size")
            return
        if e.button() != Qt.LeftButton or self._press is None:
            return
        was_drag, pressed = self._dragging, self._press_item
        self._press = None
        self._dragging = False
        if not was_drag and pressed is not None and self.view() == "list":
            self._selected = pressed            # list view: click selects, double-click opens
            self.update()
            return
        if (not was_drag and pressed is not None and pressed == self.item_at(e.position())
                and not self.c.edit_mode):
            g = self.group
            if g and pressed < len(g["items"]):
                path = g["items"][pressed]["path"]
                self.close_animated()
                self.c.launch(path)

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton or self.view() != "list" or self.c.edit_mode:
            return
        idx = self.item_at(e.position())
        g = self.group
        if idx is not None and g and idx < len(g["items"]):
            path = g["items"][idx]["path"]
            self.close_animated()
            self.c.launch(path)

    def contextMenuEvent(self, e):
        t = self.tab_at(QPointF(e.pos()))
        if t and t != "+":
            self.c.tab_menu(self.gid, t, e.globalPos(), self)
            return
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
        if not self.isVisible() or self.isActiveWindow() or self.stay_open or self.c.edit_mode:
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
        g = self.group
        target = None
        if self._drop_item is not None and g and self._drop_item < len(g["items"]):
            target = g["items"][self._drop_item]["path"]
        self._drop_item = None
        tab = self._drop_tab
        self._drop_tab = None
        if g is None or not accept_drag(e):
            return
        item = read_item(e.mimeData())
        dropped = parse_drop(e.mimeData()) if item is None else None
        gid = self.gid
        QTimer.singleShot(0, lambda: self.c.handle_drop(gid, item, dropped, target, tab=tab))
        self.update()


