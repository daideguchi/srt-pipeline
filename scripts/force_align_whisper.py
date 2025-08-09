#!/usr/bin/env python3
"""
Whisper強制アライメント字幕生成ツール
音声ファイルと台本テキストから完璧に同期したSRT字幕を生成
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import warnings
warnings.filterwarnings("ignore")

try:
    from faster_whisper import WhisperModel
    import numpy as np
except ImportError:
    print("Error: 必要なライブラリがインストールされていません")
    print("pip install 'faster-whisper==1.0.3' numpy==1.26.4")
    exit(1)


class TextNormalizer:
    """テキスト正規化処理"""
    
    @staticmethod
    def normalize(text: str) -> str:
        """テキストの正規化（比較用）"""
        # Unicode正規化
        text = unicodedata.normalize('NFKC', text)
        
        # 装飾記号・空白除去
        text = re.sub(r'[「」『』（）［］【】〈〉《》〔〕｛｝]', '', text)
        text = re.sub(r'[！？!?。、，,．.・…—─―－ー]', '', text)
        text = re.sub(r'[\s\u3000]+', '', text)
        
        # 数字の正規化
        text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        return text.lower()
    
    @staticmethod
    def split_chunks(text: str) -> List[str]:
        """台本を句読点でチャンク分割"""
        # 句点で大きく分割
        sentences = re.split(r'[。！？!?\n]+', text)
        
        chunks = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # 長い文は読点でさらに分割
            if len(sentence) > 40:
                parts = re.split(r'[、，,]+', sentence)
                for part in parts:
                    if part.strip():
                        chunks.append(part.strip())
            else:
                chunks.append(sentence.strip())
        
        return chunks


class WordAligner:
    """単語レベルアライメント処理"""
    
    @staticmethod
    def levenshtein_alignment(ref: str, hyp: str) -> List[Tuple[int, int]]:
        """レーベンシュタイン距離によるアライメント"""
        m, n = len(ref), len(hyp)
        
        # DPテーブル
        dp = np.zeros((m + 1, n + 1), dtype=int)
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if ref[i-1] == hyp[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]) + 1
        
        # バックトラック
        alignment = []
        i, j = m, n
        while i > 0 and j > 0:
            if ref[i-1] == hyp[j-1]:
                alignment.append((i-1, j-1))
                i -= 1
                j -= 1
            elif dp[i-1][j] <= dp[i][j-1]:
                i -= 1
            else:
                j -= 1
        
        return list(reversed(alignment))
    
    @staticmethod
    def map_words_to_script(script_chunk: str, whisper_words: List[Dict], 
                           normalizer: TextNormalizer) -> List[Tuple[str, float, float]]:
        """Whisper単語を台本にマッピング"""
        
        # 正規化したテキストで比較
        script_norm = normalizer.normalize(script_chunk)
        whisper_text = ''.join([w.get('word', '').strip() for w in whisper_words])
        whisper_norm = normalizer.normalize(whisper_text)
        
        if not script_norm or not whisper_norm:
            return []
        
        # アライメント取得
        alignment = WordAligner.levenshtein_alignment(script_norm, whisper_norm)
        
        if not alignment:
            return []
        
        # 時間情報をマッピング
        result = []
        word_idx = 0
        char_count = 0
        
        for word in whisper_words:
            word_text = word.get('word', '').strip()
            if not word_text:
                continue
            
            word_len = len(normalizer.normalize(word_text))
            
            # この単語に対応する台本部分を特定
            script_start = char_count
            script_end = min(char_count + word_len, len(script_chunk))
            
            if script_end > script_start:
                result.append((
                    script_chunk[script_start:script_end],
                    word.get('start', 0.0),
                    word.get('end', 0.0)
                ))
            
            char_count += word_len
            word_idx += 1
        
        return result


class SRTFormatter:
    """SRT形式処理"""
    
    def __init__(self, max_line_len: int = 36, max_lines: int = 2,
                 min_gap_ms: int = 80, max_cps: int = 17):
        self.max_line_len = max_line_len
        self.max_lines = max_lines
        self.min_gap_ms = min_gap_ms / 1000.0
        self.max_cps = max_cps
    
    def format_time(self, seconds: float) -> str:
        """時間をSRT形式に変換"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')
    
    def split_lines(self, text: str) -> List[str]:
        """テキストを字幕行に分割"""
        if len(text) <= self.max_line_len:
            return [text]
        
        lines = []
        words = text.split()
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if len(test_line) <= self.max_line_len:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                
                if len(lines) >= self.max_lines - 1:
                    break
        
        if current_line and len(lines) < self.max_lines:
            lines.append(current_line)
        
        return lines[:self.max_lines]
    
    def adjust_timing(self, start: float, end: float, text: str) -> Tuple[float, float]:
        """CPS制限に基づくタイミング調整"""
        char_count = len(text.replace(' ', ''))
        min_duration = char_count / self.max_cps
        
        if end - start < min_duration:
            end = start + min_duration
        
        return start, end
    
    def create_subtitle(self, index: int, text: str, start: float, end: float) -> str:
        """字幕エントリ作成"""
        start, end = self.adjust_timing(start, end, text)
        lines = self.split_lines(text)
        
        return f"{index}\n{self.format_time(start)} --> {self.format_time(end)}\n" + \
               "\n".join(lines) + "\n"


class ForceAligner:
    """メイン処理クラス"""
    
    def __init__(self, model_size: str = "large-v3", device: str = "auto"):
        """初期化"""
        print(f"Whisperモデル読み込み中: {model_size}")
        
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="float16" if device == "cuda" else "int8"
        )
        self.normalizer = TextNormalizer()
        self.aligner = WordAligner()
    
    def transcribe_with_timestamps(self, audio_path: str) -> List[Dict]:
        """音声認識と単語タイムスタンプ取得"""
        print("音声認識実行中...")
        
        segments, info = self.model.transcribe(
            audio_path,
            language="ja",
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200
            )
        )
        
        all_words = []
        for segment in segments:
            if hasattr(segment, 'words'):
                for word in segment.words:
                    all_words.append({
                        'word': word.word,
                        'start': word.start,
                        'end': word.end
                    })
        
        print(f"認識完了: {len(all_words)}単語")
        return all_words
    
    def align_to_script(self, script_path: str, whisper_words: List[Dict]) -> List[Dict]:
        """台本との強制アライメント"""
        print("台本アライメント実行中...")
        
        # 台本読み込み
        with open(script_path, 'r', encoding='utf-8') as f:
            script = f.read()
        
        # チャンク分割
        chunks = self.normalizer.split_chunks(script)
        
        # 各チャンクをアライメント
        aligned_chunks = []
        word_idx = 0
        
        for chunk in chunks:
            if not chunk.strip():
                continue
            
            # このチャンクに対応するWhisper単語を探す
            chunk_words = []
            chunk_norm = self.normalizer.normalize(chunk)
            accumulated_norm = ""
            
            while word_idx < len(whisper_words) and len(accumulated_norm) < len(chunk_norm):
                word = whisper_words[word_idx]
                chunk_words.append(word)
                accumulated_norm += self.normalizer.normalize(word['word'])
                word_idx += 1
                
                # 十分マッチしたら次のチャンクへ
                if len(accumulated_norm) >= len(chunk_norm) * 0.8:
                    break
            
            if chunk_words:
                aligned_chunks.append({
                    'text': chunk,
                    'start': chunk_words[0]['start'],
                    'end': chunk_words[-1]['end'],
                    'words': chunk_words
                })
        
        print(f"アライメント完了: {len(aligned_chunks)}チャンク")
        return aligned_chunks
    
    def generate_srt(self, aligned_chunks: List[Dict], formatter: SRTFormatter) -> str:
        """SRTファイル生成"""
        print("SRT生成中...")
        
        srt_entries = []
        prev_end = 0.0
        
        for i, chunk in enumerate(aligned_chunks, 1):
            start = chunk['start']
            end = chunk['end']
            text = chunk['text']
            
            # 最小ギャップ確保
            if start < prev_end + formatter.min_gap_ms:
                start = prev_end + formatter.min_gap_ms
            
            if end <= start:
                end = start + 1.0
            
            srt_entries.append(
                formatter.create_subtitle(i, text, start, end)
            )
            prev_end = end
        
        return "\n".join(srt_entries)
    
    def process(self, audio_path: str, script_path: str, output_path: str,
                formatter: SRTFormatter) -> None:
        """メイン処理"""
        # 音声認識
        whisper_words = self.transcribe_with_timestamps(audio_path)
        
        # 台本アライメント
        aligned_chunks = self.align_to_script(script_path, whisper_words)
        
        # SRT生成
        srt_content = self.generate_srt(aligned_chunks, formatter)
        
        # ファイル保存
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        print(f"✅ 完了: {output_path}")
        print(f"   生成字幕数: {len(aligned_chunks)}")


def main():
    parser = argparse.ArgumentParser(
        description='Whisper強制アライメント字幕生成ツール'
    )
    
    parser.add_argument('--audio', required=True, help='音声ファイルパス')
    parser.add_argument('--script', required=True, help='台本テキストファイル')
    parser.add_argument('--out', required=True, help='出力SRTファイル')
    parser.add_argument('--model', default='large-v3', 
                       choices=['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3'],
                       help='Whisperモデルサイズ')
    parser.add_argument('--device', default='auto',
                       choices=['auto', 'cpu', 'cuda'],
                       help='実行デバイス')
    parser.add_argument('--max-line-len', type=int, default=36,
                       help='1行の最大文字数')
    parser.add_argument('--max-lines', type=int, default=2,
                       help='字幕の最大行数')
    parser.add_argument('--min-gap-ms', type=int, default=80,
                       help='字幕間の最小ギャップ（ミリ秒）')
    parser.add_argument('--max-cps', type=int, default=17,
                       help='最大CPS（文字/秒）')
    
    args = parser.parse_args()
    
    # パス確認
    if not Path(args.audio).exists():
        print(f"エラー: 音声ファイルが見つかりません: {args.audio}")
        return 1
    
    if not Path(args.script).exists():
        print(f"エラー: 台本ファイルが見つかりません: {args.script}")
        return 1
    
    # フォーマッター設定
    formatter = SRTFormatter(
        max_line_len=args.max_line_len,
        max_lines=args.max_lines,
        min_gap_ms=args.min_gap_ms,
        max_cps=args.max_cps
    )
    
    # アライナー実行
    aligner = ForceAligner(args.model, args.device)
    aligner.process(args.audio, args.script, args.out, formatter)
    
    return 0


if __name__ == "__main__":
    exit(main())