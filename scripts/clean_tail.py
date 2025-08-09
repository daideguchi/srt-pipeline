#!/usr/bin/env python3
# scripts/clean_tail.py
import argparse, re, sys, unicodedata
from pathlib import Path

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\r\n","\n").replace("\r","\n")
    return s

def parse_srt(text: str):
    blocks = re.split(r"\n\s*\n", text.strip())
    cues = []
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip()]
        if not lines: continue
        if re.fullmatch(r"\d+", lines[0]): lines = lines[1:]
        if not lines: continue
        m = re.match(r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[0])
        if not m: continue
        start, end = m.group(1), m.group(2)
        txt = "\n".join(lines[1:]).strip()
        cues.append({"start": start, "end": end, "text": txt})
    return cues

def write_srt(cues, path: Path):
    with path.open("w", encoding="utf-8") as f:
        for i,c in enumerate(cues, start=1):
            f.write(f"{i}\n{c['start']} --> {c['end']}\n{c['text']}\n\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="outp", required=True)
    ap.add_argument("--final-anchor", required=True, help="最終行に必ず含まれるべき文（句点有無許容）")
    ap.add_argument("--script", default=None, help="元台本（任意・未使用）")
    args = ap.parse_args()

    srt = Path(args.inp).read_text(encoding="utf-8", errors="ignore")
    srt = norm(srt)
    cues = parse_srt(srt)

    # アンカーのゆるい候補
    anchor = norm(args.final_anchor)
    alts = { anchor, anchor.rstrip("。"), anchor.replace("。","") }

    true_last = None
    for i,c in enumerate(cues):
        t = norm(c["text"])
        if any(a in t for a in alts):
            true_last = i  # 最後に見つかった位置を採用
    if true_last is None:
        print("⚠️ 最終アンカーが見つかりません。SRTを変更せず保存します。", file=sys.stderr)
        trimmed = cues
    else:
        trimmed = cues[:true_last+1]

    Path(args.outp).parent.mkdir(parents=True, exist_ok=True)
    write_srt(trimmed, Path(args.outp))
    print(f"original_cues={len(cues)}  trimmed_cues={len(trimmed)}  true_last_index={true_last+1 if true_last is not None else 'N/A'}")

if __name__ == "__main__":
    main()