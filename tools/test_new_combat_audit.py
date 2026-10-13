"""Independent boundary regressions; no reference engine or raw seed input."""
import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
from test_no_sl_solver import state
import test_combat_candidate_v12 as growth_fixtures
import plain_combat as plain
import combat_candidate_v11 as search
import combat_candidate_v12 as growth


class AuditTests(unittest.TestCase):
    def test_disabled_flint_matches_normal_score(self):
        s=state();s['_boss_disabled']=True;s['blinds']['big']['name']='The Flint'
        self.assertEqual(plain.options(s),plain.a.options(s))

    def test_blue_joker_growth_bound_accounts_for_refill(self):
        s=growth_fixtures.Tests().fixture()
        s['jokers']['cards'].append({'key':'j_blue_joker','value':{'effect':''},'modifier':{},'state':{}})
        choice=growth.growth_action(s);self.assertIsNotNone(choice)
        played=choice['params']['cards'];diag=choice['diagnostics']
        after,_,_=growth.grow.prior.transition(s,'play',played,[])
        old_count=s['cards']['count'];draws=min(old_count,s['hand']['limit']-len(after['hand']['cards']))
        after['cards']['count']=old_count-draws
        remaining=[i for i in range(len(s['hand']['cards'])) if i not in played]
        retained=[remaining.index(i) for i in diag['retained_winning_indices']]
        self.assertEqual(diag['retained_model_clear_bound'],growth.grow.a.conservative_score(after,retained))
        self.assertEqual(diag['refill_deck_count_cost'],draws)

    def test_continuation_does_not_depend_on_unused_tail_order(self):
        s=state();s['round'].update(hands_left=4,discards_left=1)
        w=copy.deepcopy(s['_belief']['unseen']);v=[w[0]]+list(reversed(w[1:]))
        left,_,_=search.v1.static.transition(s,'play',[0],w)
        right,_,_=search.v1.static.transition(s,'play',[0],v)
        self.assertEqual(left['hand'],right['hand'])
        self.assertEqual(search.continuation(left),search.continuation(right))


if __name__=='__main__':unittest.main()
