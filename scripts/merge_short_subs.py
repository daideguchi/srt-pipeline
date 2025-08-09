#!/usr/bin/env python3
"""
短い字幕を統合して読みやすくするツール
"""

from srt_utils import parse_srt, write_srt, Subtitle
from typing import List

def merge_short_subtitles(subtitles: List[Subtitle], min_duration: float = 1.0, 
                         max_length: int = 72) -> List[Subtitle]:
    """短い字幕を隣接する字幕と統合"""
    
    if not subtitles:
        return []
    
    merged = []
    i = 0
    
    while i < len(subtitles):
        current = subtitles[i]
        
        # 現在の字幕が短すぎる、または隣の字幕も短い場合は統合を検討
        if (current.duration() < min_duration or 
            (i + 1 < len(subtitles) and subtitles[i + 1].duration() < min_duration)):
            
            # 統合候補を収集
            merge_candidates = [current]
            j = i + 1
            total_length = len(current.text)
            
            # 隣接する短い字幕を収集（最大文字数を超えない範囲で）
            while (j < len(subtitles) and 
                   total_length + len(subtitles[j].text) + 1 <= max_length and
                   (subtitles[j].duration() < min_duration or len(merge_candidates) == 1)):
                
                merge_candidates.append(subtitles[j])
                total_length += len(subtitles[j].text) + 1
                j += 1
                
                # 十分な長さになったら停止
                if sum(s.duration() for s in merge_candidates) >= min_duration:
                    break
            
            # 統合実行
            if len(merge_candidates) > 1:
                merged_text = "".join([s.text for s in merge_candidates])
                merged_start = merge_candidates[0].start_time
                merged_end = merge_candidates[-1].end_time
                
                # 最小時間を確保
                if merged_end - merged_start < min_duration:
                    merged_end = merged_start + min_duration
                
                merged_subtitle = Subtitle(
                    index=len(merged) + 1,
                    start_time=merged_start,
                    end_time=merged_end,
                    text=merged_text
                )
                
                merged.append(merged_subtitle)
                i = j
            else:
                # 統合しない場合はそのまま追加
                current.index = len(merged) + 1
                if current.duration() < 0.8:
                    current.end_time = current.start_time + 0.8
                merged.append(current)
                i += 1
        else:
            # 十分な長さの字幕はそのまま追加
            current.index = len(merged) + 1
            merged.append(current)
            i += 1
    
    return merged

def main():
    # 最適化されたSRTを読み込み
    with open('aligned_optimized.srt', 'r', encoding='utf-8') as f:
        subtitles = parse_srt(f.read())
    
    print(f"📋 読み込み: {len(subtitles)}個の字幕")
    
    # 統合処理
    merged = merge_short_subtitles(subtitles, min_duration=0.8, max_length=72)
    
    print(f"🔄 統合後: {len(merged)}個の字幕")
    
    # 最終版として保存
    write_srt(merged, 'final_aligned_perfect.srt')
    
    print("✅ 最終版保存完了: final_aligned_perfect.srt")
    
    # 統計情報
    if merged:
        durations = [s.duration() for s in merged]
        print(f"📊 平均表示時間: {sum(durations)/len(durations):.2f}秒")
        print(f"📊 最短時間: {min(durations):.2f}秒")
        print(f"📊 最長時間: {max(durations):.2f}秒")
        print(f"📊 総時間: {merged[-1].end_time:.2f}秒")

if __name__ == "__main__":
    main()