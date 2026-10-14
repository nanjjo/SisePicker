import copy
import json
import os
import tempfile
import unittest
from unittest import mock
from naver_import import PREFIX, parse_naver_text, group_naver, as_record, recording_text, create_guide
from config_manager import Config

SAMPLE={'source':'https://new.land.naver.com/','complexId':'140148','name':'고덕풍경채어바니티','households':'780',
 'approvalDate':'2024-01-30','complete':True,'warnings':[],
 'types':[{'key':'117MB','supplyPyeong':'35','exclusiveArea':'84.23','sale':'18.5','lease':'8.5'},
          {'key':'119SA','supplyPyeong':'36','exclusiveArea':'84.19','sale':'17.5','lease':'9.0'},
          {'key':'138A','supplyPyeong':'42','exclusiveArea':'101.04','sale':'25.0','lease':'12.0'}]}

class NaverImportTest(unittest.TestCase):
    def test_grouping_and_filter_are_independent(self):
        data=parse_naver_text(PREFIX+json.dumps(SAMPLE))
        self.assertEqual([(g['area'],g['sale'],g['lease']) for g in group_naver(data)], [('84','17.5','8.5')])
        self.assertEqual([g['area'] for g in group_naver(data,'supply')],['35','36'])
        self.assertEqual([g['area'] for g in group_naver(data,cutoff='exclusive')],['84','101'])
        groups=group_naver(data)
        self.assertEqual(recording_text(groups,'고덕 24\n84) 17.5/8.5'),'고덕 24\n85) 17.5/8.5')
    def test_hyphenated_area_types(self):
        data=copy.deepcopy(SAMPLE)
        data['types'][0]['key']='83A-2'
        self.assertEqual(parse_naver_text(PREFIX+json.dumps(data))['types'][0]['key'],'83A-2')
        data['types'][0]['key']='83A-'
        with self.assertRaises(ValueError):parse_naver_text(PREFIX+json.dumps(data))

    def test_numbered_types_group_by_numeric_area(self):
        data=copy.deepcopy(SAMPLE)
        data['types']=[dict(key='76D1',supplyPyeong='23',exclusiveArea='59.1',sale='6.0',lease='4.5'),
                       dict(key='76D2',supplyPyeong='23',exclusiveArea='59.2',sale='6.5',lease='4.0')]
        parsed=parse_naver_text(PREFIX+json.dumps(data))
        self.assertEqual([(g['area'],g['sale'],g['lease']) for g in group_naver(parsed)], [('59','6.0','4.0')])
        self.assertEqual([g['area'] for g in group_naver(parsed,'supply')], ['23'])

    def test_validation(self):
        self.assertIsNone(parse_naver_text('hello'))
        for key,value in [('source','https://evil.test'),('households','780^'),('approvalDate','2024-02-31'),('complete','true')]:
            data=copy.deepcopy(SAMPLE);data[key]=value
            with self.assertRaises(ValueError):parse_naver_text(PREFIX+json.dumps(data))
        data=copy.deepcopy(SAMPLE);data['types'][0]['sale']='125/6'
        with self.assertRaises(ValueError):parse_naver_text(PREFIX+json.dumps(data))
    def test_missing_values_remain_unknown(self):
        data=copy.deepcopy(SAMPLE)
        for row in data['types']:row['sale']='?'
        self.assertEqual(group_naver(data)[0]['sale'],'?')
    def test_guide_bundles_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            text=create_guide(d).read_text('utf-8')
            self.assertIn('javascript:',text);self.assertIn('네이버 부동산 → SisePicker',text)

class NaverGuiTest(unittest.TestCase):
    def test_import_switch_output_and_recording(self):
        import tkinter as tk
        import gui_app
        root=tk.Tk();root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as d, mock.patch.object(gui_app,'save_config'):
                gui=gui_app.SisePickerGUI(root,config=Config(pptx_path=os.path.join(d,'t.pptx'),auto_copy=True,auto_add_ppt=True),ask_zone_on_start=False)
                gui.notebook.select(gui.naver_tab)
                with mock.patch.object(root,'clipboard_get',return_value=PREFIX+json.dumps(SAMPLE)),mock.patch.object(gui,'add_to_ppt') as ppt:
                    gui.read_clipboard();ppt.assert_not_called()
                self.assertEqual(gui.var_nav_basis.get(),'공급평수 (평)')
                self.assertIn('35)',gui.result_text());self.assertIn('36)',gui.result_text())
                gui.var_nav_basis.set('전용면적 (㎡)');gui._regroup_naver()
                self.assertEqual(gui.result_text(),"고덕풍경채어바니티 24' 780^\n84) 17.5/8.5")
                self.assertTrue(gui._ready_for_output())
                gui.var_pyeong.set(True)
                self.assertIn('84)',gui.result_text())  # Never use legacy divisor on Naver areas.
                gui.var_nav_basis.set('공급평수 (평)');gui._regroup_naver()
                self.assertIn('35)',gui.result_text());self.assertIn('36)',gui.result_text())
                gui.var_nav_basis.set('전용면적 (㎡)');gui._regroup_naver()
                gui._record(gui.result_text(),True)
                self.assertTrue(os.path.exists(gui.recorder.file_for('34')))
                gui._nav_record['complete']=False
                self.assertFalse(gui._ready_for_output());gui.var_nav_review.set(True);self.assertTrue(gui._ready_for_output())
                gui.var_approval.set('2024-02-31');self.assertFalse(gui._ready_for_output())
                from sise_parser import lines_to_text
                lines=['단지','99y','60','1','2'];text,rec=lines_to_text(lines)
                gui._handle_result(('web',lines,text,rec,''))
                self.assertIsNone(gui._nav_record)
                gui.on_close()
        finally:
            try:root.destroy()
            except tk.TclError:pass

if __name__=='__main__':unittest.main()
