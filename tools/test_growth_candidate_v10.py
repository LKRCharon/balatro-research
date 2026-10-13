import sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v10 as g
from test_route_v3 import state,joker

class Tests(unittest.TestCase):
    def test_first_conditional_multiplier_not_filtered_by_q25(self):
        s=state();s['money']=7;s['shop']['cards']=[joker('j_zany',1)]
        s['shop']['cards'][0]['modifier']['rental']=True
        with patch.object(g,'metrics',return_value=(.4,.4,.3)),patch.object(g,'outlook',return_value=.4):
            self.assertEqual(g.choose_joker(s)[0],'buy')

    def test_two_rentals_cannot_use_bridge_exception(self):
        s=state();s['money']=7;s['jokers']['cards']=[joker('j_joker',1)]
        s['jokers']['cards'][0]['modifier']['rental']=True
        s['shop']['cards']=[joker('j_zany',1)];s['shop']['cards'][0]['modifier']['rental']=True
        with patch.object(g,'metrics',return_value=(.4,.4,.3)),patch.object(g,'outlook',return_value=.4):
            self.assertIsNone(g.choose_joker(s))

if __name__=='__main__':unittest.main()
