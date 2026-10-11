"""OCR 엔진 래퍼 — Windows 내장 OCR(winocr) 을 기본으로 사용한다.

recognize(image, lang) -> list[str]  (줄 단위 텍스트)

winocr 는 Windows.Media.Ocr 을 파이썬에서 호출하는 패키지다.
  pip install winocr
한국어 인식은 Windows 설정 > 시간 및 언어 > 언어 에 "한국어" 언어팩이 있어야 한다.
"""
from __future__ import annotations

import logging
import os
import re

from PIL import Image

log = logging.getLogger("SisePicker")


class OcrUnavailableError(RuntimeError):
    pass


class OcrLanguageMissingError(OcrUnavailableError):
    """OCR 엔진은 있지만 해당 언어의 Windows OCR 팩이 없다."""

    def __init__(self, msg: str, lang: str, tag: str):
        super().__init__(msg)
        self.lang = lang
        self.tag = tag


_LANG_TAGS = {"ko": "ko-KR", "en": "en-US", "ja": "ja-JP", "zh": "zh-CN"}


def capability_name(lang: str) -> str:
    tag = _LANG_TAGS.get(lang, lang)
    return f"Language.OCR~~~{tag}~0.0.1.0"


def install_ocr_pack(lang: str) -> bool:
    """관리자 권한(UAC) PowerShell 로 Windows OCR 언어팩을 설치한다. 창을 띄우고 바로 돌아온다.

    exe 하나만 배포해도 되도록 별도 bat 없이 앱 안에서 처리한다.
    """
    import ctypes

    cap = capability_name(lang)
    ps = (
        f"Write-Host 'Installing Windows OCR pack {cap} ... (1-3 min, internet required)'; "
        f"Add-WindowsCapability -Online -Name '{cap}'; "
        f"Get-WindowsCapability -Online -Name 'Language.OCR*' | Where-Object State -eq 'Installed' "
        f"| Select-Object -ExpandProperty Name; "
        f"Write-Host ''; Write-Host 'Done. Start SisePicker again.'; Read-Host 'Press Enter to close'"
    )
    args = f'-NoProfile -ExecutionPolicy Bypass -Command "{ps}"'
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", args, None, 1)
        return rc > 32
    except Exception:
        return False


def _flatten(image: Image.Image) -> Image.Image:
    img = image
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg
    return img.convert("RGB")


def _prepare(image: Image.Image, scale: int) -> Image.Image:
    """OCR 전처리 (실측 기반).

    1) 알파는 흰 배경으로 합치고 확대 (작은 캡쳐는 확대해야 숫자 인식률이 올라간다).
    2) 녹색/주황 강조 셀(흰 글자)만 반전해 배경이 흰색이 되게 한다 — 회색조(안티앨리어싱) 유지.
       딱딱한 이진화는 Windows OCR 이 작은 숫자를 못 읽어(4.1→41, 행 누락) 쓰지 않는다.
    3) 표의 세로/가로 격자선을 지운다 — 세로선이 '1' 로 읽히는 것(실측: "2.6 1 3.7") 방지.
    """
    small = _flatten(image)
    scale = max(1, int(scale or 1))
    w, h = small.size
    big = small.resize((w * scale, h * scale), Image.LANCZOS) if scale > 1 else small
    gray = _invert_colored_cells(big, scale)
    gray = _erase_grid_lines(gray, small.convert("L"), scale)
    return gray.convert("RGB")


def _invert_colored_cells(big_rgb: Image.Image, scale: int) -> Image.Image:
    """채도 높은 셀 영역만 밝기 반전 + 배경이 흰색(≈245)이 되도록 배율. 나머지는 원본 회색조."""
    from PIL import ImageFilter, ImageOps

    gray = big_rgb.convert("L")
    sat = big_rgb.convert("HSV").split()[1]
    # 닫힘(팽창→침식): 셀 안의 흰 글자 구멍은 메우고, 셀 바깥으로는 번지지 않게 한다
    # (팽창만 하면 셀 주변 흰 여백까지 반전되어 굵은 검은 띠가 생긴다 — 실측)
    k = max(3, (2 * scale + 1) * 2 + 1)
    mask = sat.point(lambda v: 255 if v >= 90 else 0).filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    if not mask.getbbox():
        return gray
    inverted = ImageOps.invert(gray)
    hist = Image.composite(inverted, Image.new("L", gray.size, 0), mask).histogram()
    # 마스크 안에서 글자(반전 후 어두운 값, <40)를 뺀 히스토그램의 봉우리들 = 셀 배경색.
    # 가장 밝은 배경(작은 값)을 245 로 보내면 더 어두운 배경은 흰색으로 잘린다.
    body = hist[40:]
    peak = max(body) if body else 0
    factor = 1.0
    if peak:
        for v in range(40, 256):
            if hist[v] >= peak * 0.3:
                factor = 245.0 / v
                break
    inverted = inverted.point(lambda v: min(255, int(v * factor)))
    return Image.composite(inverted, gray, mask)


def _erase_grid_lines(gray_big: Image.Image, gray_small: Image.Image, scale: int,
                      col_ratio: float = 0.45, row_ratio: float = 0.6) -> Image.Image:
    """어두운 픽셀이 세로로 45%/가로로 60% 이상 차지하는 열/행 = 격자선 → 흰색으로.

    판정은 처리된 이미지를 원본 크기로 줄인 것(BOX)에서 하고, 지우기는 확대 이미지에 한다.
    """
    w, h = gray_small.size
    gray_small = gray_big.resize((w, h), Image.BOX)
    px = list(gray_small.getdata())
    dark = [v < 110 for v in px]
    col_counts = [0] * w
    row_counts = [0] * h
    for y in range(h):
        base = y * w
        for x in range(w):
            if dark[base + x]:
                col_counts[x] += 1
                row_counts[y] += 1
    out = gray_big.copy()
    from PIL import ImageDraw
    d = ImageDraw.Draw(out)
    W, H = out.size
    for x, c in enumerate(col_counts):
        if c >= h * col_ratio:
            d.rectangle([x * scale - 1, 0, (x + 1) * scale, H], fill=255)
    for y, c in enumerate(row_counts):
        if c >= w * row_ratio:
            d.rectangle([0, y * scale - 1, W, (y + 1) * scale], fill=255)
    return out


def _plain(image: Image.Image, scale: int) -> Image.Image:
    """색 셀 반전 없이 확대 + 격자선 제거만 한 회색조 (2차 OCR 용)."""
    small = _flatten(image)
    scale = max(1, int(scale or 1))
    big = small.resize((small.width * scale, small.height * scale), Image.LANCZOS) if scale > 1 else small
    gray = _erase_grid_lines(big.convert("L"), small.convert("L"), scale)
    return gray.convert("RGB")


def _save_debug(img: Image.Image) -> None:
    """OCR 에 실제로 넘긴 이미지를 logs\\last_ocr_input.png 로 남긴다 (인식 문제 진단용)."""
    try:
        from app_paths import app_dir
        d = os.path.join(app_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        img.save(os.path.join(d, "last_ocr_input.png"))
    except Exception:
        pass


def _rect(word) -> tuple[float, float, float, float] | None:
    r = word.get("bounding_rect") if isinstance(word, dict) else getattr(word, "bounding_rect", None)
    if r is None:
        return None
    get = (lambda k: r.get(k)) if isinstance(r, dict) else (lambda k: getattr(r, k, None))
    try:
        return float(get("x")), float(get("y")), float(get("width")), float(get("height"))
    except (TypeError, ValueError):
        return None


def words_to_rows(words: list[tuple[float, float, float, float, str]]) -> list[str]:
    """단어 상자들을 y 로 행 묶음, x 로 정렬해 표의 행 순서대로 줄을 만든다.

    Windows OCR 은 표를 열 단위로 읽는 경우가 있어(60, 2.6, 1.5, 85, ...) 위치로 다시 행을 만든다.
    """
    if not words:
        return []
    rows = _cluster_rows(words)
    return [" ".join(t[4] for t in sorted(row, key=lambda t: t[0])) for row in rows]


def _overlap(a, b) -> float:
    """두 상자의 겹침 비율 (작은 상자 기준)."""
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    small = min(aw * ah, bw * bh) or 1.0
    return inter / small


def merge_results(primary, secondary) -> list[str]:
    """(테스트/호환용) 두 결과를 합쳐 행으로."""
    merged = merge_words([(primary, 1.0), (secondary, 1.0)])
    if not merged:
        return _result_to_lines(primary) or _result_to_lines(secondary)
    return words_to_rows(merged)


def _words(result) -> list[tuple]:
    words: list[tuple] = []
    for ln in (result or {}).get("lines", []):
        ws = ln.get("words", []) if isinstance(ln, dict) else getattr(ln, "words", [])
        for wd in ws or []:
            wt = wd.get("text") if isinstance(wd, dict) else getattr(wd, "text", None)
            rc = _rect(wd)
            if wt and rc:
                words.append((*rc, wt.strip()))
    return words


def _result_to_lines(result) -> list[str]:
    words: list[tuple] = []
    texts: list[str] = []
    for ln in result.get("lines", []):
        text = ln.get("text") if isinstance(ln, dict) else getattr(ln, "text", None)
        if text:
            texts.append(text.strip())
        ws = ln.get("words", []) if isinstance(ln, dict) else getattr(ln, "words", [])
        for wd in ws or []:
            wt = wd.get("text") if isinstance(wd, dict) else getattr(wd, "text", None)
            rc = _rect(wd)
            if wt and rc:
                words.append((*rc, wt.strip()))
    if words:
        return words_to_rows(words)
    if not texts and result.get("text"):
        texts = [s.strip() for s in str(result["text"]).splitlines() if s.strip()]
    return texts


def recognize(image: Image.Image, lang: str = "ko", scale: int = 4) -> list[str]:
    """이미지에서 표의 행 순서대로 줄 텍스트를 뽑는다.

    엔진 조합 (실측 근거):
      - 숫자: RapidOCR(PaddleOCR PP-OCRv4, onnxruntime, exe 에 내장) — Windows OCR 이 굵은 강조 셀 숫자(4.1, 5.3)를
        통째로 놓치거나 '41'/'鏖3' 으로 읽는 반면, RapidOCR 은 모든 변형에서 신뢰도 1.0 으로 읽었다.
      - 한글(단지명): RapidOCR 내장 모델은 중국어/영어용이라 한글을 못 읽으므로 Windows OCR 결과로 보충한다.
    RapidOCR 이 없으면(개발 환경 등) Windows OCR 다중 변형으로만 처리한다.
    """
    words: list[tuple] = []
    rapid_ok = False
    try:
        words = _rapid_words(image, scale)
        rapid_ok = True
    except OcrUnavailableError as e:
        log.warning("RapidOCR 사용 불가, Windows OCR 만 사용: %s", e)

    try:
        win_results = _windows_results(image, scale, lang, variants=1 if rapid_ok else 5)
    except OcrLanguageMissingError:
        if not rapid_ok:
            raise
        log.warning("Windows OCR 언어팩 없음 — 단지명(한글)은 인식되지 않습니다.")
        win_results = []
    except OcrUnavailableError:
        if not rapid_ok:
            raise
        win_results = []

    if rapid_ok:
        win_words = merge_words(win_results)
        ko_words = _rapid_korean_words(image, scale)          # 한국어 모델이 있으면 단지명은 이것을 우선
        words = _combine_rapid_windows(words, win_words, ko_words)
    else:
        words = merge_words(win_results)

    words = filter_table_words(words)
    if rapid_ok:
        detected = words
        words = _verify_price_cells(image, words, scale)
        try:
            import json
            from cell_reader import verify
            from app_paths import app_dir
            words, cells = verify(image, detected, words, scale, _cluster_rows, _get_rapid(), _has_decimal_shape)
            with open(os.path.join(app_dir(), "logs", "last_ocr_full_cells.json"), "w", encoding="utf-8") as handle:
                json.dump(cells, handle, ensure_ascii=False, indent=2)
        except Exception:
            log.exception("전체 셀 검증 실패 — 기존 인식 결과 유지")
    return words_to_rows(words)


def _choose_cell_value(original: str, candidates: list[dict], source_height: float) -> tuple[str, str]:
    """높은 신뢰도도 소수점 손실을 보장하지 않으므로 원본 해상도를 함께 검사한다."""
    if source_height < 10:
        expected = {"color", "contrast", "nearest", "inverse_smooth", "inverse_nearest"}
        if (re.fullmatch(r"-?\d+\.\d+", original)
                and {c.get("variant") for c in candidates} == expected
                and len(candidates) == len(expected)
                and all(c["text"] == original and c["score"] >= .95 for c in candidates)):
            return original, "작은 글자: 다섯 방식의 소수점 포함 결과 일치"
        return "?", "원본 글자 높이 10px 미만 — 더 크게 캡처 필요"
    usable = [c for c in candidates if c["score"] >= 0.8 and _VALUE_RE.fullmatch(c["text"])]
    values = {c["text"] for c in usable}
    if len(usable) < 2 or max((c["score"] for c in usable), default=0) < 0.9:
        return "?", "셀 재인식 신뢰도 부족"
    if len(values) != 1 or (original != "?" and original not in values):
        return "?", "전체 표와 셀 재인식 후보 불일치"
    return usable[0]["text"], "재인식 일치"


def _verify_price_cells(image: Image.Image, words: list[tuple], scale: int) -> list[tuple]:
    """면적 행 아래 숫자를 원본색/강조색 반전/원본 픽셀 확대로 재인식한다.

    기존 좌표계를 유지하며 불확실한 값은 ?로 반환한다. 후보와 신뢰도는
    last_ocr_cells.json에 기록한다. 소수점을 임의로 삽입하지 않는다.
    """
    import json
    import math
    import numpy as np
    from PIL import ImageOps
    from app_paths import app_dir

    if not words:
        return words
    rows = _cluster_rows(words)
    area_index = next((i for i, row in enumerate(rows)
                       if row and all(_AREA_RE.fullmatch(w[4]) for w in row)), None)
    if area_index is None:
        return words
    big = _plain_rgb(image, scale)
    factor = max(1, int(scale or 1))
    source = _flatten(image)
    output = [w for row in rows[:area_index + 1] for w in row]
    diagnostics = []
    engine = None
    for row in rows[area_index + 1:]:
        for word in row:
            x, y, w, h, original = word
            # ? 상자는 실제 글자 검출 상자가 아니라 합성 좌표이므로 재인식에 쓰지 않는다.
            if (not _VALUE_RE.fullmatch(original)
                    or w <= 0 or h <= 0 or x < 0 or y < 0
                    or x + w > big.width or y + h > big.height):
                output.append(word)
                continue
            bounds = (max(0, math.floor(x - h * .2)), max(0, math.floor(y - h * .15)),
                      min(big.width, math.ceil(x + w + h * .2)), min(big.height, math.ceil(y + h * 1.15)))
            crop = big.crop(bounds)
            candidates = []
            try:
                if engine is None:
                    engine = _get_rapid()
                variants = [("color", crop), ("contrast", _invert_colored_cells(crop, factor).convert("RGB"))]
                # 부드럽게 확대한 영상을 다시 확대하면 사라진 소수점이 복원되지 않는다.
                # 원본에서 직접 잘라 픽셀 경계를 보존한 독립 후보를 비교한다.
                native_bounds = (bounds[0] // factor, bounds[1] // factor,
                                 math.ceil(bounds[2] / factor), math.ceil(bounds[3] / factor))
                native = source.crop(native_bounds)
                decimal_shape = _has_decimal_shape(native)
                native_scale = max(4, factor)
                inverted = ImageOps.invert(native.convert("L"))
                inverted_size = (native.width * native_scale, native.height * native_scale)
                native = native.resize((native.width * native_scale, native.height * native_scale),
                                       Image.Resampling.NEAREST)
                variants.append(("nearest", native))
                for label, variant in variants:
                    result, _ = engine(np.array(variant), use_det=False, use_cls=False)
                    if result and len(result) == 1:
                        text, score = result[0][:2]
                        text = str(text).strip().replace("−", "-")
                        if _DASH_RE.fullmatch(text):
                            text = "-"
                        candidates.append({"variant": label, "text": text, "score": float(score)})
                value, reason = _choose_cell_value(original, candidates, h / factor)
                integer_price = bool(re.fullmatch(r"-?\d+", original))
                if value == "?" or integer_price:
                    for label, method in [("inverse_smooth", Image.Resampling.LANCZOS),
                                          ("inverse_nearest", Image.Resampling.NEAREST)]:
                        variant = inverted.resize(inverted_size, method).convert("RGB")
                        result, _ = engine(np.array(variant), use_det=False, use_cls=False)
                        if result and len(result) == 1:
                            text, score = result[0][:2]
                            candidates.append({"variant": label, "text": str(text).strip(),
                                               "score": float(score)})
                    if integer_price:
                        # 정수 후보도 반전 검사를 생략하지 않는다. 검사 누락/저신뢰도는 확정하지 않는다.
                        inverse = [c for c in candidates if c.get("variant", "").startswith("inverse_")]
                        value, reason = _choose_cell_value(original, candidates, h / factor)
                        if len(inverse) != 2 or any(c["score"] < .9 for c in inverse):
                            value, reason = "?", "정수 가격 색반전 검증 부족"
                        if value == "?":
                            value, reason = _recover_decimal_from_inversion(original, candidates, h / factor, reason)
                        if re.fullmatch(r"-?\d+", value) and decimal_shape:
                            value, reason = "?", "원본 글자 하단에 소수점 의심 형태 — 직접 확인 필요"
                    elif h / factor < 10:
                        value, reason = _choose_cell_value(original, candidates, h / factor)
                    else:
                        value, reason = _recover_decimal_from_inversion(original, candidates, h / factor, reason)
            except Exception as exc:
                value, reason = "?", f"셀 재인식 실패: {exc}"
            output.append((x, y, w, h, value))
            diagnostics.append({"box": [x / factor, y / factor, w / factor, h / factor],
                                "original": original, "candidates": candidates,
                                "selected": value, "reason": reason})
            if value == "?":
                log.warning("시세 셀 %r 확인 필요: %s", original, reason)
    try:
        directory = os.path.join(app_dir(), "logs")
        os.makedirs(directory, exist_ok=True)
        image.save(os.path.join(directory, "last_ocr_original.png"))
        with open(os.path.join(directory, "last_ocr_cells.json"), "w", encoding="utf-8") as handle:
            json.dump(diagnostics, handle, ensure_ascii=False, indent=2)
    except Exception:
        log.exception("셀 재인식 진단 로그 저장 실패")
    return output


def _has_decimal_shape(crop):
    """작은 점 또는 숫자 밑줄에 붙은 점 모양을 감지한다. 값 보정에는 사용하지 않는다."""
    import cv2
    import numpy as np
    gray = np.array(crop.convert("L"))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    border = np.concatenate((mask[0], mask[-1], mask[:, 0], mask[:, -1]))
    if np.median(border) > 0:
        mask = 255 - mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    bodies = [s for s in stats[1:] if s[3] >= 6 and s[4] >= 8]
    if not bodies:
        return False
    baseline = max(int(s[1] + s[3]) for s in bodies)
    for index in range(1, count):
        x, y, w, h, area = map(int, stats[index])
        if 2 <= area <= 9 and w <= 3 and h <= 3 and baseline - 3 <= y + h <= baseline + 1:
            return True
        if h >= 6 and w >= 5:
            tail = labels[y:y + h, x + w - 2:x + w] == index
            ys = np.where(tail)[0]
            if len(ys) >= 3 and ys.min() >= h * .65 and ys.max() - ys.min() >= 1:
                return True
    return False


def _recover_decimal_from_inversion(original, candidates, source_height, reason):
    """서로 다른 확대의 반전 후보가 일치하고 차이가 소수점뿐일 때만 복구한다."""
    inverted = [c for c in candidates if c.get("variant") in {"inverse_smooth", "inverse_nearest"}]
    if source_height < 10 or len(inverted) != 2 or any(c["score"] < .9 for c in inverted):
        return "?", reason
    value = inverted[0]["text"]
    if inverted[1]["text"] != value or not re.fullmatch(r"-?\d+\.\d+", value):
        return "?", reason
    # 기존 영상에서도 소수점 후보가 한 번 이상 관측돼야 한다.
    previous = [c for c in candidates if not c.get("variant", "").startswith("inverse_")
                and c["score"] >= .8]
    allowed = {value, value.replace(".", "")}
    if (original not in allowed or not any(c["text"] == value for c in previous)
            or any(c["text"] not in allowed for c in previous)):
        return "?", reason
    return value, "가격 칸 색반전의 두 확대 후보 일치 — 소수점 복구"


_HANGUL_RE = re.compile(r"[가-힣]")
_YEAR_TOKEN_RE = re.compile(r"^\d{2}\s*[yY년]")


def _combine_rapid_windows(rapid: list[tuple], win: list[tuple], ko: list[tuple] | None = None) -> list[tuple]:
    """행 단위로 엔진을 나눈다: 첫 행(단지명, 한글) = Windows OCR, 연식 행부터 = RapidOCR.

    캡쳐는 항상 '단지명 / 연식 / 표' 순서이므로 RapidOCR 의 연식 토큰(NNy) 위치를 경계로 삼는다.
    경계 위의 RapidOCR 단어(한글을 숫자로 읽은 잡음)는 버리고, Windows OCR 이 그 위에서 읽은 한글 행을 넣는다.
    연식 행을 못 찾으면 예전 방식(RapidOCR 우선 + 한글 보충)으로 합친다.
    """
    years = [w for w in rapid if _YEAR_TOKEN_RE.match(w[4])] or [w for w in win if _YEAR_TOKEN_RE.match(w[4])]
    if years:
        y_top = min(w[1] for w in years)
        h = years[0][3]
        boundary = y_top - h * 0.3
        body = [w for w in rapid if w[1] + w[3] / 2 >= boundary]
        win_body = [w for w in win if w[1] + w[3] / 2 >= boundary]
        body = repair_table(body, win_body)
        name_words: list[tuple] = []
        if ko:
            # RapidOCR 한국어 모델(models\\korean_*.onnx)이 있으면 단지명은 이것을 우선 사용
            above_ko = [w for w in ko if w[1] + w[3] / 2 < boundary and _HANGUL_RE.search(w[4])]
            name_words = [w for row in _cluster_rows(above_ko) for w in row] if above_ko else []
        if not name_words:
            above = [w for w in win if w[1] + w[3] / 2 < boundary]
            name_rows = [row for row in _cluster_rows(above) if any(_HANGUL_RE.search(w[4]) for w in row)] if above else []
            name_words = [w for row in name_rows for w in row]
        if not name_words:
            # Windows 가 한글을 못 읽었으면 RapidOCR 의 위쪽 단어라도(잡음 제외) 남긴다
            name_words = [w for w in rapid if w[1] + w[3] / 2 < boundary and not _is_noise_token(w)]
        return name_words + body

    win_hangul = [w for w in win if _HANGUL_RE.search(w[4])]
    merged = list(rapid)
    for wd in win_hangul:
        clash = [ex for ex in merged if _overlap(wd, ex) >= 0.3]
        if not clash:
            merged.append(wd)
        elif all(_is_noise_token(ex) for ex in clash):
            merged = [ex for ex in merged if ex not in clash] + [wd]
    return merged


_AREA_RE = re.compile(r"^\d{2,3}$")
_DASH_RE = re.compile(r"^[-–—_ー一]+$")            # 값 없음 셀의 대시 (OCR 이 '—', '_', '一' 로도 읽음)
_VALUE_RE = re.compile(r"^([-−–]?\d+(\.\d+)?|[-–—_ー一]+)$")


def repair_table(body: list[tuple], win_body: list[tuple]) -> list[tuple]:
    """표 구조 제약으로 RapidOCR 결과를 보정한다: 3~5행(면적/매매/전세)은 열 수가 같아야 한다.

    body 는 연식 행부터의 RapidOCR 단어, win_body 는 같은 영역의 Windows OCR 단어(예비).
    1) 값 행(4·5행)의 단어 x 중심을 묶어 열을 정한다 (열 수 = 표의 열 수).
    2) 면적 행(3행)의 각 열에 2~3자리 정수가 없으면 → 그 자리의 잡음 토큰(실측 '74'→'t2')을 버리고
       Windows OCR 이 같은 자리에서 읽은 정수로 채운다.
    3) 값 행의 빈 열도 Windows OCR 의 숫자로 채운다.
    """
    if not any(_YEAR_TOKEN_RE.match(w[4]) for w in body):
        body = list(body) + [w for w in win_body if _YEAR_TOKEN_RE.match(w[4])]
    if not body:
        return body
    rows = _cluster_rows(body)
    if len(rows) < 3:
        return body
    year_row, area_row, value_rows = rows[0], rows[1], rows[2:]
    if not any(_YEAR_TOKEN_RE.match(w[4]) for w in year_row):
        return body

    # 열 중심: 값 행 단어 + 면적 행의 유효 정수
    seeds = [w for r in value_rows for w in r] + [w for w in area_row if _AREA_RE.match(w[4])]
    if not seeds:
        return body
    med_w = sorted(w[2] for w in seeds)[len(seeds) // 2] or 1.0
    tol = max(med_w * 0.8, 10.0)
    centers: list[float] = []
    for w in sorted(seeds, key=lambda t: t[0] + t[2] / 2):
        xc = w[0] + w[2] / 2
        for i, c in enumerate(centers):
            if abs(c - xc) <= tol:
                centers[i] = (c + xc) / 2
                break
        else:
            centers.append(xc)
    centers.sort()

    def nearest_col(w):
        xc = w[0] + w[2] / 2
        i = min(range(len(centers)), key=lambda k: abs(centers[k] - xc))
        return i if abs(centers[i] - xc) <= tol else None

    def win_at(row, col, pattern):
        ryc = sum(t[1] + t[3] / 2 for t in row) / len(row)
        rh = sum(t[3] for t in row) / len(row)
        cands = [w for w in win_body
                 if abs((w[1] + w[3] / 2) - ryc) <= rh * 0.6 and nearest_col(w) == col and pattern.match(w[4])]
        return min(cands, key=lambda w: abs(centers[col] - (w[0] + w[2] / 2))) if cands else None

    # RapidOCR이 행 전체를 놓쳐도 Windows가 읽은 행은 복원한다.
    # 엔진마다 상자 높이가 달라 Windows 면적 글자의 중심이 Rapid 면적 중심보다
    # 아래일 수 있다. 중심이 아닌 면적 행 하단으로 구분해야 면적을 값 행에 재삽입하지 않는다.
    area_bottom = max(w[1] + w[3] for w in area_row)
    additions = [w for w in win_body if w[1] + w[3] / 2 > area_bottom
                 and nearest_col(w) is not None and _VALUE_RE.fullmatch(w[4])]
    value_rows = _cluster_rows([w for row in value_rows for w in row] + additions)
    primary_words = set(body)

    out = list(year_row)
    # 면적 행
    fixed_area = []
    for col in range(len(centers)):
        here = [w for w in area_row if nearest_col(w) == col]
        good = [w for w in here if _AREA_RE.match(w[4])]
        if good:
            fixed_area.append(good[0])
        else:
            alt = win_at(area_row, col, _AREA_RE)
            if alt:
                log.info("면적 행 %d열: RapidOCR %r → Windows %r 로 보정", col, [w[4] for w in here], alt[4])
                fixed_area.append(alt)
            elif here:
                fixed_area.append(here[0])          # 대안이 없으면 원래 토큰 유지(파서 경고로 드러남)
    out.extend(fixed_area)
    # 값 행
    for row in value_rows:
        for col in range(len(centers)):
            here = [w for w in row if nearest_col(w) == col]
            good = [w for w in here if w in primary_words and _VALUE_RE.match(w[4])]
            if good:
                out.append(min(good, key=lambda w: abs(centers[col] - (w[0] + w[2] / 2))))
            else:
                alt = win_at(row, col, _VALUE_RE)
                if alt:
                    log.info("값 행 %d열: RapidOCR %r → Windows %r 로 보정", col, [w[4] for w in here], alt[4])
                    out.append(alt)
                else:
                    # 누락을 대시(실제 값 없음)와 구분하고 열 위치를 유지한다.
                    ry = sum(w[1] for w in row) / len(row)
                    rh = sum(w[3] for w in row) / len(row)
                    out.append((centers[col] - rh / 4, ry, rh / 2, rh, "?"))
        # 열에 못 붙은 단어(표 밖)는 버린다
    return out


_CLEAN_NUM_RE = re.compile(r"^\d+(\.\d+)?[y년^~]?$")   # 60, 4.1, 98y, 1350^


def _is_noise_token(w: tuple) -> bool:
    """한글 단어 자리에서 RapidOCR 이 읽은 것이 잡음인지: 깨끗한 숫자 토큰이 아니거나, 한 글자이거나,
    글자 수에 비해 상자가 지나치게 넓으면(실측 '2' 가 단지명 상자 전체 폭) 잡음."""
    x, y, bw, bh, t = w
    if not _CLEAN_NUM_RE.match(t) or len(t) <= 1:
        return True
    density = bw / max(1.0, bh * len(t))
    return density > 1.5
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_rapid_engine = None


KOREAN_MODEL_NAME = "korean_PP-OCRv4_rec_mobile.onnx"
KOREAN_KEYS_NAME = "korean_dict.txt"
_rapid_ko_engine = None
_rapid_ko_checked = False


def _get_rapid():
    global _rapid_engine
    if _rapid_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa: WPS433
        except ImportError as e:
            raise OcrUnavailableError(f"rapidocr_onnxruntime 없음 ({e})") from e
        _rapid_engine = RapidOCR()
    return _rapid_engine


def korean_model_path() -> str | None:
    """RapidOCR 한국어 인식 모델 위치. 앱 폴더(exe 옆) 또는 PyInstaller 번들의 models\\ 에서 찾는다."""
    import sys

    from app_paths import app_dir
    cands = [os.path.join(app_dir(), "models", KOREAN_MODEL_NAME)]
    if getattr(sys, "_MEIPASS", None):
        cands.append(os.path.join(sys._MEIPASS, "models", KOREAN_MODEL_NAME))
    cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", KOREAN_MODEL_NAME))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def _get_rapid_korean():
    """한국어 모델이 있으면 그 모델로 인식하는 RapidOCR 엔진, 없으면 None (한 번만 검사)."""
    global _rapid_ko_engine, _rapid_ko_checked
    if _rapid_ko_checked:
        return _rapid_ko_engine
    _rapid_ko_checked = True
    path = korean_model_path()
    if not path:
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: WPS433
        kwargs = {"rec_model_path": path}
        keys = os.path.join(os.path.dirname(path), KOREAN_KEYS_NAME)
        if os.path.isfile(keys):
            kwargs["rec_keys_path"] = keys       # 모델에 글자표가 내장돼 있지 않은 경우만 필요
        _rapid_ko_engine = RapidOCR(**kwargs)
        log.info("RapidOCR 한국어 모델 사용: %s", path)
    except Exception as e:
        log.warning("한국어 모델 로드 실패(%s) — Windows OCR 로 단지명 인식: %s", path, e)
        _rapid_ko_engine = None
    return _rapid_ko_engine


def _rapid_korean_words(image: Image.Image, scale: int) -> list[tuple]:
    eng = _get_rapid_korean()
    if eng is None:
        return []
    try:
        return _rapid_words(image, scale, engine=eng, keep_cjk=True, label="rapid-ko")
    except OcrUnavailableError as e:
        log.warning("한국어 모델 인식 실패: %s", e)
        return []


def _rapid_words(image: Image.Image, scale: int, engine=None, keep_cjk: bool = False,
                 label: str = "rapid") -> list[tuple]:
    """RapidOCR 로 확대한 원본을 읽어 (x, y, w, h, text) 단어 목록으로. 줄에 공백이 있으면 토큰별로 상자를 나눈다."""
    import numpy as np

    eng = engine if engine is not None else _get_rapid()
    img = _plain_rgb(image, scale)
    if label == "rapid":
        _save_debug(img)
    try:
        result, _ = eng(np.array(img))
    except Exception as e:
        raise OcrUnavailableError(f"RapidOCR 실행 실패: {e}") from e
    words: list[tuple] = []
    for item in result or []:
        box, text, score = item[0], str(item[1]), float(item[2])
        text = text.strip()
        if _DASH_RE.match(text):
            text = "-"      # 값 없음 셀의 대시 ('一' 는 CJK 지만 대시로 본다)
        elif _CJK_RE.search(text) and not keep_cjk:
            continue        # 중국어 모델이 한글 단지명을 한자로 읽은 것 → 통째로 버림 (실측: '叶2R' 등, 잔여 '2' 도 잡음)
        if not text or score < 0.5:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        words.extend(_split_tokens(x, y, w, h, text))
    _save_debug_words(0, {"lines": [{"text": t, "words": [
        {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}}]} for x, y, w, h, t in words]},
        label=label)
    return words


def _split_tokens(x: float, y: float, w: float, h: float, text: str) -> list[tuple]:
    toks = text.split()
    if len(toks) <= 1:
        return [(x, y, w, h, text)]
    total = sum(len(t) for t in toks) + (len(toks) - 1)   # 공백 포함 글자 수 비례로 폭 배분
    out = []
    cur = 0
    for t in toks:
        tx = x + w * cur / total
        tw = w * len(t) / total
        out.append((tx, y, tw, h, t))
        cur += len(t) + 1
    return out


def _plain_rgb(image: Image.Image, scale: int) -> Image.Image:
    small = _flatten(image)
    scale = max(1, int(scale or 1))
    if scale > 1:
        small = small.resize((small.width * scale, small.height * scale), Image.LANCZOS)
    return small


def _windows_results(image: Image.Image, scale: int, lang: str, variants: int = 5) -> list[tuple]:
    """Windows OCR(winocr) 로 전처리 변형들을 읽어 [(result, 좌표배율)] 반환."""
    try:
        import winocr  # noqa: WPS433  (Windows 전용, 지연 import)
    except ImportError as e:
        raise OcrUnavailableError(
            "winocr 패키지가 없습니다.  pip install winocr  후 다시 실행하세요.\n"
            f"({e})"
        ) from e

    vs = _variants(image, scale)[:max(1, variants)]
    results = []
    try:
        for i, (im, factor) in enumerate(vs):
            r = winocr.recognize_pil_sync(im, lang)
            results.append((r, factor))
            _save_debug_words(i, r, label="windows")
    except Exception as e:  # winrt 쪽 예외 종류가 다양하다
        if results:
            log.warning("OCR 변형 %d 실패: %s", len(results), e)
        else:
            tag = _LANG_TAGS.get(lang, lang)
            raise OcrLanguageMissingError(
                f"Windows OCR 호출 실패 — 언어 '{lang}' OCR 팩이 설치되어 있지 않은 것 같습니다.\n\n"
                f"관리자 PowerShell 에서 다음을 실행하면 설치됩니다:\n"
                f"  Add-WindowsCapability -Online -Name \"{capability_name(lang)}\"\n"
                f"(설정 > 시간 및 언어 > 언어 및 지역 > 한국어 > 언어 옵션 > 광학 문자 인식 으로도 가능)\n\n"
                f"원본 오류: {e}", lang, tag
            ) from e
    return results


def _variants(image: Image.Image, scale: int) -> list[tuple[Image.Image, float]]:
    """OCR 에 넣어 볼 전처리 변형들 (이미지, 기준 대비 좌표 배율). 앞이 우선, 서로 놓친 글자를 보충한다.

    실측: Windows OCR 이 강조 셀(반전 후 흰 배경의 굵은 검은 숫자)을 어떤 변형에서는 통째로 무시한다.
    0) 색 셀 반전 회색조 + 격자선 제거            1) 0 을 살짝 흐림(굵은 글자 완화)
    2) 0 을 1.5배 더 확대                        3) 원본 회색조 + 격자선 제거
    4) 색 셀만 딱딱한 흑백(테두리 흰색으로)
    """
    from PIL import ImageFilter

    base = _prepare(image, scale)
    blurred = base.filter(ImageFilter.GaussianBlur(radius=max(0.6, scale * 0.25)))
    bigger = base.resize((int(base.width * 1.5), int(base.height * 1.5)), Image.LANCZOS)
    plain = _plain(image, scale)
    hard = _hard_cells(image, scale)
    return [(base, 1.0), (blurred, 1.0), (bigger, 1.5), (plain, 1.0), (hard, 1.0)]


def _hard_cells(image: Image.Image, scale: int) -> Image.Image:
    """색 셀 안만 흑백(흰 글자→검정, 나머지→흰색)으로 바꾸고 바깥은 원본 회색조."""
    from PIL import ImageFilter

    small = _flatten(image)
    scale = max(1, int(scale or 1))
    big = small.resize((small.width * scale, small.height * scale), Image.LANCZOS) if scale > 1 else small
    gray = big.convert("L")
    sat = big.convert("HSV").split()[1]
    k = max(3, (2 * scale + 1) * 2 + 1)
    mask = sat.point(lambda v: 255 if v >= 90 else 0).filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    if not mask.getbbox():
        return _erase_grid_lines(gray, small.convert("L"), scale).convert("RGB")
    light = gray.point(lambda v: 0 if v > 200 else 255)
    out = Image.composite(light, gray, mask)
    out = out.filter(ImageFilter.GaussianBlur(radius=0.7))
    return _erase_grid_lines(out, small.convert("L"), scale).convert("RGB")


def merge_words(results: list[tuple]) -> list[tuple]:
    """여러 변형의 (결과, 좌표배율)을 합친다. 앞 결과가 우선, 뒤 결과는 겹치지 않는 위치의 단어만 보충.

    1.5배 확대 변형의 상자는 배율로 나눠 기준 좌표로 맞춘다.
    """
    merged: list[tuple] = []
    for r, factor in results:
        for x, y, w, h, t in _words(r):
            wd = (x / factor, y / factor, w / factor, h / factor, t)
            if all(_overlap(wd, ex) < 0.3 for ex in merged):
                merged.append(wd)
    return merged


_AREA_TOKEN = re.compile(r"^\d{2,3}$")
_NUM_TOKEN = re.compile(r"\d|^[-–—_ー一]+$|^\?$")       # 숫자, 대시, 인식 누락


def filter_table_words(words: list[tuple]) -> list[tuple]:
    """표 밖 글자(지도 위 '단지', '216', '2' 등) 제거.

    면적 행(2~3자리 정수들로만 된 첫 숫자 행)의 x 범위를 표의 폭으로 보고, 그 행 이하에서는 범위 밖 단어를 버린다.
    면적 행 위(단지명·연식)는 그대로 둔다.
    """
    if not words:
        return words
    rows = _cluster_rows(words)
    area_row = None
    for row in rows:
        nums = [w for w in row if _NUM_TOKEN.search(w[4])]
        if nums and all(_AREA_TOKEN.match(w[4]) for w in nums):
            area_row = row
            break
    if area_row is None:
        return words
    areas = []
    for word in area_row:
        if _AREA_TOKEN.match(word[4]) and not any(_overlap(word, other) >= 0.3 for other in areas):
            areas.append(word)
    h = sorted(w[3] for w in areas)[len(areas) // 2]
    left = min(w[0] for w in areas)
    right = max(w[0] + w[2] for w in areas)
    if len(areas) >= 2:
        centers = sorted(w[0] + w[2] / 2 for w in areas)
        gap = min(b - a for a, b in zip(centers, centers[1:]))
        margin = gap * 0.6
    else:
        margin = h * 2.2
    lo, hi = left - margin, right + margin
    area_y = sum(w[1] + w[3] / 2 for w in area_row) / len(area_row)
    head_lo, head_hi = lo - h * 3, hi + h * 3     # 제목/연식 상자는 표보다 넓을 수 있어 넉넉히
    centers = [w[0] + w[2] / 2 for w in areas]
    out = []
    below: list[tuple] = []
    for w in words:
        yc = w[1] + w[3] / 2
        if yc < area_y - h * 0.6:
            if w[0] < head_hi and w[0] + w[2] > head_lo:
                out.append(w)                 # 면적 행 위(단지명/연식): 표 폭과 겹치는 것만
        elif _NUM_TOKEN.search(w[4]):
            below.append(w)
    # 면적 행 이하: 표는 열이 정렬되어 있으므로 각 단어를 가장 가까운 면적 열에 붙이고,
    # 같은 행·같은 열에 여러 단어가 오면 열 중심에 가장 가까운 것만 남긴다 (실측: 지도 글자 'H21' + 값 '5').
    for row in _cluster_rows(below):
        best: dict[int, tuple] = {}
        for w in row:
            xc = w[0] + w[2] / 2
            col = min(range(len(centers)), key=lambda i: abs(centers[i] - xc))
            dist = abs(centers[col] - xc)
            if dist > margin:
                continue
            if col not in best or dist < abs(centers[col] - (best[col][0] + best[col][2] / 2)):
                best[col] = w
        out.extend(best.values())
    return out


def _cluster_rows(words: list[tuple]) -> list[list[tuple]]:
    hs = sorted(wd[3] for wd in words)
    med_h = hs[len(hs) // 2] or 1.0
    tol = med_h * 0.6
    rows: list[list[tuple]] = []
    for wd in sorted(words, key=lambda t: t[1] + t[3] / 2):
        yc = wd[1] + wd[3] / 2
        for row in rows:
            ryc = sum(t[1] + t[3] / 2 for t in row) / len(row)
            if abs(yc - ryc) <= tol:
                row.append(wd)
                break
        else:
            rows.append([wd])
    rows.sort(key=lambda row: sum(t[1] + t[3] / 2 for t in row) / len(row))
    return rows


def _save_debug_words(i: int, result, label: str = "variant") -> None:
    """각 엔진/변형이 읽은 단어를 logs\\last_ocr_words.txt 에 남긴다 (rapid 가 먼저 쓰고 windows 는 덧붙임)."""
    try:
        from app_paths import app_dir
        path = os.path.join(app_dir(), "logs", "last_ocr_words.txt")
        mode = "w" if (i == 0 and label == "rapid") or (i == 0 and label == "windows" and _rapid_engine is None) else "a"
        # (rapid-ko / windows 는 뒤에 덧붙인다)
        with open(path, mode, encoding="utf-8") as f:
            f.write(f"[{label} {i}]\n")
            for x, y, w, h, t in _words(result):
                f.write(f"  {t!r} x={x:.0f} y={y:.0f} w={w:.0f} h={h:.0f}\n")
    except Exception:
        pass
