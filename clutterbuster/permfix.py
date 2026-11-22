"""Fixing "access denied" on shared (Public Desktop) shortcuts - automatically, but safely.

Windows only lets admins change shortcuts on C:\\Users\\Public\\Desktop. When hiding one fails
with "access denied" (error 5), Clutter Buster can ask Windows ONCE (one UAC prompt) to run
a small helper:   cmd /c icacls "<file>" /grant "<you>:M" & icacls "<next file>" ...
 - only for exactly those files (full paths, no wildcards, never the Desktop folder itself)
 - only the helper is elevated, never Clutter Buster itself
Afterwards the app simply tries hiding them again.
"""
import ctypes
import logging
import os
import sys

from . import desktop_files as df

log = logging.getLogger("cb")
MAX_CMD = 7000          # cmd.exe lines must stay under 8191 characters
ERROR_CANCELLED = 1223  # you clicked "No" on the Windows permission prompt


class Cancelled(Exception):
    pass


def current_user():
    dom, user = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME") or os.environ.get("USER", "")
    return f"{dom}\\{user}" if dom and user else user


def eligible(p, public_dir=None):
    """A grouped item that failed to hide with access denied and is a FILE directly on the Public Desktop."""
    public_dir = public_dir if public_dir is not None else df.public_desktop_dir()
    if not public_dir or not p or df.is_url(p):
        return False
    if df.norm(os.path.dirname(p)) != df.norm(public_dir):
        return False
    if not os.path.isfile(p) or os.path.islink(p):
        return False
    if any(ch in os.path.basename(p) for ch in '%"*?'):
        return False          # can't be passed safely through cmd.exe - left for a manual fix
    return df.last_error(p) == df.ERROR_ACCESS_DENIED


def candidates(failed_paths):
    pub = df.public_desktop_dir()
    return sorted({p for p in failed_paths if eligible(p, pub)}, key=str.lower)


def icacls_exe():
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icacls.exe")


def build_command(files, user=None):
    """-> (cmd.exe path, its parameters, the files that fit). One icacls per file, chained."""
    user = user or current_user()
    cmd = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    parts, used = [], []
    for f in files:
        part = f'"{icacls_exe()}" "{f}" /grant "{user}:M"'
        if sum(len(x) + 3 for x in parts) + len(part) > MAX_CMD:
            break
        parts.append(part)
        used.append(f)
    # /s + outer quotes: cmd removes exactly the outer pair and keeps every inner quote
    return cmd, '/d /s /c "' + " & ".join(parts) + '"', used


if sys.platform == "win32":
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                    ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    _shell32.ShellExecuteExW.restype = wintypes.BOOL
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]


def launch(files):
    """Start the elevated helper (Windows shows its permission prompt). Returns
    (process handle, files included). Raises Cancelled if you said No, OSError otherwise."""
    if sys.platform != "win32":
        raise OSError("only on Windows")
    exe, params, used = build_command(files)
    if not used:
        raise OSError("nothing to fix")
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040 | 0x00000100      # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = params
    info.nShow = 0                            # SW_HIDE: no black window
    if not _shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        if err == ERROR_CANCELLED:
            raise Cancelled()
        raise OSError(f"Windows error {err}")
    return info.hProcess, used


def poll(handle):
    """None while the helper still runs, else its exit code (the handle is closed then)."""
    if sys.platform != "win32" or not handle:
        return 0
    if _k32.WaitForSingleObject(handle, 0) == 0x102:      # WAIT_TIMEOUT
        return None
    code = wintypes.DWORD()
    _k32.GetExitCodeProcess(handle, ctypes.byref(code))
    _k32.CloseHandle(handle)
    return int(code.value)
