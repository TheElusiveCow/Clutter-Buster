"""Tiny, quiet open/close sounds. Made by the app itself (no downloads)."""
import math
import os
import struct
import sys
import wave

from . import paths

RATE = 44100


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


def ensure():
    os.makedirs(paths.sounds_dir(), exist_ok=True)
    specs = {"open.wav": (520, 820, 95), "close.wav": (760, 430, 85)}
    for name, (a, b, ms) in specs.items():
        fp = os.path.join(paths.sounds_dir(), name)
        if not os.path.exists(fp):
            _tone(fp, a, b, ms)


def play(name):
    if sys.platform != "win32":
        return
    try:
        import winsound
        fp = os.path.join(paths.sounds_dir(), name + ".wav")
        if os.path.exists(fp):
            winsound.PlaySound(fp, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass
