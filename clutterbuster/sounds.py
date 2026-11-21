"""Tiny, quiet open/close sounds. Made by the app itself (no downloads)."""
import math
import os
import struct
import sys
import wave

from . import paths

RATE = 44100
SETTINGS = {"on": True, "volume": 50}   # Settings > Sounds (volume 0-100)
_made_at = [None]


def _tone(file_path, f_start, f_end, ms, volume=0.07):
    n = int(RATE * ms / 1000)
    frames = bytearray()
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = f_start + (f_end - f_start) * t
        phase += 2 * math.pi * freq / RATE
        env = min(1.0, t * 12) * (1 - t) ** 2  # soft attack, gentle fade
        frames += struct.pack("<h", int(32767 * volume * env * math.sin(phase)))
    with wave.open(file_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def ensure(force=False):
    """(Re)make the two little sounds at the chosen volume (Windows' simple player has no
    volume knob, so the volume is baked into the sound files)."""
    os.makedirs(paths.sounds_dir(), exist_ok=True)
    vol = 0.14 * max(0, min(100, int(SETTINGS["volume"]))) / 100
    if _made_at[0] == vol and not force:
        return
    specs = {"open.wav": (520, 820, 95), "close.wav": (760, 430, 85)}
    for name, (a, b, ms) in specs.items():
        _tone(os.path.join(paths.sounds_dir(), name), a, b, ms, volume=vol)
    _made_at[0] = vol


def play(name):
    if sys.platform != "win32" or not SETTINGS["on"] or int(SETTINGS["volume"]) <= 0:
        return
    try:
        import winsound
        fp = os.path.join(paths.sounds_dir(), name + ".wav")
        if os.path.exists(fp):
            winsound.PlaySound(fp, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass
