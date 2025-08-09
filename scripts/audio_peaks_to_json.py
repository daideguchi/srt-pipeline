#!/usr/bin/env python3
"""
音声解析スクリプト - ffmpeg silencedetectで無音区間と発話区間を抽出し、
各無音の中心（valley）も計算してJSONに出力する。
依存: ffmpeg/ffprobe
"""

import json
import re
import subprocess
import sys
from pathlib import Path

def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err

def get_audio_duration(audio_path: str) -> float:
    rc, out, err = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ])
    if rc != 0:
        raise RuntimeError(f"ffprobe failed: {err}")
    try:
        return float(out.strip())
    except:
        return 0.0

def silencedetect(audio: str, silence_threshold_db: int = -35, min_silence_ms: int = 220):
    audio = Path(audio)
    if not audio.exists():
        raise FileNotFoundError(audio)

    duration = get_audio_duration(audio)

    # silencedetect出力をstderrからパース
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(audio),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:duration={min_silence_ms/1000.0}",
        "-f", "null", "-"
    ]
    rc, out, err = run(cmd)
    lines = (out + "\n" + err).splitlines()

    # silence_start / silence_endを抽出
    events = []
    for line in lines:
        m1 = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m1:
            events.append({"type":"start","time": float(m1.group(1))})
        m2 = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if m2:
            events.append({"type":"end","time": float(m2.group(1)), "dur": float(m2.group(2))})

    # start/endをペアにして無音区間へ
    silences = []
    i = 0
    while i < len(events):
        if i+1 < len(events) and events[i]["type"] == "start" and events[i+1]["type"] == "end":
            s = float(events[i]["time"])
            e = float(events[i+1]["time"])
            sd = float(events[i+1].get("dur", max(0.0, e-s)))
            v = (s + e) / 2.0  # valley
            silences.append({"start": s, "end": e, "duration": sd, "valley": v})
            i += 2
        else:
            i += 1

    # 発話区間（無音の補集合）を作る
    talkspurts = []
    last = 0.0
    for seg in silences:
        if seg["start"] > last:
            talkspurts.append({"start": last, "end": seg["start"], "duration": seg["start"] - last})
        last = seg["end"]
    if last < duration:
        talkspurts.append({"start": last, "end": duration, "duration": duration - last})

    return {
        "audio_path": str(audio),
        "duration": duration,
        "params": {"silence_db": silence_threshold_db, "min_silence_ms": min_silence_ms},
        "silences": silences,
        "talkspurts": talkspurts
    }

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--silence_db", type=int, default=-35)
    ap.add_argument("--min_silence_ms", type=int, default=220)
    args = ap.parse_args()

    print(f"🔄 音声解析中: {args.audio}")
    data = silencedetect(args.audio, args.silence_db, args.min_silence_ms)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ audio_peaks_to_json: {args.out}")
    print(f"   無音区間: {len(data['silences'])}個 / 発話区間: {len(data['talkspurts'])}個 / 音声長: {data['duration']:.3f}s")