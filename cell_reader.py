"""행/열 중심 사이의 경계로 셀 전체를 잘라 재검증한다."""
import re
import numpy as np
from PIL import Image, ImageOps


def candidates(crop, engine):
    scale = max(4, round(64 / max(1, crop.height)))
    size = (crop.width * scale, crop.height * scale)
    gray = crop.convert("L")
    hsv = np.array(crop.convert("HSV"))
    colored = (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 100)
    if colored.mean() > .35:
        levels = np.array(gray, dtype=float)
        background = float(np.median(levels[colored]))
        normalized = np.clip(255 - (levels-background)*255/max(20,255-background),0,255).astype("uint8")
        crop = Image.fromarray(normalized).convert("RGB")
        gray = crop.convert("L")
    # 셀 배경이 어두우면 흰 배경/검은 글자로 통일한다.
    border = np.concatenate((np.array(gray)[0], np.array(gray)[-1]))
    if np.median(border) < 190:
        gray = ImageOps.invert(gray)
    variants = [crop.resize(size, Image.Resampling.LANCZOS),
                crop.resize(size, Image.Resampling.NEAREST),
                ImageOps.autocontrast(gray).resize(size, Image.Resampling.LANCZOS).convert("RGB")]
    result = []
    for variant in variants:
        items, _ = engine(np.array(variant), use_det=False, use_cls=False)
        if items and len(items) == 1:
            value, score = items[0][:2]
            result.append((str(value).strip().replace("−", "-"), float(score)))
    return result


def consensus(items, kind):
    pattern = {"area": r"\d{2,3}", "year": r"(\d{2})\s*[yY].*",
               "price": r"-?\d+(?:\.\d+)?|-"}[kind]
    values = []
    for value, score in items:
        match = re.fullmatch(pattern, value)
        if not match or score < .90:
            return None
        values.append(match.group(1) if kind == "year" else value)
    if len(values) == 3 and len(set(values)) == 1:
        return values[0]
    return None


def verify(image, words, checked, scale, cluster, engine, decimal_shape):
    """격자 경계를 추정할 수 없는 표는 기존 결과를 유지한다. 모든 좌표는 원본 단위."""
    rows = cluster(words)
    area_index = next((i for i, row in enumerate(rows)
                       if row and all(re.fullmatch(r"\d{2,3}", w[4]) for w in row)), None)
    if area_index is None or area_index == 0 or len(rows) < area_index + 3:
        return checked, []
    rows = [sorted(row, key=lambda w: w[0]) for row in rows]
    areas = rows[area_index]
    factor = max(1, int(scale or 1))
    cx = [(w[0] + w[2] / 2) / factor for w in areas]
    cy = [sum(w[1] + w[3] / 2 for w in row) / len(row) / factor for row in rows]
    gap = cy[area_index + 1] - cy[area_index]
    if gap < 6 or any(cx[i+1] - cx[i] < 8 for i in range(len(cx)-1)):
        return checked, []
    xedges = ([cx[0] - (cx[1] - cx[0]) / 2] if len(cx) > 1 else [cx[0] - gap])
    xedges += [(a+b)/2 for a,b in zip(cx,cx[1:])]
    xedges += [cx[-1] + ((cx[-1] - cx[-2])/2 if len(cx)>1 else gap)]
    original = image.convert("RGB")
    output = {w[:4]: w for w in checked}
    evidence = []

    def inspect(word, bounds, kind):
        x0,y0,x1,y1 = bounds
        if x0 < 0 or y0 < 0 or x1 > image.width or y1 > image.height or x1-x0 < 5 or y1-y0 < 5:
            return
        box = tuple(map(round, bounds))
        crop = original.crop(box)
        items = candidates(crop, engine)
        agreed = consensus(items, kind)
        prior = output.get(word[:4], word)[4]
        value = prior
        if kind == "price":
            # 소수점을 추측하지 않고 기존 전체 표 후보와 일치할 때만 복원한다.
            if prior == "?" and agreed == word[4] and re.fullmatch(r"-?\d+\.\d+", agreed or ""):
                value = agreed
            # 정수의 의심스러운 점 모양은 전체 셀에서도 재확인한다.
            if re.fullmatch(r"-?\d+", prior) and decimal_shape(crop):
                value = "?"
        elif kind == "area":
            value = agreed or "?"
        elif kind == "year":
            value = (agreed or "?") + "y"
        output[word[:4]] = (*word[:4], value)
        evidence.append(dict(kind=kind, box=box, original=word[4], candidates=items, selected=value))

    for r in range(area_index, len(rows)):
        top = (cy[r-1] + cy[r])/2 + .5
        bottom = (cy[r]+cy[r+1])/2 - .5 if r+1<len(rows) else cy[r]+(cy[r]-cy[r-1])/2-.5
        for col, center in enumerate(cx):
            nearby = [w for w in rows[r] if xedges[col] <= (w[0]+w[2]/2)/factor < xedges[col+1]]
            if len(nearby) != 1:
                continue
            inspect(nearby[0], (xedges[col]+1,top,xedges[col+1]-1,bottom),
                    "area" if r == area_index else "price")
    for w in rows[area_index-1]:
        if re.match(r"\d{2}\s*[yY]", w[4]):
            inspect(w, (max(0,w[0]/factor-2),max(0,w[1]/factor-2),
                        min(image.width,(w[0]+w[2])/factor+2),
                        min(image.height,(w[1]+w[3])/factor+2)), "year")
    return list(output.values()), evidence
