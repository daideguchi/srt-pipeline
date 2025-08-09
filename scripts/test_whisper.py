#!/usr/bin/env python3
"""
Whisper機能テスト
"""

import os
import sys
sys.path.append('.')

try:
    from faster_whisper import WhisperModel
    print("✅ faster-whisper インポート成功")
    
    # モデル読み込みテスト
    print("📡 小さいモデルでテスト中...")
    model = WhisperModel("tiny", device="cpu")
    print("✅ Whisperモデル読み込み成功")
    
    print("🎯 基本機能動作確認完了！")
    print("💡 次のステップ: 音声ファイルと台本を用意してテスト実行")
    
except ImportError as e:
    print(f"❌ インポートエラー: {e}")
except Exception as e:
    print(f"❌ エラー: {e}")