#!/usr/bin/env python3
"""
SRT to WebVTT converter for production use
実運用向けSRT→VTT変換ツール
"""
import argparse
import re
from pathlib import Path

def srt_to_vtt(srt_content: str) -> str:
    """SRT形式をWebVTT形式に変換"""
    # SRTのタイムコード形式 (HH:MM:SS,mmm) をVTT形式 (HH:MM:SS.mmm) に変換
    vtt_content = re.sub(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', r'\1:\2:\3.\4', srt_content)
    
    # WebVTTヘッダーを追加
    vtt_content = "WEBVTT\n\n" + vtt_content
    
    return vtt_content

def main():
    parser = argparse.ArgumentParser(description='SRT to WebVTT converter')
    parser.add_argument('--in', dest='input_file', required=True, help='Input SRT file')
    parser.add_argument('--out', dest='output_file', required=True, help='Output VTT file')
    args = parser.parse_args()
    
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return 1
    
    # SRTファイルを読み込み
    with input_path.open('r', encoding='utf-8') as f:
        srt_content = f.read()
    
    # VTTに変換
    vtt_content = srt_to_vtt(srt_content)
    
    # 出力ディレクトリを作成
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # VTTファイルを保存
    with output_path.open('w', encoding='utf-8') as f:
        f.write(vtt_content)
    
    print(f"✅ Converted: {input_path} → {output_path}")
    return 0

if __name__ == '__main__':
    exit(main())