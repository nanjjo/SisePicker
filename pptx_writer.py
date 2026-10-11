"""PPT 에 시세 텍스트 박스를 추가한다 (python-pptx) — 생활권별 슬라이드.

- 생활권 이름이 있으면 제목(placeholder)에 그 이름이 들어 있거나 같은 내용의 텍스트 박스가 있는 슬라이드를 찾아
  거기에 박스를 쌓고, 없으면 맨 뒤에 새 슬라이드를 만들어 제목('SisePicker-Title')을 넣는다.
- 생활권 이름이 비어 있으면 예전처럼 마지막 슬라이드에 넣는다.
- 새 박스는 항상 슬라이드 가운데 같은 위치에 배치한다. 기존 박스는 이동하지 않는다.
PowerPoint 에 파일이 열려 있으면 COM(pywin32)으로 실행 중인 PowerPoint 에 직접 넣는다(편집 중에도 추가 가능).
그 외에는 python-pptx 로 파일을 고친다. 둘 다 실패하면 PermissionError.
"""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.util import Cm, Pt

from config_manager import Config

SHAPE_PREFIX = "SisePicker-"
TITLE_SHAPE = "SisePicker-Title"
TITLE_TOP_CM = 0.5
TITLE_HEIGHT_CM = 1.4


def _existing_count(slide) -> int:
    return sum(1 for sh in slide.shapes
               if (sh.name or "").startswith(SHAPE_PREFIX) and sh.name != TITLE_SHAPE)


def _slide_matches_zone(slide, zone: str) -> bool:
    """제목 placeholder 에 생활권 이름이 들어 있거나, 어떤 텍스트 박스의 내용이 생활권 이름과 같으면 그 슬라이드."""
    try:
        title = slide.shapes.title
    except Exception:
        title = None
    if title is not None and title.has_text_frame and zone in title.text_frame.text:
        return True
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.strip() == zone:
            return True
    return False


def _find_zone_slide(prs, zone: str):
    for slide in prs.slides:
        if _slide_matches_zone(slide, zone):
            return slide
    return None


def _title_bottom_cm(slide) -> float:
    """제목(placeholder 또는 SisePicker-Title)의 아래 끝 (cm). 없으면 0."""
    try:
        title = slide.shapes.title
    except Exception:
        title = None
    cands = [sh for sh in slide.shapes if sh.name == TITLE_SHAPE]
    if title is not None:
        cands.append(title)
    if not cands:
        return 0.0
    return max((sh.top + sh.height) for sh in cands) / 360000.0


def _blank_layout(prs):
    for layout in prs.slide_layouts:
        if not layout.placeholders:
            return layout
    return prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]


def _new_zone_slide(prs, zone: str, cfg: Config):
    slide = prs.slides.add_slide(_blank_layout(prs))
    width = prs.slide_width - Cm(2 * cfg.box_left_cm)
    box = slide.shapes.add_textbox(Cm(cfg.box_left_cm), Cm(TITLE_TOP_CM), width, Cm(TITLE_HEIGHT_CM))
    box.name = TITLE_SHAPE
    tf = box.text_frame
    run = tf.paragraphs[0].add_run()
    run.text = zone
    run.font.size = Pt(cfg.box_font_pt + 9)
    run.font.bold = True
    return slide


def add_text_to_pptx(text: str, cfg: Config, pptx_path: str | None = None,
                     zone: str = "") -> tuple[int, str]:
    """text 를 생활권 슬라이드(없으면 새로 만듦)에 텍스트 박스로 추가하고 저장.

    PowerPoint 에 그 파일이 열려 있으면 COM(실행 중인 PowerPoint)으로 직접 넣어 편집 중에도 추가된다.
    아니면 python-pptx 로 파일을 고쳐 저장한다.
    반환: (슬라이드 번호(1-base), 만들어진 shape 이름)
    """
    path = pptx_path or cfg.pptx_path
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PPT 파일이 없습니다: {path}")

    live = _add_via_powerpoint(text, cfg, path, zone)
    if live is not None:
        return live
    return _add_via_file(text, cfg, path, zone)


# ----------------------------------------------------------------------------- COM (열려 있는 PowerPoint)
PT_PER_CM = 28.3465
PP_LAYOUT_BLANK = 12
MSO_TEXT_ORIENTATION_HORIZONTAL = 1


def _find_open_presentation(path: str):
    """실행 중인 PowerPoint 에서 path 를 열어 둔 Presentation 을 찾는다. 없으면 None (PowerPoint 미실행 포함)."""
    try:
        import pythoncom  # noqa: WPS433
        import win32com.client  # noqa: WPS433
    except ImportError:
        return None
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    try:
        app = win32com.client.GetActiveObject("PowerPoint.Application")
    except Exception:
        return None
    want = os.path.normcase(os.path.abspath(path))
    try:
        for pres in app.Presentations:
            if os.path.normcase(str(pres.FullName)) == want:
                return pres
    except Exception:
        return None
    return None


def _com_slide_matches_zone(slide, zone: str) -> bool:
    for sh in slide.Shapes:
        try:
            if sh.HasTextFrame:
                t = str(sh.TextFrame.TextRange.Text).strip()
                if t == zone:
                    return True
                if zone in t and _com_is_title(sh):
                    return True
        except Exception:
            continue
    return False


def _com_is_title(sh) -> bool:
    """제목 placeholder(msoPlaceholder=14, ppPlaceholderTitle=1/CenterTitle=3) 또는 이름이 Title/제목/SisePicker-Title."""
    name = str(sh.Name)
    if name == TITLE_SHAPE or name.lower().startswith("title") or name.startswith("제목"):
        return True
    try:
        return sh.Type == 14 and sh.PlaceholderFormat.Type in (1, 3)
    except Exception:
        return False


def _com_title_bottom_cm(slide) -> float:
    bottom = 0.0
    for sh in slide.Shapes:
        if _com_is_title(sh):
            bottom = max(bottom, (sh.Top + sh.Height) / PT_PER_CM)
    return bottom


def _add_via_powerpoint(text: str, cfg: Config, path: str, zone: str):
    """열려 있는 PowerPoint 문서에 COM 으로 텍스트 박스를 추가하고 저장. 해당 문서가 열려 있지 않으면 None."""
    pres = _find_open_presentation(path)
    if pres is None:
        return None
    zone = (zone or "").strip()
    slides = pres.Slides
    slide = None
    if cfg.zone_slide_id is not None:
        slide = next((slides.Item(i) for i in range(1, slides.Count + 1)
                      if slides.Item(i).SlideID == cfg.zone_slide_id), None)
        if slide is None:
            raise ValueError("연결된 생활권 페이지가 없습니다. 생활권 관리에서 PPT 다시 가져오기를 실행하세요.")
    if zone:
        for i in range(1, slides.Count + 1):
            if slide is None and _com_slide_matches_zone(slides.Item(i), zone):
                slide = slides.Item(i)
                break
        if slide is None:
            slide = slides.Add(slides.Count + 1, PP_LAYOUT_BLANK)
            width_pt = pres.PageSetup.SlideWidth - 2 * cfg.box_left_cm * PT_PER_CM
            title = slide.Shapes.AddTextbox(MSO_TEXT_ORIENTATION_HORIZONTAL, cfg.box_left_cm * PT_PER_CM,
                                            TITLE_TOP_CM * PT_PER_CM, width_pt, TITLE_HEIGHT_CM * PT_PER_CM)
            title.Name = TITLE_SHAPE
            title.TextFrame.TextRange.Text = zone
            title.TextFrame.TextRange.Font.Size = cfg.box_font_pt + 9
            title.TextFrame.TextRange.Font.Bold = True
        top0 = max(cfg.box_top_cm, _com_title_bottom_cm(slide) + 0.3)
    else:
        if slides.Count == 0:
            slides.Add(1, PP_LAYOUT_BLANK)
        slide = slides.Item(slides.Count)
        top0 = cfg.box_top_cm

    idx = sum(1 for sh in slide.Shapes if str(sh.Name).startswith(SHAPE_PREFIX) and sh.Name != TITLE_SHAPE)
    left = max(0, (pres.PageSetup.SlideWidth - cfg.box_width_cm * PT_PER_CM) / 2)
    top = max(0, (pres.PageSetup.SlideHeight - cfg.box_height_cm * PT_PER_CM) / 2)
    box = slide.Shapes.AddTextbox(MSO_TEXT_ORIENTATION_HORIZONTAL, left, top,
                                  cfg.box_width_cm * PT_PER_CM, cfg.box_height_cm * PT_PER_CM)
    box.Name = f"{SHAPE_PREFIX}{idx + 1}"
    tr = box.TextFrame.TextRange
    tr.Text = "\r".join(text.splitlines() or [""])
    tr.Font.Size = cfg.box_font_pt
    tr.Font.Bold = False
    try:
        tr.Paragraphs(1).Font.Bold = True
    except Exception:
        pass
    try:
        pres.Save()
    except Exception:
        pass        # 저장이 막혀도(읽기 전용 등) PowerPoint 안에는 이미 들어가 있다 — 사용자가 저장하면 된다
    return int(slide.SlideIndex), str(box.Name)


# ----------------------------------------------------------------------------- 파일 직접 편집 (python-pptx)
def _add_via_file(text: str, cfg: Config, path: str, zone: str) -> tuple[int, str]:
    prs = Presentation(path)
    zone = (zone or "").strip()
    if cfg.zone_slide_id is not None:
        slide = next((s for s in prs.slides if s.slide_id == cfg.zone_slide_id), None)
        if slide is None:
            raise ValueError("연결된 생활권 페이지가 없습니다. 생활권 관리에서 PPT 다시 가져오기를 실행하세요.")
    elif zone:
        slide = _find_zone_slide(prs, zone) or _new_zone_slide(prs, zone, cfg)
        top0 = max(cfg.box_top_cm, _title_bottom_cm(slide) + 0.3)
    else:
        if len(prs.slides) == 0:
            prs.slides.add_slide(_blank_layout(prs))
        slide = prs.slides[len(prs.slides) - 1]
        top0 = cfg.box_top_cm

    idx = _existing_count(slide)
    left = max(0, (prs.slide_width - Cm(cfg.box_width_cm)) // 2)
    top = max(0, (prs.slide_height - Cm(cfg.box_height_cm)) // 2)

    box = slide.shapes.add_textbox(left, top, Cm(cfg.box_width_cm), Cm(cfg.box_height_cm))
    box.name = f"{SHAPE_PREFIX}{idx + 1}"
    tf = box.text_frame
    tf.word_wrap = True
    lines = text.splitlines() or [""]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = p.add_run()
        run.text = ln
        run.font.size = Pt(cfg.box_font_pt)
        if i == 0:
            run.font.bold = True

    try:
        prs.save(path)
    except PermissionError as e:
        raise PermissionError(
            f"PPT 저장 실패 — 파일이 다른 프로그램에서 잠겨 있습니다.\n{path}\n"
            "(PowerPoint 에 열려 있으면 자동으로 그 창에 직접 넣습니다. 그런데도 실패하면 PowerPoint 가 "
            "다른 사용자 권한으로 실행 중이거나 pywin32 가 없는 경우입니다.)"
        ) from e
    slide_no = list(prs.slides).index(slide) + 1
    return slide_no, box.name


def read_zone_titles(path):
    """생활권 제목과 영구 슬라이드 ID. 열린 PPT의 미저장 제목도 읽는다."""
    live = _find_open_presentation(path)
    rows = []
    if live is not None:
        for slide in live.Slides:
            for sh in slide.Shapes:
                if sh.HasTextFrame:
                    title = str(sh.TextFrame.TextRange.Text).strip()
                    if "생활권" in title and "\n" not in title and "\r" not in title and len(title) <= 100:
                        rows.append(dict(name=title, title=title, slide_id=int(slide.SlideID), page=int(slide.SlideIndex)))
                        break
    else:
        prs = Presentation(path)
        for i, slide in enumerate(prs.slides, 1):
            for sh in slide.shapes:
                if sh.has_text_frame:
                    title = sh.text.strip()
                    if "생활권" in title and "\n" not in title and "\r" not in title and len(title) <= 100:
                        rows.append(dict(name=title, title=title, slide_id=slide.slide_id, page=i))
                        break
    return rows
