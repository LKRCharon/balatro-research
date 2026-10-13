import unittest
from unittest.mock import patch
import no_sl_solver_v3 as v3
from test_no_sl_solver import state
from belief import base_deck

class V3Tests(unittest.TestCase):
    def test_trio_rank_candidate(self):
        s=state();d=base_deck()
        s['hand']['cards']=[d[k] for k in ('S_9','H_9','D_5','C_4','S_2')]
        roots=v3.discard_roots(s,v3.a.options(s))
        self.assertIn((2,3,4),roots)

    def test_blackboard_red_cleanup(self):
        s=state();s['jokers']['cards']=[{'key':'j_blackboard','value':{},'state':{},'modifier':{}}]
        roots=v3.discard_roots(s,v3.a.options(s))
        self.assertIn((1,2,4),roots)

    def test_green_and_banner_discard_costs(self):
        s=state();s['round']['discards_left']=2
        s['jokers']['cards']=[{'key':'j_green_joker','value':{'effect':'当前 +9 倍'},'state':{},'modifier':{}}]
        after=v3.after_discard(s,[0],s['_belief']['unseen'])
        self.assertEqual(v3.a.current_number(after['jokers']['cards'][0]),8)
        self.assertEqual(after['round']['discards_left'],1)
        self.assertEqual(s['round']['discards_left'],2)

    def test_weak_hand_draw_route_beats_early_play(self):
        s=state();s['round']['discards_left']=2
        with patch.object(v3.v1.static,'scenarios',return_value=[s['_belief']['unseen']]*4):
            out=v3.choose(s,{'samples':4,'time_budget':10})
        self.assertEqual(out['method'],'discard')
        self.assertEqual(out['diagnostics']['mode'],'v3_discard_opportunity')

    def test_immediate_clear_delegates_without_samples(self):
        s=state();s['blinds']['big']['score']=10;s['round']['discards_left']=2
        with patch.object(v3.v1.static,'scenarios',side_effect=AssertionError('must not sample')):
            out=v3.choose(s)
        self.assertEqual(out['method'],'play')



class FinalHandGuardTests(unittest.TestCase):
    def fake_play(self):
        return {'method':'play','params':{'cards':[0]},'diagnostics':{'mode':'fallback'}}

    def test_zero_clear_samples_never_spend_short_final_hand(self):
        s=state();s['round'].update(hands_left=1,discards_left=2)
        s['blinds']['big']['score']=1934
        with patch.object(v3,'_choose_opportunity',return_value=self.fake_play()):
            out=v3.choose(s)
        self.assertEqual(out['method'],'discard')
        self.assertTrue(out['diagnostics']['last_hand_model_shortfall'])

    def test_hidden_last_hand_replaces_unknown_card(self):
        s=state();s['round'].update(hands_left=1,discards_left=2)
        s['blinds']['big']['score']=1934
        s['hand']['cards'][3]={'key':'hidden','state':{'hidden':True},'modifier':{},'value':{}}
        with patch.object(v3,'_choose_opportunity',return_value=self.fake_play()):
            out=v3.choose(s)
        self.assertEqual(out['method'],'discard');self.assertEqual(out['params']['cards'],[3])

    def test_no_discards_cannot_preserve_redraw(self):
        s=state();s['round'].update(hands_left=1,discards_left=0)
        with patch.object(v3,'_choose_opportunity',return_value=self.fake_play()):
            out=v3.choose(s)
        self.assertEqual(out['method'],'play')

    def test_noop_rearrangement_converts_to_play(self):
        s=state();s['blinds']['big']['score']=10
        fake={'method':'rearrange','params':{'hand':list(range(5))},'diagnostics':{'mode':'fallback'}}
        with patch.object(v3,'_choose_opportunity',return_value=fake):
            out=v3.choose(s)
        self.assertEqual(out['method'],'play')
        self.assertTrue(out['diagnostics']['noop_rearrangement_avoided'])

if __name__=='__main__':unittest.main()
