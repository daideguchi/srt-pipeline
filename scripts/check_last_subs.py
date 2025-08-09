#!/usr/bin/env python3
import re

with open('subs/final_merged.srt', 'r', encoding='utf-8') as f:
    txt = f.read().strip()

blocks = re.split(r"\n\s*\n", txt)
print(f"Total blocks: {len(blocks)}")

# Last 5 blocks
for i, b in enumerate(blocks[-5:], len(blocks)-4):
    print(f"--- Block {i} ---")
    print(b)
    print()