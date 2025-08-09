#!/usr/bin/env python3
"""
SRT字幕生成メインスクリプト
音声ファイルと台本から高精度な字幕を生成
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# ローカルモジュール
try:
    from force_align_whisper import ForceAligner, SRTFormatter as WhisperFormatter
    from vad_align import VADAligner
    from srt_utils import parse_srt, SRTOptimizer, SRTValidator, export_to_json, write_srt
except ImportError as e:
    print(f"Error: モジュールの読み込みに失敗しました: {e}")
    print("必要なファイルが同じディレクトリにあることを確認してください")
    sys.exit(1)


class SRTGenerator:
    """統合SRT生成システム"""
    
    def __init__(self):
        self.supported_methods = ['whisper', 'vad', 'both']
    
    def generate_whisper(self, audio_path: str, script_path: str, 
                        model: str = "large-v3", device: str = "auto",
                        **kwargs) -> str:
        """Whisper強制アライメント"""
        print("🎯 Whisper強制アライメント実行中...")
        
        formatter = WhisperFormatter(
            max_line_len=kwargs.get('max_line_len', 36),
            max_lines=kwargs.get('max_lines', 2),
            min_gap_ms=kwargs.get('min_gap_ms', 80),
            max_cps=kwargs.get('max_cps', 17)
        )
        
        aligner = ForceAligner(model, device)
        temp_output = "temp_whisper.srt"
        
        aligner.process(audio_path, script_path, temp_output, formatter)
        
        return temp_output
    
    def generate_vad(self, audio_path: str, script_path: str, **kwargs) -> str:
        """VADベース整列"""
        print("🎯 VADベース整列実行中...")
        
        aligner = VADAligner(
            energy_threshold=kwargs.get('energy_threshold', 0.02),
            silence_duration_ms=kwargs.get('silence_ms', 300)
        )
        
        temp_output = "temp_vad.srt"
        aligner.process(audio_path, script_path, temp_output)
        
        return temp_output
    
    def combine_results(self, whisper_srt: str, vad_srt: str) -> str:
        """2つの結果を統合"""
        print("🔄 結果統合中...")
        
        # パース
        with open(whisper_srt, 'r', encoding='utf-8') as f:
            whisper_subs = parse_srt(f.read())
        
        with open(vad_srt, 'r', encoding='utf-8') as f:
            vad_subs = parse_srt(f.read())
        
        # Whisperの精度とVADのタイミングを統合
        combined = []
        
        for i, (w_sub, v_sub) in enumerate(zip(whisper_subs, vad_subs)):
            # Whisperのテキスト + VADのタイミングを重み付け
            start_time = (w_sub.start_time * 0.7) + (v_sub.start_time * 0.3)
            end_time = (w_sub.end_time * 0.7) + (v_sub.end_time * 0.3)
            
            combined_sub = type(w_sub)(
                index=i + 1,
                start_time=start_time,
                end_time=end_time,
                text=w_sub.text  # Whisperのテキストを優先
            )
            
            combined.append(combined_sub)
        
        # 残りの処理
        if len(whisper_subs) > len(vad_subs):
            for j in range(len(vad_subs), len(whisper_subs)):
                whisper_subs[j].index = j + 1
                combined.append(whisper_subs[j])
        elif len(vad_subs) > len(whisper_subs):
            for j in range(len(whisper_subs), len(vad_subs)):
                vad_subs[j].index = j + 1
                combined.append(vad_subs[j])
        
        # 一時ファイルに保存
        combined_output = "temp_combined.srt"
        write_srt(combined, combined_output)
        
        return combined_output
    
    def post_process(self, srt_path: str, **kwargs) -> str:
        """後処理・最適化"""
        print("✨ 後処理・最適化中...")
        
        with open(srt_path, 'r', encoding='utf-8') as f:
            subtitles = parse_srt(f.read())
        
        # 最適化
        optimizer = SRTOptimizer(
            max_cps=kwargs.get('max_cps', 17),
            max_line_length=kwargs.get('max_line_len', 36),
            max_lines=kwargs.get('max_lines', 2),
            min_gap_ms=kwargs.get('min_gap_ms', 80)
        )
        
        optimized = optimizer.optimize(subtitles)
        
        # 検証
        validator = SRTValidator()
        issues = validator.validate(optimized)
        
        if issues and kwargs.get('verbose', False):
            print("⚠️ 検証で発見された問題:")
            for issue in issues[:10]:  # 最初の10件のみ
                print(f"   {issue}")
        
        # 保存
        final_output = srt_path.replace('temp_', 'final_')
        write_srt(optimized, final_output)
        
        return final_output
    
    def process(self, audio_path: str, script_path: str, output_path: str,
                method: str = "whisper", **kwargs) -> None:
        """メイン処理"""
        print(f"🚀 SRT生成開始: {method}方式")
        print(f"   音声: {audio_path}")
        print(f"   台本: {script_path}")
        print(f"   出力: {output_path}")
        
        try:
            temp_files = []
            
            if method == "whisper":
                result_srt = self.generate_whisper(audio_path, script_path, **kwargs)
                temp_files.append(result_srt)
                
            elif method == "vad":
                result_srt = self.generate_vad(audio_path, script_path, **kwargs)
                temp_files.append(result_srt)
                
            elif method == "both":
                whisper_srt = self.generate_whisper(audio_path, script_path, **kwargs)
                vad_srt = self.generate_vad(audio_path, script_path, **kwargs)
                result_srt = self.combine_results(whisper_srt, vad_srt)
                temp_files.extend([whisper_srt, vad_srt, result_srt])
            
            else:
                raise ValueError(f"未知の方式: {method}")
            
            # 後処理
            final_srt = self.post_process(result_srt, **kwargs)
            temp_files.append(final_srt)
            
            # 最終ファイルをリネーム
            Path(final_srt).rename(output_path)
            
            # 一時ファイル削除
            if not kwargs.get('keep_temp', False):
                for temp_file in temp_files:
                    if Path(temp_file).exists():
                        Path(temp_file).unlink()
            
            # 統計情報
            with open(output_path, 'r', encoding='utf-8') as f:
                final_subs = parse_srt(f.read())
            
            print(f"\n✅ 生成完了!")
            print(f"   字幕数: {len(final_subs)}")
            if final_subs:
                print(f"   開始: {final_subs[0].start_time:.2f}秒")
                print(f"   終了: {final_subs[-1].end_time:.2f}秒")
            
            # JSON出力
            if kwargs.get('export_json', False):
                json_path = output_path.replace('.srt', '.json')
                export_to_json(final_subs, json_path)
                print(f"   JSON: {json_path}")
            
        except Exception as e:
            print(f"❌ エラー: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description='SRT字幕生成ツール - Whisper強制アライメント & VAD整列',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # Whisper強制アライメント（推奨）
  python srtgen.py --audio video.wav --script script.txt --out subtitle.srt

  # VADベース整列
  python srtgen.py --audio video.wav --script script.txt --out subtitle.srt --method vad

  # 両方式を統合（最高精度）
  python srtgen.py --audio video.wav --script script.txt --out subtitle.srt --method both

  # 高品質設定
  python srtgen.py --audio video.wav --script script.txt --out subtitle.srt \\
    --model large-v3 --device cuda --max-cps 15 --export-json
        """
    )
    
    # 必須引数
    parser.add_argument('--audio', required=True, 
                       help='音声ファイルパス (.wav, .mp3, .mp4など)')
    parser.add_argument('--script', required=True,
                       help='台本テキストファイル')
    parser.add_argument('--out', required=True,
                       help='出力SRTファイル')
    
    # 処理方式
    parser.add_argument('--method', default='whisper',
                       choices=['whisper', 'vad', 'both'],
                       help='処理方式 (default: whisper)')
    
    # Whisper設定
    parser.add_argument('--model', default='large-v3',
                       choices=['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3'],
                       help='Whisperモデル (default: large-v3)')
    parser.add_argument('--device', default='auto',
                       choices=['auto', 'cpu', 'cuda'],
                       help='実行デバイス (default: auto)')
    
    # VAD設定
    parser.add_argument('--energy-threshold', type=float, default=0.02,
                       help='VAD音声検出閾値 (default: 0.02)')
    parser.add_argument('--silence-ms', type=int, default=300,
                       help='VAD無音判定時間(ms) (default: 300)')
    
    # 字幕フォーマット
    parser.add_argument('--max-line-len', type=int, default=36,
                       help='1行の最大文字数 (default: 36)')
    parser.add_argument('--max-lines', type=int, default=2,
                       help='字幕の最大行数 (default: 2)')
    parser.add_argument('--min-gap-ms', type=int, default=80,
                       help='字幕間ギャップ(ms) (default: 80)')
    parser.add_argument('--max-cps', type=int, default=17,
                       help='最大CPS (default: 17)')
    
    # オプション
    parser.add_argument('--export-json', action='store_true',
                       help='JSON形式でもエクスポート')
    parser.add_argument('--keep-temp', action='store_true',
                       help='一時ファイルを保持')
    parser.add_argument('--verbose', action='store_true',
                       help='詳細出力')
    
    args = parser.parse_args()
    
    # ファイル存在確認
    if not Path(args.audio).exists():
        print(f"❌ 音声ファイルが見つかりません: {args.audio}")
        return 1
    
    if not Path(args.script).exists():
        print(f"❌ 台本ファイルが見つかりません: {args.script}")
        return 1
    
    # 出力ディレクトリ作成
    output_dir = Path(args.out).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 実行
    generator = SRTGenerator()
    
    try:
        generator.process(
            args.audio, args.script, args.out,
            method=args.method,
            model=args.model,
            device=args.device,
            energy_threshold=args.energy_threshold,
            silence_ms=args.silence_ms,
            max_line_len=args.max_line_len,
            max_lines=args.max_lines,
            min_gap_ms=args.min_gap_ms,
            max_cps=args.max_cps,
            export_json=args.export_json,
            keep_temp=args.keep_temp,
            verbose=args.verbose
        )
        
        print(f"\n🎉 字幕ファイル生成完了: {args.out}")
        return 0
        
    except KeyboardInterrupt:
        print("\n⏹️ 処理が中断されました")
        return 1
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())