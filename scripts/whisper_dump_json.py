#!/usr/bin/env python3
"""
Whisper解析スクリプト - 単語レベルタイムスタンプをJSON出力
"""
import json
import sys
from pathlib import Path

def main():
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print("❌ faster-whisper が必要です", file=sys.stderr)
        print("  pip install 'faster-whisper==1.0.3' numpy==1.26.4", file=sys.stderr)
        sys.exit(1)

    import argparse
    ap = argparse.ArgumentParser(description="Whisperで音声解析して単語タイムスタンプをJSON出力")
    ap.add_argument("--audio", required=True, help="入力音声ファイル")
    ap.add_argument("--out", required=True, help="出力JSONファイル")
    ap.add_argument("--model", default="large-v3", help="Whisperモデル")
    ap.add_argument("--device", default="auto", help="デバイス（auto/cpu/cuda）")
    ap.add_argument("--compute_type", default="int8", help="計算タイプ（CPU想定）")
    ap.add_argument("--language", default="ja", help="言語")
    args = ap.parse_args()

    print(f"🔄 Whisper解析中: {args.audio}")
    print(f"   モデル: {args.model} / デバイス: {args.device}")
    
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, info = model.transcribe(
        args.audio, 
        language=args.language, 
        word_timestamps=True, 
        vad_filter=True
    )
    
    res = {
        "language": info.language, 
        "duration": info.duration, 
        "segments": []
    }
    
    total_words = 0
    for seg in segments:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "start": w.start, 
                    "end": w.end, 
                    "text": w.word
                })
                total_words += 1
        
        res["segments"].append({
            "id": seg.id, 
            "start": seg.start, 
            "end": seg.end,
            "text": seg.text, 
            "words": words
        })
    
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"✅ whisper_dump_json: {args.out}")
    print(f"   音声長: {info.duration:.1f}秒")
    print(f"   セグメント数: {len(res['segments'])}")
    print(f"   単語数: {total_words}")

if __name__ == "__main__":
    main()