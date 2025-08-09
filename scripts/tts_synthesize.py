#!/usr/bin/env python3
# scripts/tts_synthesize.py - Gemini TTS統合（補助機能）
"""
Gemini TTS を使った音声合成
用途:
1. 代替ナレーション（完全合成で納品）
2. ガイド用TTS（理想的な文字タイムライン作成の補助）
"""

import os
import argparse
import mimetypes
import struct
from pathlib import Path
from google import genai
from google.genai import types


def _parse_audio_mime(mime: str):
    """MIME文字列から音声パラメータを解析"""
    bits, rate = 16, 24000
    for part in (mime or "").split(";"):
        p = part.strip().lower()
        if p.startswith("rate="):
            try:
                rate = int(p.split("=", 1)[1])
            except:
                pass
        if "audio/l" in p:
            try:
                bits = int(p.split("l", 1)[1])
            except:
                pass
    return bits, rate


def _wav_wrap(raw: bytes, mime: str) -> bytes:
    """生音声データをWAVヘッダで包む"""
    bits, rate = _parse_audio_mime(mime)
    ch = 1
    bps = bits // 8
    block = ch * bps
    byte_rate = rate * block
    data_size = len(raw)
    
    # WAVヘッダ作成
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE", b"fmt ", 16, 1, ch,
        rate, byte_rate, block, bits, b"data", data_size
    )
    return hdr + raw


def main():
    ap = argparse.ArgumentParser(description="Gemini TTSで音声合成")
    ap.add_argument("--text", required=True, help="文字列 or テキストファイルパス")
    ap.add_argument("--out", required=True, help="出力WAVファイル")
    ap.add_argument("--voice", default="Puck", help="音声モデル (Puck, Zephyr)")
    ap.add_argument("--temperature", type=float, default=1.0, help="温度パラメータ")
    args = ap.parse_args()

    # テキスト読み込み（ファイルまたは直接指定）
    if Path(args.text).exists():
        text = Path(args.text).read_text(encoding="utf-8")
        print(f"📄 台本読み込み: {args.text}")
    else:
        text = args.text
        print(f"📝 直接テキスト使用: {text[:50]}...")

    # 出力ディレクトリ作成
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # API キー確認
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("❌ GEMINI_API_KEY が未設定です。環境変数を設定してください。")

    print(f"🎤 TTS開始: voice={args.voice}, temp={args.temperature}")

    # Gemini クライアント初期化
    client = genai.Client(api_key=api_key)
    
    # TTS設定
    genconf = types.GenerateContentConfig(
        temperature=args.temperature,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=args.voice)
            )
        ),
    )
    
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=text)])]

    # ストリーミングで音声受信
    bufs, mime = [], None
    try:
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-pro-preview-tts",
            contents=contents,
            config=genconf,
        ):
            if not getattr(chunk, "candidates", None):
                continue
            
            candidate = chunk.candidates[0]
            if not candidate.content.parts:
                continue
                
            part = candidate.content.parts[0]
            if not hasattr(part, "inline_data") or not part.inline_data:
                continue
                
            if part.inline_data.data:
                bufs.append(part.inline_data.data)
                mime = part.inline_data.mime_type or mime
                
    except Exception as e:
        raise SystemExit(f"❌ TTS生成エラー: {e}")

    if not bufs:
        raise SystemExit("❌ 音声データを受信できませんでした。")

    # 音声データ結合
    raw = b"".join(bufs)
    print(f"🔊 音声受信完了: {len(raw):,}バイト, MIME={mime}")

    # WAV形式で保存
    if mime and (mimetypes.guess_extension(mime) in [".wav", ".wave"]):
        # すでにWAV形式
        out.write_bytes(raw)
    else:
        # 非WAVならWAVヘッダで包む（L16/24kHz前提）
        wrapped = _wav_wrap(raw, mime or "audio/L16;rate=24000")
        out.write_bytes(wrapped)

    print(f"✅ TTS完了: {out} ({out.stat().st_size:,}バイト)")
    
    # 音声長確認（簡易）
    try:
        import subprocess
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
            "-of", "default=nk=1:nw=1", str(out)
        ], capture_output=True, text=True)
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            print(f"🕐 音声長: {duration:.2f}秒")
    except:
        pass


if __name__ == "__main__":
    main()