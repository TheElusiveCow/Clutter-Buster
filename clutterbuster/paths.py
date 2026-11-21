"""Where Clutter Buster keeps its own files, plus logging and crash logging.

Everything the app saves lives in ONE folder: %APPDATA%\\ClutterBuster
  layout.json   your groups (names, positions, which items are in them)
  ledger.json   the list of desktop items the app has hidden (so it can always un-hide them)
  backups\\      automatic copies of layout.json (the last 20)
  error.log     crashes / unexpected errors (should stay empty)
  app.log       a simple diary of what the app did
  status.json   a quick health report written at start-up
"""
import datetime
import json
import logging
import os
import sys
import threading
import traceback

APP_NAME = "ClutterBuster"


def app_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def path(*parts):
    return os.path.join(app_dir(), *parts)


def layout_file():
    return path("layout.json")


def ledger_file():
    return path("ledger.json")


def backups_dir():
    return path("backups")


def sounds_dir():
    return path("sounds")


def error_log():
    return path("error.log")


def app_log():
    return path("app.log")


def status_file():
    return path("status.json")


def ensure_dirs():
    for d in (app_dir(), backups_dir(), sounds_dir()):
        os.makedirs(d, exist_ok=True)


def atomic_write_json(file_path, data):
    """Write JSON safely: write a temp file first, then swap it in.
    If the PC loses power mid-write, the old file is still intact."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    tmp = file_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, file_path)


def read_json(file_path, default):
    """Read JSON. Missing file -> default. Damaged file -> keep a copy, return default."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            os.replace(file_path, f"{file_path}.broken-{stamp}")
        except OSError:
            pass
        logging.getLogger("cb").error("Could not read %s, started fresh (kept a .broken copy)", file_path)
        return default


_handlers = []


def setup_logging():
    """app.log gets normal notes; error.log gets only real errors."""
    ensure_dirs()
    log = logging.getLogger("cb")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    info_h = logging.FileHandler(app_log(), encoding="utf-8", delay=True)
    info_h.setLevel(logging.INFO)
    info_h.setFormatter(fmt)
    err_h = logging.FileHandler(error_log(), encoding="utf-8", delay=True)
    err_h.setLevel(logging.ERROR)
    err_h.setFormatter(fmt)
    for h in (info_h, err_h):
        log.addHandler(h)
        _handlers.append(h)
    return log


def close_logging():
    """Release the log files (needed before the app folder can be deleted)."""
    log = logging.getLogger("cb")
    for h in list(_handlers):
        try:
            log.removeHandler(h)
            h.close()
        except Exception:
            pass
    _handlers.clear()


def install_excepthook():
    """Any unexpected error gets written to error.log instead of vanishing."""
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("cb").error("Unexpected error:\n%s", text)
        if sys.stderr:  # pythonw has no console; python.exe does
            sys.stderr.write(text)

    def thread_hook(args):
        hook(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = hook
    threading.excepthook = thread_hook
