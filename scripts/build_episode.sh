#!/usr/bin/env bash
set -euo pipefail

MP3="${1:-}"
SCRIPT_TXT="${2:-}"
AUDIO_WAV="audio/voice.wav"

MERGED_SRT="subs/final_merged.srt"
FINAL_SRT="subs/final_for_upload.srt"
FINAL_VTT="subs/final_for_upload.vtt"
CLIPS_CSV="reports/clips.csv"

# 仮想環境が存在する場合は自動アクティベート
if [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
    echo "🐍 仮想環境をアクティベートしました"
fi

PYTHON="${PYTHON:-python3}"

err(){ echo "ERROR: $*" >&2; exit 1; }

[[ -n "$MP3" && -f "$MP3" ]] || err "mp3 が見つかりません: $MP3"
[[ -n "$SCRIPT_TXT" && -f "$SCRIPT_TXT" ]] || err "台本TXTが見つかりません: $SCRIPT_TXT"

mkdir -p audio subs reports

echo "🎧 1) mp3→WAV(24k/mono/PCM) 正規化"
ffmpeg -y -i "$MP3" -ar 24000 -ac 1 -c:a pcm_s16le "$AUDIO_WAV" -loglevel error

echo "🧠 2) Whisper強制アライン → subs/final_merged.srt"
# 既存の tail マージではなく、フルアラインで統一（台本通りの新規音声前提）
"$PYTHON" scripts/force_align_whisper.py \
  --audio "$AUDIO_WAV" \
  --script "$SCRIPT_TXT" \
  --out "$MERGED_SRT" \
  --model large-v3 \
  --device cpu --compute_type int8 \
  --beam_size 1 --best_of 1 --vad_filter True --language ja

[[ -s "$MERGED_SRT" ]] || err "merged SRT ができませんでした: $MERGED_SRT"

echo "✂️ 3) 末尾クランプ（-20ms）→ SRT/VTT"
"$PYTHON" scripts/srt_clamp_to_audio.py \
  --srt "$MERGED_SRT" \
  --audio "$AUDIO_WAV" \
  --out "$FINAL_SRT" \
  --epsilon_ms 20 --min_gap_ms 80 --min_dur_ms 800

ffmpeg -y -i "$FINAL_SRT" "$FINAL_VTT" -loglevel error

echo "📋 4) 編集用CSV（開始/終了/尺/テキスト）"
"$PYTHON" - "$FINAL_SRT" "$CLIPS_CSV" <<'PY'
import sys, re, pathlib, csv
srt = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').strip()
out = sys.argv[2]
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
pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
with open(out,"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f)
    w.writerow(["start_sec","end_sec","duration_sec","text"])
    w.writerows(rows)
print(f"wrote {len(rows)} rows to {out}")
PY

echo "✅ DONE"
echo "  - $FINAL_SRT"
echo "  - $FINAL_VTT"
echo "  - $CLIPS_CSV"