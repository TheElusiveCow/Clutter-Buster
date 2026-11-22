"""Windows integration: Start with Windows, and the entry in Settings > Apps.

Everything lives under HKEY_CURRENT_USER, so no admin rights are needed:
  * HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run              value "ClutterBuster"
  * HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ClutterBuster

On non-Windows computers (automated tests only) a pretend registry (FAKE) is used.
"""
import datetime
import logging
import os
import sys

log = logging.getLogger("cb")
IS_WIN = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ClutterBuster"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ClutterBuster"
FAKE = {}   # {key: {name: value}} - tests only


def program_dir():
    """The code folder (the one with main.py)."""
    return os.environ.get("CLUTTERBUSTER_PROGRAM_DIR") or \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pythonw_path():
    venv = os.path.join(program_dir(), ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv):
        return venv
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        cand = exe[:-10] + "pythonw.exe"
        if os.path.exists(cand):
            return cand
    return exe


def launch_command(*args):
    cmd = f'"{pythonw_path()}" "{os.path.join(program_dir(), "main.py")}"'
    return cmd + "".join(" " + a for a in args)


# ------------------------------------------------------------------ registry helpers
def _set(key, name, value):
    if not IS_WIN:
        FAKE.setdefault(key, {})[name] = value
        return True
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
            winreg.SetValueEx(k, name, 0, kind, value)
        return True
    except OSError as e:
        log.error("Registry write failed (%s\\%s): %s", key, name, e)
        return False


def _get(key, name):
    if not IS_WIN:
        return FAKE.get(key, {}).get(name)
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _delete_value(key, name):
    if not IS_WIN:
        FAKE.get(key, {}).pop(name, None)
        return True
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("Registry delete failed (%s\\%s): %s", key, name, e)
        return False
    return True


def _delete_key(key):
    if not IS_WIN:
        FAKE.pop(key, None)
        return True
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)   # our key has no sub-keys
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("Registry key delete failed (%s): %s", key, e)
        return False
    return True


# ------------------------------------------------------------------ Start with Windows
def autostart_enabled():
    return bool(_get(RUN_KEY, RUN_NAME))


def set_autostart(on):
    if on:
        return _set(RUN_KEY, RUN_NAME, launch_command())
    return _delete_value(RUN_KEY, RUN_NAME)


# ------------------------------------------------------------------ Settings > Apps entry
def register_uninstall(version, icon_path=None):
    """(Re)write the Settings > Apps entry. Safe to call on every start."""
    vals = {
        "DisplayName": "Clutter Buster",
        "DisplayVersion": str(version).split()[0],
        "Publisher": "Brian",
        "DisplayIcon": icon_path if icon_path and os.path.exists(icon_path) else pythonw_path(),
        "UninstallString": launch_command("--uninstall"),
        "InstallLocation": program_dir(),
        "URLInfoAbout": "https://github.com/TheElusiveCow/Clutter-Buster",
        "NoModify": 1,
        "NoRepair": 1,
        "EstimatedSize": 400,   # KB, just the app's own code (not Python)
    }
    if not _get(UNINSTALL_KEY, "InstallDate"):
        vals["InstallDate"] = datetime.date.today().strftime("%Y%m%d")
    return all(_set(UNINSTALL_KEY, k, v) for k, v in vals.items())


def uninstall_registered():
    return _get(UNINSTALL_KEY, "DisplayName") == "Clutter Buster"


def unregister_uninstall():
    return _delete_key(UNINSTALL_KEY)
