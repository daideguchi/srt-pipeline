#!/usr/bin/env python3
"""
SRT Rules - 日本語字幕の実用的調整ルール

シンプルで確実な調整のみ:
1. CPS調整（表示時間延長）
2. 改行最適化
3. 句読点調整
"""

import re
import unicodedata
import sys
import os
from typing import List

# スクリプトディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from srt_utils import SRTSegment, load_srt


def normalize_text(text: str) -> str:
    """テキスト正規化"""
    return unicodedata.normalize("NFKC", text.strip())


def calculate_cps(text: str, duration: float) -> float:
    """CPS計算"""
    clean_text = re.sub(r'[\s\n]', '', text)
    return len(clean_text) / max(duration, 0.001)


def improve_line_breaks(text: str, max_chars: int = 13) -> str:
    """改行を改善"""
    text = normalize_text(text)
    
    if len(text) <= max_chars:
        return text
    
    # 既存の改行を削除
    text = text.replace('\n', '')
    
    # 日本語句読点
    punctuation = "。！？、…"
    
    # 自然な分割点を探す
    best_split = len(text) // 2
    
    # 句読点で分割
    for i, char in enumerate(text):
        if char in punctuation and i <= max_chars:
            best_split = i + 1
    
    # 分割点がなければ文字数で分割
    if best_split == len(text) // 2:
        best_split = min(max_chars, len(text) // 2)
    
    if best_split >= len(text):
        return text
    
    line1 = text[:best_split]
    line2 = text[best_split:]
    
    # 再帰的に2行目も処理
    if len(line2) > max_chars:
        line2 = improve_line_breaks(line2, max_chars)
    
    return line1 + '\n' + line2


def extend_timing_for_cps(segments: List[SRTSegment], target_cps: float = 5.0) -> List[SRTSegment]:
    """CPS調整のための表示時間延長"""
    improved_segments = []
    
    for i, seg in enumerate(segments):
        text_len = len(re.sub(r'[\s\n]', '', seg.text))
        current_duration = seg.end - seg.start
        current_cps = calculate_cps(seg.text, current_duration)
        
        # CPS が高すぎる場合のみ調整
        if current_cps > target_cps:
            # 理想的な表示時間を計算
            ideal_duration = text_len / target_cps
            extension_needed = ideal_duration - current_duration
            
            # 前後のセグメントとの間隔を確認
            prev_end = segments[i-1].end if i > 0 else 0
            next_start = segments[i+1].start if i < len(segments) - 1 else float('inf')
            
            # 延長可能な範囲を計算
            max_start_extension = max(0, seg.start - prev_end - 0.1)
            max_end_extension = max(0, next_start - seg.end - 0.1)
            
            # 延長を配分（前30%, 後70%）
            start_extension = min(extension_needed * 0.3, max_start_extension)
            end_extension = min(extension_needed * 0.7, max_end_extension)
            
            # まだ足りない場合は残りを分配
            remaining = extension_needed - start_extension - end_extension
            if remaining > 0:
                additional_start = min(remaining * 0.5, max_start_extension - start_extension)
                additional_end = min(remaining * 0.5, max_end_extension - end_extension)
                start_extension += additional_start
                end_extension += additional_end
            
            new_start = seg.start - start_extension
            new_end = seg.end + end_extension
        else:
            new_start = seg.start
            new_end = seg.end
        
        improved_segments.append(SRTSegment(
            index=seg.index,
            start=new_start,
            end=new_end,
            text=seg.text
        ))
    
    return improved_segments


def improve_readability(segments: List[SRTSegment]) -> List[SRTSegment]:
    """読みやすさ改善"""
    improved = []
    
    for seg in segments:
        # 改行を改善
        improved_text = improve_line_breaks(seg.text)
        
        improved.append(SRTSegment(
            index=seg.index,
            start=seg.start,
            end=seg.end,
            text=improved_text
        ))
    
    return improved


def format_timestamp(seconds: float) -> str:
    """秒をSRTタイムスタンプに変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def save_srt(segments: List[SRTSegment], output_path: str) -> None:
    """SRTファイル保存"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for seg in segments:
            start_time = format_timestamp(seg.start)
            end_time = format_timestamp(seg.end)
            
            f.write(f"{seg.index}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{seg.text}\n\n")


def apply_minimal_improvements(input_path: str, output_path: str) -> None:
    """最小限の実用的改善を適用"""
    print("🔧 Applying minimal practical improvements...")
    
    # 元の字幕をロード
    segments = load_srt(input_path)
    print(f"📋 Loaded {len(segments)} segments")
    
    # 1. CPS改善のための表示時間延長
    print("⏰ Extending timing for better CPS...")
    timing_improved = extend_timing_for_cps(segments, target_cps=5.5)
    
    # 2. 読みやすさ改善
    print("📖 Improving readability...")
    final_segments = improve_readability(timing_improved)
    
    # 3. 保存
    save_srt(final_segments, output_path)
    print(f"💾 Improved subtitles saved: {output_path}")
    
    # 改善効果を計算
    original_avg_cps = sum(calculate_cps(seg.text, seg.end - seg.start) for seg in segments) / len(segments)
    improved_avg_cps = sum(calculate_cps(seg.text, seg.end - seg.start) for seg in final_segments) / len(final_segments)
    
    print(f"📊 CPS improvement: {original_avg_cps:.2f} → {improved_avg_cps:.2f}")
    
    return final_segments


if __name__ == "__main__":
    input_file = "subs/final_production_direct.srt"
    output_file = "subs/improved_aligned.srt"
    
    apply_minimal_improvements(input_file, output_file)