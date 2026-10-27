"""Stand-in voices for the scenario film: one clip per line in data/storyboard.json.

Usage (from video/hf-scenario):
    ..\\..\\code\\backend\\venv\\Scripts\\python tools\\tts.py [--force]

Every line in the film is spoken by the team: on camera (raw/S01.mp4 ...) or in a phone voice-over
(raw/V1.m4a ...). These AI voices only exist for the storyboard preview; tools/build.mjs uses the team's
recording wherever it exists. A line may carry "tts" (what is sent to the voice, e.g. digits spelled out);
captions use "text", which may be a list of caption chunks spoken as one sentence.

Writes assets/audio/lines/<shot>_<n>.wav (48 kHz stereo, loudness-normalised to -16 LUFS, tail trimmed)
and data/lines.json (duration of every clip). Unchanged lines are not synthesised again.
edge-tts is the Microsoft Edge read-aloud voice: no account, no key.
Windows console is cp950: this script prints ASCII only.
"""
import asyncio
import hashlib
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
BOARD = json.load(open(os.path.join(ROOT, "data", "storyboard.json"), encoding="utf-8"))
RAW_DIR = os.path.join(ROOT, "assets", "audio", "lines", "raw")
OUT_DIR = os.path.join(ROOT, "assets", "audio", "lines")
INDEX = os.path.join(ROOT, "data", "lines.json")
TAIL = 0.35
LUFS = -16.0
os.makedirs(RAW_DIR, exist_ok=True)


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


async def synth(text, out, voice):
    kw = {"rate": voice.get("rate", "+0%")}
    if voice.get("pitch"):
        kw["pitch"] = voice["pitch"]
    comm = edge_tts.Communicate(text, voice["voice"], boundary="WordBoundary", **kw)
    last_end = 0.0
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                last_end = (chunk["offset"] + chunk["duration"]) / 1e7
    return last_end


def normalise(src, dst, keep):
    """Two-pass EBU R128 loudnorm, trimmed to `keep` seconds, 48 kHz stereo WAV."""
    ff = ffmpeg_bin()
    probe = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", src, "-t", f"{keep:.3f}",
         "-af", f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    stats = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", probe.stderr, re.S).group(0))
    af = (f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
          f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
          f":offset={stats['target_offset']}:linear=true")
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-t", f"{keep:.3f}",
                    "-af", af, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst], check=True)


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return round(w.getnframes() / w.getframerate(), 3)


async def main():
    force = "--force" in sys.argv
    index = json.load(open(INDEX, encoding="utf-8")) if os.path.exists(INDEX) else {}
    fresh = {}
    for shot in BOARD["shots"]:
        for n, line in enumerate(shot.get("lines", [])):
            key = f"{shot['id']}_{n}"
            voice = BOARD["voices"][line["who"]]
            text = "".join(line["text"]) if isinstance(line["text"], list) else line["text"]
            spoken = line.get("tts", text)
            digest = hashlib.sha1(json.dumps([voice, spoken], ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
            wav = os.path.join(OUT_DIR, f"{key}.wav")
            old = index.get(key)
            if not force and old and old.get("hash") == digest and os.path.exists(wav):
                fresh[key] = old
                continue
            raw = os.path.join(RAW_DIR, f"{key}.mp3")
            for attempt in range(4):
                try:
                    speech_end = await synth(spoken, raw, voice)
                    break
                except edge_tts.exceptions.NoAudioReceived:
                    # the read-aloud service occasionally returns nothing; a retry a moment later works
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 + attempt * 2)
            normalise(raw, wav, speech_end + TAIL)
            fresh[key] = {"who": line["who"], "hash": digest, "speech_end": round(speech_end, 3), "dur": wav_seconds(wav)}
            print(f"{key}: {fresh[key]['dur']}s")
            json.dump({**index, **fresh}, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(fresh, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(fresh)} lines")


asyncio.run(main())
