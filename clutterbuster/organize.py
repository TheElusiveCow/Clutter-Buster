"""'Automatically do it': look at what's on the desktop and SUGGEST groups.

This module only reads. It never changes a file - it just looks at names, file types and
(for shortcuts) where the shortcut points. The review window (organize_dialog.py) shows the
suggestions, and nothing happens until you click Apply.
"""
import os
import re

from . import desktop_files as df
from .icons import display_name

# (key, suggested name, accent, words in the item NAME, words in the shortcut TARGET path)
CATEGORIES = [
    ("games", "Games", "#30D158",
     ["steam", "epic games", "ea app", "ea", "origin", "battle.net", "battlenet", "ubisoft", "uplay",
      "gog galaxy", "gog", "riot client", "riot", "valorant", "league of legends", "minecraft", "fortnite",
      "call of duty", "warzone", "the sims", "sims 4", "roblox", "xbox", "playnite", "rockstar games",
      "overwatch", "apex legends", "counter-strike", "cs2", "dota", "grand theft auto", "gta", "cyberpunk",
      "elden ring", "baldur", "battlefield", "halo", "forza", "diablo", "world of warcraft", "hearthstone",
      "genshin", "retroarch", "dolphin", "yuzu", "ryujinx", "pcsx2", "rpcs3", "heroic", "game", "games",
      "launcher", "fifa", "ea sports", "rocket league", "destiny", "starfield", "skyrim", "fallout"],
     ["steamapps", "\\steam\\", "epic games", "\\games\\", "riot games", "ea games", "origin games",
      "ubisoft", "gog galaxy", "battle.net", "xboxgames", "rockstar games", "\\electronic arts\\"]),
    ("ai", "AI", "#BF5AF2",
     ["lm studio", "lmstudio", "comfyui", "comfy", "ollama", "stable diffusion", "automatic1111", "a1111",
      "forge", "fooocus", "invokeai", "chatgpt", "openai", "claude", "anthropic", "gemini", "copilot",
      "grok", "gpt4all", "koboldcpp", "kobold", "oobabooga", "text generation", "sillytavern", "pinokio",
      "anythingllm", "msty", "jan", "whisper", "perplexity", "midjourney", "llama", "cursor", "ai",
      "hugging face", "huggingface", "swarmui", "stability matrix", "amuse"],
     ["comfyui", "lm studio", "lm-studio", "ollama", "stable-diffusion", "pinokio", "stabilitymatrix",
      "\\cursor\\", "koboldcpp", "gpt4all"]),
    ("browsers", "Browsers", "#0A84FF",
     ["chrome", "google chrome", "firefox", "mozilla firefox", "edge", "microsoft edge", "brave", "opera",
      "opera gx", "vivaldi", "tor browser", "arc", "zen browser", "librewolf", "waterfox", "chromium",
      "duckduckgo", "thorium", "floorp"],
     ["chrome.exe", "firefox.exe", "msedge.exe", "brave.exe", "opera.exe", "vivaldi.exe", "launcher.exe\\opera"]),
    ("chat", "Chat & Social", "#5E5CE6",
     ["discord", "teams", "microsoft teams", "slack", "telegram", "whatsapp", "signal", "zoom", "skype",
      "messenger", "element", "guilded", "teamspeak", "mumble"],
     ["discord", "telegram", "whatsapp", "slack", "zoom"]),
    ("media", "Media", "#FF375F",
     ["spotify", "vlc", "obs", "obs studio", "itunes", "apple music", "netflix", "plex", "audacity",
      "davinci", "davinci resolve", "premiere", "photoshop", "lightroom", "after effects", "gimp", "blender",
      "capcut", "media player", "windows media player", "kodi", "paint.net", "krita", "inkscape",
      "paint", "handbrake", "foobar", "musicbee", "streamlabs", "shotcut", "clipchamp", "photos", "canva"],
     ["spotify", "vlc", "obs-studio", "blender", "davinci", "adobe"]),
    ("tools", "Tools", "#64D2FF",
     ["control panel", "task manager", "notepad", "notepad++", "calculator", "7-zip", "winrar", "cpu-z",
      "gpu-z", "hwinfo", "hwmonitor", "afterburner", "msi afterburner", "rivatuner", "icue", "armoury",
      "nvidia", "geforce", "nvidia app", "amd software", "adrenalin", "radeon", "ccleaner", "revo",
      "powertoys", "snipping", "rufus", "crystaldisk", "everything", "wiztree", "treesize", "logitech",
      "g hub", "razer", "synapse", "signalrgb", "openrgb", "wallpaper engine", "anydesk", "teamviewer",
      "vpn", "nordvpn", "malwarebytes", "settings", "terminal", "powershell", "command prompt", "cmd",
      "visual studio", "vs code", "visual studio code", "code", "git", "github desktop", "python",
      "pycharm", "docker", "postman", "sublime", "putty", "filezilla", "file explorer", "this pc",
      "recycle bin", "device manager", "regedit", "obsidian", "bitwarden", "1password", "keepass",
      "sharex", "greenshot", "lightshot", "autohotkey", "qbittorrent", "utorrent", "ddu", "occt",
      "cinebench", "3dmark", "furmark", "process explorer", "autoruns", "veracrypt", "macrium",
      "ventoy", "balena", "etcher"],
     ["\\windows\\system32\\", "\\sysinternals", "microsoft vs code", "\\git\\", "powertoys", "7-zip",
      "nvidia corporation", "\\amd\\"]),
]
EXTRA = {
    "documents": ("Documents", "#FFD60A"),
    "folders": ("Folders", "#FF9F0A"),
    "websites": ("Websites", "#0A84FF"),
    "apps": ("Apps", "#AC8E68"),
    "other": ("Other files", "#8E8E93"),
}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".txt", ".md", ".rtf",
           ".odt", ".ods", ".odp", ".csv", ".one", ".pages", ".numbers", ".key", ".epub", ".json", ".log"}
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff", ".svg", ".mp4",
             ".mov", ".mkv", ".avi", ".webm", ".wmv", ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
APP_EXT = {".lnk", ".exe", ".appref-ms", ".bat", ".cmd", ".msc"}
# words in an existing group's NAME that say which kind of things it holds
GROUP_WORDS = {
    "games": {"game", "games", "gaming", "play", "steam"},
    "ai": {"ai", "llm", "llms", "ml"},
    "browsers": {"browser", "browsers", "internet"},
    "chat": {"chat", "social", "talk", "messages", "messaging"},
    "media": {"media", "music", "video", "videos", "photo", "photos", "pictures", "creative", "art"},
    "tools": {"tool", "tools", "utility", "utilities", "system", "dev", "code", "coding"},
    "documents": {"doc", "docs", "documents", "work", "papers", "files"},
    "folders": {"folder", "folders"},
    "websites": {"web", "websites", "sites", "links", "bookmarks"},
    "apps": {"apps", "programs", "software"},
}
ORDER = ["games", "ai", "browsers", "chat", "tools", "media", "documents", "folders", "websites", "apps", "other"]


def _words(text):
    return re.findall(r"[a-z0-9.+\-]+", text.lower())


def _has_word(name, kw):
    """Whole-word match ('ea' matches 'EA' or 'EA app' but not 'Steam' or 'Real')."""
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", name) is not None


# ------------------------------------------------------------------ .lnk reading (read-only)
def lnk_target(path):
    """Where a Windows shortcut points ('' if it can't be read). Pure reading, no COM."""
    try:
        with open(path, "rb") as f:
            data = f.read(1 << 16)
    except OSError:
        return ""
    try:
        if len(data) < 0x4C or data[:4] != b"\x4c\x00\x00\x00":
            return ""
        flags = int.from_bytes(data[0x14:0x18], "little")
        pos = 0x4C
        if flags & 0x01:   # HasLinkTargetIDList
            pos += 2 + int.from_bytes(data[pos:pos + 2], "little")
        if flags & 0x02:   # HasLinkInfo
            start = pos
            hsize = int.from_bytes(data[start + 4:start + 8], "little")
            li_flags = int.from_bytes(data[start + 8:start + 12], "little")
            if li_flags & 0x01:
                if hsize >= 0x24:
                    uoff = int.from_bytes(data[start + 28:start + 32], "little")
                    if uoff:
                        s = start + uoff
                        end = s
                        while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
                            end += 2
                        txt = data[s:end].decode("utf-16-le", "ignore")
                        if txt:
                            return txt
                off = int.from_bytes(data[start + 16:start + 20], "little")
                s = start + off
                end = data.index(b"\x00", s)
                return data[s:end].decode("mbcs" if os.name == "nt" else "latin-1", "ignore")
            pos = start + int.from_bytes(data[start:start + 4], "little")
        # no LinkInfo (e.g. Store apps): try the relative path string
        unicode = bool(flags & 0x80)
        for bit in (0x04, 0x08):    # name, relative path
            if flags & bit:
                n = int.from_bytes(data[pos:pos + 2], "little")
                size = n * (2 if unicode else 1)
                txt = data[pos + 2:pos + 2 + size].decode("utf-16-le" if unicode else "latin-1", "ignore")
                pos += 2 + size
                if bit == 0x08 and txt:
                    return txt
    except Exception:
        return ""
    return ""


GAME_SCHEMES = ("steam:", "com.epicgames.launcher:", "uplay:", "ubisoft:", "origin:", "origin2:",
                "eaapp:", "ea:", "battlenet:", "riotclient:", "goggalaxy:", "xbox:", "ms-xbl-", "roblox:",
                "minecraft:", "rockstar:")


def url_file_info(path):
    """(URL, IconFile) from a .url internet shortcut - reading only."""
    url = icon = ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f.read(1 << 15).splitlines():
                low = line.strip().lower()
                if low.startswith("url="):
                    url = line.strip()[4:]
                elif low.startswith("iconfile="):
                    icon = line.strip()[9:]
    except OSError:
        pass
    return url, icon


# ------------------------------------------------------------------ classifying
def classify(path):
    """Return a category key for one desktop item."""
    if df.is_url(path):
        return "websites"
    name = display_name(path).lower()
    ext = os.path.splitext(path)[1].lower()
    if os.path.isdir(path):
        for key, _n, _a, words, _t in CATEGORIES:
            if key in ("ai", "games") and any(_has_word(name, w) for w in words if len(w) > 2):
                return key
        return "folders"
    if ext == ".url":
        url, icon = url_file_info(path)
        low = url.lower()
        if low.startswith(GAME_SCHEMES) or "steamapps" in icon.lower() or "\\steam\\" in icon.lower() \
                or "epic games" in icon.lower():
            return "games"           # e.g. Steam / Epic game shortcuts (steam://rungameid/...)
        if low.startswith(("http://", "https://")) or not low:
            return "websites"
        for key, _n, _a, words, _t in CATEGORIES:   # some other app link: go by its name
            if any(_has_word(name, w) for w in words):
                return key
        return "apps"
    target = lnk_target(path).lower() if ext == ".lnk" else (path.lower() if ext == ".exe" else "")
    if ext in APP_EXT or not ext:
        for key, _n, _a, words, tparts in CATEGORIES:
            if any(_has_word(name, w) for w in words):
                return key
            if target and any(t in target for t in tparts):
                return key
        if target and os.path.splitext(target)[1] in DOC_EXT:
            return "documents"
        return "apps" if ext in APP_EXT else "other"
    if ext in DOC_EXT:
        return "documents"
    if ext in MEDIA_EXT:
        return "media"
    return "other"


def category_name(key):
    for k, n, a, _w, _t in CATEGORIES:
        if k == key:
            return n, a
    return EXTRA.get(key, ("Other files", "#8E8E93"))


def match_existing_group(key, groups):
    """Pick one of your existing groups for a category: by its name first, then by what's in it."""
    for g in groups:
        if set(_words(g.get("name", ""))) & GROUP_WORDS.get(key, set()):
            return g
    best, best_share = None, 0.0
    for g in groups:
        items = [it["path"] for it in g.get("items", [])]
        if not items:
            continue
        cats = [classify(p) for p in items]
        share = cats.count(key) / len(cats)
        if share > 0.5 and share > best_share:
            best, best_share = g, share
    return best


def suggest(layout, items=None):
    """Build the suggestion list. Only looks; changes nothing.

    Returns a list of dicts:
      {"key", "name", "accent", "gid" (existing group id or None), "enabled", "items": [{"path", "on"}]}
    """
    if items is None:
        items = df.list_desktop_items()
    buckets = {}
    for p in items:
        if layout.group_of(p) is not None:
            continue            # already in a group
        if df.is_hidden(p):
            continue            # hidden by you (or Windows) - leave it alone
        if os.path.basename(p).lower() in ("desktop.ini", "thumbs.db"):
            continue
        buckets.setdefault(classify(p), []).append(p)
    out = []
    used_gids = set()
    for key in ORDER:
        paths_ = buckets.get(key)
        if not paths_:
            continue
        name, accent = category_name(key)
        g = match_existing_group(key, [g for g in layout.groups if g["id"] not in used_gids])
        if g is not None:
            used_gids.add(g["id"])
        out.append({
            "key": key,
            "name": g["name"] if g else name,
            "accent": (g.get("accent") or accent) if g else accent,
            "gid": g["id"] if g else None,
            "enabled": key != "other",       # odd files: suggested, but off until you tick it
            "items": [{"path": p, "on": True}
                      for p in sorted(paths_, key=lambda x: display_name(x).lower())],
        })
    return out
