# Clutter Buster

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
> need permission to hide. Brian's three (Steam, EA, Epic Games Launcher) were given that
> permission once (a Windows "Modify" grant for Brian's account on just those three shortcuts).
> That permission stays in place - it's harmless and Clutter Buster doesn't need it removed.
> If a new Public-desktop item can't be hidden it stays visible (and in its group) - run `--rehide` after fixing it.

## Start / stop it
Open a terminal in this folder:

```
.venv\Scripts\pythonw.exe main.py             start (no black console window)
.venv\Scripts\python.exe  main.py --quit      quit nicely (shows everything on the desktop again)
.venv\Scripts\python.exe  main.py --rehide    try again to hide grouped items that could not be hidden
.venv\Scripts\pythonw.exe main.py --uninstall remove Clutter Buster (same as Settings > Apps > Uninstall)
```

Or use the broom icon by the clock > **Quit**. It **starts with Windows** by itself
(turn that off in Settings > General).

## Use it
- **Ctrl+Space** anywhere opens search on top of everything. Type a few letters
  ("clc" finds Calculator), Up/Down to pick, Enter to open, Esc to close.
  It searches your desktop, your groups, your favorites and saved websites - never the web.
- **+ New Group** (next to the search bar) makes a group on the left; type its name, press Enter.
- **✨ Auto** (next to + New Group) = *Automatically do it* - see below.
- **Drag** desktop shortcuts, files, folders, `.url` files or links from your browser onto a group.
- **Click a small tile** to open it (a compact popup grows out of the tile).
  Click an item to open it. Click anywhere else or press Esc to close.
- **Right-click a group** > *Accent color* or *Show as > Small tile / Big panel*.
- **Big panels**: click an item to open it, click the title to open the popup,
  the "..." button for the menu.
- **Drag an item out**: drag an icon out of an open popup or a big panel and drop it on the bare
  desktop - it leaves the group and shows on the desktop again (only its Hidden flag is cleared;
  the file never moves). A see-through ghost icon follows the mouse. Drop it on another group to
  move it there instead (still hidden). Undo puts it back. Press Esc while dragging to cancel.
- **Resize** any group by dragging its edges or corners (a 16 px zone along each edge, and a
  grip with three little lines in the bottom-right corner that shows on hover and in Edit layout).
  Small tiles stay square and grow from the corner you pull. Icons scale and never get cut off;
  very small groups hide labels until you hover (hovering never opens anything).
- **Drag an item onto another item** (in a popup or big panel) to make a new group with both.
  Drag an item onto another group to move it there.
- **Favorites dock**: a small glass strip under the search bar that appears when your
  mouse comes near. Drag things onto it, or right-click an item > *Add to favorites*.
  Right-click a favorite to remove it. Favorites never hide anything.
- **Badges**: a group shows a colored number when new items land in it; it clears when you open it.
- **Undo** button (or Ctrl+Z) undoes any change. Layout backups are automatic.
- **Broom icon** by the clock: Settings, Automatically do it, Edit layout, Undo, Quit,
  and the red **Remove Clutter Buster**.

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
- **Settings** (broom icon > *Settings...*): General (stage 4), Appearance, Search (Ctrl+Space, read-only for now),
  Dock (auto-hide on/off), Sounds (on/off + volume), About (version + GitHub link), and the red
  *Remove Clutter Buster* button.

### Stage 4
- **Automatically do it** (the **gear** button by + New Group > *Auto organize*, the broom icon menu, or
  Settings > General): looks at the visible items on your desktop (yours and the Public one)
  and suggests groups by name, file type and where a shortcut points - **Games** (Steam, EA,
  Epic, anything inside a games/steamapps folder), **AI** (LM Studio, ComfyUI, Ollama, Cursor...),
  **Browsers**, **Chat & Social**, **Tools**, **Media**, **Documents**, **Folders**, **Websites**,
  **Apps** (everything else that's a program) and *Other files* (off unless you tick it).
  It reuses groups you already have when they fit (e.g. your "AI" group).
  A glass review window shows every suggestion: untick a group to skip it, untick an item to
  leave it on the desktop, rename new groups, or use *Move to...* to put an item in another group.
  **Nothing changes until you click Apply**, and Apply is **one Undo step**. Items you hid
  yourself and items already in a group are left alone. It never sorts by itself later.
- **Start with Windows**: on by default; Settings > General has the switch. It's a normal
  per-user "Run" entry (no admin), so it also shows in Task Manager > Startup apps.
- **Settings > Apps**: Clutter Buster now appears in Windows Settings > Apps > Installed apps
  (with the broom icon, publisher Brian, version 0.5.0) and can be uninstalled from there.

### Version 0.5.2: tabs on top, names on fences
- **The name is inside every group now**, on top (nothing sticks out under small tiles, so
  snapped tiles never overlap). Tabs sit right under the name as a pill bar (the selected tab is
  highlighted); long names are cut with "…", and when there are too many a **▾** button lists
  them all. Very small tiles show dots instead.
- **Names under icons** on small tiles and big panels whenever there's room (Settings >
  Appearance > *Show names in big panels*: Auto / Always / Never; or per group, see below).
- **Click an icon on a small tile to open it** (like big panels). Empty space or the name opens
  the group. Icons light up when you point at them.
- **Group settings (the gear next to A- / A+)**: accent colour (with a colour picker right in
  the panel), its own theme, name size + font/colour, small tile / big panel, icons per row,
  show names, transparency, Use defaults and Delete group. Every change is one Undo step.
- **No more separate colour windows.** The theme editor, name style and group settings pick
  colours inside their own window (swatches, hue, brightness, #hex), so nothing can open
  hidden behind and freeze the app. Messages always open in front.
- **Delete your own themes**: in the theme editor, the gear menu or Settings (asks once;
  Ctrl+Z brings it back). Built-in themes can't be deleted; if it was in use, Auto takes over.
- **Hidden items stay hidden**: if an app's updater (or anything else) makes a grouped item
  visible again, it's hidden again within seconds (desktop folder watch + a check every 30 s).
- `faults.log` records a stack trace if the app ever crashes or stops responding for 20 s.

### Version 0.5.1: easier on the desktop
- **Drag icons straight out.** Drag an icon out of a big panel, or one of the little icons
  inside a small tile, onto the desktop and it shows there again; drop it on another group to
  move it there. A plain click still opens / launches; dragging an empty spot still moves the
  group, and the edges still resize.
- **Real thumbnails** for pictures and videos (jpg, png, webp, gif, mp4, mkv...). Uses Windows'
  own thumbnails (they work for hidden files too), made in the background and cached.
- **Tabs on small tiles.** A group with 2+ tabs shows little pills (or dots when names don't
  fit) at the bottom of its tile; click one to switch the preview in place. Clicking the rest
  of the tile opens it on that tab. Big panels always show their tab bar.
- **Name size buttons.** Hover a group's name: **A-** / **A+** (8-36 pt), or Ctrl + mouse
  wheel over the name. The gear menu has a *Name size* slider for every group. One Undo per
  burst. The pencil renames in place.
- **Magnetic snapping.** Groups snap to each other (8 px gap), line up tops/lefts/centres and
  snap to the screen edges and taskbar, with faint guide lines. Hold **Alt** to place freely.
  Settings > Appearance > *Snap groups to each other*. *Tidy up* still snaps to the grid.
- **Names in big panels**: Settings > Appearance > *Show names in big panels* (Auto / Always /
  Never). Auto shows up to 2 lines when there's room; hover for the full name.
- **Shared desktop permissions.** When a Public-desktop shortcut can't be hidden, a small
  message asks first, then Windows shows ONE permission prompt for exactly those files
  (`icacls <file> /grant you:M`). Clutter Buster itself never runs as admin. Turn it off in
  Settings > General; retry from the group or broom menu: *Fix hiding permission...*.
- **Choose the quick search shortcut**: Settings > Search, click the box and press the keys
  (Ctrl/Alt/Shift + a key). If another app has it you're told and the old one stays.
  *Reset to Ctrl+Space* puts it back.
- **Settings**: the red *Remove Clutter Buster* button is always at the bottom left (pages
  scroll now), and checkboxes have a clear box with a coloured fill and a white tick.

### Version 0.5: tabs, name styles, the gear menu
- **Tabs inside groups.** Every group starts with one tab (no tab bar shown). Click the small
  **+** (top right of a popup or big panel, or right-click a group > *Add a tab*) to add one and
  type its name. Then a pill-shaped tab bar shows at the top - right on the desktop for big
  panels - and clicking a tab switches in place. **Right-click a tab**: Rename, Move left/right,
  View (Icons or **List** with Name / Date modified / Type columns - click selects, double-click
  opens), New tab, Delete (its items move to the first tab). Drag an item onto a tab's name to
  move it there; new things you drop in go to the tab you're looking at. Each tab has its own
  pages; the last tab you used is remembered; small tiles preview the first tab; the badge
  counts all tabs. Every change is one Undo step. Older layouts get one tab per group
  automatically (a copy of the old `layout.json` is kept in `backups\before-tabs-....json`).
- **Bigger names + Name style.** Group names are bigger now (11 pt under tiles, 12.5 pt on
  panels - Windows scales points for your display). **Double-click a name** to rename it right
  there (Enter saves, Esc cancels). Right-click a group > **Name style...** picks any font on
  your PC, size, bold/italic, color and a shadow or outline, with a live preview.
  **Settings > Appearance > Group names...** sets the default for every group; a group's own
  style wins. Anything left on "Default" follows the theme.
- **Icons per row** now really applies, live: the small tile previews, the big panels and the
  popup all follow it (before, the tile preview was fixed at 3 x 3 and panels ignored it).
- **The gear (Settings) button** next to *+ New Group* opens a small glass menu: Auto organize,
  Undo / Redo (Ctrl+Z / Ctrl+Y), Themes + **Edit theme...** (built-in themes are saved as your
  own copy), **Hide all groups** (their items stay hidden; also in the broom menu),
  **Lock layout** (no moving, resizing or rearranging; clicks still open things; also in the
  broom menu), Group transparency, **Tidy up** (snaps every group to the grid, one Undo step),
  Sound on/off + volume, and *All settings...*.
- **The favorites dock stays visible** (still behind your windows). Settings > Dock can turn
  auto-hide back on.
- **Couldn't hide?** If Windows refuses to hide an item (usually a shortcut on the shared Public
  desktop that needs admin permission), its group shows a small orange **!** and the tooltip
  names it. If the same shortcut exists on both your desktop and the Public one, both copies
  are hidden.
- **Resizing** groups: a wider grab zone on every edge and a corner grip (diagonal lines).

## Uninstall / remove
Any of these does the same thing:
- Windows **Settings > Apps > Installed apps > Clutter Buster > ... > Uninstall**
- the red **Remove Clutter Buster** button (broom icon menu, or Settings)
- `.venv\Scripts\pythonw.exe main.py --uninstall`

You get **one** confirmation. Then it: shows every grouped item on your desktop again
(only what it hid itself - it stops if anything can't be shown), turns off Start with Windows,
removes the Settings > Apps entry, deletes `%APPDATA%\ClutterBuster`, and closes.
Your desktop files are never deleted or moved.

The confirmation has an **unticked** box *Also delete the program folder
(C:\Users\Brian\CodeProjects\clutter-buster)*. Only if you tick it, a tiny one-off script in
`%TEMP%` waits for the app to close and then deletes that folder (it double-checks it's really
Clutter Buster's folder first, then deletes itself). Leave it unticked to keep the code and the
Git history. The Public-desktop permission given to Steam/EA/Epic is left as it is (harmless).

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
| `clutterbuster/searchbar.py` | The search bar, and the + New Group and gear buttons. |
| `clutterbuster/quickmenu.py` | The gear menu (auto organize, undo/redo, themes, hide/lock, sound, transparency, tidy up). |
| `clutterbuster/tabs.py` | Tabs inside groups: the pill tab bar and the List view. |
| `clutterbuster/namestyle.py` / `namestyle_dialog.py` | How group names look, and the Name style window. |
| `clutterbuster/winicons.py` | Real, sharp icons for each item, looked up like Explorer does (shortcut icon locations, .url icon files, 256 px). |
| `clutterbuster/shortcuts.py` | Reads where .lnk / .url shortcuts point and where their pictures come from (read-only). |
| `clutterbuster/organize.py` | *Automatically do it*: reads names, file types and shortcut targets and suggests groups (read-only). |
| `clutterbuster/organize_dialog.py` | The glass review window for those suggestions (Apply / Cancel). |
| `clutterbuster/integration.py` | Start with Windows and the Settings > Apps entry (per-user registry, no admin). |
| `clutterbuster/removal.py` | Remove / uninstall: the confirmation, restoring the desktop, the optional folder cleanup. |
| `clutterbuster/edit_toolbar.py` | The floating Edit layout toolbar (sliders + Done). |
| `clutterbuster/settings.py` | The glass Settings window. |
| `clutterbuster/theme_maker.py` | The custom theme maker with its live preview. |
| `clutterbuster/glasswin.py` | Shared look for the glass dialog windows (buttons, sliders). |
| `clutterbuster/dock.py` | The favorites dock (always visible; auto-hide is optional). |
| `clutterbuster/tray.py` | The broom icon by the clock and its menu. |
| `clutterbuster/ledger.py` | The written list of everything the app hid, and the hide/un-hide rules. |
| `clutterbuster/desktop_files.py` | Finds your desktop folders and flips the Hidden checkbox. Nothing else. |
| `clutterbuster/desktop_layer.py` | Keeps groups, search bar and dock *behind* your windows, like desktop icons; notices full-screen games. |
| `clutterbuster/store.py` | Saves your groups and favorites, makes backups, keeps the Undo history. |
| `clutterbuster/glass.py` | The frosted-glass look, badges, and safe drag-and-drop rules. |
| `clutterbuster/theme.py` | All colors and sizes: Clean White, Neon Gamer, custom themes, Auto light/dark. |
| `clutterbuster/icons.py` | Real Windows icons, a globe for websites, friendly names. |
| `clutterbuster/sounds.py` | Makes and plays the soft open/close sounds. |
| `clutterbuster/showcase.py` | The safe demo used for screenshots (pretend groups, a pretend desktop in %TEMP%, temp settings). |
| `clutterbuster/blur.py` | Windows blur helper (kept for later themes). |
| `tests/smoke_test.py` | Automated safety checks using a pretend desktop (developer use). |
| `tools/screenshot.py` | Saves a screenshot of the main screen (developer use). |
| `tools/icon_diag.py` | Lists every grouped item with its shortcut target / icon source and old-vs-new icon (read-only, developer use). |
| `tools/suggest_preview.py` | Prints what *Automatically do it* would suggest, without changing anything (developer use). |

## Where your settings live
`%APPDATA%\ClutterBuster`: `layout.json` (groups, favorites, layout, theme choice, custom themes), `ledger.json` (what was hidden),
`backups\` (last 20 copies), `error.log` (should stay empty), `app.log`, `app.pid`, `status.json`, `broom.ico`.
In the registry (your user only): `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value
`ClutterBuster`, and the key `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\ClutterBuster`.

## Coming later
Changing the search shortcut.
