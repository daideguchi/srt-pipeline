#!/usr/bin/env python3
"""
実運用向け字幕生成スクリプト
音声 + 台本 → SRT + VTT の完全自動化
"""
import argparse
import subprocess
import sys
from pathlib import Path
import re

def run_command(cmd, description=""):
    """コマンド実行とログ出力"""
    print(f"🔄 {description}")
    print(f"   $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error in {description}")
        print(f"   Command: {cmd}")
        print(f"   Error: {result.stderr}")
        return False, result.stderr
    
    if result.stdout.strip():
        print(f"   {result.stdout.strip()}")
    
    return True, result.stdout

def extract_date_from_path(path: str) -> str:
    """ファイルパスから日付を抽出"""
    # YYYY-MM-DD 形式を抽出
    match = re.search(r'(\d{4}-\d{2}-\d{2})', path)
    if match:
        return match.group(1)
    
    # YYYYMMDD 形式を抽出してハイフン付きに変換
    match = re.search(r'(\d{8})', path)
    if match:
        date_str = match.group(1)
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    
    # 見つからない場合は今日の日付
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d')

def main():
    parser = argparse.ArgumentParser(description='実運用向け字幕生成')
    parser.add_argument('--audio', required=True, help='音声ファイル（audio/内）')
    parser.add_argument('--script', required=True, help='台本ファイル')
    parser.add_argument('--date', help='日付（YYYY-MM-DD、省略時は自動推定）')
    parser.add_argument('--model', default='large-v3', help='Whisperモデル（default: large-v3）')
    parser.add_argument('--device', default='auto', help='デバイス（auto/cpu/cuda）')
    parser.add_argument('--offset-ms', type=int, default=20, help='末尾オフセット（ms）')
    args = parser.parse_args()
    
    # ファイル存在確認
    audio_path = Path(args.audio)
    script_path = Path(args.script)
    
    if not audio_path.exists():
        print(f"❌ Audio file not found: {audio_path}")
        return 1
    
    if not script_path.exists():
        print(f"❌ Script file not found: {script_path}")
        return 1
    
    # 日付推定
    date = args.date or extract_date_from_path(str(audio_path))
    print(f"📅 Episode date: {date}")
    
    # 出力ファイル名設定
    aligned_srt = f"subs/{date}_aligned.srt"
    final_srt = f"subs/{date}_final.srt"
    final_vtt = f"subs/{date}_final.vtt"
    report_base = f"reports/{date}"
    
    # 出力ディレクトリ作成
    Path("subs").mkdir(exist_ok=True)
    Path("reports").mkdir(exist_ok=True)
    
    print(f"🎯 Generating subtitles for {date}")
    print(f"   Audio: {audio_path}")
    print(f"   Script: {script_path}")
    print(f"   Model: {args.model} ({args.device})")
    print(f"   Output: {final_srt}, {final_vtt}")
    print("=" * 60)
    
    # Step 1: Whisper強制アライン
    cmd1 = f"""python3 scripts/force_align_whisper.py \\
        --audio {audio_path} \\
        --script {script_path} \\
        --out {aligned_srt} \\
        --model {args.model} --device {args.device}"""
    
    success, output = run_command(cmd1, "Whisper強制アライン")
    if not success:
        return 1
    
    # Step 2: 末尾クランプ
    cmd2 = f"""python3 scripts/pad_to_audio_end.py \\
        --in {aligned_srt} \\
        --audio {audio_path} \\
        --out {final_srt} \\
        --offset-ms {args.offset_ms}"""
    
    success, output = run_command(cmd2, f"末尾クランプ（-{args.offset_ms}ms）")
    if not success:
        return 1
    
    # Step 3: 同期検証
    cmd3 = f"python3 scripts/check_durations.py --audio {audio_path} --srt {final_srt}"
    success, output = run_command(cmd3, "音声同期検証")
    if not success:
        return 1
    
    # 差分解析
    if "diff" in output:
        diff_match = re.search(r'diff.*?=(-?\d+\.\d+)s', output)
        if diff_match:
            diff_value = float(diff_match.group(1))
            if abs(diff_value) > 0.05:
                print(f"⚠️ Warning: 同期差分が大きいです ({diff_value:.3f}s > ±0.05s)")
            else:
                print(f"✅ 同期精度良好: {diff_value:.3f}s")
    
    # Step 4: VTT変換
    cmd4 = f"python3 srt_to_vtt.py --in {final_srt} --out {final_vtt}"
    success, output = run_command(cmd4, "WebVTT変換")
    if not success:
        return 1
    
    # Step 5: 台本一致度レポート（任意）
    cmd5 = f"""python3 scripts/compare_srt_vs_script.py \\
        --srt {final_srt} \\
        --script {script_path} \\
        --out {report_base}"""
    
    print("🔄 台本一致度レポート生成（任意）")
    success, output = run_command(cmd5, "台本一致度レポート")
    
    # 最終確認
    final_srt_path = Path(final_srt)
    final_vtt_path = Path(final_vtt)
    
    print("\n" + "=" * 60)
    print("🎉 字幕生成完了")
    print(f"📄 SRT: {final_srt_path} ({final_srt_path.stat().st_size} bytes)")
    print(f"🎬 VTT: {final_vtt_path} ({final_vtt_path.stat().st_size} bytes)")
    
    # 字幕数カウント
    with final_srt_path.open('r', encoding='utf-8') as f:
        srt_content = f.read()
        subtitle_count = len(re.findall(r'^\d+$', srt_content, re.MULTILINE))
    
    print(f"🔢 字幕数: {subtitle_count}")
    print(f"📊 レポート: {report_base}_*.csv")
    print("\n✅ CapCut/Vrew/YouTubeに即インポート可能です")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())