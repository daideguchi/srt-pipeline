#!/usr/bin/env python3
"""
SRT Utility Functions - シンプルな字幕解析ツール
"""

import re
import unicodedata
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class SRTSegment:
    index: int
    start: float
    end: float
    text: str


def parse_timestamp(timestamp: str) -> float:
    """SRTタイムスタンプを秒に変換"""
    # 00:00:05,860 -> 5.860
    parts = timestamp.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds_parts = parts[2].split(',')
    seconds = int(seconds_parts[0])
    milliseconds = int(seconds_parts[1])
    
    total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    return total_seconds


def load_srt(file_path: str) -> List[SRTSegment]:
    """SRTファイルを読み込み"""
    segments = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # セグメントごとに分割
    segment_blocks = re.split(r'\n\s*\n', content.strip())
    
    for block in segment_blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            try:
                index = int(lines[0])
                timeline = lines[1]
                text = '\n'.join(lines[2:])
                
                # タイムスタンプ解析
                start_str, end_str = timeline.split(' --> ')
                start = parse_timestamp(start_str)
                end = parse_timestamp(end_str)
                
                segments.append(SRTSegment(
                    index=index,
                    start=start,
                    end=end,
                    text=text
                ))
            except (ValueError, IndexError):
                continue
    
    return segments


def analyze_srt_quality(segments: List[SRTSegment]) -> Dict[str, Any]:
    """SRT品質分析"""
    if not segments:
        return {"error": "No segments found"}
    
    # 基本統計
    total_duration = segments[-1].end if segments else 0
    durations = [seg.end - seg.start for seg in segments]
    
    # CPS（文字/秒）計算
    cps_values = []
    for seg in segments:
        text_len = len(unicodedata.normalize("NFKC", seg.text.replace('\n', '').replace(' ', '')))
        duration = seg.end - seg.start
        if duration > 0:
            cps = text_len / duration
            cps_values.append(cps)
    
    # 読みやすさ分析
    short_segments = sum(1 for d in durations if d < 1.0)
    long_segments = sum(1 for d in durations if d > 10.0)
    high_cps = sum(1 for cps in cps_values if cps > 6.0)
    
    # 行数分析
    line_counts = [seg.text.count('\n') + 1 for seg in segments]
    long_lines = sum(1 for seg in segments for line in seg.text.split('\n') if len(line) > 15)
    
    analysis = {
        "basic_stats": {
            "total_segments": len(segments),
            "total_duration": round(total_duration, 1),
            "avg_duration": round(sum(durations) / len(durations), 2),
            "min_duration": round(min(durations), 2),
            "max_duration": round(max(durations), 2)
        },
        "readability": {
            "avg_cps": round(sum(cps_values) / len(cps_values), 2) if cps_values else 0,
            "max_cps": round(max(cps_values), 2) if cps_values else 0,
            "high_cps_count": high_cps,
            "avg_lines": round(sum(line_counts) / len(line_counts), 1),
            "long_lines": long_lines
        },
        "timing_issues": {
            "short_segments": short_segments,
            "long_segments": long_segments,
            "gaps": count_gaps(segments),
            "overlaps": count_overlaps(segments)
        },
        "content_analysis": {
            "total_chars": sum(len(seg.text.replace('\n', '').replace(' ', '')) for seg in segments),
            "punctuation_endings": count_punctuation_endings(segments)
        }
    }
    
    return analysis


def count_gaps(segments: List[SRTSegment]) -> int:
    """セグメント間の空白を数える"""
    gaps = 0
    for i in range(len(segments) - 1):
        if segments[i + 1].start > segments[i].end + 0.1:  # 0.1秒以上の空白
            gaps += 1
    return gaps


def count_overlaps(segments: List[SRTSegment]) -> int:
    """重複セグメントを数える"""
    overlaps = 0
    for i in range(len(segments) - 1):
        if segments[i].end > segments[i + 1].start:
            overlaps += 1
    return overlaps


def count_punctuation_endings(segments: List[SRTSegment]) -> int:
    """句読点で終わるセグメントを数える"""
    endings = "。！？…」』"
    count = 0
    for seg in segments:
        if seg.text.strip() and seg.text.strip()[-1] in endings:
            count += 1
    return count


def compare_with_script(segments: List[SRTSegment], script_path: str) -> Dict[str, Any]:
    """台本との比較分析"""
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # テキスト正規化
        def normalize_text(text):
            text = unicodedata.normalize("NFKC", text)
            text = re.sub(r'[「」『』\s\n]', '', text)  # 括弧と空白削除
            return text
        
        script_normalized = normalize_text(script_content)
        srt_text = ''.join(seg.text for seg in segments)
        srt_normalized = normalize_text(srt_text)
        
        # 類似度計算（簡易版）
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, script_normalized, srt_normalized).ratio()
        
        return {
            "script_chars": len(script_normalized),
            "srt_chars": len(srt_normalized),
            "similarity": round(similarity, 3),
            "coverage": round(len(srt_normalized) / len(script_normalized), 3) if script_normalized else 0
        }
    
    except Exception as e:
        return {"error": str(e)}


def generate_quality_report(srt_path: str, script_path: str = None) -> str:
    """品質レポート生成"""
    segments = load_srt(srt_path)
    analysis = analyze_srt_quality(segments)
    
    report = f"""🔍 SRT字幕品質レポート
{'='*50}

📊 基本統計:
- セグメント数: {analysis['basic_stats']['total_segments']}
- 総時間: {analysis['basic_stats']['total_duration']}秒
- 平均セグメント長: {analysis['basic_stats']['avg_duration']}秒
- 最短/最長: {analysis['basic_stats']['min_duration']}/{analysis['basic_stats']['max_duration']}秒

📖 読みやすさ:
- 平均CPS: {analysis['readability']['avg_cps']} (理想: 4-6)
- 最大CPS: {analysis['readability']['max_cps']}
- 高CPS(>6)セグメント: {analysis['readability']['high_cps_count']}個
- 平均行数: {analysis['readability']['avg_lines']}
- 長い行(>15字): {analysis['readability']['long_lines']}個

⏰ タイミング品質:
- 短すぎ(<1s): {analysis['timing_issues']['short_segments']}個
- 長すぎ(>10s): {analysis['timing_issues']['long_segments']}個
- 空白: {analysis['timing_issues']['gaps']}箇所
- 重複: {analysis['timing_issues']['overlaps']}箇所

📝 内容品質:
- 総文字数: {analysis['content_analysis']['total_chars']}
- 句読点終了: {analysis['content_analysis']['punctuation_endings']}個
"""
    
    # 台本比較があれば追加
    if script_path:
        comparison = compare_with_script(segments, script_path)
        if 'error' not in comparison:
            report += f"""
📋 台本比較:
- 台本文字数: {comparison['script_chars']}
- 字幕文字数: {comparison['srt_chars']}
- 類似度: {comparison['similarity']} (1.0が完全一致)
- カバー率: {comparison['coverage']} (1.0が完全カバー)
"""
    
    # 品質評価
    issues = []
    if analysis['readability']['avg_cps'] > 6:
        issues.append("⚠️ CPS高すぎ (読みにくい可能性)")
    if analysis['timing_issues']['short_segments'] > 5:
        issues.append("⚠️ 短いセグメントが多い")
    if analysis['readability']['long_lines'] > 10:
        issues.append("⚠️ 長い行が多い")
    
    if issues:
        report += f"\n🚨 検出された問題:\n" + "\n".join(f"- {issue}" for issue in issues)
    else:
        report += f"\n✅ 品質良好！"
    
    return report


if __name__ == "__main__":
    # テスト実行
    srt_file = "subs/final_production_direct.srt"
    script_file = "script_4_2.txt"
    
    report = generate_quality_report(srt_file, script_file)
    print(report)