import sys,unittest,copy,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import round_capacity_v2 as n
from test_no_sl_solver import state
from belief import base_deck

def fixture(keys):
 s=state();s['blinds']['big']['score']=100000
 s['jokers']['cards']=[{'key':k,'state':{},'modifier':{},'value':{}} for k in keys]
 return s

class CopyCapacityTests(unittest.TestCase):
 def test_blueprint_chip_target(self):
  s=fixture(['j_stuntman','j_blueprint']);t,order=n.reorder_for_combat(s)
  self.assertEqual(order,[1,0]);self.assertEqual(n.a.score(t,[0])[0],516)
 def test_blueprint_plus_mult_target(self):
  s=fixture(['j_joker','j_blueprint']);t,order=n.reorder_for_combat(s)
  self.assertEqual(order,[1,0]);self.assertEqual(n.a.score(t,[0])[0],144)
 def test_plus_mult_precedes_copied_xmult(self):
  s=fixture(['j_cavendish','j_blueprint','j_joker']);t,_=n.reorder_for_combat(s)
  self.assertEqual(n.a.score(t,[0])[0],720)
 def test_brainstorm_accounts_for_leftmost_target_tradeoff(self):
  s=fixture(['j_joker','j_cavendish','j_brainstorm']);t,_=n.reorder_for_combat(s)
  self.assertGreaterEqual(n.a.score(t,[0])[0],n.a.score(s,[0])[0])
  self.assertEqual(n.copying.count(t,'j_joker'),2)
  self.assertEqual(n.a.score(t,[0])[0],432)
 def test_debuff_target_not_copied(self):
  s=fixture(['j_stuntman','j_blueprint','j_joker']);s['jokers']['cards'][0]['state']['debuff']=True
  t,_=n.reorder_for_combat(s)
  self.assertEqual(n.copying.count(t,'j_stuntman'),0);self.assertEqual(n.copying.count(t,'j_joker'),2)
 def test_physical_editions_not_copied(self):
  s=fixture(['j_joker','j_blueprint']);s['jokers']['cards'][0]['modifier']['edition']='FOIL'
  t,_=n.reorder_for_combat(s)
  self.assertEqual(n.a.score(t,[0])[0],594)
 def test_burglar_entry_can_then_reallocate_to_combat(self):
  s=fixture(['j_burglar','j_blueprint','j_joker']);c=n.canonical(s)
  sim,_=n.prepare(c,c['_belief']['deck'])
  self.assertEqual(sim['round']['hands_left'],11);self.assertEqual(sim['round']['discards_left'],0)
  out,_=n.reorder_for_combat(sim);self.assertEqual(n.copying.count(out,'j_joker'),2)
 def test_no_mutation_and_common_worlds(self):
  s=fixture(['j_joker','j_blueprint']);before=copy.deepcopy(s);t,_=n.reorder_for_combat(s)
  self.assertEqual(s,before)
  self.assertEqual(n.worlds_for(n.canonical(s)['_belief']['deck'],4),n.worlds_for(n.canonical(t)['_belief']['deck'],4))
if __name__=='__main__':unittest.main()
