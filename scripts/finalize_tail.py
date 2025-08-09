#!/usr/bin/env python3
# finalize_tail.py - 末尾クランプ＆VTT出力

import re, subprocess
from pathlib import Path

TARGET_OFFSET_MS = 20  # 音声末尾-20ms
MIN_DUR = 1.2

def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err

def audio_len(path: str) -> float:
    rc, out, err = run([
        "ffprobe","-v","error","-show_entries","format=duration","-of","default=nk=1:nw=1", path
    ])
    if rc != 0:
        raise RuntimeError(err)
    return float(out.strip())

def parse_srt(path: str):
    text = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues=[]
    for b in blocks:
        ls=[ln for ln in b.splitlines() if ln.strip()]
        if not ls: continue
        if re.fullmatch(r"\d+", ls[0]): ls=ls[1:]
        if not ls: continue
        m=re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", ls[0])
        if not m: continue
        def tosec(ts):
            h,m,sms=ts.split(":"); s,ms=sms.split(",")
            return int(h)*3600+int(m)*60+int(s)+int(ms)/1000.0
        st,ed=tosec(m.group(1)),tosec(m.group(2))
        txt="\n".join(ls[1:])
        cues.append({"start":st,"end":ed,"text":txt})
    return cues

def fmt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def out_srt(cues):
    out=[]
    for i,c in enumerate(cues,1):
        out.append(str(i))
        out.append(f"{fmt_time(c['start'])} --> {fmt_time(c['end'])}")
        out.append(c.get("text","").rstrip())
        out.append("")
    return "\n".join(out).strip() + "\n"

def out_vtt(cues):
    lines=["WEBVTT",""]
    for c in cues:
        st=fmt_time(c["start"]).replace(",",".")
        ed=fmt_time(c["end"]).replace(",",".")
        lines.append(f"{st} --> {ed}")
        lines.append(c.get("text","").rstrip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out_vtt", required=True)
    ap.add_argument("--target_offset_ms", type=int, default=TARGET_OFFSET_MS)
    args = ap.parse_args()

    cues = parse_srt(args.inp)
    if not cues:
        raise SystemExit("❌ no cues")

    a = audio_len(args.audio)
    last_end = max(c["end"] for c in cues)
    target = max(0.0, a - args.target_offset_ms/1000.0)

    # 最後に到達しているキューを見つけクランプ
    idx = max(range(len(cues)), key=lambda i: cues[i]["end"])
    span = max(MIN_DUR, cues[idx]["end"] - cues[idx]["start"])
    cues[idx]["end"] = min(target, max(0.0, cues[idx]["end"]))
    cues[idx]["start"] = max(0.0, cues[idx]["end"] - span)

    Path(args.out).write_text(out_srt(cues), encoding="utf-8")
    Path(args.out_vtt).write_text(out_vtt(cues), encoding="utf-8")

    print(f"✅ finalize: audio={a:.3f}s  srt_end(before)={last_end:.3f}s  srt_end(after)={cues[idx]['end']:.3f}s")

if __name__ == "__main__":
    main()