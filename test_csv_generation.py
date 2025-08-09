#!/usr/bin/env python3
import sys, re, pathlib, csv

srt_file = "subs/final_for_upload.srt"
output_file = "reports/test_clips.csv"

if not pathlib.Path(srt_file).exists():
    print(f"❌ SRTファイルが見つかりません: {srt_file}")
    sys.exit(1)

srt = pathlib.Path(srt_file).read_text(encoding='utf-8').strip()

def parse_time(t):
    h,m,sms = t.split(":"); s,ms = sms.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

rows=[]
for b in re.split(r"\n\s*\n", srt):
    ls=[ln for ln in b.splitlines() if ln.strip()]
    if not ls: continue
    if re.fullmatch(r"\d+", ls[0]): ls = ls[1:]
    if not ls: continue
    m = re.match(r"^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", ls[0])
    if not m: continue
    st, et = parse_time(m.group(1)), parse_time(m.group(2))
    tx = "\n".join(ls[1:]).strip().replace("\n"," / ")
    rows.append([st, et, round(et-st,3), tx])

pathlib.Path(output_file).parent.mkdir(parents=True, exist_ok=True)
with open(output_file,"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f)
    w.writerow(["start_sec","end_sec","duration_sec","text"])
    w.writerows(rows)

print(f"✅ CSVファイル生成テスト完了: wrote {len(rows)} rows to {output_file}")

# 最初の3行を確認表示
with open(output_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()[:4]
    print("📋 生成されたCSVの先頭部分:")
    for line in lines:
        print(f"  {line.strip()}")