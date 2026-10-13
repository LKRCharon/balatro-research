import sys,unittest,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import round_capacity_v3 as n
from test_no_sl_solver import state

def held(key):return {'key':key,'set':'TAROT','state':{},'modifier':{},'value':{}}

class TarotCapacityTests(unittest.TestCase):
 def test_four_supported_tarots_use_same_runtime_targets_and_update_deck(self):
  for key,enh,count in [('c_empress','MULT',2),('c_heirophant','BONUS',2),('c_justice','GLASS',1),('c_chariot','STEEL',1)]:
   with self.subTest(key=key):
    s=state();s['consumables']['cards']=[held(key)];before=copy.deepcopy(s)
    expected=n.consumables.held_action(s)[1]['cards']
    t,uses=n.apply_held_tarots(s)
    self.assertEqual(uses[0]['targets'],expected);self.assertEqual(len(expected),count)
    self.assertFalse(t['consumables']['cards'])
    self.assertEqual(sum(n.a.mod(c).get('enhancement')==enh for c in t['_belief']['deck']),count)
    self.assertEqual(s,before)
 def test_targets_do_not_depend_on_unseen_order(self):
  s=state();s['consumables']['cards']=[held('c_empress')];t=copy.deepcopy(s);t['_belief']['unseen'].reverse();t['future_draw_order']=['PRIVATE']
  self.assertEqual(n.apply_held_tarots(s)[1],n.apply_held_tarots(t)[1])
 def test_capacity_cache_includes_consumables_and_glass_limitations(self):
  s=state();a=n.estimate(s);s['consumables']['cards']=[held('c_justice')];b=n.estimate(s)
  self.assertEqual(a['public_deck_hash'],b['public_deck_hash'])
  self.assertTrue(any(b['tarot_uses_by_world']))
  self.assertIn('glass_attrition_after_Tarot_not_modeled',b['limitations'])
 def test_unmodeled_tarot_not_assigned_weakness(self):
  s=state();s['consumables']['cards']=[held('c_death')];result=n.estimate(s)
  self.assertIn('other_held_consumables_not_simulated',result['limitations'])
if __name__=='__main__':unittest.main()
