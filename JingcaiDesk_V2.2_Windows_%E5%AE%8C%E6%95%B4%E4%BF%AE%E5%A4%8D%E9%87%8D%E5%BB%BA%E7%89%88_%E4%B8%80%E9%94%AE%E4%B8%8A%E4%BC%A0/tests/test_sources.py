import sys,pathlib,unittest
from datetime import datetime,timedelta
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
import sources,core

class TestSource(unittest.TestCase):
 def test_kickoff(self):
  self.assertEqual(sources.kickoff_cst('2026-11-03T11:00:00Z').strftime('%Y-%m-%d %H:%M'),'2026-11-03 19:00')
 def test_requires_5_matches(self):
  self.assertIsNone(sources.proxy_xg([],1,2,datetime(2026,11,3,tzinfo=core.CST)))
 def test_no_future_leakage(self):
  kickoff=datetime(2026,11,3,20,tzinfo=core.CST)
  rows=[]
  for i in range(7):
   dt=kickoff-timedelta(days=7*(i+1))
   rows.append({'utcDate':dt.astimezone(__import__('datetime').timezone.utc).isoformat(),'status':'FINISHED', 'homeTeam':{'id':1},'awayTeam':{'id':2},'score':{'fullTime':{'home':2,'away':1}}})
  a=sources.proxy_xg(rows,1,2,kickoff)
  self.assertIsNotNone(a)
  future={'utcDate':(kickoff+timedelta(days=1)).astimezone(__import__('datetime').timezone.utc).isoformat(),'status':'FINISHED', 'homeTeam':{'id':1},'awayTeam':{'id':2},'score':{'fullTime':{'home':30,'away':0}}}
  self.assertEqual(a,sources.proxy_xg(rows+[future],1,2,kickoff))
 def test_probability_math(self):
  p=core.predict(1.5,1.2)
  self.assertAlmostEqual(sum(p['wdl']),1,places=6)
if __name__=='__main__':unittest.main()
