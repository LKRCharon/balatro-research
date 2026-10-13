import sys,unittest,copy
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import growth_candidate_v14 as n
import growth_candidate_v13 as frozen
from test_growth_candidate_v13 import shop,joker

def xjoker(key,value=1):
 c=joker(key);c['value']['effect']='当前 '+str(value);return c

def projected(s,key):
 t,notes=n.visible_growth(s)
 return next(n.a.current_number(c) for c in t['jokers']['cards'] if c['key']==key),t,notes

class V14Tests(unittest.TestCase):
 def test_binding_does_not_patch_frozen_module(self):
  self.assertIs(n.action.__globals__['grown'],n.grown)
  self.assertIsNot(n.grown,frozen.grown)
  self.assertEqual(frozen.VERSION,'growth_candidate_v13')
 def test_constellation_requires_visible_opportunity(self):
  s=shop();s['jokers']['cards']=[xjoker('j_constellation')]
  self.assertEqual(projected(s,'j_constellation')[0],1)
  s['shop']['cards']=[{'key':'c_mercury','set':'PLANET','cost':{'buy':3}}]
  value,t,notes=projected(s,'j_constellation')
  self.assertAlmostEqual(value,1.1);self.assertEqual(t['money'],27)
 def test_shared_cash_not_double_spent(self):
  s=shop();s['money']=3;s['jokers']['cards']=[xjoker('j_constellation'),xjoker('j_hologram')]
  s['shop']['cards']=[{'key':'c_mercury','set':'PLANET','cost':{'buy':3}},{'key':'S_2','set':'DEFAULT','cost':{'buy':3}}]
  t,notes=n.visible_growth(s)
  self.assertEqual(t['money'],0)
  self.assertAlmostEqual(n.a.current_number(t['jokers']['cards'][0]),1.1)
  self.assertEqual(n.a.current_number(t['jokers']['cards'][1]),1)
 def test_hologram_entry_and_conditional_dna(self):
  s=shop();s['jokers']['cards']=[xjoker('j_hologram'),joker('j_certificate'),joker('j_dna')]
  value,t,notes=projected(s,'j_hologram');self.assertEqual(value,1.5)
  self.assertTrue(any(x.get('heuristic') for x in notes))
 def test_vampire_pays_enhancement_cost(self):
  s=shop();s['jokers']['cards']=[xjoker('j_vampire')];s['_belief']['deck'][0]['modifier']={'enhancement':'BONUS'}
  original=copy.deepcopy(s);value,t,notes=projected(s,'j_vampire')
  self.assertGreater(value,1);self.assertNotIn('enhancement',t['_belief']['deck'][0]['modifier']);self.assertEqual(s,original)
 def test_madness_does_not_assume_free_companion_destruction(self):
  s=shop();s['jokers']['cards']=[xjoker('j_madness'),joker('j_joker')]
  self.assertEqual(projected(s,'j_madness')[0],1)
  s['jokers']['cards'][1]['modifier']['eternal']=True
  self.assertEqual(projected(s,'j_madness')[0],1.5)
 def test_yorick_needs_public_counter_and_cheap_discard(self):
  s=shop();c=xjoker('j_yorick');s['jokers']['cards']=[c]
  self.assertEqual(projected(s,'j_yorick')[0],1)
  c['value']['effect']='当前 1 再弃掉 3 张';self.assertEqual(projected(s,'j_yorick')[0],2)
  s['jokers']['cards'].append(joker('j_banner'));self.assertEqual(projected(s,'j_yorick')[0],1)
 def test_wee_zero_twos_means_zero_growth(self):
  s=shop();s['jokers']['cards']=[xjoker('j_wee',0)]
  self.assertEqual(projected(s,'j_wee')[0],0)
  s['_belief']['deck'][0]['value']['rank']='2'
  self.assertGreater(projected(s,'j_wee')[0],0)
 def test_cash_before_strong_joker_and_reobserve(self):
  s=shop();s['money']=10;s['shop']['cards']=[joker('j_blueprint'),{'key':'c_hermit','set':'TAROT','cost':{'buy':3}}]
  before=copy.deepcopy(s)
  with patch.object(n,'choose_joker',return_value=('buy',{'card':0})) as choose:
   first=n.action(s)
   choose.assert_not_called()
   self.assertEqual((first[0],first[1]['card'],first[1]['use']),('buy',1,True))
   self.assertEqual(n.diagnostics()['cash_priority']['cash_after_if_executed'],14)
   self.assertEqual(s,before)
   # Only the subsequent observation supplies the realized proceeds.
   after=copy.deepcopy(s);after['money']=14;after['shop']['cards'].pop(1)
   second=n.action(after);choose.assert_called_once()
   self.assertEqual(second,('buy',{'card':0}))
 def test_zero_net_hermit_does_not_preempt_joker(self):
  s=shop();s['money']=6;s['shop']['cards']=[joker('j_blueprint'),{'key':'c_hermit','set':'TAROT','cost':{'buy':3}}]
  with patch.object(n,'choose_joker',return_value=('buy',{'card':0})) as choose:
   out=n.action(s)
  choose.assert_called_once();self.assertEqual(out,('buy',{'card':0}))
  self.assertNotIn('cash_priority',n.diagnostics())
 def test_temperance_positive_net_with_full_consumable_slots(self):
  s=shop();s['money']=10;s['jokers']['cards']=[joker('j_joker'),joker('j_banner')]
  s['consumables']={'limit':1,'count':1,'cards':[{'key':'c_pluto','set':'PLANET'}]}
  s['shop']['cards']=[{'key':'c_temperance','set':'TAROT','cost':{'buy':3}}]
  with patch.object(n,'choose_joker',side_effect=AssertionError('cash must be first')):
   out=n.action(s)
  self.assertTrue(out[1]['use']);self.assertEqual(n.diagnostics()['cash_priority']['net_cash_gain'],1)
 def test_cash_shortcut_respects_explicit_use_legality(self):
  s=shop();s['shop']['cards']=[{'key':'c_hermit','set':'TAROT','cost':{'buy':3},'can_use':False}]
  self.assertIsNone(n.immediate_cash_action(s))
  s['shop']['cards'][0]['can_use']=True;s['overlay']=True
  self.assertIsNone(n.immediate_cash_action(s))
if __name__=='__main__':unittest.main()
