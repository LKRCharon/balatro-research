"""Independent v15/v3 boundaries, no game or hidden draw lookup."""
import copy,sys,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import round_capacity_v3 as capacity
import growth_candidate_v15 as growth
from test_no_sl_solver import state
from test_round_capacity_v3 import held
from test_growth_candidate_v13 import shop,joker

class ReviewTests(unittest.TestCase):
 def test_duplicate_rank_different_permanent_bonus_matches_exact_token(self):
  s=state();first=copy.deepcopy(s['hand']['cards'][0]);second=copy.deepcopy(first)
  first['permanent_bonus']=0;second['permanent_bonus']=60
  s['hand']['cards']=[second];s['_belief']['deck']=[first,copy.deepcopy(second)]
  s['consumables']['cards']=[held('c_chariot')]
  t,uses=capacity.apply_held_tarots(s)
  self.assertEqual(t['_belief']['deck'][0].get('modifier',{}).get('enhancement'),None)
  self.assertEqual(t['_belief']['deck'][1]['modifier']['enhancement'],'STEEL')
 def test_duplicate_identical_targets_update_two_copies_only(self):
  s=state();c=copy.deepcopy(s['hand']['cards'][0]);s['hand']['cards']=[copy.deepcopy(c),copy.deepcopy(c)]
  s['_belief']['deck']=[copy.deepcopy(c) for _ in range(3)];s['consumables']['cards']=[held('c_empress')]
  t,uses=capacity.apply_held_tarots(s)
  self.assertEqual(sum(x.get('modifier',{}).get('enhancement')=='MULT' for x in t['_belief']['deck']),2)
 def test_perkeo_reserved_template_not_consumed(self):
  s=state();s['jokers']['cards']=[joker('j_perkeo')];s['consumables']['cards']=[held('c_empress')]
  t,uses=capacity.apply_held_tarots(s);self.assertEqual(uses,[]);self.assertEqual(len(t['consumables']['cards']),1)
 def test_no_target_uses_future_tail(self):
  s=state();s['consumables']['cards']=[held('c_chariot')];other=copy.deepcopy(s)
  other['_belief']['unseen']=[{'key':'H_K','value':{'rank':'K','suit':'H'},'modifier':{},'state':{}}]*30
  self.assertEqual(capacity.apply_held_tarots(s)[1],capacity.apply_held_tarots(other)[1])
 def test_duplicate_planets_only_one_removed_and_counter_once(self):
  s=shop();p={'key':'c_mercury','set':'PLANET','cost':{'buy':3}}
  s['shop']['cards']=[copy.deepcopy(p),copy.deepcopy(p)];c=joker('j_constellation');c['value']['effect']='当前 1.4';s['jokers']['cards']=[c,joker('j_blueprint'),joker('j_brainstorm')]
  t=growth.planet_after_use(s,p,3,index=1)
  self.assertEqual(len(t['shop']['cards']),1);self.assertAlmostEqual(growth.a.current_number(t['jokers']['cards'][0]),1.5)
  # remaining visible copy is a genuinely separate future opportunity.
  u=growth.planet_after_use(t,p,3,index=0);self.assertAlmostEqual(growth.a.current_number(u['jokers']['cards'][0]),1.6)
  self.assertIsNone(growth.planet_after_use(u,p,3,index=0))

if __name__=='__main__':unittest.main()
