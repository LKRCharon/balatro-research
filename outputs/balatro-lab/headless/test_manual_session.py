import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manual_session as m


class ManualTests(unittest.TestCase):
    def test_no_policy_import_action_or_auto_path(self):
        tree=ast.parse(Path(m.__file__).read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                self.assertNotIn(node.func.attr,('action','auto','operate','start') if isinstance(node.func.value,ast.Name) and node.func.value.id=='h' else ('action','auto'))
        with self.assertRaisesRegex(ValueError,'no automatic'):m.operate('nonexistent','step')

    def test_numerics_distinct_categories_only(self):
        class A:
            @staticmethod
            def options(s):return [(100,(0,1),'Pair',(0,1)),(90,(2,3),'Pair',(2,3)),(30,(0,),'High Card',(0,))]
            @staticmethod
            def uncertain(s):return False
        rows=m.numerical_scores({'state':'SELECTING_HAND'},A)
        self.assertEqual([r['hand_type'] for r in rows],['Pair','High Card'])
        self.assertFalse(any('method' in r or 'action' in r for r in rows))
        self.assertEqual(m.numerical_scores({'state':'SHOP'},A),[])

    def test_compact_retains_hand_modifiers_and_costs(self):
        source={'state':'SHOP','hand':{'cards':[{'key':'H_A','modifier':{'seal':'RED','enhancement':'BONUS'},'state':{'debuff':True}}]},'shop':{'cards':[{'key':'j_joker','cost':{'buy':2},'value':{'effect':'+4 mult'},'modifier':{'rental':True}}]}}
        out=m.compact(source)
        self.assertEqual(out['hand']['cards'][0]['index'],0)
        self.assertTrue(out['hand']['cards'][0]['state']['debuff'])
        self.assertEqual(out['shop']['cards'][0]['cost']['buy'],2)
        self.assertEqual(out['shop']['cards'][0]['value']['effect'],'+4 mult')

    def test_all_journal_rows_label_controller(self):
        with patch.object(m.h.Environment,'_write') as write:
            env=object.__new__(m.ManualEnvironment)
            env._write({'event':'intent','id':1})
            env._write({'event':'result','id':1})
            self.assertEqual([c.args[0]['controller_origin'] for c in write.call_args_list],['controller','controller'])

    def test_existing_session_no_restart(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'restarted'):m.start('a','b',32,d,'c','test')

    def test_modules_never_load_policy(self):
        with patch.object(m.importlib,'import_module',side_effect=lambda name:name) as load:
            self.assertEqual(m.modules(),('advisor','belief','execution'))
            self.assertNotIn('policy',[c.args[0] for c in load.call_args_list])

    def test_same_seed_other_session_cannot_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);protocol=root/'protocol.json';protocol.write_text('{}')
            m.claim_seed(root/'registry.sqlite',protocol,32,root/'first')
            with self.assertRaises(FileExistsError):m.claim_seed(root/'registry.sqlite',protocol,32,root/'second')

    def test_numeric_failure_preserves_observation(self):
        class Env:
            state={'state':'SELECTING_HAND'};sequence=4
            def action_space(self):return {'methods':['play']}
        with tempfile.TemporaryDirectory() as d,patch.object(m.h,'visible',return_value=Env.state),patch.object(m,'numerical_scores',side_effect=ValueError('unsafe detail')):
            result=m.snapshot(Path(d),Env(),None,None)
            self.assertEqual(result['numerical_error'],'ValueError')
            self.assertEqual(result['sequence'],4)
            self.assertEqual(json.loads((Path(d)/'observation.json').read_text())['numerical_scores'],[])

    def test_failed_preplay_numeric_tool_does_not_block_manual_action(self):
        class Env:
            state={'state':'SELECTING_HAND','round':{'chips':0}};sequence=4;calls=0
            def action_space(self):return {'methods':['play']}
            def step(self,method,params):
                self.calls+=1;self.sequence+=1
                return {'state':'ROUND_EVAL','round':{'chips':400,'last_hand':{'total':400}}}
        class Execution:
            @staticmethod
            def validate(*args):pass
        class Advisor:
            @staticmethod
            def score(*args):raise ValueError('unavailable numeric estimate')
        env=Env()
        with tempfile.TemporaryDirectory() as d,patch.object(m.h,'visible',return_value=env.state):
            m.perform(Path(d),env,None,Execution,Advisor,'play',{'cards':[0],'reason':'controller choice'})
            self.assertEqual(env.calls,1)
            row=json.loads((Path(d)/'predictions.jsonl').read_text())
            self.assertIsNone(row['predicted']);self.assertTrue(row['uncertain'])
            self.assertEqual(row['actual'],400);self.assertEqual(row['numerical_error'],'ValueError')
            self.assertIsNone(row['within_one'])

if __name__=='__main__':unittest.main()

