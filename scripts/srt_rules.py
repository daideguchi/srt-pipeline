#!/usr/bin/env python3
# srt_rules.py - 日本語SRTの基本ルールと整形

import re
import unicodedata

MAX_CPS_DEFAULT = 17.0
MAX_LINE_CHARS_DEFAULT = 36
MAX_LINES_DEFAULT = 2

def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s

def visible_len(s: str) -> int:
    # 改行除去の可視文字数（空白は数える）
    return len(re.sub(r"\n", "", s))

def calc_cps(text: str, duration_sec: float) -> float:
    dur = max(0.001, float(duration_sec))
    chars = visible_len(text.strip())
    return chars / dur

def _split_by_punct(s: str):
    # 強: 。！？　弱: 、，・　補助: 読点後の空白
    return re.split(r"(?<=[。！？])|(?<=[、，・])", s)

def wrap_ja(text: str, max_chars_per_line=MAX_LINE_CHARS_DEFAULT, max_lines=MAX_LINES_DEFAULT):
    """
    句読点を優先して2行以内に自然改行。超過は素直に分割。
    """
    s = norm_text(text).strip()
    if not s:
        return [""]
    # まず句読点の塊で拾う
    chunks = [c for c in _split_by_punct(s) if c]
    lines = []
    cur = ""
    for ch in chunks:
        if len(cur + ch) <= max_chars_per_line:
            cur += ch
        else:
            if cur:
                lines.append(cur)
                cur = ch
            else:
                # 単体でも入らない長塊は強制分割
                while len(ch) > max_chars_per_line:
                    lines.append(ch[:max_chars_per_line])
                    ch = ch[max_chars_per_line:]
                cur = ch
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)

    # まだ余剰がある場合は最後の行に押し込む
    rest = s[len("".join(lines)):]
    if rest and len(lines) > 0:
        lines[-1] = (lines[-1] + rest)[:max_chars_per_line]

    # 行数超過時は先頭2行に圧縮
    lines = lines[:max_lines]
    if not lines:
        lines = [s[:max_chars_per_line]]
    return lines

def enforce_layout(text: str, duration_sec: float,
                   max_chars_per_line=MAX_LINE_CHARS_DEFAULT,
                   max_lines=MAX_LINES_DEFAULT,
                   max_cps=MAX_CPS_DEFAULT):
    """
    行折り返しを行い、CPS制約も確認して返す。
    戻り値: (lines: list[str], ok: bool)
    """
    lines = wrap_ja(text, max_chars_per_line, max_lines)
    cps = calc_cps("\n".join(lines), duration_sec)
    ok = (cps <= max_cps) and all(len(line) <= max_chars_per_line for line in lines)
    return lines, ok