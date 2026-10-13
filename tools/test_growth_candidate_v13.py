import sys,unittest,copy
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v13 as n
from test_no_sl_solver import state

def joker(key,**modifier):
 return {'key':key,'set':'JOKER','value':{},'state':{},'modifier':modifier,'cost':{'buy':4,'sell':2}}

def shop():
 s=state();s['state']='SHOP';s['money']=30;s['ante_num']=4
 s['blinds']={'small':{'status':'UPCOMING','name':'Small Blind','score':6000},'big':{'status':'UPCOMING','name':'Big Blind','score':9000},'boss':{'status':'UPCOMING','name':'The Wall','score':12000}}
 s['jokers']['count']=0;s['shop']={'cards':[]};return s

class V13Tests(unittest.TestCase):
 def test_expiring_all_passive_resource_deltas(self):
  s=shop();s['hand']['limit']=10;s['_base_hands']=4;s['_base_discards']=6
  s['jokers']['cards']=[joker('j_troubadour',perishable=1),joker('j_merry_andy',perishable=1),joker('j_drunkard',perishable=1),joker('j_juggler',perishable=1)]
  t=n.future_resources(s)
  self.assertEqual((t['hand']['limit'],t['_base_hands'],t['_base_discards']),(8,5,2))
 def test_stuntman_expiry_restores_hand_size(self):
  s=shop();s['hand']['limit']=6;s['jokers']['cards']=[joker('j_stuntman',perishable=1)]
  self.assertEqual(n.future_resources(s)['hand']['limit'],8)
 def test_turtle_declines_and_expires(self):
  s=shop();s['hand']['limit']=10;c=joker('j_turtle_bean');c['value']['effect']='当前 2';s['jokers']['cards']=[c];s['jokers']['count']=1
  one=n.future_resources(s,1);two=n.future_resources(s,2)
  self.assertEqual(one['hand']['limit'],9);self.assertEqual(two['hand']['limit'],8);self.assertFalse(two['jokers']['cards'])
  self.assertEqual(s['hand']['limit'],10)
 def test_large_gain_rental_with_cash_exception(self):
  s=shop();t=shop();s['jokers']['cards']=[joker('j_joker',rental=True),joker('j_banner',rental=True)]
  offer=joker('j_abstract',rental=True,eternal=True);t['jokers']['cards']=s['jokers']['cards']+[offer];t['money']=20
  self.assertTrue(n.affordable(s,t,offer,1.36,7.79));self.assertTrue(n.diagnostics()['last_affordability']['exception'])
  t['money']=8;self.assertFalse(n.affordable(s,t,offer,1.36,7.79))
  self.assertIn(n.diagnostics()['last_affordability']['reason'],('rental_cash_or_gain_exception_threshold_failed','next_round_rent_cash_floor_negative'))
 def test_noneternal_exception_requires_next_rent_cash(self):
  s=shop();t=shop();offer=joker('j_joker',rental=True);t['jokers']['cards']=[joker('j_banner',rental=True),offer];t['money']=6
  self.assertTrue(n.affordable(s,t,offer,1.2,3));t['money']=5
  self.assertFalse(n.affordable(s,t,offer,1.2,3))
 def test_copy_offer_selected_from_modeled_gain(self):
  s=shop();s['jokers']['cards']=[joker('j_stuntman'),joker('j_joker')];s['jokers']['count']=2;s['shop']['cards']=[joker('j_blueprint'),joker('j_flower_pot')]
  def measured(t):
   sim=copy.deepcopy(t);sim['state']='SELECTING_HAND';sim['blinds']['small']['status']='CURRENT'
   sim,_=n.round_capacity.reorder_for_combat(sim)
   score=n.a.options(sim)[0][0]/1000
   return (score,score,score)
  with patch.object(n,'metrics',side_effect=measured),patch.object(n,'outlook',side_effect=lambda t:measured(t)[0]):
   out=n.action(s)
  self.assertEqual(out[0],'buy');self.assertEqual(out[1]['card'],0)
  offers=n.diagnostics()['offers'];self.assertTrue(offers[0]['accepted']);self.assertFalse(offers[1]['accepted'])
  self.assertIn('measured',offers[1]['reason'])
 def test_same_conditional_key_accepted_when_measured_interaction_strong(self):
  s=shop();s['shop']['cards']=[joker('j_flower_pot')]
  def measured(t):return (2,2,2) if 'j_flower_pot' in n.a.keys(t) else (.8,.8,.8)
  with patch.object(n,'metrics',side_effect=measured),patch.object(n,'outlook',side_effect=lambda t:measured(t)[0]):
   out=n.choose_joker(s)
  self.assertEqual(out[0],'buy');self.assertEqual(out[1]['card'],0)
 def test_unmodeled_boss_discount_is_explicit_not_safety(self):
  s=shop();report={'available':True,'samples':4,'q25':200,'mean':200,'target':100,'limitations':['unmodeled_boss:The Hook']}
  with patch.object(n.round_capacity,'estimate',return_value=report):
   score=n.outlook(s)
  self.assertEqual(score,1)
  d=n.diagnostics()['capacity_evaluations'][-1]
  self.assertTrue(d['unknown_boss_risk']);self.assertFalse(d['capacity_is_safety_certificate'])
 def test_capacity_crossing_one_cannot_override_insolvent_rent(self):
  s=shop();t=shop();offer=joker('j_joker',rental=True);t['jokers']['cards']=[offer];t['money']=0
  self.assertFalse(n.affordable(s,t,offer,.5,2))
if __name__=='__main__':unittest.main()
