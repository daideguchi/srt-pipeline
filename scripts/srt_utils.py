#!/usr/bin/env python3
"""
SRT字幕ユーティリティ
SRTファイルの処理、変換、最適化機能
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import timedelta


@dataclass
class Subtitle:
    """字幕データクラス"""
    index: int
    start_time: float
    end_time: float
    text: str
    
    def duration(self) -> float:
        """字幕の表示時間"""
        return self.end_time - self.start_time
    
    def cps(self) -> float:
        """Characters Per Second"""
        char_count = len(self.text.replace(' ', '').replace('\n', ''))
        if self.duration() == 0:
            return float('inf')
        return char_count / self.duration()
    
    def to_srt(self) -> str:
        """SRT形式に変換"""
        return f"{self.index}\n{format_srt_time(self.start_time)} --> {format_srt_time(self.end_time)}\n{self.text}\n"


def parse_srt_time(time_str: str) -> float:
    """SRT時間形式をfloatに変換"""
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    
    if len(parts) != 3:
        raise ValueError(f"Invalid SRT time format: {time_str}")
    
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    
    return hours * 3600 + minutes * 60 + seconds


def format_srt_time(seconds: float) -> str:
    """floatをSRT時間形式に変換"""
    td = timedelta(seconds=seconds)
    total_seconds = td.total_seconds()
    
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = total_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')


def parse_srt(content: str) -> List[Subtitle]:
    """SRTファイルをパース"""
    subtitles = []
    
    # エントリーごとに分割
    entries = re.split(r'\n\s*\n', content.strip())
    
    for entry in entries:
        if not entry.strip():
            continue
        
        lines = entry.strip().split('\n')
        
        if len(lines) < 3:
            continue
        
        try:
            # インデックス
            index = int(lines[0])
            
            # タイムコード
            time_match = re.match(
                r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
                lines[1]
            )
            
            if not time_match:
                continue
            
            start_time = parse_srt_time(time_match.group(1))
            end_time = parse_srt_time(time_match.group(2))
            
            # テキスト（複数行対応）
            text = '\n'.join(lines[2:])
            
            subtitles.append(Subtitle(index, start_time, end_time, text))
            
        except (ValueError, IndexError):
            continue
    
    return subtitles


def write_srt(subtitles: List[Subtitle], output_path: str) -> None:
    """字幕リストをSRTファイルに保存"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for subtitle in subtitles:
            f.write(subtitle.to_srt())
            f.write('\n')


class SRTOptimizer:
    """SRT最適化クラス"""
    
    def __init__(self, max_cps: float = 17, max_line_length: int = 36,
                 max_lines: int = 2, min_gap_ms: int = 80):
        self.max_cps = max_cps
        self.max_line_length = max_line_length
        self.max_lines = max_lines
        self.min_gap_seconds = min_gap_ms / 1000.0
    
    def optimize(self, subtitles: List[Subtitle]) -> List[Subtitle]:
        """字幕を最適化"""
        optimized = []
        
        for i, sub in enumerate(subtitles):
            # CPS調整
            sub = self._adjust_cps(sub)
            
            # テキスト分割
            sub.text = self._optimize_text_layout(sub.text)
            
            # ギャップ調整
            if i > 0:
                prev_sub = optimized[-1]
                if sub.start_time < prev_sub.end_time + self.min_gap_seconds:
                    sub.start_time = prev_sub.end_time + self.min_gap_seconds
            
            optimized.append(sub)
        
        return optimized
    
    def _adjust_cps(self, subtitle: Subtitle) -> Subtitle:
        """CPS制限に基づく時間調整"""
        current_cps = subtitle.cps()
        
        if current_cps > self.max_cps:
            # 表示時間を延長
            char_count = len(subtitle.text.replace(' ', '').replace('\n', ''))
            required_duration = char_count / self.max_cps
            subtitle.end_time = subtitle.start_time + required_duration
        
        return subtitle
    
    def _optimize_text_layout(self, text: str) -> str:
        """テキストレイアウトの最適化"""
        # 既に改行がある場合はそのまま
        if '\n' in text:
            lines = text.split('\n')
            return '\n'.join(lines[:self.max_lines])
        
        # 長さチェック
        if len(text) <= self.max_line_length:
            return text
        
        # 自動改行
        return self._auto_split_text(text)
    
    def _auto_split_text(self, text: str) -> str:
        """テキストを自動で改行"""
        # 句読点での分割を試みる
        split_points = []
        
        for match in re.finditer(r'[、。，,！？!?]', text):
            split_points.append(match.end())
        
        if not split_points:
            # 句読点がない場合は中央付近で分割
            mid = len(text) // 2
            
            # 最も近い空白を探す
            for i in range(mid, len(text)):
                if text[i] == ' ':
                    split_points = [i + 1]
                    break
            
            if not split_points:
                for i in range(mid, 0, -1):
                    if text[i] == ' ':
                        split_points = [i + 1]
                        break
            
            if not split_points:
                split_points = [mid]
        
        # 最適な分割点を選択
        best_point = None
        best_diff = float('inf')
        
        for point in split_points:
            line1_len = point
            line2_len = len(text) - point
            
            if line1_len <= self.max_line_length and line2_len <= self.max_line_length:
                diff = abs(line1_len - line2_len)
                if diff < best_diff:
                    best_diff = diff
                    best_point = point
        
        if best_point:
            return text[:best_point].rstrip() + '\n' + text[best_point:].lstrip()
        
        # 分割できない場合は強制的に分割
        return text[:self.max_line_length] + '\n' + text[self.max_line_length:]


class SRTMerger:
    """複数のSRTを結合"""
    
    @staticmethod
    def merge(srt_files: List[str], output_path: str) -> None:
        """複数のSRTファイルを結合"""
        all_subtitles = []
        
        for srt_file in srt_files:
            with open(srt_file, 'r', encoding='utf-8') as f:
                subtitles = parse_srt(f.read())
                all_subtitles.extend(subtitles)
        
        # 時間順にソート
        all_subtitles.sort(key=lambda x: x.start_time)
        
        # インデックス再割り当て
        for i, sub in enumerate(all_subtitles, 1):
            sub.index = i
        
        write_srt(all_subtitles, output_path)


class SRTShifter:
    """字幕のタイミング調整"""
    
    @staticmethod
    def shift(subtitles: List[Subtitle], offset: float) -> List[Subtitle]:
        """全字幕を指定秒数シフト"""
        shifted = []
        
        for sub in subtitles:
            new_sub = Subtitle(
                index=sub.index,
                start_time=max(0, sub.start_time + offset),
                end_time=max(0, sub.end_time + offset),
                text=sub.text
            )
            shifted.append(new_sub)
        
        return shifted
    
    @staticmethod
    def stretch(subtitles: List[Subtitle], factor: float) -> List[Subtitle]:
        """字幕の時間を伸縮"""
        stretched = []
        
        for sub in subtitles:
            new_sub = Subtitle(
                index=sub.index,
                start_time=sub.start_time * factor,
                end_time=sub.end_time * factor,
                text=sub.text
            )
            stretched.append(new_sub)
        
        return stretched


class SRTValidator:
    """SRT検証"""
    
    @staticmethod
    def validate(subtitles: List[Subtitle]) -> List[str]:
        """字幕の問題をチェック"""
        issues = []
        
        for i, sub in enumerate(subtitles):
            # 時間の妥当性
            if sub.start_time >= sub.end_time:
                issues.append(f"字幕 {sub.index}: 開始時間が終了時間より後")
            
            # 表示時間
            duration = sub.duration()
            if duration < 0.5:
                issues.append(f"字幕 {sub.index}: 表示時間が短すぎる ({duration:.2f}秒)")
            elif duration > 7.0:
                issues.append(f"字幕 {sub.index}: 表示時間が長すぎる ({duration:.2f}秒)")
            
            # CPS
            cps = sub.cps()
            if cps > 20:
                issues.append(f"字幕 {sub.index}: CPSが高すぎる ({cps:.1f})")
            
            # オーバーラップ
            if i > 0:
                prev_sub = subtitles[i-1]
                if sub.start_time < prev_sub.end_time:
                    issues.append(f"字幕 {sub.index}: 前の字幕とオーバーラップ")
            
            # テキスト長
            lines = sub.text.split('\n')
            if len(lines) > 2:
                issues.append(f"字幕 {sub.index}: 3行以上 ({len(lines)}行)")
            
            for line_num, line in enumerate(lines, 1):
                if len(line) > 42:
                    issues.append(f"字幕 {sub.index} 行{line_num}: 文字数オーバー ({len(line)}文字)")
        
        return issues


def export_to_json(subtitles: List[Subtitle], output_path: str) -> None:
    """字幕をJSON形式でエクスポート"""
    data = []
    
    for sub in subtitles:
        data.append({
            'index': sub.index,
            'start': sub.start_time,
            'end': sub.end_time,
            'text': sub.text,
            'duration': sub.duration(),
            'cps': sub.cps()
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def import_from_json(json_path: str) -> List[Subtitle]:
    """JSONから字幕をインポート"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    subtitles = []
    
    for item in data:
        subtitles.append(Subtitle(
            index=item['index'],
            start_time=item['start'],
            end_time=item['end'],
            text=item['text']
        ))
    
    return subtitles


if __name__ == "__main__":
    # テスト用
    print("SRT Utilities Library")
    print("Use: import srt_utils")
    print("\nAvailable classes:")
    print("  - Subtitle: 字幕データクラス")
    print("  - SRTOptimizer: 字幕最適化")
    print("  - SRTMerger: 字幕結合")
    print("  - SRTShifter: タイミング調整")
    print("  - SRTValidator: 検証")
    print("\nFunctions:")
    print("  - parse_srt(): SRTパース")
    print("  - write_srt(): SRT保存")
    print("  - export_to_json(): JSON出力")
    print("  - import_from_json(): JSONインポート")