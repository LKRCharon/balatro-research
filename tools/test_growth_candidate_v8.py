import sys, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v8 as g
from test_route_v3 import state,joker

class Tests(unittest.TestCase):
    def test_free_riff_with_empty_slots_is_not_score_filtered(self):
        s=state();s['state']='SMODS_BOOSTER_OPENED';s['money']=3
        s['pack']={'cards':[joker('j_riff_raff',0)]}
        with patch.object(g,'metrics',return_value=(.3,.3,.2)),patch.object(g,'outlook',return_value=.3):
            self.assertEqual(g.choose_joker(s,True)[0],'pack')

    def test_early_eternal_relative_gain(self):
        s=state();s['money']=9;s['shop']['cards']=[joker('j_odd_todd',4)]
        s['shop']['cards'][0]['modifier']['eternal']=True
        def metrics(x): return (.2625,.2625,.2625) if x['jokers']['cards'] else (.21,.21,.21)
        with patch.object(g,'metrics',side_effect=metrics),patch.object(g,'outlook',return_value=.2625):
            self.assertEqual(g.choose_joker(s)[0],'buy')

    def test_two_unsupported_rentals_rejected(self):
        s=state();s['jokers']['cards']=[joker('j_joker',1)]
        s['jokers']['cards'][0]['modifier']['rental']=True
        offer=joker('j_half',1);offer['modifier']['rental']=True
        t=state();t['money']=20;t['jokers']['cards']=[s['jokers']['cards'][0],offer]
        self.assertFalse(g.affordable(s,t,offer,.4,.8))

if __name__=='__main__':unittest.main()
