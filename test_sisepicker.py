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


class OcrEngineTest(unittest.TestCase):
    def test_full_cell_consensus_rejects_missing_or_conflicting_candidates(self):
        from cell_reader import consensus
        self.assertEqual(consensus([("85", .95)] * 3, "area"), "85")
        self.assertIsNone(consensus([("85", .95)] * 2, "area"))
        self.assertIsNone(consensus([("85", .95), ("86", .95), ("85", .95)], "area"))
        self.assertEqual(consensus([("92y700^", .95)] * 3, "year"), "92")
        self.assertIsNone(consensus([("9.6", .89)] * 3, "price"))

    def test_full_cells_recover_price_and_mark_uncertain_area_without_shifting(self):
        from cell_reader import verify
        import ocr_engine as ocr
        from PIL import Image
        words = [(20,10,50,10,"92y700^"), (20,30,10,10,"61"), (60,30,10,10,"84"),
                 (20,50,10,10,"2.3"), (60,50,10,10,"2.6"),
                 (20,70,10,10,"1.6"), (60,70,10,10,"1.9")]
        checked = [(*w[:4], "?" if i >= 3 else w[4]) for i,w in enumerate(words)]
        readings = [[("61", .99), ("67", .99), ("61", .99)], [("84",.99)]*3,
                    [("2.3",.99)]*3, [("2.6",.99)]*3, [("1.6",.99)]*3,
                    [("1.9",.99)]*3, [("92y700^",.99)]*3]
        with mock.patch("cell_reader.candidates", side_effect=readings):
            out, evidence = verify(Image.new("RGB", (100,100), "white"), words, checked,
                                   1, ocr._cluster_rows, None, lambda crop: False)
        self.assertEqual(ocr.words_to_rows(out), ["92y", "? 84", "2.3 2.6", "1.6 1.9"])
        self.assertEqual(len(evidence), 7)

    """winocr 없이 전처리/행 재구성만 검증."""

    def test_gukhwa_offset_area_boxes_do_not_erase_prices(self):
        import ocr_engine as ocr
        rapid = [(116,168,75,47,"92y"), (215,168,100,47,"666^"),
                 (168,262,86,56,"84"), (322,262,84,54,"92"),
                 (28,354,72,47,"6.5"), (181,355,67,46,"7.5"), (325,356,75,43,"6.5"),
                 (26,434,68,48,"3.3"), (177,434,69,48,"3.3"), (329,434,68,49,"3.5")]
        windows = [(27,262,67,44,"77"), (171,266,78,44,"84"), (327,270,74,44,"92"),
                   (26,434,60,36,"3.3"), (178,438,60,36,"3.3"), (330,442,60,35,"3.5")]
        repaired = ocr.repair_table(rapid, windows)
        lines = ocr.words_to_rows(ocr.filter_table_words(repaired))
        self.assertEqual(lines, ["92y 666^", "77 84 92", "6.5 7.5 6.5", "3.3 3.3 3.5"])
        # 이미 중복된 상자가 들어와도 열 간격이 0이 되어 가격 행을 버리지 않는다.
        duplicated = repaired + windows[:3]
        self.assertEqual(ocr.words_to_rows(ocr.filter_table_words(duplicated)), lines)

    def test_cell_verification_rejects_lost_decimal_despite_high_confidence(self):
        import ocr_engine as ocr
        candidates = [{"text": "72", "score": .999}] * 2
        value, reason = ocr._choose_cell_value("72", candidates, 8)
        self.assertEqual(value, "?")
        self.assertIn("캡처", reason)

    def test_cell_verification_disagreement_is_not_silent_correction(self):
        import ocr_engine as ocr
        for original, candidates in [
            ("85", [{"text": "8.5", "score": .99}] * 2),
            ("17.5", [{"text": "17.5", "score": .99}, {"text": "17.6", "score": .95}]),
            ("72", [{"text": "72", "score": .99}]),
        ]:
            self.assertEqual(ocr._choose_cell_value(original, candidates, 14)[0], "?")

    def test_cell_verification_agreement_and_missing_cell(self):
        import ocr_engine as ocr
        for value in ["7.2", "72", "-", "-0.3"]:
            candidates = [{"text": value, "score": .96}] * 2
            self.assertEqual(ocr._choose_cell_value(value, candidates, 14)[0], value)
            self.assertEqual(ocr._choose_cell_value("?", candidates, 14)[0], value)

    def test_cell_verification_preserves_columns_and_writes_evidence(self):
        import ocr_engine as ocr
        import app_paths
        from PIL import Image
        words = [(5, 5, 60, 12, "가나"), (10, 25, 20, 12, "68"), (55, 25, 20, 12, "85"),
                 (10, 50, 20, 12, "7.2"), (55, 50, 20, 12, "85")]
        engine = mock.Mock(side_effect=[([["7.2", .99]], None)] * 3 + [([["8.5", .99]], None)] * 5)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app_paths, "app_dir", return_value=directory), \
             mock.patch.object(ocr, "_get_rapid", return_value=engine):
            out = ocr._verify_price_cells(Image.new("RGB", (100, 80), "white"), words, 1)
            self.assertEqual(ocr.words_to_rows(out), ["가나", "68 85", "7.2 8.5"])
            with open(os.path.join(directory, "logs", "last_ocr_cells.json"), encoding="utf-8") as f:
                evidence = json.load(f)
            self.assertEqual(evidence[1]["candidates"][0]["text"], "8.5")
            self.assertEqual(evidence[1]["selected"], "8.5")
        self.assertEqual(engine.call_count, 8)

    def test_inversion_decimal_recovery_requires_corroboration(self):
        import ocr_engine as ocr
        candidates = [{"variant": "color", "text": "125", "score": .999},
                      {"variant": "nearest", "text": "12.5", "score": .904},
                      {"variant": "inverse_smooth", "text": "12.5", "score": .91},
                      {"variant": "inverse_nearest", "text": "12.5", "score": .97}]
        recover = lambda orig, cs, h=11: ocr._recover_decimal_from_inversion(orig, cs, h, "conflict")[0]
        self.assertEqual(recover("125", candidates), "12.5")
        self.assertEqual(recover("135", candidates), "?")
        self.assertEqual(recover("125", candidates, 8), "?")
        self.assertEqual(recover("125", candidates[:1] + candidates[2:]), "?")
        self.assertEqual(recover("125", candidates[:-1]), "?")
        for replacement in [{"text": "125", "score": .99}, {"text": "12.5", "score": .89}]:
            changed = candidates[:-1] + [dict(replacement, variant="inverse_nearest")]
            self.assertEqual(recover("125", changed), "?")

    def test_nearest_decimal_conflict_is_not_accepted_as_integer(self):
        import ocr_engine as ocr
        candidates = [{"variant": "color", "text": "125", "score": .999},
                      {"variant": "contrast", "text": "125", "score": .998},
                      {"variant": "nearest", "text": "12.5", "score": .904}]
        self.assertEqual(ocr._choose_cell_value("125", candidates, 10.5)[0], "?")

    def test_integer_price_checks_inversion_and_attached_decimal(self):
        import ocr_engine as ocr
        import app_paths
        from PIL import Image
        image = Image.open(os.path.join(os.path.dirname(__file__), "tests", "fixtures",
                                       "sisetong-hanmaru-lucky-small.png"))
        words = [(200, 200, 80, 40, "102"), (223, 313, 92, 40, "125")]
        engine = mock.Mock(return_value=([["125", .999]], None))
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app_paths, "app_dir", return_value=directory), \
             mock.patch.object(ocr, "_get_rapid", return_value=engine):
            out = ocr._verify_price_cells(image, words, 4)
        self.assertEqual(out[-1][4], "?")
        self.assertEqual(engine.call_count, 5)
        image.close()

    def test_clean_integer_survives_inversion_check(self):
        import ocr_engine as ocr
        import app_paths
        from PIL import Image
        words = [(10, 10, 20, 12, "68"), (10, 30, 20, 12, "13")]
        for responses, expected in [(["13"] * 5, "13"), (["13"] * 3 + ["1.3"] * 2, "?")]:
            engine = mock.Mock(side_effect=[([[text, .99]], None) for text in responses])
            with tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(app_paths, "app_dir", return_value=directory), \
                 mock.patch.object(ocr, "_get_rapid", return_value=engine):
                out = ocr._verify_price_cells(Image.new("RGB", (60, 60), "white"), words, 1)
            self.assertEqual(out[-1][4], expected)
            self.assertEqual(engine.call_count, 5)

    def test_small_decimal_requires_all_five_strong_matching_variants(self):
        import ocr_engine as ocr
        labels = ["color", "contrast", "nearest", "inverse_smooth", "inverse_nearest"]
        candidates = [{"variant": label, "text": "9.6", "score": .986} for label in labels]
        self.assertEqual(ocr._choose_cell_value("9.6", candidates, 8.5)[0], "9.6")
        self.assertEqual(ocr._choose_cell_value("9.6", candidates[:-1], 8.5)[0], "?")
        for text, score in [("96", .999), ("9.6", .94)]:
            changed = candidates[:-1] + [dict(candidates[-1], text=text, score=score)]
            self.assertEqual(ocr._choose_cell_value("9.6", changed, 8.5)[0], "?")
        integers = [dict(c, text="96") for c in candidates]
        self.assertEqual(ocr._choose_cell_value("96", integers, 8.5)[0], "?")
        duplicates = candidates[:-1] + [candidates[0]]
        self.assertEqual(ocr._choose_cell_value("9.6", duplicates, 8.5)[0], "?")

    def test_cell_verification_failure_is_visible(self):
        import ocr_engine as ocr
        import app_paths
        from PIL import Image
        words = [(10, 10, 20, 12, "68"), (10, 30, 20, 12, "7.2")]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(app_paths, "app_dir", return_value=directory), \
             mock.patch.object(ocr, "_get_rapid", side_effect=RuntimeError("test")):
            out = ocr._verify_price_cells(Image.new("RGB", (60, 60), "white"), words, 1)
        self.assertEqual(out[-1][4], "?")

    def test_logged_hanmaru_missing_five_is_recovered(self):
        import ocr_engine as ocr
        rapid = [(89,145,201,44,"92y700^"), (72,238,79,55,"76"), (227,238,83,54,"92"),
                 (81,330,71,46,"6.5"), (233,332,61,43,"8.1"), (252,412,29,46,"6"),
                 (84,490,58,47,"1.5"), (239,490,52,46,"2.1")]
        fixed = ocr.repair_table(rapid, [(103,415,22,34,"5")])
        self.assertEqual(ocr.words_to_rows(fixed), ["92y700^", "76 92", "6.5 8.1", "5 6", "1.5 2.1"])
        missing = ocr.words_to_rows(ocr.filter_table_words(ocr.repair_table(rapid, [])))
        self.assertEqual(missing[3], "? 6")
        self.assertEqual(parse_lines(["한마루삼성"] + missing).rows[1], ["?", "6"])

    def test_windows_can_restore_entire_missing_row_and_year(self):
        import ocr_engine as ocr
        body = [(10,40,20,10,"60"), (60,40,20,10,"85"),
                (10,60,20,10,"4.1"), (60,60,20,10,"5.3"),
                (10,100,20,10,"1.5"), (60,100,20,10,"1.6")]
        win = [(10,20,20,10,"98y"), (10,80,20,10,"2.6"), (60,80,20,10,"3.7")]
        self.assertEqual(ocr.words_to_rows(ocr.repair_table(body, win)),
                         ["98y", "60 85", "4.1 5.3", "2.6 3.7", "1.5 1.6"])

    def test_words_to_rows_column_major(self):
        import ocr_engine
        # Windows OCR 이 열 단위로 읽은 경우(실측): 60, 2.6, 1.5, 85, 3.7, 1.6 → 위치로 행 복원
        words = [(5, 60, 20, 12, "60"), (5, 80, 20, 12, "2.6"), (5, 100, 20, 12, "1.5"),
                 (45, 60, 20, 12, "85"), (45, 80, 20, 12, "3.7"), (45, 100, 20, 12, "1.6"),
                 (5, 5, 60, 14, "샘머리1단"), (5, 30, 60, 12, "98y"), (50, 30, 30, 12, "1350^"),
                 (5, 70, 20, 12, "4.1"), (45, 70, 20, 12, "5.3")]
        self.assertEqual(ocr_engine.words_to_rows(words), SAMPLE)
        res = {"lines": [{"text": "x", "words": [
            {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        self.assertEqual(ocr_engine._result_to_lines(res), SAMPLE)
        # 상자 정보가 없으면 줄 텍스트 그대로
        self.assertEqual(ocr_engine._result_to_lines({"lines": [{"text": "a"}, {"text": "b"}]}), ["a", "b"])

    def test_prepare_keeps_white_text_on_colored_cells(self):
        from PIL import Image, ImageDraw
        import ocr_engine
        img = Image.new("RGB", (60, 40), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 20, 60, 40], fill=(92, 184, 92))       # 녹색 셀
        d.rectangle([10, 5, 30, 10], fill="black")             # 흰 배경의 검은 글자(대용)
        d.rectangle([10, 27, 30, 29], fill="white")            # 녹색 셀의 흰 글자(대용, 획 두께 3px)
        out = ocr_engine._prepare(img, 3).convert("L")
        self.assertEqual(out.size, (180, 120))
        self.assertLess(out.getpixel((60, 22)), 40)            # 검은 글자 → 어둡게
        self.assertLess(out.getpixel((60, 84)), 40)            # 색 셀의 흰 글자 → 어둡게(반전)
        self.assertGreater(out.getpixel((150, 100)), 200)      # 녹색 배경 → 밝게
        self.assertEqual(out.getpixel((150, 20)), 255)         # 흰 배경 → 그대로

    def test_merge_results_adds_missing_words_only(self):
        import ocr_engine
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        primary = res([(5, 5, 60, 14, "샘머리1단"), (5, 30, 30, 12, "98y"), (5, 60, 20, 12, "60"), (45, 60, 20, 12, "85"),
                       (5, 70, 20, 12, "4.1"), (45, 70, 20, 12, "5.3")])             # 1차: 아래 두 행 누락
        secondary = res([(5, 60, 20, 12, "60"), (45, 60, 20, 12, "85"), (6, 70, 18, 12, "41"),  # 겹침 → 무시
                         (5, 80, 20, 12, "2.6"), (45, 80, 20, 12, "3.7"), (5, 100, 20, 12, "1.5"), (45, 100, 20, 12, "1.6")])
        self.assertEqual(ocr_engine.merge_results(primary, secondary),
                         ["샘머리1단", "98y", "60 85", "4.1 5.3", "2.6 3.7", "1.5 1.6"])


    def test_filter_table_words_drops_map_text(self):
        import ocr_engine
        # 실측(샘머리2단): 지도 위 '단', '2', '21(' 이 표 옆에서 읽힘. 표는 85 한 열.
        words = [(20, 5, 120, 20, "샘머리2단"), (20, 35, 60, 14, "98y"), (85, 35, 50, 14, "2200^"),
                 (330, 10, 40, 16, "216"),                                   # 표 위쪽 지도 글자 (표 폭 밖)
                 (150, 70, 40, 16, "85"), (155, 95, 30, 16, "5"), (150, 120, 40, 16, "3.3"),
                 (5, 120, 30, 16, "단"), (300, 120, 40, 16, "21("), (60, 110, 15, 16, "2"),
                 (152, 145, 36, 16, "1.7")]
        rows = ocr_engine.words_to_rows(ocr_engine.filter_table_words(words))
        self.assertEqual(rows, ["샘머리2단", "98y 2200^", "85", "5", "3.3", "1.7"])
        # 대시(값 없음)는 표 안 토큰으로 남는다
        dash_words = words + [(155, 170, 30, 16, "—")]
        self.assertEqual(ocr_engine.words_to_rows(ocr_engine.filter_table_words(dash_words))[-1], "—")
        # 같은 행·같은 열에 두 단어(지도 'H21' 와 값 '5'): 열 중심에 가까운 '5' 만
        words2 = words + [(118, 95, 34, 16, "H21")]
        rows2 = ocr_engine.words_to_rows(ocr_engine.filter_table_words(words2))
        self.assertEqual(rows2, ["샘머리2단", "98y 2200^", "85", "5", "3.3", "1.7"])
        text, _ = lines_to_text(rows, area_divisor=2.48)
        self.assertEqual(text, "샘머리2단지 98\n34) 5.0/3.3")

    def test_merge_words_scales_bigger_variant(self):
        import ocr_engine
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        base = res([(10, 10, 20, 10, "60")])
        bigger = res([(15, 15, 30, 15, "60"), (15, 45, 30, 15, "4.1")])   # 1.5배 좌표
        merged = ocr_engine.merge_words([(base, 1.0), (bigger, 1.5)])
        self.assertEqual([w[4] for w in merged], ["60", "4.1"])
        self.assertAlmostEqual(merged[1][1], 30.0)

    def test_split_tokens(self):
        import ocr_engine
        toks = ocr_engine._split_tokens(100, 10, 90, 20, "98y 1350^")
        self.assertEqual([t[4] for t in toks], ["98y", "1350^"])
        self.assertEqual(toks[0][0], 100)
        self.assertAlmostEqual(toks[1][0] + toks[1][2], 190)

    def test_recognize_combines_rapid_numbers_and_windows_hangul(self):
        import ocr_engine
        from PIL import Image
        rapid = [(73, 155, 74, 49, "98y"), (171, 155, 123, 49, "1350^"), (63, 246, 84, 59, "60"), (213, 247, 83, 56, "85"),
                 (75, 340, 59, 43, "4.1"), (220, 340, 71, 43, "5.3"), (72, 423, 66, 52, "2.6"), (226, 422, 63, 54, "3.7")]
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        win = [(res([(71, 43, 262, 58, "샘머리1단"), (96, 152, 76, 40, "98y"), (83, 247, 74, 42, "60"),
                     (91, 338, 54, 36, "41")]), 1.0)]                       # Windows: 한글 + 오독 '41'
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_windows_results", return_value=win):
            lines = ocr_engine.recognize(Image.new("RGB", (10, 10)), "ko", 4)
        self.assertEqual(lines, ["샘머리1단", "98y 1350^", "60 85", "4.1 5.3", "2.6 3.7"])   # '41' 은 4.1 과 겹쳐 무시
        text, _ = lines_to_text(lines, area_divisor=2.48)
        self.assertEqual(text, "샘머리1단지 98\n24) 4.1/2.6\n34) 5.3/3.7")

    def test_hangul_name_beats_rapid_noise_at_same_spot(self):
        import ocr_engine
        from PIL import Image
        # 실측: RapidOCR 이 단지명 자리를 '2' 로 읽어 Windows 의 '샘머리1단' 이 겹침으로 버려졌다
        rapid = [(56, 31, 270, 71, "2"), (81, 140, 74, 47, "98y"), (180, 140, 123, 47, "1350^"),
                 (67, 235, 83, 54, "60"), (217, 234, 83, 54, "85"), (78, 328, 60, 42, "4.1"), (228, 328, 72, 43, "5.3")]
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        win = [(res([(59, 35, 262, 58, "샘머리1단"), (84, 144, 76, 40, "98y")]), 1.0)]
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_windows_results", return_value=win):
            lines = ocr_engine.recognize(Image.new("RGB", (10, 10)), "ko", 4)
        self.assertEqual(lines, ["샘머리1단", "98y 1350^", "60 85", "4.1 5.3"])

    def test_first_row_from_windows_rest_from_rapid(self):
        import ocr_engine
        from PIL import Image
        # 실측(샘머리2단): RapidOCR 이 첫 행을 '22' 로, Windows 가 '샘머리2단' 으로. 연식 행(98y) 위 = Windows 행만 사용
        rapid = [(56, 31, 270, 71, "22"), (81, 140, 74, 47, "98y"), (180, 140, 123, 47, "2200^"),
                 (150, 235, 40, 54, "85"), (155, 328, 30, 42, "5"), (150, 407, 40, 48, "3.3"), (152, 490, 36, 46, "1.7")]
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        win = [(res([(59, 35, 262, 58, "샘머리2단"), (84, 144, 76, 40, "98y"), (150, 235, 40, 54, "85"),
                     (150, 407, 40, 48, "33")]), 1.0)]                        # Windows 의 표 숫자는 쓰지 않는다
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_windows_results", return_value=win):
            lines = ocr_engine.recognize(Image.new("RGB", (10, 10)), "ko", 4)
        self.assertEqual(lines, ["샘머리2단", "98y 2200^", "85", "5", "3.3", "1.7"])
        text, _ = lines_to_text(lines, area_divisor=2.48)
        self.assertEqual(text, "샘머리2단지 98\n34) 5.0/3.3")

    def test_repair_area_row_from_windows_when_rapid_misreads(self):
        import ocr_engine
        from PIL import Image
        # 실측(청솔): RapidOCR 이 면적 '74' 를 't2' 로 읽음 → 열은 2개인데 면적 1개. Windows 가 같은 자리에서 '74' 를 읽었다.
        rapid = [(78, 196, 113, 75, "91y"), (229, 196, 151, 75, "980*"),
                 (60, 332, 116, 82, "t2"), (275, 331, 127, 82, "85"),
                 (91, 475, 48, 62, "5"), (295, 473, 90, 65, "6.1"),
                 (66, 590, 103, 80, "2.7"), (318, 594, 45, 70, "3"),
                 (65, 712, 105, 70, "2.3"), (301, 712, 82, 70, "3.1")]
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        win = [(res([(143, 35, 174, 54, "청솔"), (435, 202, 7, 82, "1"), (84, 204, 104, 60, "91y"), (212, 204, 159, 48, "980^"),
                     (63, 339, 106, 62, "74"), (95, 479, 38, 50, "5"), (75, 599, 86, 50, "2.7"), (71, 719, 94, 50, "2.3"),
                     (283, 339, 114, 62, "85"), (323, 599, 38, 50, "3"), (307, 719, 66, 50, "3.1")]), 1.0)]
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_windows_results", return_value=win):
            lines = ocr_engine.recognize(Image.new("RGB", (10, 10)), "ko", 4)
        self.assertEqual(lines, ["청솔", "91y 980*", "74 85", "5 6.1", "2.7 3", "2.3 3.1"])
        text, rec = lines_to_text(lines, area_divisor=2.48)
        self.assertEqual(text, "청솔 91\n30) 5.0/2.7\n34) 6.1/3.0")
        self.assertEqual(rec.warnings, [])

    def test_rapid_words_drop_cjk_tokens(self):
        import ocr_engine
        class FakeEngine:
            def __call__(self, arr):
                return ([[[[0, 0], [100, 0], [100, 20], [0, 20]], "叶2R", 0.6],
                         [[[0, 30], [40, 30], [40, 50], [0, 50]], "60", 1.0],
                         [[[0, 60], [90, 60], [90, 80], [0, 80]], "98y 1350^", 0.9],
                         [[[0, 90], [30, 90], [30, 110], [0, 110]], "一", 0.8]], None)    # 대시를 한자 '一' 로 읽음
        from PIL import Image
        with mock.patch.object(ocr_engine, "_get_rapid", return_value=FakeEngine()):
            words = ocr_engine._rapid_words(Image.new("RGB", (10, 10)), 1)
        self.assertEqual([w[4] for w in words], ["60", "98y", "1350^", "-"])

    def test_korean_model_words_take_precedence_for_name(self):
        import ocr_engine
        from PIL import Image
        rapid = [(56, 31, 270, 71, "22"), (81, 140, 74, 47, "98y"), (180, 140, 123, 47, "1350^"),
                 (67, 235, 83, 54, "60"), (217, 234, 83, 54, "85"), (78, 328, 60, 42, "4.1"), (228, 328, 72, 43, "5.3")]
        ko = [(59, 35, 262, 58, "샘머리1단"), (81, 140, 74, 47, "98y")]          # 한국어 모델: 정확한 단지명
        def res(words):
            return {"lines": [{"text": "x", "words": [
                {"text": t, "bounding_rect": {"x": x, "y": y, "width": w, "height": h}} for x, y, w, h, t in words]}]}
        win = [(res([(59, 35, 262, 58, "생머리1단")]), 1.0)]                      # Windows: 오독
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_rapid_korean_words", return_value=ko), \
             mock.patch.object(ocr_engine, "_windows_results", return_value=win):
            lines = ocr_engine.recognize(Image.new("RGB", (10, 10)), "ko", 4)
        self.assertEqual(lines[0], "샘머리1단")
        # 한국어 모델이 없으면(빈 목록) Windows 결과를 쓴다
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_rapid_korean_words", return_value=[]), \
             mock.patch.object(ocr_engine, "_windows_results", return_value=win):
            lines = ocr_engine.recognize(Image.new("RGB", (10, 10)), "ko", 4)
        self.assertEqual(lines[0], "생머리1단")

    def test_korean_model_engine_plumbing(self):
        """한국어 모델 파일이 있을 때 rec_model_path 로 RapidOCR 을 만드는 경로 — 내장 ch 모델을 대용으로 검사."""
        import ocr_engine
        try:
            import rapidocr_onnxruntime
        except ImportError:
            self.skipTest("rapidocr_onnxruntime 없음")
        ch_model = os.path.join(os.path.dirname(rapidocr_onnxruntime.__file__), "models", "ch_PP-OCRv4_rec_infer.onnx")
        ocr_engine._rapid_ko_engine, ocr_engine._rapid_ko_checked = None, False
        try:
            with mock.patch.object(ocr_engine, "korean_model_path", return_value=ch_model):
                eng = ocr_engine._get_rapid_korean()
                self.assertIsNotNone(eng)
                from PIL import Image
                words = ocr_engine._rapid_words(
                    Image.open("/root/.claude/uploads/c576b331-be36-5d18-b95e-0e9be8063959/aa3d33c7-image.png")
                    if os.path.isfile("/root/.claude/uploads/c576b331-be36-5d18-b95e-0e9be8063959/aa3d33c7-image.png")
                    else Image.new("RGB", (80, 80), "white"), 4, engine=eng, keep_cjk=True, label="rapid-ko")
                self.assertIsInstance(words, list)
        finally:
            ocr_engine._rapid_ko_engine, ocr_engine._rapid_ko_checked = None, False
        with mock.patch.object(ocr_engine.os.path, "isfile", return_value=False):
            self.assertIsNone(ocr_engine.korean_model_path())

    def test_recognize_rapid_only_when_windows_pack_missing(self):
        import ocr_engine
        from PIL import Image
        rapid = [(63, 246, 84, 59, "60"), (75, 340, 59, 43, "4.1"), (72, 423, 66, 52, "2.6")]
        def missing(*a, **k):
            raise ocr_engine.OcrLanguageMissingError("x", "ko", "ko-KR")
        with mock.patch.object(ocr_engine, "_rapid_words", return_value=rapid), \
             mock.patch.object(ocr_engine, "_windows_results", side_effect=missing):
            self.assertEqual(ocr_engine.recognize(Image.new("RGB", (10, 10))), ["60", "4.1", "2.6"])

    def test_variants_shapes(self):
        from PIL import Image
        import ocr_engine
        img = Image.new("RGB", (40, 30), "white")
        vs = ocr_engine._variants(img, 4)
        self.assertEqual(len(vs), 5)
        self.assertEqual(vs[0][0].size, (160, 120))
        self.assertEqual(vs[2][0].size, (240, 180))
        self.assertEqual(vs[2][1], 1.5)


class NameDictTest(unittest.TestCase):
    def test_jamo_similarity_and_match(self):
        import name_dict
        names = ["샘머리1단지", "샘머리2단지", "청솔", "꿈나무", "목련"]
        self.assertEqual(name_dict.decompose("샘"), "ㅅㅐㅁ")
        self.assertEqual(name_dict.best_match("생머리1단지", names)[0], "샘머리1단지")   # 실측 오독
        self.assertEqual(name_dict.best_match("꿍나무", names)[0], "꿈나무")
        self.assertEqual(name_dict.best_match("한마루", names), None)                    # 사전에 없음
        self.assertEqual(name_dict.best_match("목련2단지", names), None)                  # 숫자 다르면 다른 단지
        self.assertEqual(name_dict.best_match("샘머리2단지", names), ("샘머리2단지", 1.0))

    def test_load_and_learn(self):
        import name_dict
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "단지목록.txt")
            self.assertEqual(name_dict.load_names(p), [])
            self.assertTrue(name_dict.learn(p, "샘머리1단지"))
            self.assertFalse(name_dict.learn(p, "샘머리1단지"))     # 중복 아님
            self.assertFalse(name_dict.learn(p, "98"))              # 한글 없는 건 무시
            with open(p, "a", encoding="utf-8") as f:
                f.write("[둔산생활권]\n# 주석\n청솔\n")
            self.assertEqual(name_dict.load_names(p), ["샘머리1단지", "청솔"])


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


class GuiSmokeTest(unittest.TestCase):
    def test_tabs_default_to_naver_and_separate_clipboard_types(self):
        import gui_app
        gui = gui_app.SisePickerGUI(self.root, config=Config(watch_clipboard=True), ask_zone_on_start=False)
        self.assertTrue(gui._nav_mode())
        self.assertEqual([gui.notebook.tab(t, "text") for t in gui.notebook.tabs()], ["네이버 부동산", "시세통", "이미지 OCR"])
        gui.notebook.select(gui.web_tab)
        self.assertTrue(gui._web_mode())
        self.assertFalse(gui.preview_frame.grid_info())
        with mock.patch.object(gui, "_read_web_clipboard", return_value=False) as web, \
             mock.patch.object(gui, "_grab", return_value=None) as image:
            gui.read_clipboard()
            web.assert_called_once()
            image.assert_not_called()
            gui._watch_tick()
            image.assert_not_called()
            gui.notebook.select(gui.ocr_tab)
            gui._on_tab_changed()
            self.assertTrue(gui.preview_frame.grid_info())
            web.reset_mock()
            gui.read_clipboard()
            web.assert_not_called()
            image.assert_called_once()
        gui.result_grid.set_text("단지 92\n85) 8.5/3.5")
        gui.notebook.select(gui.web_tab)
        gui._on_tab_changed()
        self.assertEqual(gui.result_grid.get_text(), "단지 92\n85) 8.5/3.5")
        self.assertFalse(gui.preview_frame.grid_info())

    def test_web_import_bypasses_ocr_and_holds_automatic_outputs(self):
        import gui_app
        from web_import import PREFIX
        gui = gui_app.SisePickerGUI(self.root, config=Config(auto_copy=True, auto_add_ppt=True,
              record_dir=os.path.join(self.tmp.name,"rec")), ask_zone_on_start=False)
        gui.notebook.select(gui.web_tab)
        raw = PREFIX+json.dumps(dict(source="https://sisetong.kr/",name="한마루럭키",year="92",
                                    areas=["76","102"], rows=[["-","12.5"],["3.7","6.5"]]))
        with mock.patch.object(self.root,"clipboard_get",return_value=raw), \
             mock.patch.object(gui,"_grab") as grab, \
             mock.patch.object(gui,"_copy_to_clipboard") as copy, \
             mock.patch.object(gui,"_record") as record:
            gui.read_clipboard()
            self.assertIn("102) 12.5/6.5", gui.result_grid.get_text())
            self.assertEqual(gui.result_grid.name.get(),"한마루럭키")
            self.assertTrue(gui._pending_record)
            grab.assert_not_called()
            copy.assert_not_called()
            record.assert_not_called()
            gui.result_grid.rows[0][0][1].set("1.0")
            gui._read_web_clipboard(watch=True)
            self.assertIn("76) 1.0/3.7",gui.result_grid.get_text())

    """tkinter 생성 → OCR mock → 결과/클립보드 → config 왕복 → destroy."""

    def test_empty_prices_still_show_sale_and_lease_columns(self):
        from result_grid import ResultGrid
        grid = ResultGrid(self.root)
        grid.set_text("국화신동아 92\n77) \n84) \n92) ")
        self.assertEqual(len(grid.rows), 3)
        self.assertTrue(all(len(variables) == 3 for variables, _ in grid.rows))
        self.assertEqual(len(grid.issues()), 6)
        self.assertEqual(grid.get_text(), "국화신동아 92\n77) ?/?\n84) ?/?\n92) ?/?")
        grid.set_text("국화신동아 92\n77) 6.5", price_columns=1)
        self.assertEqual(grid.get_text(), "국화신동아 92\n77) 6.5")

    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"디스플레이 없음: {e}")
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(config_manager, "config_path",
                                        lambda: os.path.join(self.tmp.name, "cfg.json"))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        try:
            self.root.destroy()
        except Exception:
            pass
        self.tmp.cleanup()

    def test_unknown_cells_hold_automatic_outputs(self):
        import gui_app
        cfg = Config(auto_copy=True, auto_add_ppt=True, record_dir=os.path.join(self.tmp.name, "rec"))
        gui = gui_app.SisePickerGUI(self.root, config=cfg, ask_zone_on_start=False)
        lines = ["가나", "98y", "60 85", "? 5.3", "2.6 3.7"]
        text, rec = lines_to_text(lines)
        with mock.patch.object(gui, "_record") as record, \
             mock.patch.object(gui, "_copy_to_clipboard") as copy, \
             mock.patch.object(gui, "add_to_ppt") as ppt:
            gui._handle_result(("ok", lines, text, rec, ""))
        record.assert_not_called()
        copy.assert_not_called()
        ppt.assert_not_called()
        self.assertEqual(gui.result_text(), text)
        self.assertIn("보류", gui.var_status.get())

    def test_grid_edit_highlights_and_records_pending_result_once(self):
        import gui_app
        from result_grid import ResultGrid
        cfg = Config(auto_copy=False, record_dir=os.path.join(self.tmp.name, "rec"), zone="테스트",
                     use_name_dict=False)
        gui = gui_app.SisePickerGUI(self.root, config=cfg, ask_zone_on_start=False)
        # 기존 항목 이후 보류된 새 항목을 고쳐도 이전 항목을 덮어쓰지 않는다.
        gui._record("이전단지 90\n60) 1.0/0.5", new_entry=True)
        lines = ["가나", "98y", "60 85", "? 5.3", "2.6 3.7"]
        text, rec = lines_to_text(lines)
        gui._handle_result(("ok", lines, text, rec, ""))
        issue = gui.result_grid.issues()[0]
        self.assertEqual(issue["entry"].cget("background"), ResultGrid.REVIEW)
        with mock.patch.object(gui, "_copy_to_clipboard") as copy, \
             mock.patch.object(gui_app.pptx_writer, "add_text_to_pptx") as ppt:
            gui.copy_result()
            gui.add_to_ppt()
            copy.assert_not_called()
            ppt.assert_not_called()
            issue["var"].set("bad")
            self.assertEqual(len(gui.result_grid.issues()), 1)
            issue["var"].set("4.1")
            self.assertEqual(issue["entry"].cget("background"), ResultGrid.EDITED)
            self.assertEqual(gui.result_grid.issues(), [])
            gui.copy_result()
            gui.copy_result()
            self.assertEqual(copy.call_args.args[0], "가나 98\n60) 4.1/2.6\n85) 5.3/3.7")
        self.assertEqual(gui.recorder.count, 2)
        with open(gui.recorder.file_for("24"), encoding="utf-8-sig") as f:
            self.assertEqual(f.read().splitlines(), ["이전단지 90' 1.0", "가나 98' 4.1"])

    def test_grid_roundtrip_validation_and_paste(self):
        import gui_app
        from result_grid import ResultGrid
        grid = ResultGrid(self.root)
        text = "가나(1단지) 98\n60) -/-0.3/1.2\n85) 5.3/3.7/1.6"
        grid.set_text(text)
        self.assertEqual(grid.get_text(), text)
        self.assertEqual(grid.issues(), [])
        grid.rows[0][0][1].set("")
        self.assertEqual(len(grid.issues()), 1)
        grid.rows[1][0][2].set("?")
        with mock.patch.object(grid, "focus_get", return_value=None):
            grid.focus_next_issue()
            first = grid._last_issue_entry
            grid.focus_next_issue()
            self.assertNotEqual(grid._last_issue_entry, first)
        grid.set_text("새단지 05\n84) 9.0/4.0")
        self.assertEqual(len(grid.rows), 1)
        self.assertEqual(grid.issues(), [])
        gui = gui_app.SisePickerGUI(self.root, config=Config(record_enabled=False), ask_zone_on_start=False)
        with mock.patch.object(gui, "read_clipboard") as read:
            gui._paste_shortcut(mock.Mock(widget=grid.cells[0]["entry"]))
            read.assert_not_called()
            gui._paste_shortcut(mock.Mock(widget=gui.btn_clip))
            read.assert_called_once()

    def test_flow(self):
        from PIL import Image
        import gui_app

        img = Image.new("RGB", (100, 120), "white")
        fake_ocr = mock.Mock(return_value=SAMPLE)
        cfg = Config(pptx_path=os.path.join(self.tmp.name, "no.pptx"), auto_copy=True,
                     record_dir=os.path.join(self.tmp.name, "rec"), zone="둔산생활권", show_confirm_dialog=True)
        gui = gui_app.SisePickerGUI(self.root, config=cfg, ocr_func=fake_ocr,
                                    clipboard_grab=lambda: img, ask_zone_on_start=False)
        with mock.patch.object(gui_app.messagebox, "askokcancel", return_value=True) as ask:
            gui.notebook.select(gui.ocr_tab)
            gui.read_clipboard()
            for _ in range(100):          # 워커 스레드 → 큐 → GUI
                self.root.update()
                if not gui._busy:
                    break
                time.sleep(0.05)
            ask.assert_called_once()
            self.assertIn("60m² → 24평", ask.call_args[0][1])
        self.assertFalse(gui._busy)
        fake_ocr.assert_called_once()
        self.assertEqual(gui.result_text(), EXPECTED)          # 기본: 결과는 표의 원래 숫자(m²) 그대로
        self.assertIn("60m² → 24평, 85m² → 34평", gui.var_conv.get())
        self.assertIn("인식 완료", gui.var_status.get())
        self.assertIn("기록 1건", gui.var_status.get())
        f24 = os.path.join(self.tmp.name, "rec", "둔산생활권_24평.txt")
        f34 = os.path.join(self.tmp.name, "rec", "둔산생활권_34평.txt")
        with open(f24, encoding="utf-8-sig") as f:
            self.assertEqual(f.read().splitlines(), ["샘머리1단지 98' 4.1"])
        with open(f34, encoding="utf-8-sig") as f:
            self.assertEqual(f.read().splitlines(), ["샘머리1단지 98' 5.3"])
        # 결과를 고치고 복사하면 기록의 마지막 항목이 교체된다
        gui.result_grid.set_text("샘머리2단지 98\n60) 4.1/2.6")
        gui.copy_result()
        with open(f24, encoding="utf-8-sig") as f:
            self.assertEqual(f.read().splitlines(), ["샘머리2단지 98' 4.1"])
        with open(f34, encoding="utf-8-sig") as f:
            self.assertEqual(f.read().strip(), "")
        # 생활권 변경 다이얼로그
        gui.config.zone_catalogs[gui._zone_key()].append(dict(name="서초생활권", slide_id=None))
        gui.var_zone.set("서초생활권")
        gui._apply_zone()
        self.assertEqual(gui.recorder.zone, "서초생활권")
        self.assertEqual(gui.config.zone_history[:2], ["서초생활권", "둔산생활권"])
        try:
            self.assertEqual(self.root.clipboard_get(), EXPECTED)
        except Exception:
            pass  # 헤드리스 환경에서 클립보드가 없을 수 있음

        # PPT 없음 → 에러 다이얼로그 대신 상태 메시지 (messagebox 는 mock)
        with mock.patch.object(gui_app.messagebox, "showerror") as err:
            gui.add_to_ppt()
            err.assert_called_once()
        self.assertIn("실패", gui.var_status.get())

        # config 왕복: GUI 값 변경 → 저장 → 로드
        gui.var_rows.set(3)
        gui.var_pptx.set(r"D:\p\q.pptx")
        gui.on_close()
        loaded = load_config()
        self.assertEqual(loaded.rows_to_use, 3)
        self.assertEqual(loaded.pptx_path, r"D:\p\q.pptx")
        self.assertEqual(loaded.box_font_pt, cfg.box_font_pt)  # GUI 에 없는 필드 보존

    def test_auto_add_ppt(self):
        from PIL import Image
        from pptx import Presentation
        import gui_app
        p = os.path.join(self.tmp.name, "auto.pptx")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(p)
        gui = gui_app.SisePickerGUI(self.root, config=Config(pptx_path=p, auto_add_ppt=True, auto_copy=False,
                                                  record_dir=os.path.join(self.tmp.name, "rec"), zone="둔산생활권",
                                                  show_confirm_dialog=False),
                                    ocr_func=lambda i, l, s: SAMPLE,
                                    clipboard_grab=lambda: Image.new("RGB", (10, 10)), ask_zone_on_start=False)
        gui.notebook.select(gui.ocr_tab)
        gui.read_clipboard()
        for _ in range(100):
            self.root.update()
            if not gui._busy:
                break
            time.sleep(0.05)
        self.assertIn("PPT 2번 슬라이드(둔산생활권)에 추가됨", gui.var_status.get())
        shapes = [s for s in Presentation(p).slides[1].shapes if s.name == "SisePicker-1"]
        self.assertEqual(shapes[0].text_frame.text, EXPECTED)
        gui.on_close()

    def test_name_dict_correction_and_learning(self):
        from PIL import Image
        import gui_app
        import name_dict
        ppt_dir = os.path.join(self.tmp.name, "ppt")
        os.makedirs(ppt_dir)
        cfg = Config(pptx_path=os.path.join(ppt_dir, "x.pptx"), zone="둔산생활권", auto_copy=False)
        dict_path = os.path.join(ppt_dir, "단지목록.txt")
        name_dict.learn(dict_path, "샘머리1단지")
        # OCR 이 '생머리1단' 으로 읽음 → 사전 보정으로 '샘머리1단지'
        gui = gui_app.SisePickerGUI(self.root, config=cfg, ocr_func=lambda i, l, s: ["생머리1단"] + SAMPLE[1:],
                                    clipboard_grab=lambda: Image.new("RGB", (10, 10)), ask_zone_on_start=False)
        gui.notebook.select(gui.ocr_tab)
        gui.read_clipboard()
        for _ in range(100):
            self.root.update()
            if not gui._busy:
                break
            time.sleep(0.05)
        self.assertEqual(gui.result_text(), EXPECTED)
        self.assertIn("단지명 보정: 생머리1단지 → 샘머리1단지", gui.var_conv.get())
        # 사용자가 이름을 고쳐 복사하면 사전에 학습된다
        gui.result_grid.set_text("한마루 98\n60) 4.1/2.6\n85) 5.3/3.7")
        gui.copy_result()
        self.assertIn("한마루", name_dict.load_names(dict_path))
        gui.on_close()

    def test_result_in_pyeong_option(self):
        from PIL import Image
        import gui_app
        gui = gui_app.SisePickerGUI(self.root, config=Config(record_dir=os.path.join(self.tmp.name, "rec"),
                                                             zone="둔산생활권", result_in_pyeong=True, auto_copy=False),
                                    ocr_func=lambda i, l, s: SAMPLE,
                                    clipboard_grab=lambda: Image.new("RGB", (10, 10)), ask_zone_on_start=False)
        gui.notebook.select(gui.ocr_tab)
        gui.read_clipboard()
        for _ in range(100):
            self.root.update()
            if not gui._busy:
                break
            time.sleep(0.05)
        self.assertEqual(gui.result_text(), EXPECTED_PY)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "rec", "둔산생활권_24평.txt")))
        gui.on_close()

    def test_lang_missing_offers_install(self):
        from PIL import Image
        import gui_app
        import ocr_engine

        def bad_ocr(i, l, s):
            raise ocr_engine.OcrLanguageMissingError("no pack", "ko", "ko-KR")

        gui = gui_app.SisePickerGUI(self.root, config=Config(record_dir=os.path.join(self.tmp.name, "rec")),
                                    ocr_func=bad_ocr, clipboard_grab=lambda: Image.new("RGB", (10, 10)),
                                    ask_zone_on_start=False)
        with mock.patch.object(gui_app.messagebox, "askyesno", return_value=True) as ask, \
             mock.patch.object(ocr_engine, "install_ocr_pack", return_value=True) as inst:
            gui.notebook.select(gui.ocr_tab)
            gui.read_clipboard()
            for _ in range(100):
                self.root.update()
                if not gui._busy:
                    break
                time.sleep(0.05)
            ask.assert_called_once()
            inst.assert_called_once_with("ko")
        self.assertIn("설치 창", gui.var_status.get())
        self.assertEqual(ocr_engine.capability_name("ko"), "Language.OCR~~~ko-KR~0.0.1.0")
        gui.on_close()

    def test_records_dir_next_to_pptx(self):
        import gui_app
        cfg = Config(pptx_path=os.path.join(self.tmp.name, "ppt", "시세.pptx"))   # record_dir 비어 있음
        gui = gui_app.SisePickerGUI(self.root, config=cfg, ocr_func=mock.Mock(),
                                    clipboard_grab=lambda: None, ask_zone_on_start=False)
        self.assertEqual(gui.recorder.directory, os.path.join(self.tmp.name, "ppt", "records"))
        gui.var_pptx.set(os.path.join(self.tmp.name, "other", "b.pptx"))   # PPT 를 바꾸면 기록 폴더도 따라간다
        gui._save_config()
        self.assertEqual(gui.recorder.directory, os.path.join(self.tmp.name, "other", "records"))
        gui.on_close()

    def test_confirm_cancel_skips_record(self):
        from PIL import Image
        import gui_app
        rec = os.path.join(self.tmp.name, "rec")
        gui = gui_app.SisePickerGUI(self.root, config=Config(record_dir=rec, zone="둔산생활권", show_confirm_dialog=True),
                                    ocr_func=lambda i, l, s: SAMPLE,
                                    clipboard_grab=lambda: Image.new("RGB", (10, 10)), ask_zone_on_start=False)
        with mock.patch.object(gui_app.messagebox, "askokcancel", return_value=False):
            gui.notebook.select(gui.ocr_tab)
            gui.read_clipboard()
            for _ in range(100):
                self.root.update()
                if not gui._busy:
                    break
                time.sleep(0.05)
        self.assertIn("건너뜀", gui.var_status.get())
        self.assertFalse(os.path.isdir(rec))
        self.assertEqual(gui.result_text(), EXPECTED)   # 결과는 화면에 남아 있어 고쳐서 쓸 수 있다
        gui.on_close()

    def test_always_on_top_option(self):
        import gui_app
        # xvfb(창 관리자 없음)에서는 실제 속성이 반영되지 않아 호출만 확인한다
        with mock.patch.object(self.root, "attributes", wraps=self.root.attributes) as attrs:
            gui = gui_app.SisePickerGUI(self.root, config=Config(record_dir=os.path.join(self.tmp.name, "rec"),
                                                                 always_on_top=True),
                                        ocr_func=mock.Mock(), clipboard_grab=lambda: None, ask_zone_on_start=False)
            attrs.assert_any_call("-topmost", True)
            gui.var_topmost.set(False)
            gui._on_topmost_toggle()
            attrs.assert_any_call("-topmost", False)
        self.assertFalse(load_config().always_on_top)
        self.assertIn("항상 위", gui.var_status.get())
        gui.on_close()

    def test_clipboard_without_image(self):
        import gui_app
        gui = gui_app.SisePickerGUI(self.root, config=Config(record_dir=os.path.join(self.tmp.name, "rec")),
                                    ocr_func=mock.Mock(), ask_zone_on_start=False,
                                    clipboard_grab=lambda: None)
        gui.notebook.select(gui.ocr_tab)
        gui.read_clipboard()
        self.assertIn("이미지 또는 시세통 가져오기 데이터가 없습니다", gui.var_status.get())
        gui.on_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
