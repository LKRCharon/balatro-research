import copy
import unittest
from strength_probe import probe, best, refresh
from test_route_v3 import state,joker
from belief import base_deck

class ProbeTests(unittest.TestCase):
    def prepared(self):
        s=state();s['state']='SELECTING_HAND';s['blinds']['boss']={'status':'CURRENT','name':'Small Blind','score':300}
        s['hand']['cards']=[base_deck()['S_A']];return s
    def test_abstract_stencil_removal_recomputes_joint_effect(self):
        s=self.prepared();s['jokers']['cards']=[joker('j_abstract'),joker('j_stencil')]
        r=probe(s);base=r['baseline']
        v=r['joker_marginals'][0]['structural_removal']['score']
        # One fewer Joker strengthens Stencil while Abstract's +6 disappears.
        self.assertEqual(base,16*7*4)
        self.assertEqual(v,16*1*5)
    def test_swash_recomputes_sell_sum(self):
        s=self.prepared();s['jokers']['cards']=[joker('j_swashbuckler'),joker('j_abstract')]
        s['jokers']['cards'][1]['cost']['sell']=7
        r=probe(s)
        self.assertEqual(r['joker_marginals'][1]['structural_removal']['score'],16)
    def test_uncertain_excluded(self):
        s=self.prepared();s['hand']['cards'][0]['modifier']['enhancement']='LUCKY'
        self.assertFalse(probe(s)['eligible'])
    def test_not_mutating_and_negative_capacity(self):
        s=self.prepared();s['jokers']={'limit':1,'cards':[joker('j_joker',edition='NEGATIVE')]}
        s['shop']['cards']=[joker('j_abstract')];before=copy.deepcopy(s)
        r=probe(s);self.assertEqual(s,before);self.assertEqual(r['shop_candidates'],[])

if __name__=='__main__':unittest.main()
