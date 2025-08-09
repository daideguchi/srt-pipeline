# トラブルシューティングガイド - SRT字幕生成

## 🚨 よくある問題と解決法

### 1. 処理が遅い・停止する

**症状**: Whisper処理で10分以上止まる、メモリ不足エラー

**解決法**:
```bash
# 軽量モデルに変更
python3 generate_episode.py \
  --audio audio/2025-08-09_test.wav \
  --script script_2025-08-09.txt \
  --model medium --device cpu

# さらに軽量化
python3 generate_episode.py \
  --model small --device cpu
```

**予防策**: 
- 10分以上の音声は事前に分割
- 初回はmediumで試す
- GPUがあればdevice cudaを使用

---

### 2. 音声同期がずれる（±0.05s超過）

**症状**: `diff=0.123s` など大きな差分が出る

**解決法**:
```bash
# 末尾オフセットを調整
python3 generate_episode.py \
  --offset-ms 10    # より短く
# または
  --offset-ms 40    # より長く

# 手動調整
python3 scripts/pad_to_audio_end.py \
  --in subs/2025-08-09_aligned.srt \
  --audio audio/2025-08-09_test.wav \
  --out subs/2025-08-09_final.srt \
  --offset-ms 15
```

**診断コマンド**:
```bash
python3 scripts/check_durations.py \
  --audio audio/2025-08-09_test.wav \
  --srt subs/2025-08-09_final.srt
```

---

### 3. 文字化け・エンコーディングエラー

**症状**: 日本語が文字化け、`UnicodeDecodeError`

**解決法**:
```bash
# ファイルエンコーディング確認
file script_2025-08-09.txt

# UTF-8に変換（必要時）
iconv -f SHIFT_JIS -t UTF-8 script_original.txt > script_2025-08-09.txt

# BOM削除（必要時）
sed '1s/^\xEF\xBB\xBF//' script_with_bom.txt > script_2025-08-09.txt
```

**予防策**: テキストエディタでUTF-8（BOMなし）保存

---

### 4. CapCut/Vrewで読み込めない

**症状**: 字幕ファイルのインポートでエラー

**解決法**:
```bash
# SRT形式確認・修正
python3 -c "
import re
with open('subs/2025-08-09_final.srt', 'r') as f:
    content = f.read()
print('字幕数:', len(re.findall(r'^\d+$', content, re.MULTILINE)))
print('形式エラー:', 'Error' if '-->' not in content else 'OK')
"

# WebVTT再生成
python3 srt_to_vtt.py \
  --in subs/2025-08-09_final.srt \
  --out subs/2025-08-09_final.vtt
```

**代替案**: VTT形式を試す、またはファイル名を `ja.srt` にリネーム

---

### 5. 依存関係・環境エラー

**症状**: `ModuleNotFoundError`, パッケージ不足

**解決法**:
```bash
# 仮想環境確認
source venv/bin/activate
python3 --version
pip list

# パッケージ再インストール
pip install --upgrade -r env/requirements.txt

# 個別インストール
pip install faster-whisper==1.0.3 ctranslate2 numpy
```

**環境リセット**:
```bash
rm -rf venv/
python3 -m venv venv
source venv/bin/activate
pip install -r env/requirements.txt
```

---

### 6. 台本と音声の内容が合わない

**症状**: 一致度レポートで低スコア、認識がおかしい

**診断**:
```bash
python3 scripts/compare_srt_vs_script.py \
  --srt subs/2025-08-09_final.srt \
  --script script_2025-08-09.txt \
  --out reports/2025-08-09

# worst20.csvで問題箇所確認
head -n 10 reports/2025-08-09_worst20.csv
```

**対処法**:
- 台本と音声内容の一致確認
- 句読点・改行位置の調整
- より大きなモデル（large-v3）で再処理

---

### 7. GPU関連エラー

**症状**: CUDA out of memory, GPU認識エラー

**解決法**:
```bash
# CPU強制使用
python3 generate_episode.py \
  --device cpu \
  --model medium

# GPU確認
python3 -c "import torch; print(torch.cuda.is_available())"
```

---

## 🔧 診断コマンド集

### 環境診断
```bash
# 基本環境
python3 --version
pip list | grep -E "(faster-whisper|torch|numpy)"

# ファイル確認
ls -la audio/ script_*.txt subs/
file audio/*.wav script_*.txt

# ディスク容量
df -h .
```

### ファイル詳細診断
```bash
# 音声ファイル
ffprobe -v error -show_entries format=duration -of csv=p=0 audio/test.wav

# SRTファイル
grep -c "^[0-9]\+$" subs/test.srt
tail -n 10 subs/test.srt
```

### 処理時間見積もり
- 1分音声 ≈ 1-2分処理（medium, CPU）
- 1分音声 ≈ 3-5分処理（large-v3, CPU）
- 1分音声 ≈ 0.5-1分処理（large-v3, GPU）

---

## 📞 エスカレーション時の情報収集

Claude Codeに問い合わせる際は以下を提供：

```bash
# 環境情報
echo "=== Environment ==="
python3 --version
uname -a
df -h .

echo "=== Files ==="
ls -la audio/ subs/ script_*.txt

echo "=== Last Error ==="
# エラーメッセージ全文をコピー

echo "=== Command Used ==="
# 実行したコマンドを記載
```

このログをClaude Codeに送ることで迅速な解決が可能です。