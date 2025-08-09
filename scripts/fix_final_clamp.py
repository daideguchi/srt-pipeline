#!/usr/bin/env python3
import re, wave, contextlib

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

# Process
subs = read_srt('subs/final_merged.srt')
audio = audio_duration('audio/4_2.wav')
eps = 0.020  # 20ms
target_end = audio - eps  # 517.311

print(f"Audio: {audio:.3f}s")
print(f"Target end: {target_end:.3f}s")
print(f"Original last subtitle: {subs[-1][0]:.3f} --> {subs[-1][1]:.3f}")

# Fix the last subtitle
s, e, tx = subs[-1]
e = target_end  # Set end to target

# Ensure minimum duration of 0.8s
min_dur = 0.8
if e - s < min_dur:
    s = max(0.0, e - min_dur)
    
subs[-1] = [s, e, tx]

print(f"Fixed last subtitle: {subs[-1][0]:.3f} --> {subs[-1][1]:.3f}")

# Write output
write_srt(subs, 'subs/final_for_upload.srt')
print(f"Written to subs/final_for_upload.srt")
print(f"Final diff: {subs[-1][1] - audio:.3f}s")