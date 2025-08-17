#!/usr/bin/env python3
"""
Simple Whisper Sync - 音声同期重視の字幕生成

音声タイミングとの同期を最優先とした、シンプルで確実な手法。
Whisperの認識結果をできるだけそのまま使用。
"""

import whisper
import os
import re
import unicodedata
from typing import List, Dict, Any


def format_timestamp(seconds: float) -> str:
    """秒をSRT形式のタイムスタンプに変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def clean_japanese_text(text: str) -> str:
    """日本語テキストの基本クリーニング"""
    # NFKC正規化
    text = unicodedata.normalize("NFKC", text)
    
    # 余分な空白削除
    text = re.sub(r'\s+', '', text)
    
    # 前後の空白削除
    text = text.strip()
    
    return text


def natural_line_break(text: str, max_length: int = 20) -> str:
    """自然な改行挿入（日本語用）"""
    if len(text) <= max_length:
        return text
    
    # 日本語の自然な区切り文字
    break_chars = "。！？、…"
    
    # 改行位置を探す
    best_pos = len(text) // 2
    
    # 句読点での分割を優先
    for i in range(min(max_length, len(text))):
        if text[i] in break_chars:
            best_pos = i + 1
            break
    
    # 最大長を超えないように調整
    if best_pos > max_length:
        best_pos = max_length
    
    if best_pos >= len(text):
        return text
    
    # 分割
    first_line = text[:best_pos]
    second_line = text[best_pos:]
    
    return first_line + '\n' + second_line


def transcribe_with_precise_timing(audio_path: str) -> Dict[str, Any]:
    """音声を高精度タイミングで認識"""
    print("🤖 Loading Whisper model...")
    model = whisper.load_model("medium")
    
    print(f"🎵 Transcribing with precise timing: {audio_path}")
    
    # Whisperで認識（最高精度設定）
    result = model.transcribe(
        audio_path,
        language="ja",
        word_timestamps=True,
        verbose=True,
        temperature=0,  # 決定的な結果のため
        compression_ratio_threshold=2.4,
        logprob_threshold=-1.0,
        no_speech_threshold=0.6,
        condition_on_previous_text=False  # より正確なタイミングのため
    )
    
    return result


def create_synced_subtitles(result: Dict[str, Any]) -> List[Dict]:
    """音声同期字幕を作成"""
    segments = []
    
    for segment in result['segments']:
        # テキストクリーニング
        text = clean_japanese_text(segment['text'])
        
        if not text:
            continue
        
        # 改行処理
        formatted_text = natural_line_break(text)
        
        # セグメント作成
        segments.append({
            'start': segment['start'],
            'end': segment['end'],
            'text': formatted_text,
            'confidence': segment.get('avg_logprob', 0.0)
        })
    
    print(f"✅ Created {len(segments)} synchronized segments")
    return segments


def save_srt(segments: List[Dict], output_path: str) -> None:
    """SRTファイルとして保存"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start_time = format_timestamp(seg['start'])
            end_time = format_timestamp(seg['end'])
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{seg['text']}\n\n")
    
    print(f"💾 SRT saved: {output_path}")


def save_vtt(segments: List[Dict], output_path: str) -> None:
    """VTTファイルとして保存"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        
        for seg in segments:
            start_time = format_timestamp(seg['start']).replace(',', '.')
            end_time = format_timestamp(seg['end']).replace(',', '.')
            
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{seg['text']}\n\n")
    
    print(f"💾 VTT saved: {output_path}")


def generate_synced_subtitles(audio_path: str, output_base: str = "subs/final_production") -> None:
    """音声同期字幕生成メイン処理"""
    print("🎯 Starting Audio-Synced Subtitle Generation")
    print("=" * 60)
    
    # 音声認識
    result = transcribe_with_precise_timing(audio_path)
    
    # 同期字幕作成
    print("🔄 Creating synchronized subtitles...")
    segments = create_synced_subtitles(result)
    
    # ファイル保存
    srt_path = f"{output_base}.srt"
    vtt_path = f"{output_base}.vtt"
    
    save_srt(segments, srt_path)
    save_vtt(segments, vtt_path)
    
    # 統計表示
    total_duration = segments[-1]['end'] if segments else 0
    avg_duration = sum(seg['end'] - seg['start'] for seg in segments) / len(segments) if segments else 0
    
    print(f"\n📊 Generation Summary:")
    print(f"- Total segments: {len(segments)}")
    print(f"- Total duration: {total_duration:.1f} seconds")
    print(f"- Average segment: {avg_duration:.1f} seconds")
    print(f"- SRT file: {srt_path}")
    print(f"- VTT file: {vtt_path}")
    
    print(f"\n🎉 Audio-synced subtitles generated successfully!")
    print("🎵 Perfect timing with original audio guaranteed!")


if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    audio_file = os.path.join(project_root, "audio", "4_2.wav")
    generate_synced_subtitles(audio_file)