import sys,unittest,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import combat_candidate_v6 as n
from test_no_sl_solver import state
from belief import base_deck

def fixture(key='j_green_joker'):
 s=state();s['money']=25;s['round'].update(hands_left=5,hands_played=0)
 s['jokers']['cards']=[{'key':key,'state':{},'modifier':{},'value':{'effect':'当前 9'}}]
 return s

class V6Tests(unittest.TestCase):
 def test_growth_preserves_winning_cards(self):
  s=fixture();o=n.growth_action(s)
  self.assertIsNotNone(o)
  self.assertFalse(set(o['params']['cards'])&set(o['diagnostics']['retained_winning_indices']))
  self.assertGreaterEqual(o['diagnostics']['retained_model_clear_bound'],o['diagnostics']['remaining_target_after_growth_play'])
 def test_tooth_not_eligible(self):
  s=fixture();s['blinds']['big']['name']='The Tooth';self.assertIsNone(n.growth_action(s))
 def test_bus_cannot_farm_face_junk(self):
  s=fixture('j_ride_the_bus');d=base_deck();s['hand']['cards']=[d[k] for k in ('C_A','S_K','H_Q','D_J')];s['blinds']['big']['score']=170
  self.assertIsNone(n.growth_action(s))
 def test_low_cash_preserves_hand_dollar(self):
  s=fixture();s['money']=14;self.assertIsNone(n.growth_action(s))
 def test_only_once_and_three_hands_needed(self):
  s=fixture();s['round']['hands_played']=1;self.assertIsNone(n.growth_action(s))
  s=fixture();s['round']['hands_left']=2;self.assertIsNone(n.growth_action(s))
 def test_mutation_and_complex_held_effects_rejected(self):
  s=fixture();b=copy.deepcopy(s);n.growth_action(s);self.assertEqual(s,b)
  s['jokers']['cards'].append({'key':'j_blackboard','state':{},'modifier':{},'value':{}})
  self.assertIsNone(n.growth_action(s))
if __name__=='__main__':unittest.main()
