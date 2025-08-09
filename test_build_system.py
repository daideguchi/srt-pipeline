#!/usr/bin/env python3
"""
Build system動作確認テスト
"""

import os
import sys
import subprocess
from pathlib import Path

def test_file_exists(file_path, description):
    """ファイル存在確認"""
    if Path(file_path).exists():
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} が見つかりません")
        return False

def test_command_exists(command):
    """コマンド存在確認"""
    try:
        subprocess.run([command, "--help"], capture_output=True, check=True)
        print(f"✅ {command} コマンドが利用可能")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"❌ {command} コマンドが見つかりません")
        return False

def main():
    print("🧪 Build System 動作確認テスト")
    print("=" * 50)
    
    # ファイル存在確認
    files_to_check = [
        ("scripts/build_episode.sh", "メインスクリプト"),
        ("scripts/force_align_whisper.py", "Whisper強制アライン"),
        ("scripts/srt_clamp_to_audio.py", "SRT末尾クランプ"),
        ("audio/4_2.wav", "テスト用音声"),
        ("script_4_2.txt", "テスト用台本"),
        ("env/requirements.txt", "依存関係定義")
    ]
    
    all_files_ok = True
    for file_path, description in files_to_check:
        if not test_file_exists(file_path, description):
            all_files_ok = False
    
    print("\n🔧 必要コマンド確認")
    commands_to_check = ["ffmpeg", "python3"]
    all_commands_ok = True
    for command in commands_to_check:
        if not test_command_exists(command):
            all_commands_ok = False
    
    print("\n📁 ディレクトリ構造確認")
    directories = ["audio", "subs", "scripts", "reports", "env"]
    for directory in directories:
        test_file_exists(directory, f"{directory}ディレクトリ")
    
    print("\n🐍 Python環境確認")
    try:
        # venv環境での依存関係チェック
        result = subprocess.run([
            "bash", "-c", 
            "source venv/bin/activate && pip list | grep -E '(faster-whisper|ctranslate2|numpy)'"
        ], capture_output=True, text=True)
        
        if result.returncode == 0 and result.stdout.strip():
            print("✅ 必要なPythonパッケージが確認できます")
            print(result.stdout.strip())
        else:
            print("⚠️ 一部のPythonパッケージが不足している可能性があります")
            
    except Exception as e:
        print(f"❌ Python環境チェックでエラー: {e}")
    
    print("\n📊 テスト結果")
    if all_files_ok and all_commands_ok:
        print("✅ 基本的な動作環境は整っています")
        print("\n🚀 テスト実行コマンド例:")
        print("./scripts/build_episode.sh audio/4_2.wav script_4_2.txt")
        print("# 注意: 上記はwav→mp3の変換テスト用です")
        return 0
    else:
        print("❌ 一部の環境に問題があります。上記の問題を解決してください")
        return 1

if __name__ == "__main__":
    sys.exit(main())