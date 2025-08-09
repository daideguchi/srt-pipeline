#!/usr/bin/env python3
import argparse, re, wave, contextlib, sys

def parse_time(t):
    h,m,sms = t.split(":"); s,ms = sms.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

def fmt_time(sec):
    if sec < 0: sec = 0.0
    ms = int(round(sec*1000))
    h = ms//3600000; ms%=3600000
    m = ms//60000;   ms%=60000
    s = ms//1000;    ms%=1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def read_srt(path):
    with open(path,"r",encoding="utf-8") as f:
        txt = f.read().strip()
    blocks = re.split(r"\n\s*\n", txt)
    out=[]
    for b in blocks:
        lines=[ln for ln in b.splitlines() if ln.strip()!=""]
        if not lines: continue
        if re.fullmatch(r"\d+", lines[0]): lines=lines[1:]
        if not lines: continue
        m=re.match(r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[0])
        if not m: continue
        st=parse_time(m.group(1)); et=parse_time(m.group(2))
        text="\n".join(lines[1:]).strip()
        out.append([st,et,text])
    return out

def write_srt(entries, path):
    with open(path,"w",encoding="utf-8") as f:
        for i,(s,e,tx) in enumerate(entries,1):
            f.write(f"{i}\n{fmt_time(s)} --> {fmt_time(e)}\n{tx}\n\n")

def audio_duration(path):
    with contextlib.closing(wave.open(path,'rb')) as w:
        return w.getnframes()/float(w.getframerate())

ap = argparse.ArgumentParser()
ap.add_argument("--srt", required=True)
ap.add_argument("--audio", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--epsilon_ms", type=int, default=20, help="音声末尾からこの分だけ手前で止める")
ap.add_argument("--min_gap_ms", type=int, default=80)
ap.add_argument("--min_dur_ms", type=int, default=800)
args = ap.parse_args()

subs = read_srt(args.srt)
if not subs: sys.exit("SRTが空です。")
aud_sec = audio_duration(args.audio)
eps = args.epsilon_ms/1000.0
min_dur = args.min_dur_ms/1000.0

# 末尾行を延長
s,e,tx = subs[-1]
new_end = max(e, aud_sec - eps)
if new_end - s < min_dur:
    s = max(0.0, new_end - min_dur)
subs[-1] = [s,new_end,tx]

# 最小ギャップも一応保証
mingap = args.min_gap_ms/1000.0
for i in range(1,len(subs)):
    prev,cur = subs[i-1], subs[i]
    if cur[0] < prev[1] + mingap:
        need = (prev[1]+mingap) - cur[0]
        cur[0] += need
        if cur[1] < cur[0] + min_dur:
            cur[1] = cur[0] + min_dur

write_srt(subs, args.out)
print(f"音声尺: {aud_sec:.3f}s / SRT末尾(延長後): {subs[-1][1]:.3f}s / 差: {subs[-1][1]-aud_sec:+.3f}s")