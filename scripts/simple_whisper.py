#!/usr/bin/env python3
"""
シンプルなWhisper強制アライメントツール
av依存を最小化した動作テスト版
"""

import argparse
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("Error: faster-whisper が見つかりません")
    print("インストール: pip install faster-whisper")
    sys.exit(1)


def normalize_text(text: str) -> str:
    """テキスト正規化"""
    import unicodedata
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[「」『』（）［］【】〈〉《》〔〕｛｝]', '', text)
    text = re.sub(r'[！？!?。、，,．.・…—─―－ー]', '', text)
    text = re.sub(r'[\s\u3000]+', '', text)
    return text.lower()


def format_srt_time(seconds: float) -> str:
    """SRT時間形式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')


def simple_align(audio_path: str, script_path: str, output_path: str) -> None:
    """シンプルなアライメント"""
    print(f"🎯 音声ファイル: {audio_path}")
    print(f"📝 台本ファイル: {script_path}")
    
    # 台本読み込み
    with open(script_path, 'r', encoding='utf-8') as f:
        script = f.read()
    
    # 文章分割
    sentences = [s.strip() for s in re.split(r'[。！？!?\n]+', script) if s.strip()]
    print(f"📋 分割文数: {len(sentences)}")
    
    # Whisper実行
    print("🎙️ 音声認識実行中...")
    model = WhisperModel("small", device="cpu")  # テスト用に軽量モデル
    
    segments, info = model.transcribe(
        audio_path,
        language="ja", 
        word_timestamps=True,
        vad_filter=True
    )
    
    # セグメント収集
    all_segments = []
    for segment in segments:
        all_segments.append({
            'start': segment.start,
            'end': segment.end,
            'text': segment.text
        })
    
    print(f"🔍 認識セグメント数: {len(all_segments)}")
    
    # シンプルなマッピング
    srt_content = ""
    for i, (sentence, segment) in enumerate(zip(sentences, all_segments), 1):
        if i <= len(all_segments):
            start = segment['start']
            end = segment['end']
            
            # 基本的な時間調整
            duration = end - start
            if duration < 1.0:
                end = start + max(1.0, len(sentence) * 0.05)
            
            srt_content += f"{i}\n"
            srt_content += f"{format_srt_time(start)} --> {format_srt_time(end)}\n"
            srt_content += f"{sentence}\n\n"
    
    # 保存
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    print(f"✅ 完了: {output_path}")
    print(f"📊 生成字幕数: {len(sentences)}")


def main():
    parser = argparse.ArgumentParser(description='シンプルWhisper強制アライメント')
    parser.add_argument('--audio', required=True, help='音声ファイル')
    parser.add_argument('--script', required=True, help='台本ファイル')
    parser.add_argument('--out', required=True, help='出力SRT')
    
    args = parser.parse_args()
    
    # ファイル確認
    if not Path(args.audio).exists():
        print(f"❌ 音声ファイルが見つかりません: {args.audio}")
        return 1
        
    if not Path(args.script).exists():
        print(f"❌ 台本ファイルが見つかりません: {args.script}")
        return 1
    
    try:
        simple_align(args.audio, args.script, args.out)
        return 0
    except Exception as e:
        print(f"❌ エラー: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())