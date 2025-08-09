#!/usr/bin/env python3
# scripts/pad_to_audio_end.py
import argparse, re, subprocess, shutil, wave, contextlib
from pathlib import Path

def parse_timecode(t: str) -> float:
    h,m,sms = t.split(":"); s,ms = sms.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

def fmt_time(sec: float) -> str:
    if sec < 0: sec = 0.0
    h = int(sec//3600); m = int((sec%3600)//60); s = int(sec%60)
    ms = int(round((sec - int(sec))*1000))
    if ms==1000: ms=0; s+=1; 
    if s==60: s=0; m+=1
    if m==60: m=0; h+=1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def parse_srt(text: str):
    blocks = re.split(r"\n\s*\n", text.strip())
    cues=[]
    for b in blocks:
        ls=[ln for ln in b.splitlines() if ln.strip()]
        if not ls: continue
        if re.fullmatch(r"\d+", ls[0]): ls=ls[1:]
        if not ls: continue
        m=re.match(r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", ls[0])
        if not m: continue
        start,end=m.group(1),m.group(2)
        txt="\n".join(ls[1:]).strip()
        cues.append({"start":start,"end":end,"text":txt})
    return cues

def write_srt(cues, path: Path):
    with path.open("w", encoding="utf-8") as f:
        for i,c in enumerate(cues, start=1):
            f.write(f"{i}\n{c['start']} --> {c['end']}\n{c['text']}\n\n")

def audio_duration(audio: Path) -> float:
    if audio.suffix.lower()==".wav":
        with contextlib.closing(wave.open(str(audio),'rb')) as w:
            return w.getnframes()/w.getframerate()
    # ffprobe fallback
    if shutil.which("ffprobe"):
        cmd = ["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)]
        out = subprocess.check_output(cmd).decode().strip()
        return float(out)
    raise RuntimeError("音声長が取得できません（wav 以外で ffprobe なし）")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    ap.add_argument("--offset-ms", type=int, default=20)
    ap.add_argument("--min-last-ms", type=int, default=400, help="最終行の最小長")
    args=ap.parse_args()

    srt_text = Path(args.inp).read_text(encoding="utf-8", errors="ignore")
    cues = parse_srt(srt_text)
    if not cues: raise SystemExit("SRTが空です")

    dur = audio_duration(Path(args.audio))
    target_end = max(0.0, dur - (args.offset_ms/1000.0))

    last = cues[-1]
    start_sec = parse_timecode(last["start"])
    end_sec   = parse_timecode(last["end"])
    new_end = max(target_end, end_sec)
    if new_end < start_sec + (args.min_last_ms/1000.0):
        new_end = start_sec + (args.min_last_ms/1000.0)
    last["end"] = fmt_time(new_end)

    out_path = Path(args.outp); out_path.parent.mkdir(parents=True, exist_ok=True)
    write_srt(cues, out_path)
    print(f"audio={dur:.3f}s  last_end(old)={end_sec:.3f}s -> last_end(new)={new_end:.3f}s  diff_audio_last={dur-new_end:.3f}s")

if __name__=="__main__":
    main()