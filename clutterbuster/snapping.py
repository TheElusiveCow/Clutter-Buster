"""Magnetic snapping while you drag or resize a group.

Within SNAP px (logical pixels - Windows display scaling is already applied) an edge jumps to:
  * next to another group with a small GAP between them,
  * the same left / right / top / bottom / centre line as another group,
  * the screen edges (the taskbar edge counts: we use the screen area above it).
Further away the group moves freely. Hold Alt to place freely. Faint guide lines show the snap.
"""
from PySide6.QtCore import QLineF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

SNAP = 12
GAP = 8
NEAR = 160        # side-by-side snapping only for groups this close on the other axis


def alt_held():
    return bool(QGuiApplication.queryKeyboardModifiers() & Qt.AltModifier)


def _best(cands, cur):
    best = None
    for val, guide in cands:
        d = abs(val - cur)
        if d <= SNAP and (best is None or d < best[0]):
            best = (d, val, guide)
    return best


def magnetic(r, others, screen):
    """r = the moving group's glass rect (global, QRectF) at the mouse position.
    -> (dx, dy, [guide lines]) to add to the position."""
    r = QRectF(r)
    sc = QRectF(screen)
    cx, cy = [], []
    for o in others:
        o = QRectF(o)
        span_y = (min(r.top(), o.top()) - 6, max(r.bottom(), o.bottom()) + 6)
        span_x = (min(r.left(), o.left()) - 6, max(r.right(), o.right()) + 6)
        near_v = r.top() < o.bottom() + NEAR and r.bottom() > o.top() - NEAR
        near_h = r.left() < o.right() + NEAR and r.right() > o.left() - NEAR
        if near_v:
            cx.append((o.left() - GAP - r.width(), ("v", o.left() - GAP / 2, span_y)))
            cx.append((o.right() + GAP, ("v", o.right() + GAP / 2, span_y)))
        if near_h:
            cy.append((o.top() - GAP - r.height(), ("h", o.top() - GAP / 2, span_x)))
            cy.append((o.bottom() + GAP, ("h", o.bottom() + GAP / 2, span_x)))
        cx += [(o.left(), ("v", o.left(), span_y)), (o.right() - r.width(), ("v", o.right(), span_y)),
               (o.center().x() - r.width() / 2, ("v", o.center().x(), span_y))]
        cy += [(o.top(), ("h", o.top(), span_x)), (o.bottom() - r.height(), ("h", o.bottom(), span_x)),
               (o.center().y() - r.height() / 2, ("h", o.center().y(), span_x))]
    cx += [(sc.left() + GAP, ("v", sc.left() + GAP, (sc.top(), sc.bottom()))),
           (sc.right() - GAP - r.width(), ("v", sc.right() - GAP, (sc.top(), sc.bottom())))]
    cy += [(sc.top() + GAP, ("h", sc.top() + GAP, (sc.left(), sc.right()))),
           (sc.bottom() - GAP - r.height(), ("h", sc.bottom() - GAP, (sc.left(), sc.right())))]
    bx, by = _best(cx, r.left()), _best(cy, r.top())
    dx = bx[1] - r.left() if bx else 0.0
    dy = by[1] - r.top() if by else 0.0
    return dx, dy, [_line(b[2]) for b in (bx, by) if b]


def magnetic_edges(r, edges, others, screen):
    """Resizing: snap only the edges being dragged (1=L, 2=R, 4=T, 8=B). -> (new rect, guides)."""
    r = QRectF(r)
    sc = QRectF(screen)
    guides = []
    xs = [sc.left() + GAP, sc.right() - GAP]
    ys = [sc.top() + GAP, sc.bottom() - GAP]
    for o in others:
        o = QRectF(o)
        xs += [o.left(), o.right(), o.left() - GAP, o.right() + GAP]
        ys += [o.top(), o.bottom(), o.top() - GAP, o.bottom() + GAP]
    span_y, span_x = (r.top() - 20, r.bottom() + 20), (r.left() - 20, r.right() + 20)
    for flag, get, setter, vals, kind, span in (
            (1, r.left, r.setLeft, xs, "v", span_y), (2, r.right, r.setRight, xs, "v", span_y),
            (4, r.top, r.setTop, ys, "h", span_x), (8, r.bottom, r.setBottom, ys, "h", span_x)):
        if edges & flag:
            b = _best([(v, (kind, v, span)) for v in vals], get())
            if b:
                setter(b[1])
                guides.append(_line(b[2]))
    return r, guides


def _line(g):
    kind, at, (a, b) = g
    return QLineF(at, a, at, b) if kind == "v" else QLineF(a, at, b, at)


class GuideOverlay(QWidget):
    """Faint guide lines over the screen while a group snaps. Clicks go straight through it."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.lines = []
        self.color = QColor(10, 132, 255)

    def show_lines(self, lines, color=None):
        geo = QGuiApplication.primaryScreen().geometry()
        if self.geometry() != geo:
            self.setGeometry(geo)
        self.lines = [QLineF(ln.translated(-geo.left(), -geo.top())) for ln in lines]
        if color is not None:
            self.color = QColor(color)
        if lines and not self.isVisible():
            self.show()
        self.update()

    def clear(self):
        self.lines = []
        self.hide()

    def paintEvent(self, _e):
        if not self.lines:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self.color)
        c.setAlpha(150)
        pen = QPen(c, 1.2, Qt.DashLine)
        p.setPen(pen)
        for ln in self.lines:
            p.drawLine(ln)
        p.end()


def to_rect(r):
    return QRect(round(r.left()), round(r.top()), round(r.width()), round(r.height()))
