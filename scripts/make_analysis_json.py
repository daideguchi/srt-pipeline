#!/usr/bin/env python3
# scripts/make_analysis_json.py
# 入力メディアから「解析JSON」を生成：
#  - audio_transcript: { text, segments[] }（例に近い構造）
#  - silences/talkspurts（ffmpeg silencedetect）+ valley
# 優先: whisper-cli（whisper-cpp）→ 無ければ openai-whisper に自動フォールバック

import argparse, json, os, re, subprocess, sys, time, datetime
from pathlib import Path

def run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err

def which(cmd):
    rc, out, err = run(["bash","-lc",f"command -v {cmd} || true"])
    return out.strip() if out.strip() else None

def ffprobe_duration(media):
    rc,out,err = run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nk=1:nw=1",str(media)])
    return float(out.strip()) if rc==0 and out.strip() else None

def ffprobe_frame_count(media):
    rc,out,err = run([
        "ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=nb_frames","-of","default=nk=1:nw=1",str(media)
    ])
    v = out.strip()
    try:
        return int(v) if v and v.isdigit() else None
    except:
        return None

def detect_silences(media, silence_db=-35, min_silence_ms=220):
    cmd = [
        "ffmpeg","-hide_banner","-nostats","-i",str(media),
        "-af",f"silencedetect=noise={silence_db}dB:duration={min_silence_ms/1000.0}",
        "-f","null","-"
    ]
    rc,out,err = run(cmd)
    events=[]
    for line in err.splitlines():  # stderrに出る
        m1 = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m1: events.append(("start", float(m1.group(1))))
        m2 = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if m2: events.append(("end", float(m2.group(1)), float(m2.group(2))))
    silences=[]; talkspurts=[]; i=0; last_end=0.0
    while i < len(events):
        if events[i][0]=="start" and i+1<len(events) and events[i+1][0]=="end":
            st = events[i][1]; ed = events[i+1][1]; dur = events[i+1][2]
            valley = (st+ed)/2.0
            silences.append({"start":st,"end":ed,"duration":dur,"valley":valley})
            if st > last_end:
                talkspurts.append({"start":last_end,"end":st,"duration":st-last_end})
            last_end = ed; i += 2
        else:
            i += 1
    return silences, talkspurts

def transcribe_with_whisper_cli(media, model_path=None, language="ja"):
    if not which("whisper-cli"):
        return None
    if model_path is None:
        default = Path("models/ggml-medium.bin")
        model_path = str(default) if default.exists() else None
    if model_path is None:
        return None
    tmp_base = Path("reports/whisper_cli_tmp")
    tmp_base.parent.mkdir(parents=True, exist_ok=True)
    out_base = str(tmp_base)
    rc,out,err = run([
        "whisper-cli","--model", model_path,"--language", language,
        "--output-json-full","--output-file", out_base, str(media)
    ])
    jf = Path(out_base + ".json")
    if not jf.exists():
        return None
    data = json.loads(jf.read_text(encoding="utf-8", errors="replace"))
    segs_raw = data.get("transcription") or []
    segments=[]; full_text=[]
    for i,seg in enumerate(segs_raw):
        t0 = seg.get("offsets",{}).get("from",0)/1000.0
        t1 = seg.get("offsets",{}).get("to",0)/1000.0
        txt = seg.get("text","")
        segments.append({
            "id": i, "seek": 0, "start": t0, "end": t1, "text": txt,
            "avg_logprob": None, "compression_ratio": None, "no_speech_prob": None
        })
        if txt: full_text.append(txt)
    return {"text": "".join(full_text), "segments": segments}

def transcribe_with_openai_whisper(media, model="medium", language="ja"):
    try:
        import whisper
    except ImportError:
        return None
    m = whisper.load_model(model)
    res = m.transcribe(str(media), language=language, verbose=False)
    segments=[]; full=[]
    for s in res.get("segments", []):
        segments.append({
            "id": s.get("id"), "seek": s.get("seek"),
            "start": s.get("start"), "end": s.get("end"),
            "text": s.get("text",""),
            "tokens": s.get("tokens"),
            "temperature": s.get("temperature"),
            "avg_logprob": s.get("avg_logprob"),
            "compression_ratio": s.get("compression_ratio"),
            "no_speech_prob": s.get("no_speech_prob"),
        })
        if s.get("text"): full.append(s["text"])
    return {"text": "".join(full), "segments": segments}

def main():
    ap = argparse.ArgumentParser(description="解析JSON生成（transcript + silences）")
    ap.add_argument("--in", dest="inp", required=True, help="音声/動画ファイルパス")
    ap.add_argument("--out", required=True, help="出力JSONパス")
    ap.add_argument("--engine", choices=["auto","whisper-cli","openai-whisper"], default="auto")
    ap.add_argument("--cli-model", help="whisper-cli のモデル（例: models/ggml-medium.bin）")
    ap.add_argument("--language", default="ja")
    ap.add_argument("--silence-db", type=int, default=-35)
    ap.add_argument("--min-silence-ms", type=int, default=220)
    args = ap.parse_args()

    media = Path(args.inp); start = time.time()
    duration = ffprobe_duration(media)
    frame_count = ffprobe_frame_count(media)
    try:
        silences, talkspurts = detect_silences(media, args.silence_db, args.min_silence_ms)
    except Exception:
        silences, talkspurts = [], []

    asr = None
    if args.engine in ("auto","whisper-cli"):
        asr = transcribe_with_whisper_cli(media, model_path=args.cli_model, language=args.language)
    if asr is None and args.engine in ("auto","openai-whisper"):
        asr = transcribe_with_openai_whisper(media, model="medium", language=args.language)
    if asr is None:
        print("❌ ASR失敗：whisper-cli か openai-whisper を用意してください", file=sys.stderr)
        sys.exit(2)

    out = {
        "video_path": str(media),
        "analysis_timestamp": datetime.datetime.now().isoformat(),
        "processing_time": time.time()-start,
        "frame_count": frame_count,
        "audio_transcript": {
            "text": asr.get("text",""),
            "segments": asr.get("segments", []),
            "duration": duration
        },
        "silences": silences,
        "talkspurts": talkspurts,
        "params": {
            "silence_db": args.silence_db,
            "min_silence_ms": args.min_silence_ms,
            "engine": ("whisper-cli" if which("whisper-cli") and asr else "openai-whisper"),
            "language": args.language
        }
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ wrote {args.out}")

if __name__ == "__main__":
    main()