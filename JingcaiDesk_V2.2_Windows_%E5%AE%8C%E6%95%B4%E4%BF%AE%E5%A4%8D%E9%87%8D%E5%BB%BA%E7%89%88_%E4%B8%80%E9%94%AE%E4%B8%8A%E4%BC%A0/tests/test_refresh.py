import pathlib,sys,unittest,unittest.mock as mock,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).parents[1]))
import core,refresh,sources

class SyncTests(unittest.TestCase):
 def test_thesportsdb_normalization(self):
  payload={'events':[{'idEvent':'4321','strSport':'Soccer','strTimestamp':'2026-11-03T11:00:00Z','strHomeTeam':'Alpha','strAwayTeam':'Beta','strLeague':'League X'}]}
  with mock.patch.object(sources,'request_json',return_value=payload):
   rows,w=sources.thesportsdb_day('2026-11-03')
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['kickoff'],'2026-11-03 19:00')
  self.assertEqual(rows[0]['home_xg'],'')
  self.assertIn('未核验体彩',rows[0]['source'])
 def test_football_data_no_invented_probs(self):
  payload={'competition':{'name':'Test League'},'matches':[{'id':1,'utcDate':'2026-11-03T11:00:00Z','status':'SCHEDULED','homeTeam':{'id':1,'name':'Alpha'},'awayTeam':{'id':2,'name':'Beta'}}]}
  with mock.patch.object(sources,'request_json',return_value=payload):
   rows,w=sources.football_data_day('2026-11-03','fake-token',['PL'])
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['home_xg'],'')
 def test_football_data_token_required(self):
  with self.assertRaises(ValueError):sources.football_data_day('2026-11-03','')

if __name__=='__main__':unittest.main()
