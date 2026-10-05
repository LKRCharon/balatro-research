import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
import hybrid_session as hs


class HybridTests(unittest.TestCase):
    def test_never_auto_shop_or_pack(self):
        for phase in ('SHOP','SMODS_BOOSTER_OPENED','BLIND_SELECT','ROUND_EVAL'):
            self.assertFalse(hs.auto_allowed({'state':phase},('play',{})))

    def test_combat_only_automatic_actions(self):
        state={'state':'SELECTING_HAND'}
        for method in ('play','discard','rearrange'):
            self.assertTrue(hs.auto_allowed(state,(method,{})))
        for method in ('sell','use','buy','select','skip','cash_out'):
            self.assertFalse(hs.auto_allowed(state,(method,{})))

    def test_terminal_not_automated(self):
        self.assertFalse(hs.auto_allowed({'state':'SELECTING_HAND','won':True},('play',{})))

    def test_restore_latest_public_jokers_before_hidden_boss(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'transitions.jsonl'
            hs.append(path,{'event':'result','after':{'state':'SHOP','jokers':{'cards':[{'key':'j_joker','state':{}}]}}})
            hs.append(path,{'event':'result','after':{'state':'SELECTING_HAND','jokers':{'cards':[{'key':'hidden','state':{'hidden':True}}]}}})
            state,jokers=hs.restore_journal(path)
            self.assertEqual(state['state'],'SELECTING_HAND');self.assertEqual(jokers[0]['key'],'j_joker')

    def test_train_only_and_actual_commitment(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'db.sqlite'
            with closing(sqlite3.connect(p)) as db:
                db.execute('CREATE TABLE seeds(id INTEGER,seed TEXT,commitment TEXT,partition TEXT)')
                db.executemany('INSERT INTO seeds VALUES(?,?,?,?)',[(1,'ABC',hashlib.sha256(b'ABC').hexdigest(),'train'),(2,'DEF','bad','test'),(3,'GHI','bad','train')]);db.commit()
            self.assertEqual(hs.training_seed(p,1)[0],'ABC')
            for i in (2,3):
                with self.assertRaises(ValueError):hs.training_seed(p,i)

    def test_stale_action_is_rejected_without_mutation(self):
        class Env:
            def __init__(self,*args,**kwargs):self.sequence=4;self.state={'state':'SHOP'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def observe(self):self.state={'state':'SHOP'}
        class Belief:
            class Belief:pass
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'session.json').write_text(json.dumps({'source_hashes':{},'manifest':'x','manifest_sha256':'h','registry':'r'}))
            with patch.object(hs,'files',return_value={}),patch.object(hs,'sha',return_value='h'),patch.object(hs,'load',return_value={'port':12400,'identity':'lab','input_hashes':{}}),patch.object(hs,'modules',return_value=(None,None,Belief,None)),patch.object(hs,'Environment',Env),patch.object(hs,'perform') as perform:
                with self.assertRaisesRegex(ValueError,'Stale'):hs.operate(root,'act',method='buy',expected_sequence=3)
                perform.assert_not_called()

    def test_existing_session_cannot_restart(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'never overwrite'):hs.start('manifest','db',1,d)

    def test_uncertain_mutation_is_never_retried(self):
        class Env:
            sequence=4;state={'state':'SHOP'};calls=0
            def action_space(self):return {'methods':['buy']}
            def step(self,*args):self.calls+=1;raise RuntimeError('outcome unknown')
        class Execution:
            @staticmethod
            def validate(*args):pass
        env=Env()
        with tempfile.TemporaryDirectory() as d,patch.object(hs,'visible',return_value={'state':'SHOP'}):
            with self.assertRaises(RuntimeError):hs.perform(Path(d),env,None,Execution,None,'buy',{'reason':'test'},'controller')
            self.assertEqual(env.calls,1)
            row=json.loads((Path(d)/'decisions.jsonl').read_text())
            self.assertEqual(row['origin'],'controller')


if __name__=='__main__':unittest.main()
