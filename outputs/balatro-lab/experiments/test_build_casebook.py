import json
from pathlib import Path
import tempfile
import unittest
from build_casebook import make_case,trace_cases,blob,build

class CasebookTests(unittest.TestCase):
    def test_reconciled_rejection_not_executed_but_evidence_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);d={'sequence':62,'method':'pack','params':{'card':0},'before':{'state':'SMODS_BOOSTER_OPENED','money':4}}
            events=[{'event':'intent','id':62,'method':'pack','params':{'card':0},'before':d['before']},
                    {'event':'rejection_reconciliation','id':62,'accepted':False,'applied':False},
                    {'event':'result','id':62,'accepted':False,'applied':False,'after':d['before']}]
            (root/'decisions.jsonl').write_text(json.dumps(d),encoding='utf-8')
            (root/'transitions.jsonl').write_text('\n'.join(map(json.dumps,events)),encoding='utf-8')
            c=trace_cases(root,'test','train','root_agent')[0]
            self.assertEqual(c['labels']['execution_status'],'rejected_no_mutation')
            self.assertFalse(c['labels']['after_linked']);self.assertTrue(c['labels']['action_error'])

    def test_active_manual_trace_is_not_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lab=root/'lab';work=root/'work'
            active=work/'experiments/manual-ten-002/train-active';active.mkdir(parents=True)
            # Parsing would fail if the builder inspected this live trace.
            (active/'decisions.jsonl').write_text('LIVE_PARTIAL_JSON_DO_NOT_READ',encoding='utf-8')
            report=build(lab,work)
            item=next(x for x in report['inventory'] if x['cohort']=='manual-ten-002')
            self.assertEqual(item['unfinished_or_unselected_folders_excluded'],1)
            self.assertEqual(item['trace_folders'],0)
    def test_public_projection_keeps_future_label_separate(self):
        state={'state':'SHOP','money':5,'seed':'SECRET77','hand':{'cards':[{'key':'S_A'}]},
               'jokers':{'cards':[{'key':'j_joker','modifier':{'perishable':True},'value':{'effect':'game prose'}}]},
               'shop':{'cards':[{'key':'c_jupiter'}]}}
        c=make_case('one',state,{'method':'buy','params':{'card':0,'reason':'SECRET77'},'origin':'controller'},
                    {'partition':'train'}, {}, after={'money':2},outcome='win')
        encoded=json.dumps(c)
        self.assertNotIn('SECRET77',encoded);self.assertNotIn('S_A',encoded);self.assertNotIn('game prose',encoded)
        self.assertEqual(c['input']['cash'],5);self.assertEqual(c['labels']['cash_after'],2)
        self.assertEqual(c['decision']['target_key'],'c_jupiter')
        self.assertNotIn('run_outcome',c['input']);self.assertFalse(c['labels']['optimal_action_label'])

    def test_sequence_link_and_unverified_order_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state={'state':'SELECTING_HAND','money':4,'round':{'chips':0}}
            decisions=[{'method':'play','params':{'cards':[0]},'before':state}]
            events=[{'event':'intent','id':2,'method':'discard','params':{'cards':[0]},'before':state},
                    {'event':'result','id':2,'after':{'money':3,'round':{'chips':100,'last_hand':{'total':100}}}}]
            for name,data in [('decisions',decisions),('transitions',events)]:
                (root/(name+'.jsonl')).write_text('\n'.join(map(json.dumps,data)),encoding='utf-8')
            c=trace_cases(root,'test','train','script')[0]
            self.assertFalse(c['labels']['after_linked']);self.assertEqual(c['evidence']['join'],'unlinked')
            decisions[0]['sequence']=2
            (root/'decisions.jsonl').write_text(json.dumps(decisions[0]),encoding='utf-8');blob.cache_clear()
            # Explicit ids still must match the action, not merely point to one.
            c=trace_cases(root,'test','train','script')[0]
            self.assertFalse(c['labels']['after_linked'])

    def test_entire_matching_action_sequence_can_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state={'state':'SELECTING_HAND','round':{'chips':10}}
            d={'method':'play','params':{'cards':[0]},'before':state}
            events=[{'event':'intent','id':1,'method':'start','params':{}},
                    {'event':'result','id':1,'after':state},
                    {'event':'intent','id':2,**d},
                    {'event':'result','id':2,'after':{'round':{'chips':10,'last_hand':{'total':999}}}}]
            (root/'decisions.jsonl').write_text(json.dumps(d),encoding='utf-8')
            (root/'transitions.jsonl').write_text('\n'.join(map(json.dumps,events)),encoding='utf-8')
            c=trace_cases(root,'test','train','script')[0]
            self.assertTrue(c['labels']['after_linked']);self.assertEqual(c['labels']['actual_score'],0)

if __name__=='__main__':unittest.main()
