# -*- coding: utf-8 -*-
"""
Utilities for converting Korean lyrics / g2pK-pronounced Hangul into the
Coda-SVS DiffSinger Korean phoneme set.

The converter is intentionally dependency-light: g2pK is imported only when
`use_g2pk=True`. If the input is already a pronounced Hangul string, pass
`use_g2pk=False`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


CHOSEONG = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]

JUNGSEONG = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
]

JONGSEONG = [
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
]


# Coda-SVS Korean PHONEMES.md-style mapping.
INITIAL_TO_CODA = {
    "ㄱ": "g",
    "ㄲ": "kk",
    "ㄴ": "n",
    "ㄷ": "d",
    "ㄸ": "tt",
    "ㄹ": "r",
    "ㅁ": "m",
    "ㅂ": "b",
    "ㅃ": "pp",
    "ㅅ": "s",
    "ㅆ": "ss",
    "ㅇ": None,  # silent onset
    "ㅈ": "j",
    "ㅉ": "jj",
    "ㅊ": "ch",
    "ㅋ": "k",
    "ㅌ": "t",
    "ㅍ": "p",
    "ㅎ": "h",
}

VOWEL_TO_CODA = {
    "ㅏ": ["a"],
    "ㅐ": ["e"],
    "ㅑ": ["y", "a"],
    "ㅒ": ["y", "e"],
    "ㅓ": ["eo"],
    "ㅔ": ["e"],
    "ㅕ": ["y", "eo"],
    "ㅖ": ["y", "e"],
    "ㅗ": ["o"],
    "ㅘ": ["w", "a"],
    "ㅙ": ["w", "e"],
    "ㅚ": ["w", "e"],
    "ㅛ": ["y", "o"],
    "ㅜ": ["u"],
    "ㅝ": ["w", "eo"],
    "ㅞ": ["w", "e"],
    "ㅟ": ["w", "i"],
    "ㅠ": ["y", "u"],
    "ㅡ": ["eu"],
    "ㅢ": ["eu", "i"],
    "ㅣ": ["i"],
}

FINAL_TO_CODA = {
    "": None,
    "ㄱ": "K",
    "ㄲ": "K",
    "ㅋ": "K",
    "ㄳ": "K",
    "ㄺ": "K",
    "ㄴ": "N",
    "ㄵ": "N",
    "ㄶ": "N",
    "ㄷ": "T",
    "ㅅ": "T",
    "ㅆ": "T",
    "ㅈ": "T",
    "ㅊ": "T",
    "ㅌ": "T",
    "ㅎ": "T",
    "ㄹ": "L",
    "ㄽ": "L",
    "ㄾ": "L",
    "ㅀ": "L",
    "ㅁ": "M",
    "ㄻ": "M",
    "ㅂ": "P",
    "ㅍ": "P",
    "ㄼ": "P",
    "ㄿ": "P",
    "ㅄ": "P",
    "ㅇ": "NG",
}

CODA_VOWELS = {"a", "eo", "o", "u", "eu", "i", "e", "y", "w"}
CODA_CONSONANTS = {
    "g", "n", "d", "r", "m", "b", "s", "j", "ch", "k", "t", "p", "h",
    "kk", "tt", "pp", "ss", "jj", "K", "T", "P", "N", "L", "M", "NG",
}
CODA_SILENCES = {"SP", "AP", "sil", "SIL", "pau", "br"}

PUNCTUATION_TO_SP = {
    ",", ".", "!", "?", "，", "。", "！", "？", ";", "；", ":", "：", "、",
}


@dataclass
class KoreanToCodaOptions:
    use_g2pk: bool = True
    keep_spaces_as_sp: bool = False
    punctuation_as_sp: bool = True
    word_sep: str = "SP"


def contains_hangul(text: str) -> bool:
    return any(is_hangul_syllable(ch) for ch in text)


def is_hangul_syllable(ch: str) -> bool:
    return 0xAC00 <= ord(ch) <= 0xD7A3


def decompose_hangul_syllable(ch: str) -> tuple[str, str, str]:
    if not is_hangul_syllable(ch):
        raise ValueError(f"Not a Hangul syllable: {ch!r}")

    code = ord(ch) - 0xAC00
    cho_idx = code // (21 * 28)
    jung_idx = (code % (21 * 28)) // 28
    jong_idx = code % 28
    return CHOSEONG[cho_idx], JUNGSEONG[jung_idx], JONGSEONG[jong_idx]


def normalize_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def run_g2pk(text: str) -> str:
    try:
        from g2pk import G2p
    except ImportError as exc:
        raise RuntimeError(
            "g2pK is not installed. Install it with `pip install g2pK`, "
            "or use txt_mode='coda-korean-pronounced' for already-pronounced Hangul."
        ) from exc

    return G2p()(text)


def syllable_to_coda_phones(ch: str) -> list[str]:
    cho, jung, jong = decompose_hangul_syllable(ch)

    phones: list[str] = []
    initial = INITIAL_TO_CODA.get(cho)
    if initial:
        phones.append(initial)

    vowel = VOWEL_TO_CODA.get(jung)
    if vowel is None:
        raise ValueError(f"Unsupported Korean vowel jamo {jung!r} in syllable {ch!r}")
    phones.extend(vowel)

    final = FINAL_TO_CODA.get(jong)
    if final:
        phones.append(final)

    return phones


def korean_text_to_coda_phones(
    text: str,
    options: Optional[KoreanToCodaOptions] = None,
) -> list[str]:
    if options is None:
        options = KoreanToCodaOptions()

    text = normalize_text(text)
    if options.use_g2pk:
        text = normalize_text(run_g2pk(text))

    phones: list[str] = []
    for ch in text:
        if is_hangul_syllable(ch):
            phones.extend(syllable_to_coda_phones(ch))
            continue

        if ch.isspace():
            if options.keep_spaces_as_sp and phones and phones[-1] != options.word_sep:
                phones.append(options.word_sep)
            continue

        if ch in PUNCTUATION_TO_SP:
            if options.punctuation_as_sp and phones and phones[-1] != options.word_sep:
                phones.append(options.word_sep)
            continue

        # Ignore non-Hangul leftovers by default. Number/English normalization should
        # happen before this stage if needed.
        continue

    while phones and phones[0] == options.word_sep:
        phones.pop(0)
    while phones and phones[-1] == options.word_sep:
        phones.pop()

    return phones


def load_coda_korean_txt(
    path: str,
    *,
    use_g2pk: bool = True,
    keep_spaces_as_sp: bool = False,
    punctuation_as_sp: bool = True,
    word_sep: str = "SP",
) -> list[str]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    return korean_text_to_coda_phones(
        text,
        KoreanToCodaOptions(
            use_g2pk=use_g2pk,
            keep_spaces_as_sp=keep_spaces_as_sp,
            punctuation_as_sp=punctuation_as_sp,
            word_sep=word_sep,
        ),
    )


def phone_to_cv_label(phone: str) -> str:
    if phone in CODA_VOWELS:
        return "V"
    if phone in CODA_CONSONANTS:
        return "C"
    if phone in CODA_SILENCES:
        return "SP"
    return "O"


def phone_segments_to_cv_segments(
    segments: Iterable[tuple[float, float, str]],
    *,
    merge_adjacent: bool = False,
) -> list[tuple[float, float, str]]:
    cv_segments: list[tuple[float, float, str]] = []
    for start, end, phone in segments:
        label = phone_to_cv_label(phone)
        if merge_adjacent and cv_segments and cv_segments[-1][2] == label:
            prev_start, _, prev_label = cv_segments[-1]
            cv_segments[-1] = (prev_start, end, prev_label)
        else:
            cv_segments.append((start, end, label))
    return cv_segments


def save_segments_json(path: str, segments: Iterable[tuple[float, float, str]]) -> None:
    data = [
        {"start": float(start), "end": float(end), "label": label}
        for start, end, label in segments
    ]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
