# SRT字幕生成システム - 実運用ガイド

## 🎯 概要

**音声（AI音声）+ 台本（AI生成）** から **±50ms以内同期のSRT/VTT字幕** を一発生成

**対応プラットフォーム**: CapCut / Vrew / YouTube 即インポート対応

## 📁 フォルダ構造

```
srtfile/
├── venv/                    # Python仮想環境（初回のみ）
├── scripts/                 # 補助スクリプト群
│   ├── force_align_whisper.py
│   ├── pad_to_audio_end.py
│   ├── clean_tail.py
│   ├── check_durations.py
│   └── compare_srt_vs_script.py
├── audio/                   # あなたが音声を置く場所
├── subs/                    # 生成字幕の出力先
├── reports/                 # 品質レポート
├── generate_episode.py      # 🌟メイン実行スクリプト
├── srt_to_vtt.py           # SRT→VTT変換
├── CLAUDE_CODE_TEMPLATE.md  # Claude Code用指示
└── TROUBLESHOOTING.md       # トラブル対応
```

## ⚡ 基本運用フロー

### あなたがやること（毎回）

1. **音声配置**: `audio/2025-08-09_dementia_tips.wav`
2. **台本配置**: `script_2025-08-09.txt`
3. **Claude Codeに指示**: テンプレートを使用

### Claude Codeがやること（自動）

1. **Whisper強制アライン**: 音声→SRT生成
2. **末尾クランプ**: 音声長-20msで精密同期
3. **VTT変換**: YouTube/CapCut用形式生成
4. **品質検証**: ±50ms以内確認
5. **レポート生成**: 台本一致度分析

## 🚀 使用方法

### 初回セットアップ（一度だけ）

```bash
cd srtfile
python3 -m venv venv
source venv/bin/activate
pip install -r env/requirements.txt
```

### 毎回の字幕生成

#### パターン1: Claude Codeを使う場合（推奨）

`CLAUDE_CODE_TEMPLATE.md` のテンプレートをコピーして日付部分を変更

```
【タスク】字幕生成 - 音声+台本からSRT/VTT一括生成

■ 実行コマンド
python3 generate_episode.py \
  --audio audio/2025-08-09_dementia_tips.wav \
  --script script_2025-08-09.txt \
  --model large-v3 --device auto
```

#### パターン2: 直接実行する場合

```bash
source venv/bin/activate

python3 generate_episode.py \
  --audio audio/2025-08-09_dementia_tips.wav \
  --script script_2025-08-09.txt \
  --model large-v3 --device auto
```

## 📤 成果物

### メイン納品物
- `subs/2025-08-09_final.srt` - **CapCut/Vrew用**
- `subs/2025-08-09_final.vtt` - **YouTube用**

### 品質レポート
- `reports/2025-08-09_full.csv` - 全字幕の台本一致度
- `reports/2025-08-09_worst20.csv` - 要注意箇所

### 検証結果例
```
✅ VERIFY audio=517.331s  srt_end=517.311s  diff(audio - srt)=0.020s
🔢 字幕数: 159
✅ CapCut/Vrew/YouTubeに即インポート可能です
```

## 🎛️ オプション・カスタマイズ

### モデル選択
```bash
--model medium      # 高速・標準品質
--model large-v3    # 高品質・低速（推奨）
--model small       # 超高速・簡易品質
```

### デバイス選択
```bash
--device auto       # 自動判別（推奨）
--device cpu        # CPU強制
--device cuda       # GPU使用（高速）
```

### 末尾調整
```bash
--offset-ms 20      # 音声末尾-20ms（デフォルト）
--offset-ms 10      # より短く
--offset-ms 40      # より長く
```

## 🔧 メンテナンス・部分処理

### 既存SRTの末尾調整のみ

```bash
python3 scripts/pad_to_audio_end.py \
  --in subs/existing.srt \
  --audio audio/test.wav \
  --out subs/adjusted.srt \
  --offset-ms 20

python3 srt_to_vtt.py \
  --in subs/adjusted.srt \
  --out subs/adjusted.vtt
```

### 重複削除のみ

```bash
python3 scripts/clean_tail.py \
  --in subs/messy.srt \
  --out subs/clean.srt \
  --final-anchor "ありがとうございました"
```

## 📊 品質基準

### 合格条件
- **同期精度**: ±0.05s以内（実績: ±0.02s）
- **字幕数**: 適切な文節分割
- **文字エンコーディング**: UTF-8
- **プラットフォーム**: CapCut/Vrew/YouTube 即インポート可

### 品質確認コマンド
```bash
python3 scripts/check_durations.py \
  --audio audio/test.wav \
  --srt subs/test_final.srt
```

## 🗂️ ファイル命名規則

### 推奨パターン
```
audio/2025-08-09_dementia_tips.wav     # 日付_トピック
script_2025-08-09.txt                  # script_日付
subs/2025-08-09_final.{srt,vtt}       # 日付_final
```

### メリット
- 時系列ソート可能
- 検索しやすい
- バックアップ時に整理しやすい

## 🚨 トラブル対応

よくある問題は `TROUBLESHOOTING.md` を参照

### 即対応可能な問題
- 処理が遅い → `--model medium`
- 同期がずれる → `--offset-ms` 調整  
- 文字化け → UTF-8確認
- GPU関連エラー → `--device cpu`

### Claude Code問い合わせ時
環境情報・エラーメッセージ・使用コマンドをセットで提供

## 📈 処理時間目安

| 音声長 | モデル | デバイス | 処理時間 |
|--------|--------|----------|----------|
| 5分 | medium | CPU | 5-10分 |
| 5分 | large-v3 | CPU | 15-25分 |
| 5分 | large-v3 | GPU | 3-5分 |
| 10分 | medium | CPU | 10-20分 |

## 🎉 完了確認

成功時の出力例:
```
🎉 字幕生成完了
📄 SRT: subs/2025-08-09_final.srt (15854 bytes)
🎬 VTT: subs/2025-08-09_final.vtt (14379 bytes)
🔢 字幕数: 159
✅ CapCut/Vrew/YouTubeに即インポート可能です
```

---

## 📞 サポート

- **クイックリファレンス**: `CLAUDE_CODE_TEMPLATE.md`
- **トラブル解決**: `TROUBLESHOOTING.md`
- **技術相談**: Claude Code（環境情報付きで）

**実運用準備完了 - 毎回同じワークフローで高品質字幕生成！**