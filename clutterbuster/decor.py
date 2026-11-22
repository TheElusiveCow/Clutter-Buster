"""Theme decorations painted on the glass: star dust, a wood + plaid frame, string lights,
frost and snowflakes, cartoon / comic ink outlines. All cheap enough for the cached paint."""
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QRadialGradient

from .theme import THEME

STYLES = [  # (key, label) for the theme editor
    ("", "None"), ("stars", "Star dust"), ("plaid", "Wood + plaid frame"), ("lights", "String lights"),
    ("frost", "Frost + snowflakes"), ("cartoon", "Cartoon outline"), ("comic", "Comic ink"),
]
# what a decoration needs from the theme (used when a custom theme picks one)
STYLE_DEFAULTS = {
    "plaid": {"border_w": 2.0},
    "lights": {"border_w": 1.5},
    "frost": {"border_w": 2.0},
    "cartoon": {"border_w": 3.0, "glass_border": (20, 20, 20, 255)},
    "comic": {"border_w": 3.0, "glass_border": (20, 20, 20, 255)},
}

LIGHT_COLORS = [(255, 70, 60), (60, 220, 110), (255, 200, 60), (80, 160, 255), (255, 120, 200)]


def before(p, path, rect):
    """Under the glass: the hard offset 'ink' shadow of cartoon / comic styles."""
    d = THEME.get("decor")
    if d in ("cartoon", "comic"):
        p.fillPath(path.translated(3, 3), QColor(0, 0, 0, 190 if d == "cartoon" else 150))


def inside(p, path, rect, radius):
    """On the glass (clipped to it)."""
    d = THEME.get("decor")
    if d == "stars":
        _stars(p, rect)
    elif d == "plaid":
        _plaid(p, path, rect, radius)
    elif d == "frost":
        _frost(p, rect)


def edge(p, path, rect, radius):
    """On top of the border."""
    d = THEME.get("decor")
    if d == "lights":
        _lights(p, path)
    elif d == "frost":
        _flakes(p, rect)
    elif d == "comic":
        p.setPen(QPen(QColor(20, 20, 20, 90), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(4, 4, -4, -4), max(2, radius - 4), max(2, radius - 4))


def _stars(p, rect):
    rnd = random.Random(int(rect.width()) * 131 + int(rect.height()))
    neb = QRadialGradient(QPointF(rect.right() - rect.width() * 0.2, rect.top() + rect.height() * 0.25),
                          max(rect.width(), rect.height()) * 0.6)
    neb.setColorAt(0, QColor(140, 80, 255, 46))
    neb.setColorAt(1, QColor(140, 80, 255, 0))
    p.fillRect(rect, neb)
    neb2 = QRadialGradient(QPointF(rect.left() + rect.width() * 0.15, rect.bottom()), rect.width() * 0.55)
    neb2.setColorAt(0, QColor(40, 140, 255, 36))
    neb2.setColorAt(1, QColor(40, 140, 255, 0))
    p.fillRect(rect, neb2)
    p.setPen(Qt.NoPen)
    n = int(rect.width() * rect.height() / 700)
    for _ in range(min(n, 600)):
        x = rect.left() + rnd.random() * rect.width()
        y = rect.top() + rnd.random() * rect.height()
        r = rnd.choice((0.5, 0.6, 0.7, 0.9, 1.2))
        p.setBrush(QColor(255, 255, 255, rnd.randint(50, 190)))
        p.drawEllipse(QPointF(x, y), r, r)


def _plaid(p, path, rect, radius):
    b = max(3.5, min(5.0, min(rect.width(), rect.height()) * 0.02))
    inner = QPainterPath()
    inner.addRoundedRect(rect.adjusted(2 * b, 2 * b, -2 * b, -2 * b), max(2, radius - 2 * b), max(2, radius - 2 * b))
    mid = QPainterPath()
    mid.addRoundedRect(rect.adjusted(b, b, -b, -b), max(2, radius - b), max(2, radius - b))
    wood = path.subtracted(mid)
    p.fillPath(wood, QColor(104, 64, 34))
    p.save()
    p.setClipPath(wood)
    p.setPen(QPen(QColor(70, 40, 18, 120), 1))
    y = rect.top()
    while y < rect.bottom():
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y + 1.5))
        y += 3.0
    p.restore()
    band = mid.subtracted(inner)
    p.fillPath(band, QColor(150, 28, 32))
    p.save()
    p.setClipPath(band)
    step = 6.0
    x = rect.left()
    while x < rect.right():
        p.fillRect(QRectF(x, rect.top(), 2, rect.height()), QColor(30, 20, 20, 120))
        x += step
    y = rect.top()
    while y < rect.bottom():
        p.fillRect(QRectF(rect.left(), y, rect.width(), 2), QColor(30, 20, 20, 110))
        y += step
    p.restore()
    p.setPen(QPen(QColor(70, 40, 18, 200), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(inner)


def _frost(p, rect):
    m = min(rect.width(), rect.height())
    for cx, cy in ((rect.left(), rect.top()), (rect.right(), rect.top()),
                   (rect.left(), rect.bottom()), (rect.right(), rect.bottom())):
        g = QRadialGradient(QPointF(cx, cy), m * 0.38)
        g.setColorAt(0, QColor(255, 255, 255, 170))
        g.setColorAt(0.5, QColor(255, 255, 255, 60))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(rect, g)


def snowflake(p, c, r, color):
    p.setPen(QPen(color, max(1.0, r / 7)))
    for i in range(6):
        a = i * math.pi / 3
        e = QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))
        p.drawLine(c, e)
        for f in (0.55,):
            m = QPointF(c.x() + r * f * math.cos(a), c.y() + r * f * math.sin(a))
            for s in (-1, 1):
                b = a + s * math.pi / 4
                p.drawLine(m, QPointF(m.x() + r * 0.3 * math.cos(b), m.y() + r * 0.3 * math.sin(b)))


def _flakes(p, rect):
    col = QColor(255, 255, 255, 230)
    s = max(6.0, min(11.0, min(rect.width(), rect.height()) * 0.04))
    spots = [(rect.left() + s * 1.4, rect.top() + s * 1.4, 1.0), (rect.left() + s * 3.3, rect.top() + s * 0.9, 0.6),
             (rect.right() - s * 1.4, rect.top() + s * 1.4, 1.0), (rect.right() - s * 3.2, rect.top() + s * 0.9, 0.6),
             (rect.left() + s * 1.4, rect.bottom() - s * 1.4, 0.9), (rect.left() + s * 0.9, rect.bottom() - s * 3.2, 0.55)]
    for x, y, k in spots:
        snowflake(p, QPointF(x, y), s * k, col)


def _lights(p, path):
    length = path.length()
    if length <= 0:
        return
    p.setPen(QPen(QColor(30, 60, 30, 200), 1.2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    n = max(8, int(length / 17))
    p.setPen(Qt.NoPen)
    for i in range(n):
        pt = path.pointAtPercent(i / n)
        r, g, b = LIGHT_COLORS[i % len(LIGHT_COLORS)]
        glow = QRadialGradient(pt, 7)
        glow.setColorAt(0, QColor(r, g, b, 150))
        glow.setColorAt(1, QColor(r, g, b, 0))
        p.setBrush(glow)
        p.drawEllipse(pt, 7, 7)
        p.setBrush(QColor(min(255, r + 40), min(255, g + 40), min(255, b + 40)))
        p.drawEllipse(pt, 2.4, 2.4)
