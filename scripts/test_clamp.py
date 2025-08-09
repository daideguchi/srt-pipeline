#!/usr/bin/env python3
import re, wave, contextlib

def parse_time(t):
    h,m,sms = t.split(":"); s,ms = sms.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

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

def audio_duration(path):
    with contextlib.closing(wave.open(path,'rb')) as w:
        return w.getnframes()/float(w.getframerate())

# Test
subs = read_srt('subs/final_merged.srt')
audio = audio_duration('audio/4_2.wav')

print(f"Audio duration: {audio:.3f}s")
print(f"Last subtitle: {subs[-1][0]:.3f} --> {subs[-1][1]:.3f}")
print(f"Difference: {subs[-1][1] - audio:.3f}s")

# What should be the target end time?
eps = 0.020  # 20ms
target_end = audio - eps
print(f"\nTarget end time: {target_end:.3f}s")
print(f"Current end time: {subs[-1][1]:.3f}s")
print(f"Need to change by: {target_end - subs[-1][1]:.3f}s")