import unittest,sys,pathlib,tempfile,os
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
import official,core
from datetime import datetime

class OfficialTests(unittest.TestCase):
 def test_fixture(self):
  r=official.parse_fixture(dict(jc_no='周三001',date='2026-11-04',kickoff='2026-11-04 20:00',league='测试',home='A',away='B'),'上传','', '待核对')
  self.assertEqual(r['jc_no'],'周三001')
 def test_missing_number(self):
  with self.assertRaises(ValueError):official.parse_fixture(dict(date='2026-11-04',kickoff='2026-11-04 20:00',league='测试',home='A',away='B'),'上传')
 def test_bad_time(self):
  with self.assertRaises(ValueError):official.parse_fixture(dict(jc_no='001',date='2026-11-04',kickoff='tomorrow',league='测试',home='A',away='B'),'上传')
 def test_normalize(self):
  self.assertEqual(official.normalized_team('Arsenal FC'),official.normalized_team('Arsenal'))
 def test_empty_no_prediction(self):
  self.assertRaises(ValueError,core.predict,None,1.4)
if __name__=='__main__':unittest.main()
