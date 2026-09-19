"""Narration for demo_v0.4.0: edge-tts (zh-TW-YunJheNeural) + per-cue timings.

Usage (from video/hf-demo):
    ..\\..\\code\\backend\\venv\\Scripts\\python tools\\tts.py [shot ...]

Writes assets/audio/raw/shotNN.mp3 (edge-tts output), assets/audio/shotNN.wav
(48 kHz, loudness-normalised to -16 LUFS, tail trimmed) and data/timing.json
(cue start/end in clip seconds, taken from edge-tts WordBoundary events).
edge-tts is the Microsoft Edge read-aloud voice: no account, no key.
Windows console is cp950: this script prints ASCII only.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import wave

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NARR = json.load(open(os.path.join(ROOT, "data", "narration.json"), encoding="utf-8"))
RAW_DIR = os.path.join(ROOT, "assets", "audio", "raw")
OUT_DIR = os.path.join(ROOT, "assets", "audio")
TIMING = os.path.join(ROOT, "data", "timing.json")
TAIL = 0.45  # seconds of room kept after the last spoken word
LUFS = -16.0

os.makedirs(RAW_DIR, exist_ok=True)
DISPLAY_STRIP = re.compile(r"[，。；：、]+$")  # trailing ， 。 ； ： 、


def ffmpeg_bin():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    guess = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        r"\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe"
    )
    if os.path.exists(guess):
        return guess
    raise SystemExit("ffmpeg not found on PATH")


async def synth(text, out):
    comm = edge_tts.Communicate(text, NARR["voice"], rate=NARR["rate"], boundary="WordBoundary")
    words = []
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                })
    return words


def assign(chunks, words):
    """Map word boundaries to cue indexes by sequential search in the concatenated text."""
    full = "".join(chunks)
    bounds, acc = [], 0
    for c in chunks:
        bounds.append((acc, acc + len(c)))
        acc += len(c)
    cursor, per = 0, [[] for _ in chunks]
    for w in words:
        pos = full.find(w["text"], cursor)
        if pos < 0:  # normalised token (numerals etc.): stay at the cursor
            pos = cursor
        else:
            cursor = pos + len(w["text"])
        idx = next((i for i, (a, b) in enumerate(bounds) if a <= pos < b), len(chunks) - 1)
        per[idx].append(w)
    return per


def normalise(src, dst, keep):
    """Two-pass EBU R128 loudnorm to LUFS, trimmed to `keep` seconds, 48 kHz stereo WAV."""
    ff = ffmpeg_bin()
    probe = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", src, "-t", f"{keep:.3f}",
         "-af", f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", probe.stderr, re.S)
    stats = json.loads(m.group(0))
    af = (f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
          f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
          f":offset={stats['target_offset']}:linear=true")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-t", f"{keep:.3f}",
                    "-af", af, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst], check=True)
    return float(stats["input_i"])


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return round(w.getnframes() / w.getframerate(), 3)


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want = [int(a) for a in args] or [s["shot"] for s in NARR["shots"]]
    timing = json.load(open(TIMING, encoding="utf-8")) if os.path.exists(TIMING) else {}
    if "--remeasure" in sys.argv:
        for k, v in timing.items():
            v["clip"] = wav_seconds(os.path.join(OUT_DIR, f"shot{int(k):02d}.wav"))
            print(f"shot {int(k):02d}: clip={v['clip']}")
        json.dump(timing, open(TIMING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return
    for s in NARR["shots"]:
        n = s["shot"]
        if n not in want:
            continue
        cues = s["cues"]
        tts = s.get("tts", cues)
        assert len(tts) == len(cues)
        raw = os.path.join(RAW_DIR, f"shot{n:02d}.mp3")
        words = await synth("".join(tts), raw)
        per = assign(tts, words)
        items = []
        for i, c in enumerate(cues):
            ws = per[i]
            if not ws:
                raise SystemExit(f"shot {n}: cue {i} got no word boundaries; check chunking")
            items.append({"text": DISPLAY_STRIP.sub("", c.strip()),
                          "start": round(ws[0]["start"], 3), "end": round(ws[-1]["end"], 3)})
        speech_end = round(words[-1]["end"], 3)
        keep = round(speech_end + TAIL, 3)
        wav = os.path.join(OUT_DIR, f"shot{n:02d}.wav")
        measured = normalise(raw, wav, keep)
        keep = wav_seconds(wav)
        timing[str(n)] = {"speech_end": speech_end, "clip": keep, "input_lufs": measured, "cues": items}
        print(f"shot {n:02d}: words={len(words)} speech_end={speech_end} clip={keep} in_lufs={measured}")
    ordered = {k: timing[k] for k in sorted(timing, key=int)}
    json.dump(ordered, open(TIMING, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


asyncio.run(main())
