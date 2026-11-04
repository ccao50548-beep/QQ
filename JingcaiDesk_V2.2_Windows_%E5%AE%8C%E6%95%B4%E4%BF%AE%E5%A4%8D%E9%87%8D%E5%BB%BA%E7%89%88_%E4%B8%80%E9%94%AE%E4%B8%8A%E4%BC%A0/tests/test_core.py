import sys, pathlib, unittest, math
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
from core import predict, normalize
class Test(unittest.TestCase):
 def test_probabilities(self):
  p=predict(1.6,1.1)
  self.assertAlmostEqual(sum(p['wdl']),1,places=7)
  self.assertAlmostEqual(sum(p['totals']),1,places=7)
  self.assertGreater(p['wdl'][0],p['wdl'][2])
 def test_symmetry(self):
  p=predict(1,1)
  self.assertAlmostEqual(p['wdl'][0],p['wdl'][2],places=7)
 def test_missing(self):
  with self.assertRaises(ValueError):predict(None,1)
 def test_row(self):
  r=normalize({'match_id':'001','date':'2026-11-03','home':'A','away':'B'})
  self.assertIsNone(r['home_xg'])
if __name__=='__main__':unittest.main()
