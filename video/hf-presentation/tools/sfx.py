"""Sound effects for presentation_v1.0, synthesised locally.

Usage (from video/hf-presentation):
    ..\\..\\code\\backend\\venv\\Scripts\\python tools\\sfx.py

The advisor asked for a film with narration AND sound effects. Everything here is generated from
sine tones and filtered noise with numpy, so there is no licence question and nothing is downloaded:
    click.wav   a soft key click, for a button being pressed in the captured UI
    tick.wav    a low tick, for each of the three progress steps
    chime.wav   a gentle two-note chime, for the moment a verdict appears
    whoosh.wav  a short air move, for a scene change

Mix rules (docs/demo/presentation_video_brief.md): every effect sits at least 12 dB under the
narration, none of them carries pitch material that competes with speech, and there is no music bed.
Levels here are absolute peak targets; the timeline gives each clip its own data-volume as well.
Windows console is cp950: this script prints ASCII only.
"""
import json
import os
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "assets", "audio", "sfx")
SR = 48000

os.makedirs(OUT_DIR, exist_ok=True)


def write(name, mono, peak):
    """Normalise to an absolute peak and write 48 kHz 16-bit stereo."""
    mono = np.asarray(mono, dtype=np.float64)
    top = float(np.max(np.abs(mono))) or 1.0
    mono = mono / top * peak
    # 3 ms of fade at both ends so nothing clicks on its own edges
    n = int(SR * 0.003)
    if mono.size > 2 * n:
        mono[:n] *= np.linspace(0.0, 1.0, n)
        mono[-n:] *= np.linspace(1.0, 0.0, n)
    data = np.repeat((mono * 32767).astype("<i2"), 2)
    path = os.path.join(OUT_DIR, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return path, round(mono.size / SR, 3)


def t(seconds):
    return np.arange(int(SR * seconds)) / SR


def lowpass(x, cutoff):
    """One-pole low-pass; enough shaping for short effects, and dependency-free."""
    a = np.exp(-2.0 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def click():
    """A short, dull key click: two quick partials under a 28 ms decay, no hiss tail."""
    d = t(0.042)
    env = np.exp(-d * 120.0)
    body = 0.7 * np.sin(2 * np.pi * 1850 * d) + 0.3 * np.sin(2 * np.pi * 2750 * d)
    # a touch of shaped noise gives it a physical edge instead of a beep
    rng = np.random.default_rng(11)
    noise = lowpass(rng.standard_normal(d.size), 2600) * 0.35
    return (body + noise) * env


def tick():
    """A low, quiet tick for a progress step advancing."""
    d = t(0.07)
    env = np.exp(-d * 58.0)
    body = np.sin(2 * np.pi * 320 * d) + 0.25 * np.sin(2 * np.pi * 640 * d)
    return body * env


def chime():
    """Two notes, A5 then E6, for a verdict landing. Soft attack, long-ish tail."""
    total = 0.62
    d = t(total)
    out = np.zeros(d.size)
    for freq, start, gain in ((880.0, 0.0, 1.0), (1318.5, 0.13, 0.82)):
        i0 = int(SR * start)
        dd = t(total - start)
        env = (1 - np.exp(-dd * 90.0)) * np.exp(-dd * 5.6)
        partial = np.sin(2 * np.pi * freq * dd) + 0.22 * np.sin(2 * np.pi * freq * 2 * dd)
        out[i0:i0 + dd.size] += partial * env * gain
    return out


def whoosh():
    """Filtered noise with a falling cutoff: reads as air, not as a hiss."""
    d = t(0.38)
    rng = np.random.default_rng(23)
    noise = rng.standard_normal(d.size)
    env = np.sin(np.pi * np.clip(d / d[-1], 0, 1)) ** 1.6
    # sweep by blending two fixed filters rather than a per-sample varying one
    bright = highpass(lowpass(noise, 5200), 700)
    dark = highpass(lowpass(noise, 1400), 260)
    k = np.linspace(1.0, 0.0, d.size)
    return (bright * k + dark * (1 - k)) * env


def main():
    made = {}
    # Peaks chosen so the loudest effect (the chime) still sits well under the -16 LUFS narration.
    for name, fn, peak in (
        ("click.wav", click, 0.16),
        ("tick.wav", tick, 0.12),
        ("chime.wav", chime, 0.22),
        ("whoosh.wav", whoosh, 0.14),
    ):
        path, dur = write(name, fn(), peak)
        made[name] = dur
        print(f"{name}: {dur}s peak={peak}")
    with open(os.path.join(ROOT, "data", "sfx_lengths.json"), "w", encoding="utf-8") as f:
        json.dump(made, f, indent=1)
        f.write("\n")


main()
