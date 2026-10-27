"""Music and sound effects for the scenario film, from Mixkit (data/mixkit_sources.json).

Usage (from video/hf-scenario):
    ..\\..\\code\\backend\\venv\\Scripts\\python tools\\mixkit.py

The source files come from the video-shotcraft skill installed at ~/.claude/skills/video-shotcraft
(its assets/audio/ATTRIBUTION.md lists every file's Mixkit title and URL). The licences allow the sounds
inside a film but not handing the files out on their own, so they are converted into
assets/audio/mixkit/*.wav, which git ignores, and never committed.

Music: 48 kHz stereo, two-pass EBU R128 to -20 LUFS (tools/build.mjs then ducks it under speech).
Effects: 48 kHz stereo, peak set to -1 dBFS so the gains in build.mjs mean the same for every file.
Writes data/mixkit_lengths.json (seconds per sound). Windows console is cp950: ASCII output only.
"""
import json
import os
import re
import shutil
import subprocess
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCES = json.load(open(os.path.join(ROOT, "data", "mixkit_sources.json"), encoding="utf-8"))
OUT_DIR = os.path.join(ROOT, "assets", "audio", "mixkit")
LENGTHS = os.path.join(ROOT, "data", "mixkit_lengths.json")
MUSIC_LUFS = -20.0
SFX_PEAK_DB = -1.0


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


FF = ffmpeg_bin()


def analyse(src, af):
    run = subprocess.run([FF, "-hide_banner", "-nostats", "-i", src, "-af", af, "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return run.stderr


def music(src, dst):
    stats = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}",
                                 analyse(src, f"loudnorm=I={MUSIC_LUFS}:TP=-1.5:LRA=11:print_format=json"), re.S).group(0))
    af = (f"loudnorm=I={MUSIC_LUFS}:TP=-1.5:LRA=11:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
          f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
          f":offset={stats['target_offset']}:linear=true")
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af", af,
                    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst], check=True)


def effect(src, dst):
    peak = float(re.search(r"max_volume: ([-\d.]+) dB", analyse(src, "volumedetect")).group(1))
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af", f"volume={SFX_PEAK_DB - peak:.2f}dB",
                    "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst], check=True)


def seconds(path):
    with wave.open(path, "rb") as w:
        return round(w.getnframes() / w.getframerate(), 3)


def main():
    base = os.path.expanduser(SOURCES["skillAudioDir"])
    if not os.path.isdir(base):
        raise SystemExit(
            f"not found: {base}\n"
            "Install the video-shotcraft skill first:\n"
            "  git clone --depth 1 https://github.com/Vincentwei1021/video-shotcraft.git ~/.claude/skills/video-shotcraft\n"
            "(or download each file from the Mixkit URL listed in data/mixkit_sources.json)")
    os.makedirs(OUT_DIR, exist_ok=True)
    lengths = {}
    for kind, table, convert in (("music", SOURCES["music"], music), ("sfx", SOURCES["sfx"], effect)):
        for name, item in table.items():
            src = os.path.join(base, item["file"])
            if not os.path.exists(src):
                raise SystemExit(f"missing {item['file']} in {base}")
            dst = os.path.join(OUT_DIR, f"{name}.wav")
            convert(src, dst)
            lengths[name] = seconds(dst)
            print(f"{kind:5} {name:8} {lengths[name]:7.2f}s  <- {item['file']}")
    json.dump(lengths, open(LENGTHS, "w", encoding="utf-8"), indent=1)
    print(f"{len(lengths)} sounds -> assets/audio/mixkit/, data/mixkit_lengths.json")


main()
