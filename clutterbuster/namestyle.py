"""How group NAMES look (font, size, bold/italic, color, shadow/outline).

Settings > Appearance sets the default for every group (stored in the layout's "ui", so it's
part of Undo); right-click a group > Name style... overrides it for that one group
(stored in the group as "name_style"). Missing values follow the theme.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen

from .theme import qcolor

DEFAULT = {"family": "", "size": 0, "bold": None, "italic": False, "color": "", "effect": "auto"}
EFFECTS = [("auto", "Theme default"), ("none", "None"), ("shadow", "Shadow"), ("outline", "Outline")]


def resolve(layout, group=None):
    """Merged style: built-in defaults <- your default <- this group's own style."""
    st = dict(DEFAULT)
    st.update({k: v for k, v in (layout.ui.get("name_style") or {}).items() if k in DEFAULT})
    if group is not None:
        st.update({k: v for k, v in (group.get("name_style") or {}).items() if k in DEFAULT})
    return st


def font(base, style, default_pt, default_bold):
    f = QFont(base)
    if style.get("family"):
        f.setFamily(style["family"])
    f.setPointSizeF(float(style.get("size") or default_pt))
    b = style.get("bold")
    f.setBold(default_bold if b is None else bool(b))
    f.setItalic(bool(style.get("italic")))
    return f


def color(style, default_key):
    c = style.get("color")
    return QColor(c) if c and QColor(c).isValid() else qcolor(default_key)


def draw(p, rect, text, align, style, base_font, default_pt, default_bold, color_key,
         default_effect="none", elide_w=None):
    """Draw a group name with the style. Returns the font used."""
    f = font(base_font, style, default_pt, default_bold)
    fm = QFontMetrics(f)
    if elide_w is not None:
        text = fm.elidedText(text, Qt.ElideRight, int(elide_w))
    eff = style.get("effect") or "auto"
    if eff == "auto":
        eff = default_effect
    col = color(style, color_key)
    p.save()
    p.setFont(f)
    if eff == "outline":
        # outline: trace the letters in a contrasting colour, then fill them
        x = rect.left()
        w = fm.horizontalAdvance(text)
        if align & Qt.AlignHCenter:
            x = rect.center().x() - w / 2
        elif align & Qt.AlignRight:
            x = rect.right() - w
        if align & Qt.AlignVCenter:
            y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
        else:
            y = rect.top() + fm.ascent()
        path = QPainterPath()
        path.addText(QPointF(x, y), f, text)
        dark = col.lightness() > 128
        p.setRenderHint(p.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(0, 0, 0, 200) if dark else QColor(255, 255, 255, 220), 2.6,
                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(path)
    else:
        if eff == "shadow":
            sh = QColor(0, 0, 0, 200) if col.lightness() > 128 else QColor(255, 255, 255, 200)
            p.setPen(sh)
            p.drawText(QRectF(rect).translated(1, 1), align, text)
        p.setPen(col)
        p.drawText(QRectF(rect), align, text)
    p.restore()
    return f
