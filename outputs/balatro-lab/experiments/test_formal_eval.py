import json,sqlite3,tempfile,unittest
from pathlib import Path
import formal_eval as f
import protocol as p

class FormalTests(unittest.TestCase):
    def test_registered_order_not_completion_order(self):
        rows=[{'seed_id':4,'status':'win'},{'seed_id':2,'status':'error'},{'seed_id':3,'status':'win'},{'seed_id':1,'status':'win'}]
        result=f.summarize(rows)
        self.assertEqual(result['longest_streak_in_registered_order'],2)
        self.assertEqual(result['wins_per_assigned'],.75)
        self.assertTrue(result['complete'])

    def test_unattempted_jobs_remain_denominator(self):
        result=f.summarize([{'seed_id':1,'status':'win'},{'seed_id':2,'status':'planned'}])
        self.assertEqual(result['wins_per_assigned'],.5)
        self.assertFalse(result['complete'])

    def test_interval_boundaries(self):
        self.assertAlmostEqual(f.wilson(0,16)[0],0)
        self.assertAlmostEqual(f.wilson(16,16)[1],1)
        self.assertGreater(f.wilson(0,16)[1],.19)

    def test_validation_reset_requires_claim_and_matching_seed(self):
        import sys
        sys.path.insert(0,str(f.LAB/'headless'))
        from test_environment import FakeClient
        from environment import Environment
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db=root/'registry.sqlite'
            with sqlite3.connect(db) as con:
                con.executescript("CREATE TABLE seeds(id INTEGER,seed TEXT,partition TEXT);CREATE TABLE campaigns(id TEXT,partition TEXT);CREATE TABLE jobs(id TEXT,seed_id INTEGER,campaign_id TEXT,status TEXT);INSERT INTO seeds VALUES(1,'VAL123','validation');INSERT INTO seeds VALUES(2,'TEST123','test');INSERT INTO campaigns VALUES('campaign','validation');INSERT INTO jobs VALUES('job',1,'campaign','planned');")
            con.close()
            client=FakeClient('Balatro-Lab-formaltest')
            with Environment(12599,client.identity,root/'logs',registry=db,client=client) as env:
                with self.assertRaises(ValueError):env.reset('VAL123')
                with self.assertRaises(ValueError):env.reset('VAL123',intended_partition='validation',job_id='job')
                with sqlite3.connect(db) as con:con.execute("UPDATE jobs SET status='running'")
                con.close()
                with self.assertRaises(ValueError):env.reset('TEST123',intended_partition='validation',job_id='job')
                self.assertEqual([x[0] for x in client.calls],['lab_info'])
                state=env.reset('VAL123',intended_partition='validation',job_id='job')
                self.assertEqual(state['state'],'BLIND_SELECT')
                self.assertNotIn('VAL123',(root/'logs/transitions.jsonl').read_text(encoding='utf8'))

if __name__=='__main__':unittest.main()
