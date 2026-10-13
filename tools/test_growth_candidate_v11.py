import sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v11 as g
from test_route_v3 import state,joker

class Tests(unittest.TestCase):
    def test_rejected_card_cannot_hide_affordable_buffoon(self):
        s=state();s['money']=8;s['shop']['cards']=[joker('j_flower_pot',6)]
        s['packs']={'cards':[{'key':'p_buffoon_normal_2','cost':{'buy':4}}]}
        with patch.object(g,'metrics',return_value=(.4,.4,.3)),patch.object(g,'outlook',return_value=.4),patch.object(g,'choose_joker',return_value=None):
            self.assertEqual(g.action(s)[1].get('pack'),0)

    def test_pack_does_not_create_unfunded_multi_rent(self):
        s=state();s['money']=4;s['jokers']['cards']=[joker('j_joker',1)]
        s['jokers']['cards'][0]['modifier']['rental']=True
        s['packs']={'cards':[{'key':'p_buffoon_normal_2','cost':{'buy':4}}]}
        with patch.object(g,'metrics',return_value=(.4,.4,.3)),patch.object(g,'outlook',return_value=.4),patch.object(g,'choose_joker',return_value=None):
            self.assertNotEqual(g.action(s)[0],'buy')

if __name__=='__main__':unittest.main()
