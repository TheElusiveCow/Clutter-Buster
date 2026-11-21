# Clutter Buster (stage 3)

iOS-style groups for your Windows desktop. Drag shortcuts, files, folders or website
links onto a frosted-glass group; desktop items vanish from the normal desktop
(or look faded, if Explorer shows hidden items) and live inside the group instead.

## The golden safety rule
Clutter Buster **never moves, renames or deletes** your files. Their paths never
change. The only thing it does is tick the Windows **Hidden** checkbox on a desktop
item while it's in a group, and untick it again when you take the item out,
delete the group, Quit, or remove the app. It keeps a written list (the "ledger")
of exactly what it hid, so it only ever un-hides its own work - never things you
hid yourself. Website links dragged from a browser aren't files, so nothing is hidden for them.

> If your PC shows hidden items, grouped items stay on the desktop but look faded. That's normal.
> Items on the shared **Public** desktop (e.g. Steam, EA, Epic installed "for all users")
> need permission to hide. Brian's three were given that permission once, so they hide too;
> if a new one can't be hidden it stays visible (and in its group) - run `--rehide` after fixing it.

## Start / stop it
Open a terminal in this folder:

```
.venv\Scripts\pythonw.exe main.py          start (no black console window)
.venv\Scripts\python.exe  main.py --quit   quit nicely (shows everything on the desktop again)
.venv\Scripts\python.exe  main.py --rehide try again to hide grouped items that could not be hidden
```

Or use the broom icon by the clock > **Quit**. (Start-with-Windows comes in a later stage.)

## Use it
- **Ctrl+Space** anywhere opens search on top of everything. Type a few letters
  ("clc" finds Calculator), Up/Down to pick, Enter to open, Esc to close.
  It searches your desktop, your groups, your favorites and saved websites - never the web.
- **+ New Group** (next to the search bar) makes a group on the left; type its name, press Enter.
- **Drag** desktop shortcuts, files, folders, `.url` files or links from your browser onto a group.
- **Click a small tile** to open it (a compact popup grows out of the tile).
  Click an item to open it. Click anywhere else or press Esc to close.
- **Right-click a group** > *Accent color* or *Show as > Small tile / Big panel*.
- **Big panels**: click an item to open it, click the title to open the popup,
  the "..." button for the menu.
- **Resize** any group by dragging its edges or corners. Icons scale and never get cut off;
  very small groups hide labels until you hover (hovering never opens anything).
- **Drag an item onto another item** (in a popup or big panel) to make a new group with both.
  Drag an item onto another group to move it there.
- **Favorites dock**: a small glass strip under the search bar that appears when your
  mouse comes near. Drag things onto it, or right-click an item > *Add to favorites*.
  Right-click a favorite to remove it. Favorites never hide anything.
- **Badges**: a group shows a colored number when new items land in it; it clears when you open it.
- **Undo** button (or Ctrl+Z) undoes any change. Layout backups are automatic.
- **Broom icon** by the clock: Settings, Edit layout, Undo, Quit, and the red **Remove Clutter Buster**.

### Stage 3
- **Edit layout** (right-click a group > *Edit layout*, or the broom icon > *Edit layout*):
  groups, the search bar, the dock and the + New Group/Undo buttons get a dashed outline and
  can be dragged anywhere (they snap to a grid). Pull corners/edges to resize groups - and the
  popup (open a group while editing). A floating glass toolbar has live sliders for
  **icon size, icons per row, glass transparency and glow strength**, plus **Done**.
  Esc or Done locks everything and saves. One Undo puts the whole editing session back.
  Outside Edit layout the bars stay put. (Items don't launch while editing.)
- **Themes**: *Clean White* (white frosted glass, thin RGB strip on top) and *Neon Gamer*
  (dark smoked glass with a slowly turning RGB glow along the edges). *Auto* (the default)
  follows Windows' light/dark app mode and switches by itself when Windows does.
  The glow animates at most 25 times a second and **pauses** while a game, a full-screen app
  or a maximized window covers the desktop.
- **Custom themes**: Settings > Appearance > *Make a custom theme*: pick accent, glass tint and
  text colors, frost (blur), glow and corner roundness, watch the live preview, *Save theme*.
  Saved themes appear in the theme list and can be deleted (it asks first).
  ("Frost" makes the glass milkier - it's a painted frost, not a real background blur.)
- **Settings** (broom icon > *Settings...*): Appearance, Search (Ctrl+Space, read-only for now),
  Dock (auto-hide on/off), Sounds (on/off + volume), About (version + GitHub link), and the red
  *Remove Clutter Buster* button.

## Open it in Cursor
In Cursor choose **File > Open Folder...** and pick `C:\Users\Brian\CodeProjects\clutter-buster`.

## What's in the folder
| File | What it does |
|---|---|
| `main.py` | The start button (also `--quit`, `--rehide` and the safe `--showcase` demo). |
| `clutterbuster/app.py` | The brain: groups, hiding, undo, favorites, menus, keeping windows in sync. |
| `clutterbuster/group_widget.py` | A group on the desktop: small tile or big panel, moving, resizing, drops, badges. |
| `clutterbuster/popup.py` | The compact iOS-style popup that grows out of a group. |
| `clutterbuster/quicksearch.py` | The Ctrl+Space search window. |
| `clutterbuster/fuzzy.py` | The forgiving search matching. |
| `clutterbuster/hotkey.py` | Registers Ctrl+Space with Windows. |
| `clutterbuster/searchbar.py` | The search bar, and the + New Group / Undo buttons. |
| `clutterbuster/edit_toolbar.py` | The floating Edit layout toolbar (sliders + Done). |
| `clutterbuster/settings.py` | The glass Settings window. |
| `clutterbuster/theme_maker.py` | The custom theme maker with its live preview. |
| `clutterbuster/glasswin.py` | Shared look for the glass dialog windows (buttons, sliders). |
| `clutterbuster/dock.py` | The auto-hiding favorites dock. |
| `clutterbuster/tray.py` | The broom icon by the clock and its menu. |
| `clutterbuster/ledger.py` | The written list of everything the app hid, and the hide/un-hide rules. |
| `clutterbuster/desktop_files.py` | Finds your desktop folders and flips the Hidden checkbox. Nothing else. |
| `clutterbuster/desktop_layer.py` | Keeps groups, search bar and dock *behind* your windows, like desktop icons; notices full-screen games. |
| `clutterbuster/store.py` | Saves your groups and favorites, makes backups, keeps the Undo history. |
| `clutterbuster/glass.py` | The frosted-glass look, badges, and safe drag-and-drop rules. |
| `clutterbuster/theme.py` | All colors and sizes: Clean White, Neon Gamer, custom themes, Auto light/dark. |
| `clutterbuster/icons.py` | Real Windows icons, a globe for websites, friendly names. |
| `clutterbuster/sounds.py` | Makes and plays the soft open/close sounds. |
| `clutterbuster/showcase.py` | The safe demo used for screenshots (pretend groups, temp settings). |
| `clutterbuster/blur.py` | Windows blur helper (kept for later themes). |
| `tests/smoke_test.py` | Automated safety checks using a pretend desktop (developer use). |
| `tools/screenshot.py` | Saves a screenshot of the main screen (developer use). |

## Where your settings live
`%APPDATA%\ClutterBuster`: `layout.json` (groups, favorites, layout, theme choice, custom themes), `ledger.json` (what was hidden),
`backups\` (last 20 copies), `error.log` (should stay empty), `app.log`, `app.pid`, `status.json`.

## Coming later
Start with Windows, changing the search shortcut, "Automatically do it" suggestions, and a
Windows Settings > Apps uninstall entry.
