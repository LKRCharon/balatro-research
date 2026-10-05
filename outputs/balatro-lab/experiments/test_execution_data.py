import copy,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'policies/route_v2'),str(HERE.parent/'cli'),str(HERE.parent/'scripts')]
from execution import Journal,validate
from manual_dataset import extract
from test_route_v2 import state
import advisor as a

class SafetyTests(unittest.TestCase):
    def test_predecision_and_outcome_separation(self):
        rows=[{'method':'gamestate','result':{'state':'SHOP','money':8,'seed':'SECRET','hand':{'cards':[{'key':'S_A','state':{'hidden':True}}]}}},
              {'method':'buy','params':{'card':0,'reason':'buy'},'result':{'state':'SHOP','money':3}},
              {'method':'play','params':{'cards':[0],'reason':'attempt'},'error':'bad'},
              {'method':'gamestate','result':{'state':'GAME_OVER','money':0}}]
        x,y,outcome=extract(rows,1,'group')
        self.assertEqual(x[0]['features']['money'],8)
        self.assertEqual(x[1]['features']['money'],3)
        self.assertEqual(y[0]['money_after'],3)
        self.assertEqual(outcome,'loss')
        self.assertNotIn('SECRET',json.dumps(x));self.assertNotIn('S_A',json.dumps(x))
        self.assertNotIn('run_outcome',json.dumps(x));self.assertEqual(y[1]['error'],'bad')

    def test_crash_requires_reconciliation_and_completed_loop_detected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'journal.jsonl';s=state();j=Journal(path)
            j.begin(s,'play',{'cards':[0],'reason':'test'})
            self.assertEqual(json.loads(path.read_text().splitlines()[0])['event'],'intent')
            with self.assertRaisesRegex(RuntimeError,'Unresolved'):Journal(path)
            j.finish(s);restored=Journal(path)
            with self.assertRaisesRegex(RuntimeError,'Repeated'):restored.begin(s,'play',{'cards':[0],'reason':'changed text'})

    def test_physical_order_and_invalid_actions(self):
        s=state()
        for selected in ([1,0],[0,0],[-1],[999]):
            with self.assertRaises(ValueError):validate(s,'play',{'cards':selected,'reason':'test'})
        validate(s,'rearrange',{'hand':list(reversed(range(len(s['hand']['cards'])))),'reason':'order'})
        s['jokers']['cards']=[{'modifier':{'eternal':True}}]
        with self.assertRaises(ValueError):validate(s,'sell',{'joker':0,'reason':'sell'})

    def test_lucky_floor_and_unknown_hidden(self):
        s=state();s['jokers']['cards']=[];s['hand']['cards']=s['hand']['cards'][:1]
        s['hand']['cards'][0]['modifier']={'enhancement':'LUCKY'}
        self.assertLess(a.conservative_score(s,[0]),a.score(s,[0])[0])
        s['hand']['cards'][0]['state']['hidden']=True
        self.assertIsNone(a.conservative_score(s,[0]))

if __name__=='__main__':unittest.main()
