"""The review window for 'Automatically do it'.

Shows each suggested group as a card:
  [x] (dot) [ Games          ]  existing group / new group          5 of 6 items
      [x] (icon) Steam      [Move to... v]     [x] (icon) EA     [Move to... v]
Untick a group to skip it, untick an item to leave it on the desktop, rename new groups,
or move an item to another suggestion. NOTHING changes until Apply; Apply is one Undo step.
"""
import copy

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import icons
from .glasswin import GlassPanel
from .theme import is_dark


def _extra_qss():
    if is_dark():
        field, border, pop, text = "rgba(0,0,0,70)", "rgba(255,255,255,44)", "#1E2030", "#E8ECFF"
    else:
        field, border, pop, text = "rgba(255,255,255,235)", "rgba(0,0,0,32)", "#FFFFFF", "#1C1C22"
    return f"""
    QScrollArea {{ background:transparent; border:none; }}
    QScrollArea > QWidget > QWidget {{ background:transparent; }}
    QComboBox {{ background:{field}; border:1px solid {border}; border-radius:7px; padding:2px 8px;
                 min-height:22px; }}
    QComboBox QAbstractItemView {{ background:{pop}; color:{text}; border:1px solid {border};
                                   selection-background-color:#0A84FF; selection-color:white; }}
    QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
    QScrollBar::handle:vertical {{ background:{border}; border-radius:4px; min-height:30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    QCheckBox:disabled, QLabel:disabled {{ color:gray; }}
    """


class OrganizeDialog(GlassPanel):
    def __init__(self, controller, plan, parent=None):
        super().__init__("Clutter Buster - Automatically do it", parent=parent)
        self.c = controller
        self.plan = copy.deepcopy(plan)
        self.name_edits = {}
        from PySide6.QtGui import QGuiApplication
        av = QGuiApplication.primaryScreen().availableGeometry()
        self.setFixedSize(min(980, av.width() - 40), max(520, min(900, av.height() - 80)))
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(14, 8, 14, 10)
        lay.setSpacing(8)
        t = QLabel("\u2728  Automatically do it")
        t.setObjectName("h1")
        lay.addWidget(t)
        hint = QLabel("Here's how I'd sort your desktop. Untick anything you want to leave where it is, "
                      "rename groups, or move items around. Nothing changes until you click Apply - and "
                      "one Undo puts it all back.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.scroll, 1)
        foot = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setObjectName("hint")
        foot.addWidget(self.summary, 1)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.close)
        foot.addWidget(cancel)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.clicked.connect(self.apply)
        foot.addWidget(self.apply_btn)
        lay.addLayout(foot)
        self.restyle()
        self.build()

    def restyle(self):
        from .glasswin import qss
        self.setStyleSheet(qss() + _extra_qss())
        self.update()

    # ------------------------------------------------------------ building the cards
    def _remember_names(self):
        for i, ed in self.name_edits.items():
            if i < len(self.plan) and ed.text().strip():
                self.plan[i]["name"] = ed.text().strip()[:60]

    def build(self):
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.name_edits = {}
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(10)
        if not self.plan:
            empty = QLabel("Nothing to sort - every visible item on your desktop is already in a group. \U0001F389")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            v.addStretch(1)
            v.addWidget(empty)
        for i, s in enumerate(self.plan):
            v.addWidget(self._card(i, s))
        v.addStretch(1)
        self.scroll.setWidget(content)
        self.update_summary()

    def _card(self, i, s):
        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 10, 14, 12)
        cv.setSpacing(6)
        head = QHBoxLayout()
        on = QCheckBox()
        on.setChecked(bool(s["enabled"]))
        on.setToolTip("Untick to skip this whole group")
        on.setCursor(Qt.PointingHandCursor)
        head.addWidget(on)
        dot = QLabel()
        dot.setFixedSize(14, 14)
        dot.setStyleSheet(f"background:{s.get('accent') or '#0A84FF'}; border-radius:7px;")
        head.addWidget(dot)
        if s.get("gid"):
            name = QLabel(s["name"])
            name.setObjectName("h2")
            head.addWidget(name)
            tag = QLabel("  EXISTING GROUP - items get added to it")
        else:
            name = QLineEdit(s["name"])
            name.setMaxLength(60)
            name.setFixedWidth(240)
            name.setToolTip("Rename the new group")
            name.textEdited.connect(lambda *_: self._remember_names())
            self.name_edits[i] = name
            head.addWidget(name)
            tag = QLabel("  NEW GROUP")
        tag.setObjectName("tag")
        head.addWidget(tag)
        head.addStretch(1)
        count = QLabel()
        count.setObjectName("hint")
        head.addWidget(count)
        cv.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(26, 2, 0, 0)
        widgets = []
        for j, it in enumerate(s["items"]):
            cb = QCheckBox(icons.display_name(it["path"]))
            cb.setIcon(icons.icon_for(it["path"]))
            cb.setIconSize(QSize(22, 22))
            cb.setChecked(bool(it["on"]))
            cb.setToolTip(it["path"])
            cb.setCursor(Qt.PointingHandCursor)
            cb.toggled.connect(lambda v, it=it: (it.__setitem__("on", bool(v)), self.update_summary()))
            mv = QComboBox()
            mv.addItem("Move to...", None)
            for k, other in enumerate(self.plan):
                if k != i:
                    mv.addItem(other["name"], k)
            mv.setFixedWidth(150)
            mv.setToolTip("Put this item in a different suggested group")
            mv.setCursor(Qt.PointingHandCursor)
            mv.activated.connect(lambda idx, i=i, j=j, mv=mv: self.move_item(i, j, mv.itemData(idx)))
            r, col = divmod(j, 2)
            grid.addWidget(cb, r, col * 2)
            grid.addWidget(mv, r, col * 2 + 1)
            widgets += [cb, mv]
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        cv.addLayout(grid)

        def refresh(enabled):
            s["enabled"] = bool(enabled)
            for w in widgets + [name]:
                w.setEnabled(bool(enabled))
            n_on = sum(1 for it in s["items"] if it["on"])
            count.setText(f"{n_on} of {len(s['items'])} item{'s' if len(s['items']) != 1 else ''}"
                          if enabled else "skipped")
            self.update_summary()

        on.toggled.connect(refresh)
        for w in widgets:
            if isinstance(w, QCheckBox):
                w.toggled.connect(lambda *_: refresh(on.isChecked()))
        refresh(on.isChecked())
        return card

    def move_item(self, i, j, target):
        if target is None or target == i:
            return
        self._remember_names()
        it = self.plan[i]["items"].pop(j)
        it["on"] = True
        self.plan[target]["items"].append(it)
        self.plan[target]["enabled"] = True
        self.plan[target]["items"].sort(key=lambda x: icons.display_name(x["path"]).lower())
        if not self.plan[i]["items"]:
            self.plan.pop(i)
        self.build()

    def chosen(self):
        self._remember_names()
        return [s for s in self.plan if s["enabled"] and any(it["on"] for it in s["items"])]

    def update_summary(self):
        ch = [s for s in self.plan if s["enabled"] and any(it["on"] for it in s["items"])]
        n = sum(sum(1 for it in s["items"] if it["on"]) for s in ch)
        new = sum(1 for s in ch if not s.get("gid"))
        if not n:
            self.summary.setText("Nothing selected.")
        else:
            self.summary.setText(f"Apply will put {n} item{'s' if n != 1 else ''} into {len(ch)} "
                                 f"group{'s' if len(ch) != 1 else ''} ({new} new). One Undo puts it all back.")
        self.apply_btn.setEnabled(bool(n))

    def apply(self):
        plan = self.chosen()
        self.close()
        if plan:
            self.c.apply_organize(plan)

    def closeEvent(self, e):
        if getattr(self.c, "organize_win", None) is self:
            self.c.organize_win = None
        super().closeEvent(e)
