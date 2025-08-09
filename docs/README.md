# 字幕統合パイプライン（SRT Pipeline）

## 概要

4ソース統合による高精度日本語字幕生成システム

- **CapCut/Vrew SRT**: 時間枠として活用
- **台本テキスト**: 正確な内容
- **無音解析JSON**: Valley snapping（±150ms）
- **Whisper ASR**: 境界精度調整（オプション）

## 品質基準

- **同期精度**: ±0.050s以内（目標0.020s）
- **レイアウト**: 2行/36字、CPS≤17
- **最小長**: 1.2s、最小ギャップ: 0.12s

## ファイル構成

```
audio/           # 入力音声（Git LFS管理）
├── 4_2.wav     # メインオーディオファイル
subs/            # 字幕ファイル
├── 0808.srt    # CapCut/Vrew出力（入力）
├── final_production.srt  # 最終成果物
└── final_production.vtt  # WebVTT版
scripts/         # 処理スクリプト
├── smart_subs.py         # 4ソース統合
├── srt_rules.py          # 日本語レイアウト規則
├── finalize_tail.py      # 末尾調整
└── check_durations.py    # 品質検証
reports/         # 解析結果JSON
├── audio_peaks.json      # 無音解析（既存使用）
└── whisper_medium.json   # ASR結果（既存使用）
```

## 実行方法

### 既存JSON使用モード（推奨）

```bash
# 4ソース統合
python3 scripts/smart_subs.py \\
  --audio_json reports/audio_peaks.json \\
  --whisper_json reports/whisper_medium.json \\
  --capcut_srt subs/0808.srt \\
  --script script_4_2.txt \\
  --out subs/final_smart.srt \\
  --out_vtt subs/final_smart.vtt

# 末尾調整（音声長-20ms）
python3 scripts/finalize_tail.py \\
  --in subs/final_smart.srt \\
  --audio audio/4_2.wav \\
  --out subs/final_production.srt \\
  --out_vtt subs/final_production.vtt \\
  --target_offset_ms 20

# 品質検証
python3 scripts/check_durations.py \\
  --audio audio/4_2.wav \\
  --srt subs/final_production.srt
```

### Make使用

```bash
make -f Makefile_smart smart-all
```

## Git LFS設定

大きなファイルはGit LFSで管理：

```bash
git lfs install
git lfs track "*.wav"
git lfs track "*.mp3"
git lfs track "models/*"
```

## 成果例

- **統合効果**: 381キュー → 135キュー（65%削減）
- **同期精度**: 0.065s（目標±0.050s）
- **品質**: 自然な句読点分割、適切なCPS制限

## トラブルシューティング

### 同期精度が基準を超える場合

`finalize_tail.py`の`--target_offset_ms`パラメータを調整：

```bash
# より厳密に調整（10ms）
--target_offset_ms 10

# 伸ばす方向に調整（30ms）
--target_offset_ms 30
```

### レイアウト違反

`scripts/srt_rules.py`でCPS/行長制限を確認：

- MAX_CPS_DEFAULT = 17.0
- MAX_LINE_CHARS_DEFAULT = 36
- MAX_LINES_DEFAULT = 2

## CI/CD

GitHub Actionsで軽量検証を実行。`lfs: true`でチェックアウト。