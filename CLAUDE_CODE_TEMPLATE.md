# Claude Code 指示テンプレート - 実運用

## 🎯 標準パターン：音声+台本から字幕生成

```
【タスク】字幕生成 - 音声+台本からSRT/VTT一括生成

■ 前提
- プロジェクト: srtfile/
- 音声ファイル: audio/YYYY-MM-DD_<slug>.wav（配置済み）
- 台本テキスト: script_YYYY-MM-DD.txt（配置済み）

■ 実行コマンド
python3 generate_episode.py \
  --audio audio/YYYY-MM-DD_<slug>.wav \
  --script script_YYYY-MM-DD.txt \
  --model large-v3 --device auto

■ 期待する成果物
- subs/YYYY-MM-DD_final.srt（CapCut/Vrew用）
- subs/YYYY-MM-DD_final.vtt（YouTube用）
- reports/YYYY-MM-DD_*.csv（一致度レポート）

■ 合格条件
- 音声との同期差分 ±0.05s以内
- 字幕数・最終タイムコードをログ出力
- エラー時は原因と対処法を提示

■ その他
- 処理が重い場合：--model medium を使用
- GPU利用時：--device cuda を指定
- 末尾調整：--offset-ms 10-40 で微調整可能
```

## 🔧 メンテナンス・調整パターン

```
【タスク】既存SRTの末尾調整のみ

■ 前提
- 既存SRT: subs/<name>.srt（配置済み）
- 対象音声: audio/<name>.wav

■ 実行コマンド
python3 scripts/pad_to_audio_end.py \
  --in subs/<name>.srt \
  --audio audio/<name>.wav \
  --out subs/<name>_adjusted.srt \
  --offset-ms 20

python3 srt_to_vtt.py \
  --in subs/<name>_adjusted.srt \
  --out subs/<name>_adjusted.vtt

■ 検証コマンド
python3 scripts/check_durations.py \
  --audio audio/<name>.wav \
  --srt subs/<name>_adjusted.srt
```

## 📊 レポート・分析パターン

```
【タスク】台本一致度分析

■ 実行コマンド
python3 scripts/compare_srt_vs_script.py \
  --srt subs/YYYY-MM-DD_final.srt \
  --script script_YYYY-MM-DD.txt \
  --out reports/YYYY-MM-DD

■ 成果物
- reports/YYYY-MM-DD_full.csv（全字幕分析）
- reports/YYYY-MM-DD_worst20.csv（要注意箇所）
```

## ⚡ 高速・軽量パターン

```
【タスク】軽量モードでの字幕生成（テスト用）

■ 実行コマンド
python3 generate_episode.py \
  --audio audio/YYYY-MM-DD_<slug>.wav \
  --script script_YYYY-MM-DD.txt \
  --model medium --device cpu

■ 用途
- 初回テストや動作確認
- GPU未使用環境
- 処理時間優先の場合
```

## 🚨 トラブル対応パターン

```
【タスク】エラー解決・再実行

■ 一般的な対処
1. 仮想環境の確認
   source venv/bin/activate
   pip list | grep faster-whisper

2. ファイルパス・エンコーディング確認
   file audio/*.wav
   file script_*.txt

3. 段階的実行（デバッグ用）
   python3 scripts/force_align_whisper.py --audio ... --script ... --out temp.srt --model medium
   python3 scripts/pad_to_audio_end.py --in temp.srt --audio ... --out final.srt
   python3 srt_to_vtt.py --in final.srt --out final.vtt

■ レポート要求項目
- エラーメッセージ全文
- 使用ファイル名・サイズ
- 実行環境（CPU/GPU、モデル）
```

---

## 使い方

1. 上記テンプレートの`YYYY-MM-DD`と`<slug>`を実際の値に置き換え
2. Claude Codeに貼り付け
3. 実行結果を確認

**例：**
- 音声：`audio/2025-08-09_dementia_tips.wav`  
- 台本：`script_2025-08-09.txt`

→ テンプレートの`YYYY-MM-DD`を`2025-08-09`、`<slug>`を`dementia_tips`に置換