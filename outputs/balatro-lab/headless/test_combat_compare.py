import json
import hashlib
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import combat_compare as cc


class ScheduleTests(unittest.TestCase):
    def protocol(self,n=8,workers=4):
        return {'jobs':[{'id':str(i)} for i in range(n)],'instance_manifests':[str(i) for i in range(workers)]}

    def test_all_jobs_once(self):
        calls=[];events=[]
        def launch(m,j):
            calls.append(j);return {'job_id':j,'status':'loss','terminal':True}
        done,left=cc.schedule(self.protocol(),launch,events.append)
        self.assertEqual(sorted(calls),list('01234567'))
        self.assertEqual(len(done),8);self.assertEqual(left,[])
        self.assertEqual(sum(e['event']=='claimed' for e in events),8)

    def test_worker_retires_after_nonterminal_no_retry(self):
        calls=[]
        def launch(m,j):
            calls.append(j);return {'job_id':j,'status':'truncated','terminal':False}
        done,left=cc.schedule(self.protocol(),launch,lambda e:None)
        self.assertEqual(len(done),4);self.assertEqual(len(set(calls)),4)
        self.assertEqual(len(left),4)

    def test_failure_stops_engine_even_if_other_workers_continue(self):
        calls=[]
        def launch(m,j):
            calls.append((m,j))
            if m=='0':raise RuntimeError('unknown outcome')
            return {'job_id':j,'status':'win','terminal':True}
        done,left=cc.schedule(self.protocol(workers=2),launch,lambda e:None)
        self.assertEqual(len([x for x in calls if x[0]=='0']),1)
        self.assertEqual(len(done),8);self.assertEqual(left,[])

    def test_integrity_guard_covers_runner(self):
        with patch.object(cc,'dependency_hashes',return_value={'runner':'new'}):
            with self.assertRaisesRegex(ValueError,'dependency changed'):
                cc.check_frozen({'dependency_hashes':{'runner':'old'}})

    def test_training_partition_only(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'registry.sqlite'
            with closing(sqlite3.connect(p)) as db:
                db.execute('CREATE TABLE seeds(id INTEGER,seed TEXT,commitment TEXT,partition TEXT)')
                db.executemany('INSERT INTO seeds VALUES(?,?,?,?)',[(1,'AAA',hashlib.sha256(b'AAA').hexdigest(),'train'),(2,'BBB','b','test'),(3,'CCC','bad','train')])
                db.commit()
            self.assertEqual(cc.training_seed(p,1),('AAA',hashlib.sha256(b'AAA').hexdigest()))
            with self.assertRaises(ValueError):cc.training_seed(p,2)
            with self.assertRaisesRegex(ValueError,'commitment'):cc.training_seed(p,3)

    def test_private_plan_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);plan={'protocol_path':str(root/'protocol.json'),'registry':'original'}
            (root/'protocol.json').write_text(json.dumps({'private_plan_commitment':cc.digest(plan)}))
            plan['registry']='changed';(root/'plan.json').write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError,'plan changed'):cc.read_plan(root/'plan.json')


if __name__=='__main__':unittest.main()
