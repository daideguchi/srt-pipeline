#!/usr/bin/env python3
# scripts/compare_srt_vs_script.py
import argparse, re, unicodedata, csv
from pathlib import Path
from difflib import SequenceMatcher

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
        cues.append((start,end,txt))
    return cues

def norm(s:str, compact=False)->str:
    s=unicodedata.normalize("NFKC", s).replace("\r\n","\n").replace("\r","\n")
    if compact:
        s=re.sub(r"\s+","",s)
    return s

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--srt", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True, help="出力ベースパス（拡張子なし）")
    args=ap.parse_args()

    srt_text = Path(args.srt).read_text(encoding="utf-8", errors="ignore")
    script_text = Path(args.script).read_text(encoding="utf-8", errors="ignore")
    cues = parse_srt(srt_text)
    sc = norm(script_text, compact=False)
    scc= norm(script_text, compact=True)

    rows=[]
    for i,(st,et,txt) in enumerate(cues, start=1):
        t  = norm(txt, compact=False)
        tc = norm(txt, compact=True)
        v1 = t in sc
        v2 = tc in scc
        # local similarity
        sm = SequenceMatcher(None, tc, scc)
        a,b,n = sm.find_longest_match(0,len(tc),0,len(scc))
        win = 2*len(tc) if len(tc)>0 else 0
        lo = max(0, b - win//4); hi = min(len(scc), b + win)
        local = scc[lo:hi]
        sim = SequenceMatcher(None, tc, local).ratio() if local else 0.0
        rows.append([i,st,et,len(t),v1,v2,round(sim,4),txt.replace("\n"," / ")])

    base = Path(args.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    with (base.parent / (base.stem + "_full.csv")).open("w", newline="", encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["cue","start","end","chars","verbatim","compact","similarity_local","text"]); w.writerows(rows)
    # worst 20
    rows_sorted = sorted(rows, key=lambda r: (r[5], r[6]))[:20]
    with (base.parent / (base.stem + "_worst20.csv")).open("w", newline="", encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["cue","start","end","chars","verbatim","compact","similarity_local","text"]); w.writerows(rows_sorted)
    print("📊 compare: 出力完了")

if __name__=="__main__":
    main()