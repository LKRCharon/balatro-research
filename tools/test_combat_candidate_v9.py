"""v9 conservative-clear and Boss regressions."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import combat_candidate_v9 as n
from test_no_sl_solver import state
from belief import base_deck

class V9ReviewTests(unittest.TestCase):
 def test_preserve_guaranteed_model_clear_over_lucky_expectation(self):
  s=state();s['blinds']['big']['score']=16;s['round'].update(hands_left=1,discards_left=0)
  s['hand']['cards'][4]['modifier']={'enhancement':'LUCKY'}
  out=n.choose(s)
  self.assertGreaterEqual(n.a.conservative_score(s,out['params']['cards']),16)
 def test_psychic_five_cards(self):
  s=state();s['blinds']['big']['name']='The Psychic'
  self.assertEqual(len(n.playable(s)[1]),5)
 def test_eye_does_not_repeat_pair(self):
  s=state();s['blinds']['big']['name']='The Eye';s['hands']['Pair']['played_this_round']=1
  s['hand']['cards'][1]=base_deck()['H_A']
  self.assertNotEqual(n.playable(s)[2],'Pair')
 def test_mouth_keeps_locked_pair(self):
  s=state();s['blinds']['big']['name']='The Mouth';s['round']['mouth_hand']='Pair'
  s['hand']['cards'][1]=base_deck()['H_A']
  self.assertEqual(n.playable(s)[2],'Pair')
 def test_bus_does_not_score_face_when_safe_comparable(self):
  s=state();s['blinds']['big']['score']=10000
  s['jokers']['cards']=[{'key':'j_ride_the_bus','state':{},'modifier':{},'value':{'effect':'当前 9'}}]
  option=n.playable(s)
  self.assertFalse(any(n.a.rank(s['hand']['cards'][i]) in (11,12,13) for i in option[3]))
 def test_growth_mode_preserved(self):
  from test_combat_candidate_v6 import fixture
  s=fixture();out=n.choose(s)
  self.assertEqual(out['diagnostics']['mode'],'v6_one_safe_model_growth_hand')
 def test_equal_expectation_cycle_cannot_lower_bound(self):
  from unittest.mock import patch
  s=state();s['blinds']['big']['score']=16
  options=[(40,[0],'High Card',[0]),(40,[1,2,3],'High Card',[1])]
  with patch.object(n.a,'options',return_value=options), patch.object(n.a,'conservative_score',side_effect=lambda s,ids,*args:16 if ids==[0] else 8):
   out=n.playable(s)
  self.assertEqual(out[1],[0])
if __name__=='__main__':unittest.main()
