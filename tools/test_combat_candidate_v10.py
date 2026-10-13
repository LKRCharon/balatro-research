import sys,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import combat_candidate_v10 as g
from test_no_sl_solver import state
from belief import base_deck

class Tests(unittest.TestCase):
    def test_score_neutral_cycling_can_preserve_four_flush_cards(self):
        s=state();d=base_deck();s['hand']['cards']=[d[k] for k in ('H_A','H_8','H_5','H_2','S_K','D_K','C_9','C_3')]
        o=g.playable(s)
        held=[c['key'] for i,c in enumerate(s['hand']['cards']) if i not in o[1]]
        self.assertTrue(all(k in held for k in ('H_A','H_8','H_5','H_2')))
        self.assertEqual(o[0],g.a.options(s)[0][0])

    def test_discard_does_not_treat_per_hand_quota_as_round_clear(self):
        s=state();s['round']['hands_left']=5
        rows=[{'cards':[0],'mean':70,'minimum':60,'quota_fraction':1},
              {'cards':[1],'mean':140,'minimum':16,'quota_fraction':.6}]
        result={'method':'discard','params':{'cards':[0]},'diagnostics':{'mode':'old','discard_candidates':rows}}
        with patch.object(g.prior,'choose',return_value=result):
            self.assertEqual(g.choose(s)['params']['cards'],[1])

if __name__=='__main__':unittest.main()
