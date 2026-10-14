"""SisePicker 단위 테스트 — OCR(winocr) 없이 돈다.

  python -m unittest test_sisepicker -v
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config_manager  # noqa: E402
import pptx_writer  # noqa: E402
from config_manager import Config, load_config, save_config  # noqa: E402
from sise_parser import format_record, lines_to_text, normalize_line, parse_lines  # noqa: E402

SAMPLE = ["샘머리1단", "98y 1350^", "60 85", "4.1 5.3", "2.6 3.7", "1.5 1.6"]
EXPECTED = "샘머리1단지 98\n60) 4.1/2.6\n85) 5.3/3.7"
EXPECTED_PY = "샘머리1단지 98\n24) 4.1/2.6\n34) 5.3/3.7"


class ParserTest(unittest.TestCase):
    def test_web_import_preserves_visible_prices(self):
        from web_import import parse_web_text, PREFIX
        path = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "sisetong-web-import.json")
        with open(path, encoding="utf-8") as handle:
            records = json.load(handle)
        expected = {"서대전역우": [["3.6"],["3"]], "한신휴플러": [["3.5"],["2.7"]],
                    "효성상아": [["2.3","2.6"],["1.6","1.9"]], "문화마을금": [["4.2"],["3.4"]]}
        for data in records:
            rec = parse_web_text(PREFIX + json.dumps(data))
            self.assertTrue(rec.ok)
            if rec.name in expected:
                self.assertEqual(rec.rows[:2], expected[rec.name])
        data = dict(records[0], rows=[["12.5"],["-0.3"]])
        rec = parse_web_text(PREFIX + json.dumps(data))
        self.assertIn("12.5/-0.3", format_record(rec))

    def test_web_import_rejects_misaligned_and_invalid_data(self):
        from web_import import parse_web_text, PREFIX
        data = dict(source="https://sisetong.kr/",name="테스트",year="92",areas=["76","102"],rows=[["-","12.5"],["3.7","6.5"]])
        self.assertIsNone(parse_web_text("일반 클립보드 문자열"))
        for changes in [dict(rows=[["12.5"],["6.5"]]), dict(source="https://invalid.example/"),
                        dict(year="?"),dict(areas=["85",None]),dict(name="테스트\n다른 단지"),dict(rows=[["?","12.5"],["3.7","6.5"]])]:
            with self.assertRaises(ValueError):
                parse_web_text(PREFIX+json.dumps(dict(data,**changes)))

    def test_uncertain_metadata_keeps_column_positions_and_blocks_output(self):
        text, rec = lines_to_text(["테스트", "?y", "? 84", "2.3 2.6", "1.6 1.9"])
        self.assertEqual(rec.areas, ["?", "84"])
        self.assertEqual(rec.year, "?")
        self.assertFalse(rec.ok)
        self.assertIn("?) 2.3/1.6", text)
        self.assertIn("84) 2.6/1.9", text)

    def test_sample(self):
        text, rec = lines_to_text(SAMPLE)
        self.assertEqual(text, EXPECTED)
        self.assertTrue(rec.ok)
        self.assertEqual(rec.warnings, [])

    def test_pyeong_output(self):
        from sise_parser import conversion_info
        text, rec = lines_to_text(SAMPLE, area_divisor=2.48)
        self.assertEqual(text, EXPECTED_PY)
        self.assertEqual(conversion_info(rec), "60m² → 24평, 85m² → 34평")

    def test_grid_line_read_as_one_is_dropped(self):
        text, rec = lines_to_text(["샘머리1단", "98y 1350^", "60 85", "4.1 5.3", "2.6 1 3.7"])
        self.assertEqual(text, EXPECTED)
        self.assertTrue(any("'1'" in w for w in rec.warnings))

    def test_no_danji_fix(self):
        text, _ = lines_to_text(SAMPLE, fix_danji=False)
        self.assertTrue(text.startswith("샘머리1단 98\n"))

    def test_name_already_danji(self):
        text, _ = lines_to_text(["샘머리1단지"] + SAMPLE[1:])
        self.assertTrue(text.startswith("샘머리1단지 98\n"))

    def test_single_column_integer_value(self):
        # 면적 한 열, 첫 값이 정수 '5' (실측 샘머리2단): '5' 를 면적으로 오인하지 않아야 한다
        text, rec = lines_to_text(["샘머리2단", "98y 2200^", "85", "5", "3.3", "1.7"])
        self.assertEqual(text, "샘머리2단지 98\n85) 5.0/3.3")     # 정수 값은 .0 을 붙여 float 표기
        self.assertEqual(rec.warnings, [])

    def test_integer_prices_become_float(self):
        # 실측(꿈나무): 4행 "4 6", 5행 "3 3.4" → 4.0/3.0, 6.0/3.4. 면적(3행)은 정수 그대로.
        text, _ = lines_to_text(["꿈나무", "94y540^", "71 85", "4 6", "3 3.4"])
        self.assertEqual(text, "꿈나무 94\n71) 4.0/3.0\n85) 6.0/3.4")
        text, _ = lines_to_text(["꿈나무", "94y540^", "71 85", "4 6", "3 3.4"], area_divisor=2.48)
        self.assertEqual(text, "꿈나무 94\n29) 4.0/3.0\n34) 6.0/3.4")

    def test_dash_means_no_value(self):
        # 값 없는 셀은 대시로 표기되어 있음 → 결과에도 '-' 로
        text, rec = lines_to_text(["가나", "05y 300^", "59 84", "- 9.5", "4.2 —"], area_divisor=2.48)
        self.assertEqual(text, "가나 05\n24) -/4.2\n34) 9.5/-")
        self.assertEqual(rec.warnings, [])
        from record_writer import result_to_entries
        self.assertEqual(result_to_entries(text, divisor=None), [("24", "가나 05' -"), ("34", "가나 05' 9.5")])

    def test_extra_leading_token_in_value_row_uses_trailing_values(self):
        # 실측(샘머리2단): "H21 5" — 표 밖 글자가 앞에 붙음. 열 수(1)에 맞춰 뒤의 값을 쓴다.
        text, rec = lines_to_text(["샘머리2단", "98y 2200^", "85", "H21 5", "3.3", "1.7"])
        self.assertEqual(text, "샘머리2단지 98\n85) 5.0/3.3")
        self.assertTrue(any("버렸습니다" in w for w in rec.warnings))
        text, _ = lines_to_text(["가나", "98y", "60 85", "9 4.1 5.3", "2.6 3.7"])
        self.assertEqual(text, "가나 98\n60) 4.1/2.6\n85) 5.3/3.7")

    def test_household_count_on_own_line(self):
        lines = ["샘머리1단", "98y", "1350^", "60 85", "4.1 5.3", "2.6 3.7", "1.5 1.6"]
        text, _ = lines_to_text(lines)
        self.assertEqual(text, EXPECTED)

    def test_three_areas_rows_three(self):
        lines = ["한빛마을", "05y 800^", "84 101 114", "9.5 11 12.5", "7 8.2 9.0", "5.1 5.5 6.0"]
        text, _ = lines_to_text(lines, rows_to_use=3)
        self.assertEqual(text, "한빛마을 05\n84) 9.5/7.0/5.1\n101) 11.0/8.2/5.5\n114) 12.5/9.0/6.0")

    def test_comma_decimal_and_O(self):
        lines = ["샘머리1단", "98y 1350^", "6O 85", "4,1 5.3", "2.6 3,7"]
        text, _ = lines_to_text(lines)
        self.assertEqual(text, EXPECTED)

    def test_name_on_year_line(self):
        text, _ = lines_to_text(["샘머리1단 98y 1350^", "60 85", "4.1 5.3", "2.6 3.7"])
        self.assertEqual(text, EXPECTED)

    def test_missing_values_warns(self):
        rec = parse_lines(["샘머리1단", "98y 1350^"])
        self.assertFalse(rec.ok)
        self.assertTrue(any("시세 값" in w for w in rec.warnings))

    def test_ragged_last_row_warns(self):
        _, rec = lines_to_text(["샘머리1단", "98y", "60 85", "4.1 5.3", "2.6"])
        self.assertEqual(rec.rows, [["4.1", "5.3"], ["?", "?"]])
        self.assertTrue(any("마지막 행" in w for w in rec.warnings))

    def test_negative_prices_are_single_cells(self):
        text, rec = lines_to_text(["가나", "98y", "59 84 114", "4 5 6", "3 4 5", "-0.3 -0.1 -"], rows_to_use=3)
        self.assertEqual(rec.rows[-1], ["-0.3", "-0.1", "-"])
        self.assertEqual(rec.warnings, [])
        self.assertIn("59) 4.0/3.0/-0.3", text)

    def test_incomplete_middle_row_cannot_borrow_next_row(self):
        rec = parse_lines(["가나", "98y", "60 85", "4.1", "2.6 3.7", "1.5 1.6"])
        self.assertEqual(rec.rows, [["?", "?"], ["2.6", "3.7"], ["1.5", "1.6"]])
        self.assertFalse(rec.ok)

    def test_explicit_unknown_keeps_column(self):
        text, rec = lines_to_text(["가나", "98y", "60 85", "? 5.3", "2.6 3.7"])
        self.assertEqual(text, "가나 98\n60) ?/2.6\n85) 5.3/3.7")
        self.assertFalse(rec.ok)

    def test_one_row_only(self):
        text, _ = lines_to_text(["샘머리1단", "98y", "60 85", "4.1 5.3"])
        self.assertEqual(text, "샘머리1단지 98\n60) 4.1\n85) 5.3")

    def test_normalize(self):
        self.assertEqual(normalize_line("4 . 1"), "4.1")
        self.assertEqual(normalize_line("4. 1"), "4.1")
        self.assertEqual(normalize_line("2,6"), "2.6")

    def test_format_empty(self):
        self.assertEqual(format_record(parse_lines([])), "")






class RecorderTest(unittest.TestCase):
    def test_entries(self):
        from record_writer import result_to_entries
        self.assertEqual(result_to_entries(EXPECTED),
                         [("24", "샘머리1단지 98' 4.1"), ("34", "샘머리1단지 98' 5.3")])
        self.assertEqual(result_to_entries("한빛마을\n84) 9.5"), [("34", "한빛마을 9.5")])
        self.assertEqual(result_to_entries(EXPECTED, "\t")[0], ("24", "샘머리1단지\t98'\t4.1"))
        self.assertEqual(result_to_entries("헤더만"), [])
        self.assertEqual(result_to_entries(EXPECTED_PY, divisor=None),
                         [("24", "샘머리1단지 98' 4.1"), ("34", "샘머리1단지 98' 5.3")])

    def test_to_pyeong(self):
        from record_writer import to_pyeong
        self.assertEqual([to_pyeong(a) for a in ("60", "85", "84", "114", "59", "135", "abc")],
                         ["24", "34", "34", "46", "24", "54", "abc"])
        self.assertEqual(to_pyeong("84", 3.3058), "25")  # 공급면적 표기일 때

    def test_zone_files_add_replace_persist(self):
        from record_writer import ZoneRecorder
        with tempfile.TemporaryDirectory() as d:
            rec = os.path.join(d, "records")
            r = ZoneRecorder(rec, zone="둔산생활권")
            files = r.add(EXPECTED)
            self.assertEqual(sorted(os.path.basename(f) for f in files), ["둔산생활권_24평.txt", "둔산생활권_34평.txt"])
            r.add("크로바 92\n84) 9.0/6.0\n114) 12.0/8.0")
            r.replace_last("크로바 92\n84) 9.1/6.0\n114) 12.5/8.0")      # 편집 → 마지막 항목 교체
            def read(n):
                with open(os.path.join(rec, n), encoding="utf-8-sig") as f:
                    return f.read().splitlines()
            self.assertEqual(read("둔산생활권_24평.txt"), ["샘머리1단지 98' 4.1"])
            self.assertEqual(read("둔산생활권_34평.txt"), ["샘머리1단지 98' 5.3", "크로바 92' 9.1"])
            self.assertFalse(os.path.exists(os.path.join(rec, "둔산생활권_46평.txt")))
            self.assertEqual(r.count, 2)
            # 생활권 변경 → 다른 파일
            r.zone = "서초/반포"
            r.add(EXPECTED)
            self.assertTrue(os.path.isfile(os.path.join(rec, "서초반포_24평.txt")))
            # 새 세션(새 객체)도 같은 파일에 이어 쓴다
            r2 = ZoneRecorder(rec, zone="둔산생활권")
            r2.add("한빛 05\n60) 5.0")
            self.assertEqual(read("둔산생활권_24평.txt"), ["샘머리1단지 98' 4.1", "한빛 05' 5.0"])
            with open(os.path.join(rec, "둔산생활권_24평.txt"), "rb") as f:
                self.assertEqual(f.read().count(b"\xef\xbb\xbf"), 1)      # BOM 은 파일 앞 한 번만


class ConfigTest(unittest.TestCase):
    def test_roundtrip_and_backcompat(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            cfg = Config(pptx_path=r"D:\x\y.pptx", auto_copy=False, rows_to_use=3)
            save_config(cfg, p)
            self.assertEqual(load_config(p), cfg)
            # 구버전/외부에서 만든 JSON: 모르는 키는 무시, 빠진 키는 기본값
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"pptx_path": "a.pptx", "unknown_key": 1}, f)
            c2 = load_config(p)
            self.assertEqual(c2.pptx_path, "a.pptx")
            self.assertEqual(c2.ocr_lang, "ko")
            # 구버전 값 보정: 상대 record_dir("records") → "" (PPT 폴더 기준), ocr_scale 3 → 4
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"record_dir": "records", "ocr_scale": 3}, f)
            c3 = load_config(p)
            self.assertEqual(c3.record_dir, "")
            self.assertEqual(c3.ocr_scale, 4)

    def test_missing_file_gives_default(self):
        c = load_config(os.path.join(tempfile.gettempdir(), "no_such_sisepicker.json"))
        self.assertTrue(c.pptx_path.endswith("생활권 시세따기.pptx"))
        self.assertNotIn("mussy", c.pptx_path.lower().replace(os.path.expanduser("~").lower(), ""))


class PptxWriterTest(unittest.TestCase):
    def _make_pptx(self, path):
        from pptx import Presentation
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(path)

    def test_add_two_boxes_grid(self):
        from pptx import Presentation
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.pptx")
            self._make_pptx(p)
            cfg = Config(pptx_path=p, box_columns=1)
            n1, name1 = pptx_writer.add_text_to_pptx(EXPECTED, cfg)
            n2, name2 = pptx_writer.add_text_to_pptx("두번째 05\n84) 9/7", cfg)
            self.assertEqual((n1, n2), (2, 2))
            self.assertEqual((name1, name2), ("SisePicker-1", "SisePicker-2"))
            prs = Presentation(p)
            slide = prs.slides[1]
            boxes = [s for s in slide.shapes if s.name.startswith("SisePicker-")]
            self.assertEqual(len(boxes), 2)
            self.assertEqual(boxes[0].text_frame.text, EXPECTED)
            self.assertEqual(boxes[1].top, boxes[0].top)  # 매번 같은 가운데 위치
            self.assertEqual(boxes[0].left, (prs.slide_width - boxes[0].width) // 2)
            self.assertEqual(boxes[0].top, (prs.slide_height - boxes[0].height) // 2)
            self.assertEqual(boxes[1].left, boxes[0].left)
            self.assertEqual(len(prs.slides[0].shapes), 0)      # 첫 슬라이드는 건드리지 않음

    def test_zone_slides(self):
        from pptx import Presentation
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "z.pptx")
            self._make_pptx(p)                      # 기존 2장
            cfg = Config(pptx_path=p)
            n1, _ = pptx_writer.add_text_to_pptx(EXPECTED, cfg, zone="둔산생활권")
            n2, _ = pptx_writer.add_text_to_pptx("크로바 92\n84) 9/6", cfg, zone="둔산생활권")
            n3, _ = pptx_writer.add_text_to_pptx("반포자이 08\n84) 30/15", cfg, zone="서초생활권")
            n4, _ = pptx_writer.add_text_to_pptx("한빛 05\n60) 5/3", cfg, zone="둔산생활권")
            self.assertEqual((n1, n2, n3, n4), (3, 3, 4, 3))    # 생활권마다 새 슬라이드, 같은 생활권은 같은 슬라이드
            prs = Presentation(p)
            self.assertEqual(len(prs.slides), 4)
            s3 = prs.slides[2]
            titles = [sh.text_frame.text for sh in s3.shapes if sh.name == "SisePicker-Title"]
            self.assertEqual(titles, ["둔산생활권"])
            boxes = [sh for sh in s3.shapes if sh.name.startswith("SisePicker-") and sh.name != "SisePicker-Title"]
            self.assertEqual([b.name for b in boxes], ["SisePicker-1", "SisePicker-2", "SisePicker-3"])
            title_box = [sh for sh in s3.shapes if sh.name == "SisePicker-Title"][0]
            self.assertTrue(all(b.top > title_box.top + title_box.height - 1 for b in boxes))
            self.assertEqual(len(prs.slides[0].shapes) + len(prs.slides[1].shapes), 0)

    def test_existing_title_slide_is_reused(self):
        from pptx import Presentation
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.pptx")
            prs = Presentation()
            s1 = prs.slides.add_slide(prs.slide_layouts[5])        # Title Only
            s1.shapes.title.text = "둔산생활권 시세"
            prs.slides.add_slide(prs.slide_layouts[6])
            prs.save(p)
            n, _ = pptx_writer.add_text_to_pptx(EXPECTED_PY, Config(pptx_path=p), zone="둔산생활권")
            self.assertEqual(n, 1)                                  # 새 페이지 대신 제목 슬라이드에
            prs = Presentation(p)
            self.assertEqual(len(prs.slides), 2)
            box = [sh for sh in prs.slides[0].shapes if sh.name == "SisePicker-1"][0]
            self.assertGreater(box.top, prs.slides[0].shapes.title.top + prs.slides[0].shapes.title.height - 1)

    def test_open_powerpoint_uses_com(self):
        """PowerPoint 에 열려 있으면 COM 경로로 넣고 파일은 건드리지 않는다 (COM 객체는 mock)."""
        from pptx import Presentation
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.pptx")
            self._make_pptx(p)
            before = os.path.getmtime(p)

            class Shape:
                def __init__(self, name="", text=""):
                    self.Name, self.HasTextFrame, self.Type = name, True, 17
                    self.Top, self.Height = 14.2, 40.0
                    self.TextFrame = mock.Mock()
                    self.TextFrame.TextRange.Text = text
            class Shapes(list):
                def AddTextbox(self, orient, left, top, w, h):
                    sh = Shape(); sh.Left, sh.Top, sh.Width, sh.Height = left, top, w, h
                    self.append(sh); return sh
            class Slide:
                def __init__(self, idx, shapes): self.SlideIndex, self.Shapes = idx, Shapes(shapes)
            class Slides:
                def __init__(self, items): self._items = items
                Count = property(lambda self: len(self._items))
                def Item(self, i): return self._items[i - 1]
                def Add(self, i, layout): s = Slide(i, []); self._items.append(s); return s
            pres = mock.Mock()
            pres.FullName = p
            pres.Slides = Slides([Slide(1, [Shape("Title 1", "둔산생활권 시세")]), Slide(2, [])])
            pres.PageSetup.SlideWidth = 960
            pres.PageSetup.SlideHeight = 540
            with mock.patch.object(pptx_writer, "_find_open_presentation", return_value=pres):
                n, name = pptx_writer.add_text_to_pptx(EXPECTED_PY, Config(pptx_path=p), zone="둔산생활권")
            self.assertEqual((n, name), (1, "SisePicker-1"))
            box = pres.Slides.Item(1).Shapes[-1]
            self.assertEqual(box.Name, "SisePicker-1")
            self.assertEqual(box.TextFrame.TextRange.Text, EXPECTED_PY.replace("\n", "\r"))
            self.assertGreater(box.Top, 14.2 + 40.0)                 # 제목 아래
            pres.Save.assert_called_once()
            self.assertEqual(os.path.getmtime(p), before)             # 파일은 python-pptx 로 건드리지 않음
            # 두 번째 추가는 다음 칸
            with mock.patch.object(pptx_writer, "_find_open_presentation", return_value=pres):
                n2, name2 = pptx_writer.add_text_to_pptx("가 05\n24) 1.0/0.5", Config(pptx_path=p), zone="둔산생활권")
            self.assertEqual(name2, "SisePicker-2")
            self.assertEqual(pres.Slides.Item(1).Shapes[-1].Left, box.Left)
            self.assertEqual(pres.Slides.Item(1).Shapes[-1].Top, box.Top)
            # 생활권 슬라이드가 없으면 새 슬라이드 + 제목
            with mock.patch.object(pptx_writer, "_find_open_presentation", return_value=pres):
                n3, _ = pptx_writer.add_text_to_pptx("나 05\n24) 1.0", Config(pptx_path=p), zone="서초생활권")
            self.assertEqual(n3, 3)
            self.assertEqual(pres.Slides.Item(3).Shapes[0].Name, "SisePicker-Title")

    def test_find_open_presentation_without_pywin32(self):
        # Linux(pywin32 없음) → None → 파일 경로로 진행
        self.assertIsNone(pptx_writer._find_open_presentation("x.pptx"))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            pptx_writer.add_text_to_pptx("x", Config(pptx_path=r"Z:\none\no.pptx"))




if __name__ == "__main__":
    unittest.main(verbosity=2)
