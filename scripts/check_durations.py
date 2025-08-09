#!/usr/bin/env python3
# check_durations.py - オーディオとSRTの同期検証＋ルール違反報告

import re, subprocess, json
from pathlib import Path
from srt_rules import calc_cps

MIN_DUR = 1.2
MIN_GAP = 0.12
MAX_CPS = 17.0
MAX_LINE = 36
TOL = 0.050  # 許容差 ±50ms

def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err

def audio_len(path):
    rc, out, err = run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nk=1:nw=1",str(path)])
    if rc != 0: raise RuntimeError(err)
    return float(out.strip())

def audio_len_from_json(jpath):
    data = json.loads(Path(jpath).read_text(encoding="utf-8"))
    dur = data.get("duration")
    if dur is None:
        raise RuntimeError(f"'duration' not found in {jpath}")
    return float(dur)

def parse_srt(path):
    text = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues=[]
    for b in blocks:
        ls=[ln for ln in b.splitlines() if ln.strip()]
        if not ls: continue
        if re.fullmatch(r"\d+",ls[0]): ls=ls[1:]
        if not ls: continue
        m=re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",ls[0])
        if not m: continue
        def tosec(ts):
            h,m,sms=ts.split(":"); s,ms=sms.split(",")
            return int(h)*3600+int(m)*60+int(s)+int(ms)/1000.0
        st,ed=tosec(m.group(1)),tosec(m.group(2))
        txt="\n".join(ls[1:])
        cues.append({"start":st,"end":ed,"text":txt})
    return cues

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=False, help="音声ファイル（ffprobe使用）")
    ap.add_argument("--audio_json", required=False, help="audio_peaks.json（durationを使用）")
    ap.add_argument("--srt", required=True)
    args = ap.parse_args()

    if args.audio_json:
        a = audio_len_from_json(args.audio_json)
    elif args.audio:
        a = audio_len(args.audio)
    else:
        raise SystemExit("❌ --audio か --audio_json のどちらかを指定してください。")
    cues = parse_srt(args.srt)
    if not cues:
        print("❌ No cues"); return
    end = max(c["end"] for c in cues)
    diff = a - end
    ok = abs(diff) <= TOL

    v_short=[]; v_gap=[]; v_cps=[]; v_len=[]
    prev_end = None
    for i,c in enumerate(cues,1):
        dur = c["end"] - c["start"]
        if dur < MIN_DUR: v_short.append(i)
        if prev_end is not None and c["start"] - prev_end < MIN_GAP: v_gap.append(i)
        cps = calc_cps(c["text"], max(dur,0.001))
        if cps > MAX_CPS: v_cps.append(i)
        if any(len(line) > MAX_LINE for line in (c["text"] or "").splitlines()):
            v_len.append(i)
        prev_end = c["end"]

    print(f"✅ VERIFY audio={a:.3f}s  srt_end={end:.3f}s  diff={diff:.3f}s  {'OK' if ok else 'NG'}")
    print(f"   Violations: short<{MIN_DUR}s:{len(v_short)} / gap<{MIN_GAP}s:{len(v_gap)} / cps>{MAX_CPS}:{len(v_cps)} / line>{MAX_LINE}:{len(v_len)}")
    if any([v_short, v_gap, v_cps, v_len]):
        print(f"   short: {v_short}")
        print(f"   gap  : {v_gap}")
        print(f"   cps  : {v_cps}")
        print(f"   line : {v_len}")

if __name__ == "__main__":
    main()