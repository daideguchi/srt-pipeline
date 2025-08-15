#!/usr/bin/env python3
"""
UI統合用V9エンジンラッパー
StreamlitからV9字幕生成エンジンを呼び出すためのヘルパー
"""

import subprocess
import sys
import os
from pathlib import Path
import json
import tempfile
import shutil
from typing import Tuple, Optional, Callable
import logging

class SubtitleGeneratorUI:
    """UI統合用字幕生成エンジン"""
    
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            log_callback: ログメッセージを受け取るコールバック関数
        """
        self.log_callback = log_callback or print
        self.v9_script = Path("scripts/whisperx_subtitle_generator.py")
        
    def log(self, message: str):
        """ログメッセージを出力"""
        self.log_callback(message)
    
    def validate_files(self) -> bool:
        """必要なファイルの存在確認"""
        if not self.v9_script.exists():
            self.log(f"❌ V9エンジンが見つかりません: {self.v9_script}")
            return False
        
        # WhisperXデータの確認
        whisperx_dir = Path("subs_whisperx")
        if not whisperx_dir.exists():
            self.log("❌ WhisperXデータディレクトリが見つかりません")
            return False
        
        # 必要なWhisperXファイル確認
        required_files = [
            "whisperx_aligned.json",
            "whisperx_initial.json"
        ]
        
        for file in required_files:
            if not (whisperx_dir / file).exists():
                self.log(f"❌ 必要なWhisperXファイルが見つかりません: {file}")
                return False
        
        self.log("✅ 必要なファイルがすべて確認できました")
        return True
    
    def prepare_input_files(self, audio_file_data: bytes, audio_filename: str, 
                          script_content: str) -> Tuple[Path, Path]:
        """入力ファイルを準備"""
        
        # 音声ファイルを保存
        audio_dir = Path("audio")
        audio_dir.mkdir(exist_ok=True)
        
        audio_path = audio_dir / audio_filename
        with open(audio_path, "wb") as f:
            f.write(audio_file_data)
        self.log(f"✅ 音声ファイルを保存: {audio_path}")
        
        # 台本ファイルを保存
        script_path = Path("script_temp.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        self.log(f"✅ 台本ファイルを保存: {script_path}")
        
        return audio_path, script_path
    
    def run_v9_engine(self) -> Tuple[bool, str]:
        """V9エンジンを実行"""
        try:
            self.log("🚀 V9字幕生成エンジンを開始します...")
            
            # V9エンジン実行
            cmd = [sys.executable, str(self.v9_script), "--verbose"]
            self.log(f"実行コマンド: {' '.join(cmd)}")
            
            # 実行時間制限付きで実行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10分タイムアウト
                cwd=Path.cwd()
            )
            
            if result.returncode == 0:
                self.log("✅ V9エンジンが正常に完了しました")
                self.log(f"標準出力: {result.stdout}")
                return True, result.stdout
            else:
                self.log(f"❌ V9エンジンがエラーで終了しました (exit code: {result.returncode})")
                self.log(f"エラー出力: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            error_msg = "⏱️ V9エンジンがタイムアウトしました (10分)"
            self.log(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"❌ V9エンジン実行中にエラーが発生: {str(e)}"
            self.log(error_msg)
            return False, error_msg
    
    def check_output_files(self) -> Tuple[bool, Optional[Path], Optional[Path]]:
        """出力ファイルの確認"""
        srt_path = Path("subs/final_complete.srt")
        vtt_path = Path("subs/final_complete.vtt")
        
        if srt_path.exists() and vtt_path.exists():
            self.log("✅ 字幕ファイルが正常に生成されました")
            self.log(f"SRTファイル: {srt_path} ({srt_path.stat().st_size:,} bytes)")
            self.log(f"VTTファイル: {vtt_path} ({vtt_path.stat().st_size:,} bytes)")
            return True, srt_path, vtt_path
        else:
            self.log("❌ 字幕ファイルの生成に失敗しました")
            if not srt_path.exists():
                self.log(f"SRTファイルが見つかりません: {srt_path}")
            if not vtt_path.exists():
                self.log(f"VTTファイルが見つかりません: {vtt_path}")
            return False, None, None
    
    def generate_subtitles(self, audio_file_data: bytes, audio_filename: str, 
                          script_content: str) -> Tuple[bool, Optional[Path], Optional[Path], str]:
        """
        字幕生成の全プロセスを実行
        
        Returns:
            success: 成功/失敗
            srt_path: SRTファイルパス
            vtt_path: VTTファイルパス
            message: 結果メッセージ
        """
        
        try:
            # 1. ファイル検証
            if not self.validate_files():
                return False, None, None, "必要なファイルが不足しています"
            
            # 2. 入力ファイル準備
            self.log("📁 入力ファイルを準備中...")
            audio_path, script_path = self.prepare_input_files(
                audio_file_data, audio_filename, script_content
            )
            
            # 3. V9エンジン実行
            self.log("⚙️ V9字幕生成エンジンを実行中...")
            success, output = self.run_v9_engine()
            
            if not success:
                return False, None, None, f"V9エンジン実行に失敗: {output}"
            
            # 4. 出力ファイル確認
            self.log("📋 出力ファイルを確認中...")
            success, srt_path, vtt_path = self.check_output_files()
            
            if success:
                return True, srt_path, vtt_path, "字幕生成が正常に完了しました"
            else:
                return False, None, None, "字幕ファイルの生成に失敗しました"
                
        except Exception as e:
            error_msg = f"字幕生成中に予期しないエラーが発生: {str(e)}"
            self.log(f"❌ {error_msg}")
            return False, None, None, error_msg
        
        finally:
            # 一時ファイルのクリーンアップ
            temp_script = Path("script_temp.txt")
            if temp_script.exists():
                temp_script.unlink()
                self.log("🧹 一時ファイルをクリーンアップしました")

def test_ui_engine():
    """UI エンジンの動作テスト"""
    
    def test_log(message):
        print(f"[TEST] {message}")
    
    engine = SubtitleGeneratorUI(test_log)
    
    # ファイル検証テスト
    test_log("=== ファイル検証テスト ===")
    validation_result = engine.validate_files()
    test_log(f"検証結果: {validation_result}")
    
    return validation_result

if __name__ == "__main__":
    test_ui_engine()