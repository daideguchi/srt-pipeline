# SRT字幕強制アライメントツール

音声ファイルと台本から**完璧に同期した字幕**を生成するPythonツール群です。

## 🎯 特徴

### 📍 **2つの高精度アライメント方式**

- **🔥 Whisper強制アライメント** (推奨)
  - Whisperの単語レベルタイムスタンプと台本を強制マッピング
  - **語単位の完璧な同期**を実現
  - GPU対応で高速処理

- **⚡ VADベース整列**  
  - Voice Activity Detectionで無音区間を検出
  - 台本の文字数比率で時間配分
  - 軽量で高速

- **🚀 ハイブリッド統合**
  - 両方式の結果を統合して最高精度を達成

### ✨ **プロフェッショナル品質**

- CPS制限（文字/秒）による読みやすさ確保
- 字幕間ギャップの自動調整  
- 2行36文字レイアウト最適化
- SRT形式の完全互換

## 📦 インストール

```bash
# 必要なライブラリをインストール
pip install faster-whisper numpy librosa soundfile scipy

# リポジトリをクローンまたはダウンロード
git clone <このリポジトリ>
cd srtfile

# 実行権限を付与
chmod +x *.py
```

## 🚀 使用方法

### 基本使用（Whisper強制アライメント）

```bash
python srtgen.py --audio video.wav --script script.txt --out subtitle.srt
```

### VADベース整列

```bash
python srtgen.py --audio video.wav --script script.txt --out subtitle.srt --method vad
```

### 最高精度（ハイブリッド）

```bash
python srtgen.py --audio video.wav --script script.txt --out subtitle.srt --method both
```

### 高品質設定

```bash
python srtgen.py \
  --audio video.wav \
  --script script.txt \
  --out subtitle.srt \
  --model large-v3 \
  --device cuda \
  --max-cps 15 \
  --export-json
```

## 📋 引数一覧

| 引数 | 説明 | デフォルト |
|------|------|----------|
| `--audio` | 音声ファイルパス (.wav, .mp3, .mp4など) | 必須 |
| `--script` | 台本テキストファイル | 必須 |
| `--out` | 出力SRTファイル | 必須 |
| `--method` | 処理方式 (whisper/vad/both) | whisper |
| `--model` | Whisperモデル (tiny~large-v3) | large-v3 |
| `--device` | 実行デバイス (auto/cpu/cuda) | auto |
| `--max-line-len` | 1行の最大文字数 | 36 |
| `--max-lines` | 字幕の最大行数 | 2 |
| `--min-gap-ms` | 字幕間ギャップ（ミリ秒） | 80 |
| `--max-cps` | 最大CPS（文字/秒） | 17 |
| `--export-json` | JSON形式でもエクスポート | False |
| `--verbose` | 詳細出力 | False |

## 📁 ファイル構成

```
srtfile/
├── srtgen.py              # メイン実行スクリプト
├── force_align_whisper.py # Whisper強制アライメント
├── vad_align.py          # VADベース整列
├── srt_utils.py          # SRT処理ユーティリティ
├── requirements.txt      # 依存ライブラリ
└── README.md            # このファイル
```

## 🎬 台本ファイルの準備

台本はプレーンテキスト（UTF-8）で用意してください。

### ✅ 良い例

```text
こんにちは、今日は素晴らしい天気ですね。
AIについて詳しく解説していきます。

まず最初に、機械学習の基本概念から始めましょう。
人工知能は私たちの生活を大きく変える技術です。
```

### ❌ 避けるべき例

```text
[音楽] ←装飾記号多用
こんにちは！！！！ ←感嘆符の多用  
(間) ←指示文
```

## ⚡ パフォーマンス最適化

### GPU使用（推奨）

```bash
# CUDAが利用可能な場合
python srtgen.py --audio video.wav --script script.txt --out subtitle.srt --device cuda
```

### モデルサイズ選択

- **large-v3**: 最高精度（推奨、GPU推奨）
- **medium**: バランス重視
- **small**: 高速処理重視
- **tiny**: 最軽量

```bash
# 軽量モデルで高速処理
python srtgen.py --audio video.wav --script script.txt --out subtitle.srt --model medium
```

## 🛠️ 個別ツール使用

### Whisper強制アライメントのみ

```bash
python force_align_whisper.py \
  --audio video.wav \
  --script script.txt \
  --out aligned.srt \
  --model large-v3 \
  --device cuda
```

### VAD整列のみ

```bash
python vad_align.py \
  --audio video.wav \
  --script script.txt \
  --out vad_aligned.srt \
  --energy-threshold 0.02 \
  --silence-ms 300
```

## 📊 字幕品質の調整

### 読みやすさ重視

```bash
python srtgen.py \
  --audio video.wav \
  --script script.txt \
  --out subtitle.srt \
  --max-cps 12 \
  --min-gap-ms 120
```

### 情報密度重視

```bash
python srtgen.py \
  --audio video.wav \
  --script script.txt \
  --out subtitle.srt \
  --max-cps 20 \
  --min-gap-ms 50
```

## 🔍 トラブルシューティング

### よくある問題と解決法

#### 1. モジュールが見つからない
```bash
pip install faster-whisper numpy librosa soundfile scipy
```

#### 2. CUDA関連エラー
```bash
# CPUモードで実行
python srtgen.py --device cpu ...
```

#### 3. 音声ファイル読み込みエラー
```bash
# ffmpegをインストール
# macOS: brew install ffmpeg  
# Ubuntu: sudo apt install ffmpeg
```

#### 4. 字幕の同期がずれる
```bash
# より精密なモデルを使用
python srtgen.py --model large-v3 --method both ...
```

#### 5. 処理が遅い
```bash
# 軽量モデルを使用
python srtgen.py --model small --device cpu ...
```

## 📈 処理時間の目安

| 音声長 | モデル | デバイス | 処理時間 |
|--------|--------|----------|----------|
| 10分 | large-v3 | CUDA | ~2分 |
| 10分 | large-v3 | CPU | ~8分 |
| 10分 | medium | CUDA | ~1分 |
| 10分 | small | CPU | ~3分 |

## 🎯 精度向上のコツ

1. **台本の品質**
   - 実際の発話に近い文章にする
   - 装飾記号を最小限にする

2. **音声の品質**
   - ノイズの少ない録音
   - 一定の音量レベル

3. **設定の調整**
   - 重要な動画は`--method both`
   - 長時間の場合は`large-v3`モデル

## 📄 ライセンス

MIT License

## 🤝 貢献

Issue報告やプルリクエストをお待ちしています。

## 📞 サポート

- バグ報告: GitHubのIssues
- 機能要望: GitHubのDiscussions

---

**🎉 完璧寄せの字幕生成を体験してください！**