#!/usr/bin/env python3
"""
VADベース字幕整列ツール
Voice Activity Detectionと台本比率による字幕タイミング調整
"""

import argparse
import re
import json
import warnings
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import unicodedata
warnings.filterwarnings("ignore")

try:
    import numpy as np
    import librosa
    import soundfile as sf
    from scipy import signal
except ImportError:
    print("Error: 必要なライブラリがインストールされていません")
    print("pip install numpy librosa soundfile scipy")
    exit(1)


class VADProcessor:
    """Voice Activity Detection処理"""
    
    def __init__(self, frame_duration_ms: int = 30, 
                 energy_threshold: float = 0.02,
                 silence_duration_ms: int = 300):
        self.frame_duration_ms = frame_duration_ms
        self.energy_threshold = energy_threshold
        self.silence_duration_ms = silence_duration_ms
    
    def detect_speech_regions(self, audio_path: str) -> List[Tuple[float, float]]:
        """音声区間を検出"""
        print("音声ファイル読み込み中...")
        
        # 音声読み込み
        audio, sr = librosa.load(audio_path, sr=16000, mono=True)
        
        # フレーム設定
        frame_length = int(sr * self.frame_duration_ms / 1000)
        hop_length = frame_length // 2
        
        # エネルギー計算
        energy = librosa.feature.rms(y=audio, frame_length=frame_length, 
                                     hop_length=hop_length)[0]
        
        # 正規化
        if energy.max() > 0:
            energy = energy / energy.max()
        
        # 音声区間検出
        is_speech = energy > self.energy_threshold
        
        # スムージング（短い無音を除去）
        min_silence_frames = int(self.silence_duration_ms / (self.frame_duration_ms / 2))
        is_speech = self._smooth_detection(is_speech, min_silence_frames)
        
        # 区間抽出
        regions = []
        in_speech = False
        start_frame = 0
        
        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                start_frame = i
                in_speech = True
            elif not speech and in_speech:
                start_time = start_frame * hop_length / sr
                end_time = i * hop_length / sr
                regions.append((start_time, end_time))
                in_speech = False
        
        # 最後の区間
        if in_speech:
            start_time = start_frame * hop_length / sr
            end_time = len(is_speech) * hop_length / sr
            regions.append((start_time, end_time))
        
        print(f"検出された音声区間: {len(regions)}")
        return regions
    
    def _smooth_detection(self, is_speech: np.ndarray, min_gap: int) -> np.ndarray:
        """検出結果のスムージング"""
        result = is_speech.copy()
        
        # 短い無音を埋める
        for i in range(len(result)):
            if not result[i]:
                # 前後がともに音声なら埋める
                start = max(0, i - min_gap)
                end = min(len(result), i + min_gap + 1)
                
                if np.sum(result[start:i]) > 0 and np.sum(result[i+1:end]) > 0:
                    result[i] = True
        
        return result
    
    def get_audio_duration(self, audio_path: str) -> float:
        """音声ファイルの長さを取得"""
        info = sf.info(audio_path)
        return info.duration


class ScriptProcessor:
    """台本処理"""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """テキスト正規化"""
        # Unicode正規化
        text = unicodedata.normalize('NFKC', text)
        
        # 装飾記号は残すが、処理用に簡略化
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    
    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """文章を句読点で分割"""
        # 句点での分割
        sentences = re.split(r'([。！？!?\n]+)', text)
        
        result = []
        current = ""
        
        for i, part in enumerate(sentences):
            if re.match(r'^[。！？!?\n]+$', part):
                # 句読点は前の文に含める
                if current:
                    current += part
                    result.append(current.strip())
                    current = ""
            else:
                current = part
        
        # 最後の文
        if current.strip():
            result.append(current.strip())
        
        return [s for s in result if s]
    
    @staticmethod
    def calculate_text_weight(text: str) -> float:
        """テキストの重み（読み上げ時間の推定）"""
        # 基本は文字数
        weight = len(text)
        
        # 句読点による調整
        weight += len(re.findall(r'[。！？]', text)) * 10  # 句点は長めの間
        weight += len(re.findall(r'[、，]', text)) * 3     # 読点は短い間
        
        # 記号による調整
        weight += len(re.findall(r'[「『]', text)) * 2     # 開き括弧
        weight += len(re.findall(r'[」』]', text)) * 2     # 閉じ括弧
        
        return weight


class AlignmentEngine:
    """台本と音声の整列エンジン"""
    
    def __init__(self):
        self.script_processor = ScriptProcessor()
    
    def align_script_to_regions(self, script_path: str, 
                                speech_regions: List[Tuple[float, float]]) -> List[Dict]:
        """台本を音声区間に割り当て"""
        print("台本アライメント実行中...")
        
        # 台本読み込み
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
        
        # 文章分割
        sentences = self.script_processor.split_sentences(script)
        
        # 各文の重み計算
        weights = [self.script_processor.calculate_text_weight(s) for s in sentences]
        total_weight = sum(weights)
        
        # 総音声時間
        total_speech_time = sum(end - start for start, end in speech_regions)
        
        if total_speech_time == 0 or total_weight == 0:
            return []
        
        # 時間配分
        aligned = []
        current_region_idx = 0
        current_region_start, current_region_end = speech_regions[0] if speech_regions else (0, 0)
        current_region_used = 0.0
        
        for sentence, weight in zip(sentences, weights):
            # この文に必要な時間
            duration = (weight / total_weight) * total_speech_time
            
            # 現在の区間に収まるか確認
            region_remaining = current_region_end - (current_region_start + current_region_used)
            
            if duration <= region_remaining:
                # 現在の区間に収まる
                start = current_region_start + current_region_used
                end = start + duration
                current_region_used += duration
            else:
                # 次の区間へ
                if current_region_idx + 1 < len(speech_regions):
                    current_region_idx += 1
                    current_region_start, current_region_end = speech_regions[current_region_idx]
                    current_region_used = 0.0
                    
                    start = current_region_start
                    end = min(start + duration, current_region_end)
                    current_region_used = end - start
                else:
                    # 最後の区間を延長
                    start = current_region_start + current_region_used
                    end = start + duration
                    current_region_used += duration
            
            aligned.append({
                'text': sentence,
                'start': start,
                'end': end,
                'weight': weight
            })
        
        print(f"アライメント完了: {len(aligned)}文")
        return aligned
    
    def apply_fine_tuning(self, aligned: List[Dict], 
                          speech_regions: List[Tuple[float, float]]) -> List[Dict]:
        """細かい調整を適用"""
        result = []
        
        for i, item in enumerate(aligned):
            start = item['start']
            end = item['end']
            
            # 無音区間にかからないよう調整
            for reg_start, reg_end in speech_regions:
                if start < reg_start and end > reg_start:
                    # 区間をまたいでいる場合
                    if end - reg_start > reg_start - start:
                        # 後ろの区間に寄せる
                        start = reg_start
                    else:
                        # 前の区間に収める
                        end = reg_start - 0.05
            
            # 最小長確保
            if end - start < 0.5:
                end = start + 0.5
            
            result.append({
                'text': item['text'],
                'start': max(0, start),
                'end': end
            })
        
        return result


class SRTGenerator:
    """SRT形式生成"""
    
    def __init__(self, max_line_length: int = 36, max_lines: int = 2):
        self.max_line_length = max_line_length
        self.max_lines = max_lines
    
    def format_time(self, seconds: float) -> str:
        """SRT時間形式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')
    
    def split_text(self, text: str) -> List[str]:
        """テキストを行に分割"""
        if len(text) <= self.max_line_length:
            return [text]
        
        # 読点で分割を試みる
        parts = re.split(r'([、，,])', text)
        
        lines = []
        current_line = ""
        
        for part in parts:
            if len(current_line) + len(part) <= self.max_line_length:
                current_line += part
            else:
                if current_line:
                    lines.append(current_line)
                current_line = part
                
                if len(lines) >= self.max_lines - 1:
                    break
        
        if current_line and len(lines) < self.max_lines:
            lines.append(current_line)
        
        return lines[:self.max_lines]
    
    def generate(self, aligned_data: List[Dict]) -> str:
        """SRTファイル生成"""
        print("SRT生成中...")
        
        srt_entries = []
        
        for i, item in enumerate(aligned_data, 1):
            start = item['start']
            end = item['end']
            text = item['text']
            
            # 行分割
            lines = self.split_text(text)
            
            # SRTエントリ
            entry = f"{i}\n"
            entry += f"{self.format_time(start)} --> {self.format_time(end)}\n"
            entry += "\n".join(lines)
            entry += "\n"
            
            srt_entries.append(entry)
        
        return "\n".join(srt_entries)


class VADAligner:
    """メインクラス"""
    
    def __init__(self, energy_threshold: float = 0.02,
                 silence_duration_ms: int = 300):
        self.vad = VADProcessor(
            energy_threshold=energy_threshold,
            silence_duration_ms=silence_duration_ms
        )
        self.alignment_engine = AlignmentEngine()
        self.srt_generator = SRTGenerator()
    
    def process(self, audio_path: str, script_path: str, output_path: str) -> None:
        """メイン処理"""
        # 音声区間検出
        speech_regions = self.vad.detect_speech_regions(audio_path)
        
        if not speech_regions:
            print("警告: 音声区間が検出されませんでした")
            # 全体を1つの区間として扱う
            duration = self.vad.get_audio_duration(audio_path)
            speech_regions = [(0.0, duration)]
        
        # 台本アライメント
        aligned = self.alignment_engine.align_script_to_regions(
            script_path, speech_regions
        )
        
        # 微調整
        aligned = self.alignment_engine.apply_fine_tuning(
            aligned, speech_regions
        )
        
        # SRT生成
        srt_content = self.srt_generator.generate(aligned)
        
        # 保存
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        print(f"✅ 完了: {output_path}")
        print(f"   生成字幕数: {len(aligned)}")
        
        # デバッグ情報
        if aligned:
            print(f"   開始時間: {aligned[0]['start']:.2f}秒")
            print(f"   終了時間: {aligned[-1]['end']:.2f}秒")


def main():
    parser = argparse.ArgumentParser(
        description='VADベース字幕整列ツール'
    )
    
    parser.add_argument('--audio', required=True, help='音声ファイルパス')
    parser.add_argument('--script', required=True, help='台本テキストファイル')
    parser.add_argument('--out', required=True, help='出力SRTファイル')
    parser.add_argument('--energy-threshold', type=float, default=0.02,
                       help='音声検出のエネルギー閾値')
    parser.add_argument('--silence-ms', type=int, default=300,
                       help='無音判定の最小時間（ミリ秒）')
    
    args = parser.parse_args()
    
    # パス確認
    if not Path(args.audio).exists():
        print(f"エラー: 音声ファイルが見つかりません: {args.audio}")
        return 1
    
    if not Path(args.script).exists():
        print(f"エラー: 台本ファイルが見つかりません: {args.script}")
        return 1
    
    # 処理実行
    aligner = VADAligner(
        energy_threshold=args.energy_threshold,
        silence_duration_ms=args.silence_ms
    )
    
    aligner.process(args.audio, args.script, args.out)
    
    return 0


if __name__ == "__main__":
    exit(main())