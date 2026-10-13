import sys,unittest,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import round_capacity as n
from test_no_sl_solver import state

class CapacityTests(unittest.TestCase):
 def test_common_worlds_ignore_lineup_and_deck_order(self):
  s=state();t=copy.deepcopy(s);t['_belief']['deck'].reverse();t['jokers']['cards']=[{'key':'j_joker','value':{},'modifier':{},'state':{}}]
  x=n.estimate(s);y=n.estimate(t)
  self.assertEqual(x['public_deck_hash'],y['public_deck_hash']);self.assertEqual(x['world_ids'],y['world_ids'])
 def test_needle_water_resources(self):
  for boss,h,d in [('The Needle',1,2),('The Water',5,0)]:
   s=state();s['blinds']['big']['name']=boss;x=n.estimate(s)
   self.assertEqual((x['hands'],x['discards']),(h,d))
 def test_no_input_or_cached_result_mutation(self):
  s=state();b=copy.deepcopy(s);x=n.estimate(s);x['scores'][0]=-999
  self.assertEqual(s,b);self.assertNotEqual(n.estimate(s)['scores'][0],-999)
 def test_seed_future_and_previous_hand_are_irrelevant(self):
  s=state();t=copy.deepcopy(s);t['seed']='PRIVATE';t['future_draw_order']=['PRIVATE'];t['round']['chips']=999;t['hand']['cards'].reverse()
  self.assertEqual(n.estimate(s),n.estimate(t))
 def test_wild_debuff_applied(self):
  s=n.canonical(state());s['blinds']['big']['name']='The Club';s['_belief']['deck'][0]['modifier']={'enhancement':'WILD'}
  sim,_=n.prepare(s,s['_belief']['deck'])
  self.assertTrue(sim['hand']['cards'][0]['state']['debuff'])
 def test_unknown_mechanics_marked_not_rejected(self):
  s=state();s['jokers']['cards']=[{'key':'j_hiker','value':{},'state':{},'modifier':{}}]
  x=n.estimate(s);self.assertTrue(x['available']);self.assertTrue(x['limitations']);self.assertFalse(x['optimality_claim'])
 def test_missing_deck_not_replaced_with_vanilla(self):
  s=state();s['_belief'].pop('deck');self.assertFalse(n.estimate(s)['available'])
if __name__=='__main__':unittest.main()
