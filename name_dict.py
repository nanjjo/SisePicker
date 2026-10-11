"""단지명 사전 — OCR 이 오독한 한글 단지명을 알려진 단지명으로 보정한다.

- 사전 파일: <PPT 폴더>\\단지목록.txt (한 줄에 단지명 하나, '#' 주석, '[생활권]' 구분줄 허용).
- 비교는 자모 단위로 한다: Windows OCR 의 오독은 모양이 비슷한 글자로 나므로(샘→생, 청솔→치소)
  음절 비교보다 자모(초성/중성/종성) 비교가 훨씬 잘 맞는다.
- 사용자가 결과의 단지명을 고쳐서 복사/PPT 추가하면 그 이름을 사전에 자동으로 추가한다(학습).
"""
from __future__ import annotations

import difflib
import os
import re

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
_SUFFIXES = ("아파트", "단지", "APT")


def decompose(s: str) -> str:
    """한글 음절을 초성·중성·종성 자모로 풀어 쓴다. 그 외 글자는 그대로."""
    out = []
    for ch in s:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            cho, rest = divmod(idx, 21 * 28)
            jung, jong = divmod(rest, 28)
            out.append(_CHO[cho] + _JUNG[jung] + (_JONG[jong] if jong else ""))
        else:
            out.append(ch)
    return "".join(out)


def _norm(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    for suf in _SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
    return s


def similarity(a: str, b: str) -> float:
    """자모 단위 유사도 0~1 (접미사 '아파트/단지' 는 비교에서 제외)."""
    return difflib.SequenceMatcher(None, decompose(_norm(a)), decompose(_norm(b))).ratio()


def load_names(path: str) -> list[str]:
    if not path or not os.path.isfile(path):
        return []
    names: list[str] = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            t = line.strip()
            if not t or t.startswith("#") or (t.startswith("[") and t.endswith("]")):
                continue
            if t not in names:
                names.append(t)
    return names


def best_match(name: str, names: list[str], threshold: float = 0.72) -> tuple[str, float] | None:
    """가장 비슷한 사전 항목. 유사도가 threshold 미만이면 None. 완전 일치면 (name, 1.0)."""
    if not name or not names:
        return None
    if name in names:
        return name, 1.0
    best, score = None, 0.0
    digits = re.sub(r"\D", "", _norm(name))
    for cand in names:
        if re.sub(r"\D", "", _norm(cand)) != digits:
            continue                       # 숫자(1단지/2단지)가 다르면 다른 단지
        s = similarity(name, cand)
        if s > score:
            best, score = cand, s
    if best is not None and score >= threshold:
        return best, score
    return None


def learn(path: str, name: str) -> bool:
    """사전에 없는 이름이면 파일 끝에 추가. 추가했으면 True."""
    name = name.strip()
    if not name or not re.search(r"[가-힣]", name):
        return False
    if name in load_names(path):
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new = not os.path.isfile(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8") as f:
        if new:
            f.write("# SisePicker 단지명 사전 — 한 줄에 단지명 하나. OCR 오독을 이 목록으로 보정합니다.\n")
        f.write(name + "\n")
    return True
