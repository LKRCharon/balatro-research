import sys, unittest, copy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
import combat_candidate_v5 as n
from test_no_sl_solver import state
from belief import base_deck
class V5Tests(unittest.TestCase):
 def test_four_hearts_preserved_before_weak_high_card(self):
  s=state();d=base_deck();s['hand']['cards']=[d[k] for k in ('H_A','H_K','D_T','D_9','C_8','H_6','H_4','C_3')];s['hand']['limit']=8
  s['round'].update(hands_left=5,discards_left=2);s['blinds']['big']['score']=300
  used={c['key'] for c in s['hand']['cards']};s['_belief']['unseen']=[c for k,c in d.items() if k not in used];s['cards']['count']=44
  o=n.choose(s,{'samples':8,'time_budget':1})
  self.assertEqual(o['method'],'discard');self.assertEqual(o['params']['cards'],[2,3,4,7])
 def test_balanced_sample_counts(self):
  s=state();s['round']['discards_left']=2
  rows=n.rank_discards(s,n.a.options(s),{'samples':8,'time_budget':.00001})
  self.assertTrue(rows);self.assertEqual(len({r['samples'] for r in rows}),1)
  self.assertGreaterEqual(rows[0]['samples'],1)
 def test_no_change_to_input(self):
  s=state();s['round']['discards_left']=2;b=copy.deepcopy(s);n.choose(s,{'samples':4,'time_budget':1});self.assertEqual(s,b)
 def test_immediate_clear(self):
  s=state();s['blinds']['big']['score']=10;s['round']['discards_left']=2
  self.assertEqual(n.choose(s)['diagnostics']['mode'],'v5_current_model_clear')
 def test_actual_future_order_ignored(self):
  s=state();s['round']['discards_left']=2;t=copy.deepcopy(s);t['seed']='SECRET';t['future_draw_order']=['SECRET'];t['_belief']['unseen'].reverse()
  x=n.choose(s,{'samples':8,'time_budget':10});y=n.choose(t,{'samples':8,'time_budget':10})
  self.assertEqual(x,y)
if __name__=='__main__':unittest.main()
