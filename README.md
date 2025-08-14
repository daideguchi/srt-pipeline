# Ultimate JP Subtitle System

## ✅ **完成版字幕ファイル / Final Output**

- **`subs/final_complete.srt`** - 最終完成版（SRT形式 / Final SRT)
- **`subs/final_complete.vtt`** - 最終完成版（VTT形式 / Final VTT)

**89セグメント、517秒音声に完全同期済み / 89 segments, perfectly synchronized to 517-second audio**

---

This project builds an end‑to‑end Japanese subtitle generator that integrates multiple STT engines, forced alignment with a provided script, Japanese‑friendly line breaking, natural timing adjustment, and quality checks. It outputs both SRT and VTT.

Inputs:
- `audio/4_2.wav` (8:37 Japanese audio)
- `script_4_2.txt` (reference script)

Outputs:
- `out/4_2.srt`
- `out/4_2.vtt`

Key features:
- Parallel STT across multiple engines: faster‑whisper, stable‑whisper (stable-ts), OpenAI Whisper, Google Cloud STT
- Word‑level timestamps (where supported)
- Cross‑engine integration and confidence‑weighted voting
- Script‑aware forced alignment via sequence alignment and timestamp projection
- Japanese optimal line breaks (kinshoku handling) and natural timing refinement
- Real‑time quality checks (CER, coverage, duration constraints)

## Quick Start

1) Python 3.9+ recommended. Install dependencies (many are optional; the system gracefully degrades):

```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2) Place input files:
- Audio: `audio/4_2.wav`
- Script: `script_4_2.txt`

3) (Optional) Configure Google Cloud STT:
- Install `gcloud` and set up a project.
- Create a service account with Speech-to-Text permission.
- Download a JSON key and set `GOOGLE_APPLICATION_CREDENTIALS=/path/key.json`.

4) Run:

```
python -m src.main --audio audio/4_2.wav --script script_4_2.txt --out out/4_2
```

This generates `out/4_2.srt` and `out/4_2.vtt`.

## Notes on Engines
- faster‑whisper: Uses CTranslate2 backend, fast and provides word timestamps.
- stable‑whisper (stable-ts): Improves word‑level stability; provides word timestamps.
- OpenAI Whisper (reference): Used if installed. If word timestamps are not available, an approximation per segment is used.
- Google STT: Requires `google-cloud-speech` and credentials; provides word offsets.

You can control which engines to enable via CLI flags, e.g. `--no-google --no-whisper`.

## Output Quality
- The system integrates multiple hypotheses by time‑bucketing overlapping words and selecting the best candidate by majority/weighted confidence.
- A forced alignment step maps the integrated hypothesis to the provided script at character level, projecting timestamps to script positions.
- Segmentation honors Japanese punctuation, line length targets, and kinsoku rules, then timings are smoothed with min/max duration and boundary snapping to word edges.
- Quality checks print CER against script, coverage, and any suspicious durations.

## Troubleshooting
- If no engines are available, install at least one of: `faster-whisper`, `stable-ts` (or `stable-whisper`), `whisper`, `google-cloud-speech`.
- For GPU acceleration with faster‑whisper, install with CUDA wheels for `ct2` or use `--compute-type float16` on compatible GPUs.
- If audio is not WAV/PCM, ensure `ffmpeg` is installed; engines generally handle transcoding.

## License
No license specified; internal project by request.
