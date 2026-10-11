"""기록 파일 — 인식 결과를 생활권별·평형별 파일에 누적한다 (매매값만, Excel 붙여넣기용).

    records\\둔산생활권_24평.txt :  샘머리1단지 98' 4.1
    records\\둔산생활권_34평.txt :  샘머리1단지 98' 5.3

- 파일은 세션이 바뀌어도 같은 이름에 계속 이어 쓴다(생활권별 데이터 정리용).
- 원본 면적 55~65㎡는 24평, 80~90㎡는 34평 파일로 분류하며 나머지는 제외한다.
- 결과를 편집한 뒤 복사/PPT 추가하면 마지막 항목을 교체한다: 마지막 항목이 쓴 줄들은
  각 파일의 끝에 있으므로 그 줄들을 지우고 다시 쓴다.
"""
from __future__ import annotations

import os
import re

from sise_parser import to_pyeong  # 면적→평형 변환은 파서와 공유

_INVALID = re.compile(r'[\\/:*?"<>|]')


def _split_header(header: str) -> tuple[str, str]:
    """'샘머리1단지 98' -> ('샘머리1단지', '98'). 연식이 없으면 ('...', '')."""
    parts = header.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], parts[1]
    return header, ""


def result_to_entries(result_text: str, sep: str = " ",
                      divisor: float | None = 2.48) -> list[tuple[str, str]]:
    """결과 텍스트('단지명 연식\\n면적) 매매/전세 ...') → [(평형, 줄), ...].

    '/' 뒤(전세)는 버리고 앞(매매)만 쓴다:  ("34", "샘머리1단지 98' 5.3")
    divisor=None 이면 결과 텍스트의 면적이 이미 평형이라고 보고 그대로 쓴다.
    """
    lines = [ln.strip() for ln in result_text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    name, year = _split_header(lines[0])
    year_s = f"{year}'" if year else ""
    out = []
    for ln in lines[1:]:
        area, _, vals = ln.partition(")")
        try:
            number = float(area.strip())
        except ValueError:
            continue
        if divisor is None:  # 이전 호출자의 평형 입력은 두 대상 평형만 허용
            py = area.strip() if number in (24, 34) else None
        else:
            py = "24" if 55 <= number <= 65 else "34" if 80 <= number <= 90 else None
        if py is None:
            continue
        sale = vals.strip().split("/")[0].strip()
        if sep == "\t":
            line = "\t".join([name, year_s, sale])
        else:
            line = sep.join(f for f in (name, year_s, sale) if f)
        out.append((py, line))
    return out


def safe_filename(s: str) -> str:
    s = _INVALID.sub("", s).strip()
    return s or "미지정"


class ZoneRecorder:
    def __init__(self, directory: str, zone: str = "", sep: str = " ", divisor: float | None = 2.48):
        self.directory = directory
        self.zone = zone
        self.sep = sep
        self.divisor = divisor
        self.count = 0                       # 이 세션에서 기록한 항목 수
        self._last_written: dict[str, list[str]] = {}

    def file_for(self, pyeong: str, zone: str | None = None) -> str:
        z = safe_filename(zone if zone is not None else self.zone)
        return os.path.join(self.directory, f"{z}_{pyeong}평.txt")

    def _group(self, result_text: str) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for py, line in result_to_entries(result_text, self.sep, self.divisor):
            groups.setdefault(self.file_for(py), []).append(line)
        return groups

    def add(self, result_text: str) -> list[str]:
        """항목을 파일들에 추가. 반환: 기록된 파일 경로들."""
        groups = self._group(result_text)
        if not groups:
            self._last_written = {}
            return []
        os.makedirs(self.directory, exist_ok=True)
        for path, lines in groups.items():
            self._append(path, lines)
        self._last_written = groups
        self.count += 1
        return list(groups)

    def replace_last(self, result_text: str) -> list[str]:
        """마지막 항목이 쓴 줄들을 각 파일 끝에서 제거하고 새 내용으로 다시 쓴다."""
        if not self._last_written:
            return self.add(result_text)
        for path, lines in self._last_written.items():
            self._strip_tail(path, lines)
        groups = self._group(result_text)
        os.makedirs(self.directory, exist_ok=True)
        for path, lines in groups.items():
            self._append(path, lines)
        self._last_written = groups
        return list(groups)

    @staticmethod
    def _append(path: str, lines: list[str]) -> None:
        new = not os.path.isfile(path) or os.path.getsize(path) == 0
        with open(path, "a", encoding="utf-8-sig" if new else "utf-8") as f:
            f.write("\n".join(lines) + "\n")

    @staticmethod
    def _strip_tail(path: str, lines: list[str]) -> None:
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read().splitlines()
        n = len(lines)
        if n and content[-n:] == lines:
            content = content[:-n]
        with open(path, "w", encoding="utf-8-sig") as f:
            if content:
                f.write("\n".join(content) + "\n")
