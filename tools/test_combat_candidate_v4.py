import sys, unittest, copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import combat_candidate_v4 as n
from test_no_sl_solver import state
from belief import base_deck
class Tests(unittest.TestCase):
 def test_neutral_cycle(self):
  s=state();best=n.play_option(s)
  self.assertEqual(best[0],n.a.options(s)[0][0]);self.assertGreater(len(best[1]),1)
 def test_half_cycle_caps_three(self):
  s=state();s['jokers']['cards']=[{'key':'j_half','state':{},'value':{},'modifier':{}}]
  self.assertLessEqual(len(n.play_option(s)[1]),3)
 def test_green_growth_once(self):
  s=state();s['jokers']['cards']=[{'key':'j_green_joker','state':{},'value':{'effect':'当前 9'},'modifier':{}}]
  after,_,_=n.transition(s,'play',[0],s['_belief']['unseen'])
  self.assertEqual(n.a.current_number(after['jokers']['cards'][0]),10)
 def test_input_preserved(self):
  s=state();before=copy.deepcopy(s);n.choose(s,{'samples':1,'time_budget':10});self.assertEqual(s,before)
 def test_last_hand_preserves_discard(self):
  s=state();s['round'].update(hands_left=1,discards_left=1);s['blinds']['big']['score']=100000
  self.assertEqual(n.choose(s,{'samples':1,'time_budget':10})['method'],'discard')
if __name__=='__main__':unittest.main()
