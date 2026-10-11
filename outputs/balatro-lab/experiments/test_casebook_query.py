import unittest
from casebook_query import select,select_rules

def case(partition='train',identifier='a'):
    return {'case_id':identifier,'lineage':{'partition':partition,'cohort':'manual-ten'},'controller_origin':'root_agent',
        'input':{'ante':2,'cash':4,'lineup':[{'key':'j_abstract','perishable':True}], 'blind':{'name':'The Water'}},
        'decision':{'method':'buy','target_key':'c_jupiter'},'labels':{'run_outcome':'loss'},'evidence':{}}

class RetrievalTests(unittest.TestCase):
    def test_mechanism_query_has_no_hindsight_or_raw_state(self):
        book={'rules':[{'id':'one','keys':['j_perkeo'],'check':'Check all sources','outcome':'win','hand':['S_A']}]}
        out=select_rules(book,'j_perkeo')
        self.assertEqual(len(out['rules']),1);self.assertNotIn('outcome',out['rules'][0]);self.assertNotIn('hand',out['rules'][0])
        self.assertEqual(select_rules(book,'j_dna')['rules'],[])
    def test_defaults_exclude_hindsight_validation_and_unknown_partition(self):
        report={'cases':[case(),case('validation_already_consumed','b'),case('unknown','c'),case('test','d')]}
        out=select(report)
        self.assertEqual(out['returned'],1);self.assertNotIn('labels',out['results'][0])

    def test_filters_match_lineup_or_selected_target(self):
        report={'cases':[case()]}
        self.assertEqual(select(report,joker='c_jupiter',boss='The Water',perishable=True,cash_max=5,ante_min=2)['returned'],1)
        self.assertEqual(select(report,joker='j_blueprint')['returned'],0)
        self.assertEqual(select(report,ante_max=1)['returned'],0)

    def test_explicit_research_can_include_consumed_validation_not_test(self):
        report={'cases':[case('validation_already_consumed'),case('test','b')]}
        with self.assertRaises(ValueError):select(report,include_consumed_validation=True)
        out=select(report,research=True,include_consumed_validation=True)
        self.assertEqual(out['returned'],1);self.assertEqual(out['results'][0]['labels']['run_outcome'],'loss')

if __name__=='__main__':unittest.main()
