import sys,unittest,copy
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v15 as n
from test_growth_candidate_v13 import shop,joker

def tarot(key='c_empress',price=3):return {'key':key,'set':'TAROT','state':{},'value':{},'modifier':{},'cost':{'buy':price}}

class V15Tests(unittest.TestCase):
 def test_buy_supported_tarot_to_hold_without_future_targets(self):
  s=shop();s['shop']['cards']=[tarot()]
  def metric(t):return (1.5,1.5,1.5) if t['consumables']['cards'] else (.7,.7,.7)
  with patch.object(n,'metrics',side_effect=metric),patch.object(n,'choose_joker',return_value=None):
   result=n.action(s)
  self.assertEqual(result[0],'buy');self.assertEqual(result[1]['card'],0)
  self.assertNotIn('use',result[1]);self.assertNotIn('cards',result[1])
  self.assertTrue(n.diagnostics()['offers'][0]['accepted'])
 def test_full_slot_and_price_checked_before_metrics(self):
  s=shop();s['shop']['cards']=[tarot()];s['consumables']['limit']=0
  with patch.object(n,'metrics',side_effect=AssertionError('illegal offer')):
   self.assertIsNone(n.choose_combat_tarot(s))
  self.assertEqual(n.diagnostics()['tarot_candidates'][0]['reason'],'no_consumable_slot')
  s['consumables']['limit']=2;s['money']=2
  with patch.object(n,'metrics',side_effect=AssertionError('illegal offer')):
   self.assertIsNone(n.choose_combat_tarot(s))
 def test_other_tarots_scope_is_explicit(self):
  s=shop();s['shop']['cards']=[tarot('c_death')]
  self.assertIsNone(n.choose_combat_tarot(s))
  self.assertIn('not_a_weakness_claim',n.diagnostics()['tarot_candidates'][0]['reason'])
 def test_planet_offer_consumed_constellation_once_not_per_copier(self):
  s=shop();planet={'key':'c_mercury','set':'PLANET','cost':{'buy':3}}
  c=joker('j_constellation');c['value']['effect']='当前 1';s['jokers']['cards']=[c,joker('j_blueprint')]
  s['shop']['cards']=[planet];before=copy.deepcopy(s)
  t=n.planet_after_use(s,planet,3,index=0)
  self.assertEqual(t['money'],27);self.assertFalse(t['shop']['cards'])
  self.assertAlmostEqual(n.a.current_number(t['jokers']['cards'][0]),1.1)
  self.assertEqual(t['jokers']['cards'][1]['value'],{})
  self.assertAlmostEqual(n.a.current_number(n.grown(t)['jokers']['cards'][0]),1.1)
  self.assertEqual(s,before)
 def test_inventory_planet_consumed(self):
  s=shop();planet={'key':'c_mercury','set':'PLANET','cost':{'buy':3}};s['consumables']['cards']=[planet];s['consumables']['count']=1
  t=n.planet_after_use(s,planet,0,source='inventory',index=0)
  self.assertEqual(t['money'],30);self.assertEqual(t['consumables']['count'],0)
 def test_sell_reobserve_does_not_queue_purchase(self):
  s=shop()
  with patch.object(n,'choose_joker',return_value=('sell',{'joker':0,'reason':'replace later'})),patch.object(n,'choose_combat_tarot',return_value=None):
   result=n.action(s)
  self.assertEqual(result,('sell',{'joker':0,'reason':'replace later'}))
if __name__=='__main__':unittest.main()
