"""Removing Clutter Buster (tray / Settings button, Settings > Apps, or main.py --uninstall).

Order matters and is always the same:
 1. show every item the app hid (only items in its ledger) - stop if any can't be shown
 2. turn off Start with Windows, remove the Settings > Apps entry
 3. delete the app's own settings folder (%APPDATA%\\ClutterBuster)
 4. only if you ticked the box: delete the program folder AFTER the app has closed,
    using a tiny one-off cleanup script in %TEMP% that waits for the app to exit.
Your desktop files are never deleted or moved.
"""
import logging
import os
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtWidgets import QCheckBox, QMessageBox

from . import integration, paths

log = logging.getLogger("cb")


def confirm(parent=None):
    """The one confirmation. Returns (go_ahead, also_delete_program_folder)."""
    folder = integration.program_dir()
    box = QMessageBox(parent)
    box.setWindowTitle("Remove Clutter Buster?")
    box.setIcon(QMessageBox.Warning)
    box.setText("Remove Clutter Buster?")
    box.setInformativeText(
        "This will:\n\n"
        "\u2022 show every grouped item on your desktop again\n"
        "\u2022 turn off Start with Windows\n"
        "\u2022 remove it from Settings > Apps\n"
        "\u2022 delete Clutter Buster's settings and groups\n"
        "\u2022 close the app\n\n"
        "None of your desktop files, shortcuts or folders are deleted or moved.")
    cb = QCheckBox(f"Also delete the program folder ({folder})")
    cb.setChecked(False)
    box.setCheckBox(cb)
    yes = box.addButton("Remove Clutter Buster", QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    yes.setStyleSheet("background:#e5293b;color:white;font-weight:bold;padding:4px 12px;border-radius:4px;")
    from .glass import front_dialog
    front_dialog(box)
    box.exec()
    return box.clickedButton() is yes, cb.isChecked()


def remove_all(hider, delete_folder=False, wait_pid=None):
    """Steps 1-4. Returns (ok, message)."""
    hider.unhide_all()
    if hider.ledger.hidden:
        return False, ("Some items could not be shown again, so I stopped before removing anything.\n"
                       "Details are in " + paths.error_log())
    integration.set_autostart(False)
    integration.unregister_uninstall()
    log.info("Remove Clutter Buster: desktop restored, Start with Windows off, Settings > Apps entry removed")
    folder_msg = ""
    if delete_folder:
        ok = schedule_folder_cleanup(integration.program_dir(), wait_pid or os.getpid())
        folder_msg = "" if ok else " (the program folder was left alone - it didn't look like Clutter Buster's)"
    paths.close_logging()
    shutil.rmtree(paths.app_dir(), ignore_errors=True)
    return True, "Clutter Buster was removed" + folder_msg + "."


def looks_like_program_folder(folder):
    """Only ever delete a folder that is clearly Clutter Buster's own code folder."""
    try:
        folder = os.path.abspath(folder)
        home = os.path.abspath(os.path.expanduser("~"))
        if folder in (home, os.path.dirname(folder)) or len(folder) < 8:
            return False
        if os.path.basename(folder).lower() in ("desktop", "documents", "downloads", "users"):
            return False
        return (os.path.isfile(os.path.join(folder, "main.py"))
                and os.path.isfile(os.path.join(folder, "clutterbuster", "__init__.py"))
                and os.path.isfile(os.path.join(folder, "clutterbuster", "ledger.py")))
    except Exception:
        return False


def cleanup_script(folder, pid):
    """Text of the one-off cleanup script (PowerShell on Windows, sh elsewhere)."""
    if sys.platform == "win32":
        f = folder.replace("'", "''")
        return f"""# Clutter Buster one-off cleanup: waits for the app to close, then removes its program folder.
$pidToWait = {int(pid)}
$folder = '{f}'
for ($i = 0; $i -lt 240; $i++) {{
  if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{ break }}
  Start-Sleep -Milliseconds 500
}}
Start-Sleep -Seconds 2
if ((Test-Path -LiteralPath (Join-Path $folder 'main.py')) -and (Test-Path -LiteralPath (Join-Path $folder 'clutterbuster\\ledger.py'))) {{
  for ($t = 0; $t -lt 5; $t++) {{
    Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $folder)) {{ break }}
    Start-Sleep -Seconds 2
  }}
}}
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
    q = folder.replace("'", "'\\''")
    return f"""#!/bin/sh
# Clutter Buster one-off cleanup (test version)
i=0
while kill -0 {int(pid)} 2>/dev/null && [ $i -lt 240 ]; do sleep 0.5; i=$((i+1)); done
sleep 1
if [ -f '{q}/main.py' ] && [ -f '{q}/clutterbuster/ledger.py' ]; then rm -rf '{q}'; fi
rm -f "$0"
"""


def schedule_folder_cleanup(folder, pid, temp_dir=None):
    """Start the detached cleanup script. Returns False (and does nothing) if the folder
    doesn't look like Clutter Buster's program folder."""
    if not looks_like_program_folder(folder):
        log.warning("Refusing to delete %s: not Clutter Buster's program folder", folder)
        return False
    temp_dir = temp_dir or tempfile.gettempdir()
    ext = ".ps1" if sys.platform == "win32" else ".sh"
    script = os.path.join(temp_dir, f"clutterbuster-cleanup-{os.getpid()}{ext}")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(cleanup_script(os.path.abspath(folder), pid))
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
        subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-WindowStyle", "Hidden", "-File", script],
                         creationflags=flags, close_fds=True, cwd=temp_dir)
    else:
        subprocess.Popen(["/bin/sh", script], start_new_session=True, close_fds=True, cwd=temp_dir)
    log.info("Program folder %s will be removed after the app closes", folder)
    return True
