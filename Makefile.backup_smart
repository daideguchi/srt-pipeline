# --- Makefile (project root) ---

PY := python3

AUDIO_DIR := audio
SUBS_DIR  := subs
SCRIPTS   := scripts
REPORTS   := reports

AUDIO := $(AUDIO_DIR)/4_2.wav
SRC_SRT := $(SUBS_DIR)/final_for_upload.srt
CLEAN_SRT := $(SUBS_DIR)/final_clean_tail.srt
PAD_SRT := $(SUBS_DIR)/final_clean_tail_padded.srt

FINAL_ANCHOR := 最後までご視聴いただき、本当にありがとうございました。

.PHONY: fold clean-tail pad verify final report-compare

fold:
	@mkdir -p $(AUDIO_DIR) $(SUBS_DIR) $(SCRIPTS) $(REPORTS)
	@if [ -f 4_2.wav ]; then mv -f 4_2.wav $(AUDIO_DIR)/; fi
	@for f in *.srt *.vtt; do \
		if [ -f "$$f" ]; then mv -f "$$f" $(SUBS_DIR)/; fi; \
	done
	@echo "✅ fold: 整理完了"

clean-tail: $(SCRIPTS)/clean_tail.py $(SRC_SRT)
	$(PY) $(SCRIPTS)/clean_tail.py \
		--in $(SRC_SRT) \
		--out $(CLEAN_SRT) \
		--final-anchor "$(FINAL_ANCHOR)" \
		--script script_4_2.txt
	@echo "✅ clean-tail: $(CLEAN_SRT)"

pad: $(SCRIPTS)/pad_to_audio_end.py $(CLEAN_SRT) $(AUDIO)
	$(PY) $(SCRIPTS)/pad_to_audio_end.py \
		--in $(CLEAN_SRT) \
		--audio $(AUDIO) \
		--out $(PAD_SRT) \
		--offset-ms 20
	@echo "✅ pad: $(PAD_SRT)"

verify: $(SCRIPTS)/check_durations.py $(AUDIO) $(PAD_SRT)
	$(PY) $(SCRIPTS)/check_durations.py --audio $(AUDIO) --srt $(PAD_SRT)

final: fold clean-tail pad verify
	@echo "🎯 DONE: 最終版は $(PAD_SRT)"

report-compare: $(SCRIPTS)/compare_srt_vs_script.py $(CLEAN_SRT)
	$(PY) $(SCRIPTS)/compare_srt_vs_script.py \
		--srt $(CLEAN_SRT) \
		--script script_4_2.txt \
		--out $(REPORTS)/srt_vs_script
	@echo "📊 reports/srt_vs_script_* を生成"