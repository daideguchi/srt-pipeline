#!/usr/bin/env python3
import argparse, re

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
    out=[]
    for b in re.split(r"\n\s*\n", txt):
        ls=[ln for ln in b.splitlines() if ln.strip()!=""]
        if not ls: continue
        if re.fullmatch(r"\d+", ls[0]): ls=ls[1:]
        if not ls: continue
        m=re.match(r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", ls[0])
        if not m: continue
        st=parse_time(m.group(1)); et=parse_time(m.group(2))
        tx="\n".join(ls[1:]).strip()
        out.append([st,et,tx])
    return out

def write_srt(entries, path):
    with open(path,"w",encoding="utf-8") as f:
        for i,(s,e,tx) in enumerate(entries,1):
            f.write(f"{i}\n{fmt_time(s)} --> {fmt_time(e)}\n{tx}\n\n")

def write_vtt(entries, path):
    with open(path,"w",encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for s,e,tx in entries:
            f.write(f"{fmt_time(s).replace(',', '.')} --> {fmt_time(e).replace(',', '.')}\n{tx}\n\n")

ap=argparse.ArgumentParser()
ap.add_argument("--base", required=True, help="既存SRT")
ap.add_argument("--add", required=True, help="追いSRT（先頭0秒基準）")
ap.add_argument("--gap_ms", type=int, default=120, help="結合時の最小ギャップ")
ap.add_argument("--offset", type=float, default=None, help="add側に足す秒数（未指定ならbase末尾+ギャップ）")
ap.add_argument("--out", required=True)
ap.add_argument("--out_vtt", default=None)
args=ap.parse_args()

base = read_srt(args.base)
add  = read_srt(args.add)
if not base: raise SystemExit("baseが空")
base_last = base[-1][1]
offset = args.offset if args.offset is not None else base_last + args.gap_ms/1000.0

# オフセット適用
add2=[]
for s,e,tx in add:
    add2.append([s+offset, e+offset, tx])

merged = base + add2
merged.sort(key=lambda x:(x[0], x[1]))

# 最小ギャップ/最小長のゆる保証
min_gap = args.gap_ms/1000.0
min_dur = 0.80
for i in range(1, len(merged)):
    ps,pe,_ = merged[i-1]
    cs,ce,tx = merged[i]
    if cs < pe + min_gap:
        need = pe + min_gap - cs
        cs += need
        if ce < cs + min_dur:
            ce = cs + min_dur
        merged[i] = [cs,ce,tx]

write_srt(merged, args.out)
if args.out_vtt:
    write_vtt(merged, args.out_vtt)

print(f"base末尾={base_last:.3f}s / addオフセット={offset:.3f}s / 総行数={len(merged)}")