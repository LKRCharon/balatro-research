import sys, unittest, copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v6 as g
from test_route_v3 import state, joker
class GateTests(unittest.TestCase):
    def test_legacy_cannot_bypass_rental_rejection(self):
        s=state();s['shop']['cards']=[joker('j_joker',1)];s['shop']['cards'][0]['modifier']['rental']=True;s['money']=1
        with patch.object(g,'outlook',return_value=.5),patch.object(g.legacy,'action',return_value=('buy',{'card':0})):
            self.assertEqual(g.action(s)[0],'next_round')
    def test_legacy_cannot_bypass_refresh_cap(self):
        s=state();s['money']=50
        with patch.object(g,'outlook',return_value=.5),patch.object(g.legacy,'action',return_value=('reroll',{})):
            self.assertEqual(g.action(s,rerolls_this_shop=2)[0],'next_round')
    def test_pack_rejects_free_but_unaffordable_rental(self):
        s=state();s['state']='SMODS_BOOSTER_OPENED';s['money']=0;s['pack']={'cards':[joker('j_joker',0)]};s['pack']['cards'][0]['modifier']['rental']=True
        with patch.object(g,'outlook',side_effect=lambda x:.8 if x['jokers']['cards'] else .5):
            self.assertEqual(g.action(s),('pack',{'skip':True,'reason':g.VERSION+': no legal beneficial non-debt pack Joker'}))
    def test_unknown_pack_not_treated_as_rescue(self):
        s=state();s['money']=40;s['packs']={'cards':[{'key':'p_standard_normal_1','cost':{'buy':4}}]}
        with patch.object(g,'outlook',return_value=.5),patch.object(g.legacy,'action',return_value=('buy',{'pack':0})):
            self.assertEqual(g.action(s)[0],'reroll')
    def test_combat_not_intercepted(self):
        s=state();s['state']='SELECTING_HAND';self.assertIsNone(g.action(s))

if __name__=='__main__':unittest.main()
