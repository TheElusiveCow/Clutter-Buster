"""Reading Windows shortcuts (.lnk) and internet shortcuts (.url). READ-ONLY: never writes.

lnk_info(path) -> {"target", "icon_location", "icon_index", "working_dir", "args"}
url_info(path)  -> {"url", "icon_file", "icon_index"}
Pure Python (follows Microsoft's published .lnk format), so it works the same everywhere.
"""
import os
import re

_ENV = re.compile(r"%([^%]+)%")


def expand(p):
    """Expand %ProgramFiles% style variables (works on any OS; unknown ones stay as-is)."""
    if not p:
        return ""
    return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(0)), p.strip().strip('"'))


def _cstr(data, pos, unicode):
    if unicode:
        end = pos
        while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
            end += 2
        return data[pos:end].decode("utf-16-le", "ignore")
    end = data.find(b"\x00", pos)
    end = len(data) if end < 0 else end
    return data[pos:end].decode("mbcs" if os.name == "nt" else "latin-1", "ignore")


def lnk_info(path):
    out = {"target": "", "icon_location": "", "icon_index": 0, "working_dir": "", "args": "", "relative": ""}
    try:
        with open(path, "rb") as f:
            data = f.read(1 << 17)
    except OSError:
        return out
    try:
        if len(data) < 0x4C or data[:4] != b"\x4c\x00\x00\x00":
            return out
        u32 = lambda o: int.from_bytes(data[o:o + 4], "little")       # noqa: E731
        flags = u32(0x14)
        out["icon_index"] = int.from_bytes(data[0x38:0x3C], "little", signed=True)
        pos = 0x4C
        if flags & 0x01:                       # HasLinkTargetIDList
            pos += 2 + int.from_bytes(data[pos:pos + 2], "little")
        if flags & 0x02:                       # HasLinkInfo
            start = pos
            size, hsize, li_flags = u32(start), u32(start + 4), u32(start + 8)
            if li_flags & 0x01:
                base = ""
                if hsize >= 0x24 and u32(start + 28):
                    base = _cstr(data, start + u32(start + 28), True)
                if not base:
                    base = _cstr(data, start + u32(start + 16), False)
                suffix = ""
                if hsize >= 0x24 and u32(start + 32):
                    suffix = _cstr(data, start + u32(start + 32), True)
                elif u32(start + 24):
                    suffix = _cstr(data, start + u32(start + 24), False)
                out["target"] = base + suffix
            pos = start + size
        unicode = bool(flags & 0x80)
        for bit, key in ((0x04, "name"), (0x08, "relative"), (0x10, "working_dir"),
                         (0x20, "args"), (0x40, "icon_location")):
            if flags & bit:
                n = int.from_bytes(data[pos:pos + 2], "little")
                size = n * (2 if unicode else 1)
                raw = data[pos + 2:pos + 2 + size]
                out[key] = raw.decode("utf-16-le" if unicode else "latin-1", "ignore")
                pos += 2 + size
        # extra data blocks: environment-variable target (0xA0000001) and icon (0xA0000007)
        while pos + 8 <= len(data):
            bsize = u32(pos)
            if bsize < 8:
                break
            sig = u32(pos + 4)
            if sig in (0xA0000001, 0xA0000007) and bsize >= 0x314:
                txt = _cstr(data, pos + 8 + 260, True) or _cstr(data, pos + 8, False)
                if sig == 0xA0000001 and not out["target"]:
                    out["target"] = txt
                if sig == 0xA0000007:
                    out["icon_location"] = txt
            pos += bsize
        if not out["target"] and out["relative"]:
            out["target"] = os.path.normpath(os.path.join(os.path.dirname(path), out["relative"]))
    except Exception:
        pass
    out["target"] = expand(out["target"])
    out["icon_location"] = expand(out["icon_location"])
    out.pop("name", None)
    return out


def url_info(path):
    out = {"url": "", "icon_file": "", "icon_index": 0}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read(1 << 15)
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("url=") and not out["url"]:
            out["url"] = s[4:]
        elif low.startswith("iconfile="):
            out["icon_file"] = expand(s[9:])
        elif low.startswith("iconindex="):
            try:
                out["icon_index"] = int(s[10:])
            except ValueError:
                pass
    return out
