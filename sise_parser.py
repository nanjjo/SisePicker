"""OCR 줄 텍스트 -> 시세 레코드 -> 붙여 넣을 문자열.

캡쳐 예 (OCR 줄):
    샘머리1단
    98y 1350^
    60  85
    4.1 5.3
    2.6 3.7
    1.5 1.6
->
    샘머리1단지 98
    60) 4.1/2.6
    85) 5.3/3.7
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HANGUL = re.compile(r"[가-힣]")
_YEAR = re.compile(r"(?<!\d)(\d{2}|\?)\s*[yY년]")
_NUM = re.compile(r"[-−–]?\d+(?:\.\d+)?|[-–—_ー一]|\?")   # 음수, 값 없음(-), 인식 누락(?)
_DASH = re.compile(r"^[-–—_ー一]$")
_DEC = re.compile(r"^\d+\.\d+$")


@dataclass
class SiseRecord:
    name: str = ""
    year: str = ""
    areas: list[str] = field(default_factory=list)          # ["60", "85"]
    rows: list[list[str]] = field(default_factory=list)     # [["4.1","5.3"],["2.6","3.7"]]
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (bool(self.areas) and bool(self.rows) and "?" not in self.areas
                and self.year != "?" and not any("?" in row for row in self.rows))


def normalize_line(s: str) -> str:
    """OCR 흔한 오독 보정: 소수점 쉼표, 'O'/'o'->0, 'l'/'I'->1 (숫자 사이에서만)."""
    s = s.replace("，", ",").replace("．", ".")
    s = re.sub(r"(?<=\d)[,·\-](?=\d)", ".", s)   # "3-7" (소수점 오독) -> "3.7"
    s = re.sub(r"(?<=\d)[Oo](?=\d|\.|\b)", "0", s)
    s = re.sub(r"(?<=[\d.])[lI](?=\d|\b)", "1", s)
    s = re.sub(r"(?<=\d)\s+\.\s*(?=\d)", ".", s)  # "4 . 1" -> "4.1"
    s = re.sub(r"(?<=\d)\.\s+(?=\d)", ".", s)     # "4. 1" -> "4.1"
    return s.strip()


def fix_name(name: str, fix_danji: bool = True) -> str:
    name = re.sub(r"[^\w가-힣\s()\-·]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    if fix_danji and re.search(r"\d+\s*단$", name):
        name = name + "지"
    return name


def parse_lines(lines: list[str], fix_danji: bool = True) -> SiseRecord:
    rec = SiseRecord()
    norm = [normalize_line(l) for l in lines if l and l.strip()]

    # 1) 연식 줄 찾기 ("98y 1350^")
    year_idx = -1
    for i, ln in enumerate(norm):
        m = _YEAR.search(ln)
        if m:
            rec.year = m.group(1)
            year_idx = i
            break

    # 2) 이름: 연식 줄 이전(없으면 전체)에서 한글이 있는 첫 줄
    name_range = norm[:year_idx] if year_idx >= 0 else norm
    for ln in name_range:
        if _HANGUL.search(ln):
            rec.name = fix_name(_YEAR.sub("", ln), fix_danji)
            break
    if not rec.name:
        # 연식 줄에 이름이 붙어 나온 경우 ("샘머리1단 98y")
        if year_idx >= 0 and _HANGUL.search(norm[year_idx]):
            rec.name = fix_name(_YEAR.split(norm[year_idx])[0], fix_danji)
    if not rec.name:
        rec.warnings.append("단지명을 찾지 못했습니다.")
    if not rec.year:
        rec.warnings.append("연식(NNy)을 찾지 못했습니다.")
    elif rec.year == "?":
        rec.warnings.append("연식 재인식 결과가 불확실합니다.")

    # 3) 숫자 토큰: 연식 줄 이후(없으면 이름 줄 제외 전체), 연식 줄 자체는 제외(세대수 때문)
    if year_idx >= 0:
        body = norm[year_idx + 1:]
    else:
        body = [ln for ln in norm if not _HANGUL.search(ln)]
    # 4) 면적 행 = 연식 이후 첫 숫자 줄 (줄은 OCR 단계에서 위치 기반으로 행 복원됨). 그 다음 줄들 = 시세 값
    areas: list[str] = []
    value_rows: list[list[str]] = []
    seen_area_row = False
    for ln in body:
        if _HANGUL.search(ln):
            continue  # 표 아래 다른 한글 줄은 무시
        ln = re.sub(r"\d+\s*[\^~]", " ", ln)  # 세대수 표기("1350^")가 별줄로 떨어진 경우
        toks = ["-" if _DASH.match(t) else t.replace("−", "-").replace("–", "-") for t in _NUM.findall(ln)]
        if not toks:
            continue
        if not seen_area_row:
            seen_area_row = True
            toks = [t for t in toks if not _DASH.match(t)]
            areas = [t for t in toks if t == "?" or (not _DEC.match(t) and 2 <= len(t) <= 3)]
            # 면적 행에 소수가 섞여 있으면(행 병합 오류) 소수는 값으로
            decimals = [t for t in toks if _DEC.match(t)]
            if decimals:
                value_rows.append(decimals)
        else:
            n = len(areas)
            if n and len(toks) > n:
                # 1) 세로 격자선이 '1' 로 읽힌 것 먼저 제거 (실측 "2.6 1 3.7")
                while len(toks) > n and "1" in toks:
                    toks.remove("1")
                    rec.warnings.append("격자선으로 보이는 '1' 토큰을 제거했습니다.")
                # 2) 그래도 많으면: 표는 열이 정렬되어 있으므로 값은 뒤쪽 n개, 앞의 잉여는 표 밖 잡음 (실측 "H21 5")
                if len(toks) > n:
                    rec.warnings.append(f"행의 값이 {len(toks)}개 > 면적 {n}개 — 앞의 {toks[:-n]} 를 버렸습니다.")
                    toks = toks[-n:]
            value_rows.append(toks)
    # 면적이 하나도 안 잡혔는데 소수만 있으면 한 열로 간주
    if not areas and value_rows:
        rec.warnings.append("면적 행을 찾지 못했습니다.")
    rec.areas = areas
    if "?" in areas:
        rec.warnings.append("면적 재인식 결과가 불확실합니다. 열 위치는 유지했습니다.")

    if areas and value_rows:
        n = len(areas)
        for i, row in enumerate(value_rows):
            if len(row) != n:
                label = "마지막 행" if i == len(value_rows) - 1 else f"값 {i + 1}행"
                rec.warnings.append(f"{label}의 값 개수가 면적 개수({n})와 다릅니다: {row} — 해당 행 확인 필요")
                # 좌표가 없는 불완전한 줄은 어느 열이 빠졌는지 알 수 없다.
                rec.rows.append(["?"] * n)
            else:
                rec.rows.append(row)
            if "?" in rec.rows[-1]:
                rec.warnings.append(f"값 {i + 1}행에 인식하지 못한 칸(?)이 있습니다.")
    if not value_rows:
        rec.warnings.append("시세 값을 찾지 못했습니다.")
    return rec


PYEONG_DIVISOR = 2.48   # 전용면적(m²) → 공급 평형: 3.3058 m²/평 × 전용률 0.75  (59/60→24, 84/85→34, 114→46)


def to_pyeong(area: str, divisor: float = PYEONG_DIVISOR) -> str:
    """'84' (전용 m²) -> '34' (공급 평, 반올림 정수). 숫자가 아니면 그대로."""
    try:
        return str(int(round(float(area) / divisor)))
    except (ValueError, ZeroDivisionError, TypeError):
        return area


def conversion_info(rec: SiseRecord, divisor: float = PYEONG_DIVISOR) -> str:
    """'60m² → 24평, 85m² → 34평' 형태의 확인용 문자열."""
    return ", ".join(f"{a}m² → {to_pyeong(a, divisor)}평" for a in rec.areas)


def as_price(v: str) -> str:
    """매매가/전세가는 항상 소수(float) 표기: '4' -> '4.0', '11' -> '11.0', '4.1' 은 그대로. 값 없음(대시)은 '-'."""
    if _DASH.match(v):
        return "-"
    return f"{v}.0" if re.fullmatch(r"-?\d+", v) else v


def format_record(rec: SiseRecord, rows_to_use: int = 2, area_divisor: float | None = None) -> str:
    """area_divisor 가 주어지면 면적을 평형으로 바꿔 출력한다 ('24) 4.1/2.6'). 값(매매/전세)은 float 표기."""
    head = " ".join(x for x in (rec.name, rec.year) if x)
    out = [head] if head else []
    use = rec.rows[:max(1, rows_to_use)]
    for col, area in enumerate(rec.areas):
        if area_divisor:
            area = to_pyeong(area, area_divisor)
        vals = [as_price(r[col]) for r in use if col < len(r)]
        if vals:
            out.append(f"{area}) {'/'.join(vals)}")
        else:
            out.append(f"{area}) ")
    return "\n".join(out)


def lines_to_text(lines: list[str], fix_danji: bool = True, rows_to_use: int = 2,
                  area_divisor: float | None = None) -> tuple[str, SiseRecord]:
    rec = parse_lines(lines, fix_danji)
    return format_record(rec, rows_to_use, area_divisor), rec
