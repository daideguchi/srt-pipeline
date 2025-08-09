#!/usr/bin/env python3
"""
smart_subs.py - 4ソース統合で高品質な日本語SRTを生成
前提: 既存JSONを必ず使用（再解析禁止）
- audio_json: 無音valley含む既存解析（ffmpeg silencedetect由来の整形JSON）
- whisper_json: whisper-cpp形式の既存ASR JSON
- capcut_srt: CapCut/Vrewの粗いSRT（時間枠は有用）
- script: 台本テキスト（内容の正）
"""

import json, re, unicodedata
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from srt_rules import norm_text, enforce_layout, MAX_LINE_CHARS_DEFAULT, MAX_LINES_DEFAULT, MAX_CPS_DEFAULT

MIN_DUR = 1.2
MIN_GAP = 0.12
VALLEY_SNAP_MS = 150  # ±150ms
ANCHOR_PATTERNS = [
    "最後までご視聴いただき、本当にありがとうございました",
    "最後までご視聴いただき本当にありがとうございました",
    "ご視聴ありがとうございました",
]

def fmt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def parse_srt(path: str) -> List[Dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues = []
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        if re.fullmatch(r"\d+", lines[0]):
            lines = lines[1:]
        if not lines:
            continue
        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[0])
        if not m:
            continue

        def tosec(ts: str) -> float:
            h, m, sms = ts.split(":")
            s, ms = sms.split(",")
            return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

        st, ed = tosec(m.group(1)), tosec(m.group(2))
        txt = "\n".join(lines[1:])
        cues.append({"start": st, "end": ed, "text": txt})
    return cues

def format_srt(cues: List[Dict[str, Any]]) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{fmt_time(c['start'])} --> {fmt_time(c['end'])}")
        out.append(c.get("text", "").rstrip())
        out.append("")
    return "\n".join(out).strip() + "\n"

def format_vtt(cues: List[Dict[str, Any]]) -> str:
    lines = ["WEBVTT", ""]
    for c in cues:
        st = fmt_time(c["start"]).replace(",", ".")
        ed = fmt_time(c["end"]).replace(",", ".")
        lines.append(f"{st} --> {ed}")
        lines.append(c.get("text","").rstrip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"

def load_whisper_chars(wh_json: str):
    """
    whisper-cpp JSONに対応:
    {
      "transcription": [
        {
          "text": "...",
          "offsets": {"from": ms, "to": ms},
          "tokens": [{"text":"…", "offsets":{"from":ms,"to":ms}}, ...]
        }, ...
      ]
    }
    戻り値: (asr_text, char_times, est_audio_dur)
    """
    try:
        data = json.loads(Path(wh_json).read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        data = json.loads(Path(wh_json).read_text(encoding="utf-8", errors="replace"))

    asr_text = ""
    char_times: List[float] = []
    duration = None

    if "transcription" in data:
        trs = data["transcription"]
        for seg in trs:
            seg_start = seg.get("offsets", {}).get("from", 0) / 1000.0
            seg_end   = seg.get("offsets", {}).get("to", 0) / 1000.0
            seg_text  = norm_text(seg.get("text",""))
            tokens = seg.get("tokens") or []
            if tokens:
                for tk in tokens:
                    t_text = norm_text(tk.get("text",""))
                    if not t_text:
                        continue
                    t_start = tk.get("offsets", {}).get("from", seg_start*1000)/1000.0
                    t_end   = tk.get("offsets", {}).get("to", seg_end*1000)/1000.0
                    dur = max(0.001, t_end - t_start)
                    step = dur / max(1, len(t_text))
                    for i, ch in enumerate(t_text):
                        asr_text += ch
                        char_times.append(t_start + step * i)
            else:
                if seg_text:
                    dur = max(0.001, seg_end - seg_start)
                    step = dur / max(1, len(seg_text))
                    for i, ch in enumerate(seg_text):
                        asr_text += ch
                        char_times.append(seg_start + step * i)
        if trs:
            duration = trs[-1].get("offsets", {}).get("to", 0)/1000.0

    elif "segments" in data:  # 後方互換（faster-whisper）
        for seg in data["segments"]:
            for w in seg.get("words", []) or []:
                word = norm_text(w.get("text",""))
                if not word:
                    continue
                wst, wed = w.get("start", 0.0), w.get("end", 0.0)
                dur = max(0.001, wed - wst)
                step = dur / max(1, len(word))
                for i, ch in enumerate(word):
                    asr_text += ch
                    char_times.append(wst + step * i)
        duration = data.get("duration")

    return asr_text, char_times, duration

def load_valleys(audio_json: str):
    """
    既存の無音解析JSONを読み、valley配列と推定audio長を返す
    期待構造:
    {
      "duration": 517.331,
      "silences": [{"start":..,"end":..,"duration":..,"valley":..}, ...]
    }
    """
    data = json.loads(Path(audio_json).read_text(encoding="utf-8"))
    silences = data.get("silences", [])
    valleys = [s["valley"] for s in silences if "valley" in s]
    audio_len = data.get("duration")
    return valleys, audio_len

def nearest_valley(valleys: List[float], t: float, radius_ms: int) -> float:
    if not valleys:
        return t
    radius = max(0.0, radius_ms) / 1000.0
    best, bd = t, 1e9
    for v in valleys:
        d = abs(v - t)
        if d < bd:
            bd = d; best = v
    return best if bd <= radius else t

def cut_tail_at_anchor(cues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # アンカー文を含む最後のキュー以降を捨てる
    def has_anchor(txt: str) -> bool:
        T = re.sub(r"\s+", "", txt or "")
        return any(p in T for p in ANCHOR_PATTERNS)
    for i in range(len(cues)-1, -1, -1):
        if has_anchor(cues[i]["text"]):
            return cues[:i+1]
    return cues

def distribute_text_over_capcut(script: str, capcut_cues: List[Dict[str,Any]], valleys: List[float]):
    """
    CapCutの枠を使い、台本文字列を自然に配分。
    - 枠許容量: duration * MAX_CPS_DEFAULT
    - 末尾は句読点優先（強 > 弱 > 容量）
    - 枠開始/終了は valley に±150msでスナップ（逆転しそうなら元に戻す）
    - 短すぎる枠は前方マージ、ギャップ不足は等分調整
    - 最終的に2行/36字・CPS<=17の整形を適用
    """
    S = re.sub(r"\s+", " ", norm_text(script)).strip()
    N = len(S)
    tptr = 0
    out: List[Dict[str,Any]] = []

    for c in capcut_cues:
        st, ed = float(c["start"]), float(c["end"])
        dur = max(0.001, ed - st)
        quota = int(dur * MAX_CPS_DEFAULT)

        if tptr >= N:
            txt = ""
        else:
            end_guess = min(N, tptr + max(1, quota))
            chunk = S[tptr:end_guess]

            # 強い句読点を末尾に（直近最後）
            m = re.search(r"[。！？](?!.*[。！？])", chunk)
            if m:
                cut = tptr + m.end()
            else:
                # 弱い句読点
                m2 = re.search(r"[、，](?!.*[、，])", chunk)
                # ★バグ修正済: tptr二重加算しない
                cut = tptr + (m2.end() if m2 else len(chunk))

            cut = max(cut, tptr+1)
            cut = min(cut, N)
            txt = S[tptr:cut]
            tptr = cut

        st2 = nearest_valley(valleys, st, VALLEY_SNAP_MS) if valleys else st
        ed2 = nearest_valley(valleys, ed, VALLEY_SNAP_MS) if valleys else ed
        if ed2 - st2 < 0.4:
            st2, ed2 = st, ed

        out.append({"start": st2, "end": ed2, "text": txt})

    # 残文があれば末尾へ吸収
    if tptr < N and out:
        out[-1]["text"] = (out[-1]["text"] + S[tptr:]).strip()
        tptr = N

    # 空テキストの中間キューは前へ統合
    i = 0
    while i < len(out)-1:
        if not (out[i]["text"] or "").strip():
            if i > 0:
                out[i-1]["end"] = out[i]["end"]
            out.pop(i)
        else:
            i += 1

    # 短尺マージ & ギャップ調整
    j = 0
    while j < len(out):
        cur = out[j]
        dur = cur["end"] - cur["start"]
        if dur < MIN_DUR and j > 0:
            out[j-1]["end"] = cur["end"]
            out[j-1]["text"] = (out[j-1]["text"] + cur["text"]).strip()
            out.pop(j); continue
        if j > 0:
            gap = cur["start"] - out[j-1]["end"]
            if gap < MIN_GAP:
                shift = (MIN_GAP - gap) / 2
                out[j-1]["end"] -= shift
                cur["start"] += shift
        j += 1

    # レイアウト整形
    for c in out:
        dur = max(0.001, c["end"] - c["start"])
        lines, _ok = enforce_layout(c["text"], dur,
                                    max_chars_per_line=MAX_LINE_CHARS_DEFAULT,
                                    max_lines=MAX_LINES_DEFAULT,
                                    max_cps=MAX_CPS_DEFAULT)
        c["text"] = "\n".join(lines)

    return out

def main():
    import argparse
    ap = argparse.ArgumentParser(description="4ソース統合（既存JSONのみ使用）")
    ap.add_argument("--audio_json", required=True, help="既存の無音解析JSON（valley含む）")
    ap.add_argument("--whisper_json", required=True, help="既存のASR JSON（whisper-cpp形式）")
    ap.add_argument("--capcut_srt", required=True, help="CapCut/VrewのSRT")
    ap.add_argument("--script", required=True, help="台本テキスト")
    ap.add_argument("--out", required=True, help="出力SRT")
    ap.add_argument("--out_vtt", required=True, help="出力VTT")
    args = ap.parse_args()

    valleys, audio_len = load_valleys(args.audio_json)
    capcut = parse_srt(args.capcut_srt)
    script = Path(args.script).read_text(encoding="utf-8")
    # 解析JSONの健全性確認（※将来の境界精度調整用にロードのみ）
    _asr_text, _char_times, _est_dur = load_whisper_chars(args.whisper_json)

    cues = distribute_text_over_capcut(script, capcut, valleys)
    cues = cut_tail_at_anchor(cues)

    # 時刻の健全性
    for c in cues:
        if c["end"] <= c["start"]:
            c["end"] = c["start"] + 1.2
    cues = sorted(cues, key=lambda x: x["start"])

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(format_srt(cues), encoding="utf-8")
    Path(args.out_vtt).write_text(format_vtt(cues), encoding="utf-8")

    last_end = cues[-1]["end"] if cues else 0.0
    print("🔄 4ソース統合処理完了")
    print(f"  CapCut SRT: {len(capcut)}")
    print(f"  出力: {len(cues)}  最終終了: {last_end:.3f}s  (音声長 ~{(audio_len or 0):.3f}s)")

if __name__ == "__main__":
    main()