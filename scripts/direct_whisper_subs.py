#!/usr/bin/env python3
"""
Direct Whisper Subtitle Generation - Simple & Reliable

単純で確実なWhisperベース字幕生成。複雑なアライメントなし。
Whisperの認識結果をそのまま信頼する実用的手法。
"""

import whisper
import os
import re
import unicodedata
from typing import List, Dict, Any


def load_whisper_model(model_size: str = "medium") -> whisper.Whisper:
    """Whisperモデルをロード"""
    print(f"🤖 Loading Whisper {model_size} model...")
    model = whisper.load_model(model_size)
    print("✅ Model loaded successfully")
    return model


def transcribe_audio(model: whisper.Whisper, audio_path: str) -> Dict[str, Any]:
    """音声ファイルを音声認識"""
    print(f"🎵 Transcribing: {audio_path}")
    
    # Whisperで認識実行
    result = model.transcribe(
        audio_path,
        language="ja",  # 日本語指定
        word_timestamps=True,  # 単語レベルタイムスタンプ
        verbose=False
    )
    
    print(f"✅ Transcription complete")
    print(f"📊 Detected segments: {len(result['segments'])}")
    
    return result


def format_timestamp(seconds: float) -> str:
    """秒をSRT形式のタイムスタンプに変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def clean_text(text: str) -> str:
    """テキストの基本的なクリーニング"""
    # NFKC正規化
    text = unicodedata.normalize("NFKC", text)
    
    # 余分な空白削除
    text = re.sub(r'\s+', '', text)
    
    # 基本的な整形
    text = text.strip()
    
    return text


def ensure_line_breaks(text: str, max_chars: int = 15) -> str:
    """適切な改行を挿入"""
    if len(text) <= max_chars:
        return text
    
    # 日本語句読点での分割を試行
    punctuation = "。！？、"
    
    # 句読点で分割可能な位置を探す
    for i, char in enumerate(text):
        if char in punctuation and i < max_chars:
            first_part = text[:i+1]
            second_part = text[i+1:]
            if second_part:
                return first_part + "\n" + ensure_line_breaks(second_part, max_chars)
    
    # 句読点がない場合は文字数で分割
    mid = min(max_chars, len(text) // 2)
    return text[:mid] + "\n" + text[mid:]


def optimize_segment_timing(segments: List[Dict]) -> List[Dict]:
    """セグメントタイミングの基本最適化"""
    optimized = []
    
    for i, seg in enumerate(segments):
        start = seg['start']
        end = seg['end']
        text = clean_text(seg['text'])
        
        if not text:
            continue
        
        # 最小表示時間確保
        min_duration = 1.0
        if end - start < min_duration:
            # 前後のセグメントとの間隔を考慮して延長
            if i < len(segments) - 1:
                next_start = segments[i + 1]['start']
                gap = next_start - end
                if gap > 0.1:
                    end = min(end + min_duration - (end - start), next_start - 0.05)
        
        # 改行処理
        formatted_text = ensure_line_breaks(text)
        
        optimized.append({
            'start': start,
            'end': end,
            'text': formatted_text
        })
    
    return optimized


def write_srt_file(segments: List[Dict], output_path: str) -> None:
    """SRT形式でファイル出力"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start_time = format_timestamp(seg['start'])
            end_time = format_timestamp(seg['end'])
            
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{seg['text']}\n\n")
    
    print(f"💾 SRT saved: {output_path}")


def write_vtt_file(segments: List[Dict], output_path: str) -> None:
    """VTT形式でファイル出力"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("WEBVTT\n\n")
        
        for i, seg in enumerate(segments, 1):
            start_time = format_timestamp(seg['start']).replace(',', '.')
            end_time = format_timestamp(seg['end']).replace(',', '.')
            
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{seg['text']}\n\n")
    
    print(f"💾 VTT saved: {output_path}")


def generate_subtitles(audio_path: str, model_size: str = "medium") -> None:
    """字幕生成メイン処理"""
    print("🎯 Starting Direct Whisper Subtitle Generation")
    print("=" * 50)
    
    # ファイル存在確認
    if not os.path.exists(audio_path):
        print(f"❌ Audio file not found: {audio_path}")
        return
    
    # モデルロード
    model = load_whisper_model(model_size)
    
    # 音声認識
    result = transcribe_audio(model, audio_path)
    
    # セグメント最適化
    print("🔧 Optimizing segments...")
    optimized_segments = optimize_segment_timing(result['segments'])
    
    print(f"✅ Optimized to {len(optimized_segments)} segments")
    
    # 出力ファイル作成
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    srt_path = f"subs/final_production_direct.srt"
    vtt_path = f"subs/final_production_direct.vtt"
    
    # subsディレクトリ作成
    os.makedirs("subs", exist_ok=True)
    
    # ファイル出力
    write_srt_file(optimized_segments, srt_path)
    write_vtt_file(optimized_segments, vtt_path)
    
    # 統計情報表示
    total_duration = result['segments'][-1]['end'] if result['segments'] else 0
    avg_segment_duration = total_duration / len(optimized_segments) if optimized_segments else 0
    
    print(f"\n📊 Generation Summary:")
    print(f"- Total segments: {len(optimized_segments)}")
    print(f"- Total duration: {total_duration:.1f} seconds")
    print(f"- Average segment length: {avg_segment_duration:.1f} seconds")
    print(f"- Output files: {srt_path}, {vtt_path}")
    
    print("\n🎉 Subtitle generation completed successfully!")


if __name__ == "__main__":
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    audio_file = os.path.join(project_root, "audio", "4_2.wav")
    generate_subtitles(audio_file)