import sys, unittest, copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v7 as g
from test_route_v3 import state, joker
class Tests(unittest.TestCase):
    def test_growth_zero_immediate_can_be_acquired(self):
        s=state();s['shop']['cards']=[joker('j_green_joker',3)];s['money']=20
        def metrics(x): return (.5,.9,.6) if x['jokers']['cards'] else (.5,.5,.3)
        with patch.object(g,'metrics',side_effect=metrics),patch.object(g,'outlook',return_value=.5):
            self.assertEqual(g.choose_joker(s)[0],'buy')

    def test_economy_free_slot_has_future_value(self):
        s=state();s['shop']['cards']=[joker('j_golden',4)];s['money']=20
        with patch.object(g,'metrics',return_value=(1.2,1.2,.6)),patch.object(g,'outlook',return_value=1.2):
            self.assertEqual(g.choose_joker(s)[0],'buy')

    def test_total_rent_budget_cannot_be_bypassed(self):
        s=state();s['shop']['cards']=[joker('j_joker',1)];s['money']=2
        s['shop']['cards'][0]['modifier']['rental']=True
        with patch.object(g,'metrics',return_value=(.5,.8,.6)),patch.object(g,'outlook',return_value=.8):
            self.assertIsNone(g.choose_joker(s))

    def test_projection_does_not_change_input(self):
        import copy
        s=state();s['jokers']['cards']=[joker('j_green_joker',3)];before=copy.deepcopy(s)
        t=g.grown(s);self.assertEqual(s,before);self.assertNotEqual(t,s)

    def test_combat_is_not_intercepted(self):
        s=state();s['state']='SELECTING_HAND';self.assertIsNone(g.action(s))


if __name__=='__main__':unittest.main()
