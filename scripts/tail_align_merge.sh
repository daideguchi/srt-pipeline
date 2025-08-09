#!/usr/bin/env bash
set -euo pipefail

AUDIO="${1:-audio/4_2.wav}"
BASE_SRT="${2:-subs/final_aligned_perfect.srt}"
SCRIPT_TXT="${3:-script_4_2.txt}"
OUT_SRT="${4:-subs/final_merged.srt}"
OUT_VTT="${5:-subs/final_merged.vtt}"

PYTHON="${PYTHON:-python3}"

err(){ echo "ERROR: $*" >&2; exit 1; }

[[ -f "$AUDIO" ]]     || err "音声が見つかりません: $AUDIO"
[[ -f "$BASE_SRT" ]]  || err "SRTが見つかりません: $BASE_SRT"
[[ -f "$SCRIPT_TXT" ]]|| err "台本が見つかりません: $SCRIPT_TXT"

# 1) 既存SRTの末尾秒を取得（0.10s手前から切り出す）
START="$(
$PYTHON - <<PY
import re, pathlib
p=pathlib.Path("$BASE_SRT").read_text(encoding='utf-8')
last=0.0
for b in re.split(r'\n\s*\n', p.strip()):
    ls=[ln for ln in b.splitlines() if ln.strip()]
    if not ls: continue
    if re.fullmatch(r'\d+', ls[0]): ls=ls[1:]
    if not ls: continue
    m=re.match(r'^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', ls[0])
    if not m: continue
    h,mn,ssms=m.group(2).split(':'); s,ms=ssms.split(',')
    end=int(h)*3600+int(mn)*60+int(s)+int(ms)/1000.0
    last=end
print(max(0.0,last-0.10))
PY
)"
echo "⏱ 末尾開始秒: $START"

# 2) 尾部切り出し（WAVは -c copy だと空になり得る→ PCM 再エンコードで確実化）
rm -f audio/tail.wav
ffmpeg -y -i "$AUDIO" -ss "$START" -c:a pcm_s16le -ar 24000 -ac 1 audio/tail.wav -loglevel error || true
if [[ ! -s audio/tail.wav ]]; then
  echo "⚠️ 再試行: -ss を入力の前へ移動"
  ffmpeg -y -ss "$START" -i "$AUDIO" -c:a pcm_s16le -ar 24000 -ac 1 audio/tail.wav -loglevel error
fi
[[ -s audio/tail.wav ]] || err "tail.wav が空です。START=$START を確認してください。"

# 3) venv 最小依存セット
if [[ ! -d venv ]]; then
  echo "📦 venv を作成します"
  $PYTHON -m venv venv
fi
source venv/bin/activate
python -V

python - <<PY || NEED="yes"
import importlib, sys
for m in ["faster_whisper","numpy","ctranslate2","huggingface_hub","tokenizers","onnxruntime"]:
    try: importlib.import_module(m)
    except Exception: sys.exit(1)
print("deps-ok")
PY
if [[ "${NEED:-}" == "yes" ]]; then
  echo "📥 依存導入（最小セット）"
  pip install -U pip
  pip install "faster-whisper==1.0.3" numpy==1.26.4 ctranslate2 huggingface-hub tokenizers onnxruntime
fi

# 4) Whisper 強制アライン（尾部）
python scripts/force_align_whisper.py \
  --audio audio/tail.wav \
  --script "$SCRIPT_TXT" \
  --out subs/tail_aligned.srt \
  --model medium \
  --device cpu

[[ -s subs/tail_aligned.srt ]] || err "subs/tail_aligned.srt が生成されませんでした。"

# 5) 追いSRTを +120ms オフセットで結合（最小ギャップ80ms / 最小長0.80s）
python scripts/srt_offset_merge.py \
  --base "$BASE_SRT" \
  --add  subs/tail_aligned.srt \
  --gap_ms 120 \
  --out "$OUT_SRT" \
  --out_vtt "$OUT_VTT"

# 6) 実尺検証
python - <<PY
import wave, contextlib, re, pathlib
def dur(w): 
    with contextlib.closing(wave.open(w,'rb')) as f: 
        return f.getnframes()/f.getframerate()
def last_end(s):
    t=pathlib.Path(s).read_text(encoding='utf-8').strip()
    last=0.0
    for b in re.split(r'\n\s*\n', t):
        ls=[ln for ln in b.splitlines() if ln.strip()]
        if ls and re.fullmatch(r'\d+', ls[0]): ls=ls[1:]
        if not ls: continue
        m=re.match(r'^(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', ls[0])
        if not m: continue
        h,mn,ssms=m.group(2).split(':'); s,ms=ssms.split(',')
        end=int(h)*3600+int(mn)*60+int(s)+int(ms)/1000.0
        last=end
    return last
audio = dur("$AUDIO")
end   = last_end("$OUT_SRT")
print(f'✅ DONE  audio={audio:.3f}s  srt_end={end:.3f}s  diff={end-audio:+.3f}s')
PY

echo "📄 出力: $OUT_SRT / $OUT_VTT"