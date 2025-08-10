#!/usr/bin/env python3
# oneclick.py — フォルダ内(音声/台本/CapCut SRT)を検出して一発処理（ダミー禁止・毎回フル解析）
import argparse, re, subprocess, sys, os, json, shutil
import hashlib, datetime, traceback, tarfile
from pathlib import Path

AUDIO_EXTS = [".wav", ".m4a", ".mp3", ".flac"]
TXT_EXTS   = [".txt"]
SRT_EXTS   = [".srt"]

ROOT    = Path(__file__).resolve().parents[1]  # repo root
SCRIPTS = ROOT / "scripts"
REPORTS = ROOT / "reports"
SUBS    = ROOT / "subs"
MODELS  = ROOT / "models"

def run(cmd, cwd=None, check=True):
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    if check and p.returncode != 0:
        if out: print(out)
        if err: print(err, file=sys.stderr)
        raise SystemExit(f"❌ command failed: {' '.join(map(str, cmd))}")
    return out.strip()

def require(bin_name: str):
    if shutil.which(bin_name) is None:
        raise SystemExit(f"❌ 必要コマンドが見つかりません: {bin_name}")

def list_by_ext(folder: Path, exts):
    return sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts])

def pick_exactly_one(paths, kind):
    if len(paths) == 0:
        raise SystemExit(f"❌ {kind} が見つかりません。フォルダに 1 つ入れてください。")
    if len(paths) > 1:
        msg = "\n".join(f" - {p.name}" for p in paths)
        raise SystemExit(f"❌ {kind} が複数あります。1つに絞ってください:\n{msg}")
    return paths[0]

def ensure_dirs():
    REPORTS.mkdir(parents=True, exist_ok=True)
    SUBS.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)

def hhmmssms_to_sec(h, m, s, ms):
    return h*3600 + m*60 + s + ms/1000.0

def srt_last_end(srt_path: Path) -> float:
    text = srt_path.read_text(encoding="utf-8", errors="ignore")
    last = 0.0
    for m in re.finditer(r"-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})", text):
        h, mn, s, ms = map(int, m.groups())
        t = hhmmssms_to_sec(h, mn, s, ms)
        if t > last: last = t
    return last

def audio_len_from_peaks_json(path: Path) -> float:
    data = json.loads(path.read_text(encoding="utf-8"))
    return float(data["duration"])

def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

def safe_copy_or_move(src: Path, dst: Path, mode: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "move":
        src.replace(dst)
    else:
        shutil.copy2(src, dst)

def write_manifest(dst_dir: Path, meta: dict):
    (dst_dir / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def maybe_compress(root: Path):
    tgz = root / "bundle.tgz"
    with tarfile.open(tgz, "w:gz") as tar:
        for item in root.iterdir():
            if item.name != "bundle.tgz":
                tar.add(item, arcname=item.name)
    return tgz

def main():
    ap = argparse.ArgumentParser(description="厳格：音声/台本/CapCut SRTを毎回フル解析して最終SRT/VTTを出力")
    ap.add_argument("--dir", required=True, help="入力フォルダ（音声*.wav|m4a|mp3|flac、台本*.txt、capcut*.srtを各1つ）")
    ap.add_argument("--model", default=str(MODELS / "ggml-medium.bin"),
                    help="whisper-cliのモデルパス（例: models/ggml-medium.bin）")
    ap.add_argument("--silence_db", type=int, default=-35)
    ap.add_argument("--min_silence_ms", type=int, default=220)
    ap.add_argument("--target_offset_ms", type=int, default=20)
    ap.add_argument("--tolerance", type=float, default=0.050, help="音声-字幕差分の許容秒（絶対値）")
    ap.add_argument("--out_prefix", default="final_production", help="出力ファイルの接頭辞（subs/に保存）")
    ap.add_argument("--archive_root", default=str(ROOT / "archive"), help="アーカイブ基底ディレクトリ")
    ap.add_argument("--archive_mode", choices=["move", "copy"], default="move", help="入力等を移動 or コピー")
    ap.add_argument("--compress", action="store_true", help="アーカイブをbundle.tgzに圧縮もする")
    args = ap.parse_args()
    
    archive_root = Path(args.archive_root)

    jobdir = Path(args.dir).resolve()
    if not jobdir.exists():
        raise SystemExit(f"❌ 入力フォルダが存在しません: {jobdir}")

    # 依存関係（ダミー禁止なので必須）
    require("ffmpeg")
    require("ffprobe")
    require("whisper-cli")

    # 入力を厳格に1つずつ要求
    audios  = list_by_ext(jobdir, AUDIO_EXTS)
    txts    = list_by_ext(jobdir, TXT_EXTS)
    srts    = list_by_ext(jobdir, SRT_EXTS)

    audio   = pick_exactly_one(audios, "音声ファイル")
    script  = pick_exactly_one(txts,   "台本TXT")
    capcut  = pick_exactly_one(srts,   "CapCut SRT")

    print(f"🎧 AUDIO : {audio.name}")
    print(f"📝 SCRIPT: {script.name}")
    print(f"🎬 SRT   : {capcut.name}")

    ensure_dirs()
    peaks_json   = REPORTS / "audio_peaks.json"
    whisper_json = REPORTS / "whisper_medium.json"

    tmp_srt = SUBS / f"{args.out_prefix}.tmp.srt"
    tmp_vtt = SUBS / f"{args.out_prefix}.tmp.vtt"
    out_srt = SUBS / f"{args.out_prefix}.srt"
    out_vtt = SUBS / f"{args.out_prefix}.vtt"

    # 1) 無音解析 → peaks_json（毎回実施）
    print("🔊 Step 1: 無音/valley解析 → reports/audio_peaks.json")
    run([sys.executable, str(SCRIPTS / "audio_peaks_to_json.py"),
         "--audio", str(audio),
         "--out",   str(peaks_json),
         "--silence_db", str(args.silence_db),
         "--min_silence_ms", str(args.min_silence_ms)])

    # 2) Whisper解析（毎回実施）
    print("🎤 Step 2: Whisper解析 → reports/whisper_medium.json")
    model_arg = str(args.model)
    if not Path(model_arg).exists():
        print(f"⚠️ モデルファイルが見つかりませんでした: {model_arg}")
        print("   例: models/ggml-medium.bin を配置してください（Makefileのwhisperターゲットでも取得可）")
    run(["whisper-cli",
         "--model", model_arg,
         "--language", "ja",
         "--output-json-full",
         "--output-file", str(REPORTS / "whisper_medium"),
         str(audio)])

    # 3) 4ソース統合（CapCut枠＋台本＋Whisper＋valley）→ 一時SRT/VTT
    print("🔄 Step 3: 4ソース統合 → 一時SRT/VTT")
    run([sys.executable, str(SCRIPTS / "smart_subs.py"),
         "--audio_json",   str(peaks_json),
         "--whisper_json", str(whisper_json),
         "--capcut_srt",   str(capcut),
         "--script",       str(script),
         "--out",          str(tmp_srt),
         "--out_vtt",      str(tmp_vtt)])

    # 4) 末尾クランプ（音声実体で厳密）→ 最終SRT/VTT
    print("✂️  Step 4: 末尾調整（実音声ベース） → 最終SRT/VTT")
    run([sys.executable, str(SCRIPTS / "finalize_tail.py"),
         "--in",       str(tmp_srt),
         "--audio",    str(audio),
         "--out",      str(out_srt),
         "--out_vtt",  str(out_vtt),
         "--target_offset_ms", str(args.target_offset_ms)])

    # 5) 同期検証（実音声ベース・厳格判定）
    print("🧪 Step 5: 同期検証（実音声）")
    verify_out = run([sys.executable, str(SCRIPTS / "check_durations.py"),
                      "--audio", str(audio), "--srt", str(out_srt)],
                     check=False)
    if verify_out:
        print(verify_out)

    # 自前でも最終差分を厳格評価（peaks_jsonの実測duration と 最終SRT終端）
    audio_len = audio_len_from_peaks_json(peaks_json)
    last_end  = srt_last_end(out_srt)
    diff      = abs(audio_len - last_end)
    print(f"📏 diff={diff:.3f}s  (tolerance={args.tolerance:.3f}s)")
    if diff > args.tolerance:
        raise SystemExit(f"❌ 同期差分が閾値を超えました: {diff:.3f}s > {args.tolerance:.3f}s")

    # 6) 完了表示
    print("✅ 完了")
    print(f"   出力: {out_srt.name} / {out_vtt.name}")
    print(f"   保存先: {SUBS}")
    
    # 7) 成功時のアーカイブ
    jobname = jobdir.name
    ts = stamp()
    arch_dir = archive_root / "success" / jobname / ts
    meta = {
        "status": "success",
        "jobdir": str(jobdir),
        "audio": audio.name,
        "script": script.name,
        "capcut": capcut.name,
        "outputs": [out_srt.name, out_vtt.name],
        "reports": [peaks_json.name, whisper_json.name],
        "audio_len": audio_len,
        "srt_end": last_end,
        "diff": diff,
        "tolerance": args.tolerance,
        "cmdline": " ".join(map(str, sys.argv)),
        "timestamp": ts,
        "hashes": {}
    }
    # ハッシュ計算
    for p in [audio, script, capcut, out_srt, out_vtt, peaks_json, whisper_json]:
        if p.exists(): meta["hashes"][p.name] = sha256sum(p)
    # 収納
    for p in [audio, script, capcut]:
        safe_copy_or_move(p, arch_dir / "inputs" / p.name, args.archive_mode)
    for p in [out_srt, out_vtt]:
        safe_copy_or_move(p, arch_dir / "outputs" / p.name, args.archive_mode)
    for p in [peaks_json, whisper_json]:
        safe_copy_or_move(p, arch_dir / "reports" / p.name, args.archive_mode)
    write_manifest(arch_dir, meta)
    if args.compress:
        tgz = maybe_compress(arch_dir)
        print(f"📦 archived: {arch_dir} (+ {tgz.name})")
    else:
        print(f"📦 archived: {arch_dir}")

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        # main内での意図的終了はそのまま
        raise
    except Exception:
        # 可能な範囲で失敗アーカイブ
        try:
            tb = traceback.format_exc()
            # 入力推定（存在すれば拾う）
            args = None
            for i, a in enumerate(sys.argv):
                if a == "--dir" and i+1 < len(sys.argv):
                    args = sys.argv[i+1]
                    break
            jobname = Path(args).name if args else "unknown"
            ts = stamp()
            root = Path(__file__).resolve().parents[1]
            arch_dir = root / "archive" / "failed" / jobname / ts
            arch_dir.mkdir(parents=True, exist_ok=True)
            (arch_dir / "error.txt").write_text(tb, encoding="utf-8")
            # 入力3点があればコピーで保全
            if args:
                jd = Path(args)
                for pat, sub in [("*.wav", "inputs"), ("*.m4a", "inputs"), ("*.mp3", "inputs"),
                                 ("*.flac", "inputs"), ("*.txt", "inputs"), ("*.srt", "inputs")]:
                    for p in jd.glob(pat):
                        safe_copy_or_move(p, arch_dir / sub / p.name, "copy")
            print("❌ 処理失敗。詳細: archive/failed/ に保存しました。")
        except Exception:
            pass
        raise