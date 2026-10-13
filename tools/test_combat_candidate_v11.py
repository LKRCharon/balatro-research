import copy
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
from test_no_sl_solver import state
from belief import base_deck
import combat_candidate_v11 as g


class Tests(unittest.TestCase):
    def fixture(self):
        s = state()
        deck = base_deck()
        keys = ('H_A', 'H_K', 'H_7', 'H_2', 'S_K', 'D_9', 'C_5', 'C_3')
        s['hand']['cards'] = [deck[k] for k in keys]
        s['hand'].update(limit=8, count=8)
        s['_belief']['unseen'] = [c for k, c in deck.items() if k not in keys]
        s['cards'].update(count=44, limit=52)
        s['round'].update(hands_left=5, discards_left=2)
        s['blinds']['big'].update(name='Small Blind', score=300)
        return s

    def test_balanced_batches_ignore_actual_order_and_do_not_mutate(self):
        s = self.fixture()
        before = copy.deepcopy(s)
        x = g.choose(s, {'samples': 8, 'time_budget': 60})
        self.assertEqual(s, before)
        t = copy.deepcopy(s)
        t['_belief']['unseen'].reverse()
        t['seed'] = 'PRIVATE'
        t['future_draw_order'] = ['PRIVATE']
        y = g.choose(t, {'samples': 8, 'time_budget': 60})
        self.assertEqual((x['method'], x['params']), (y['method'], y['params']))
        self.assertEqual(x['diagnostics']['ranked_candidates'], y['diagnostics']['ranked_candidates'])
        self.assertTrue(all(r['samples'] == 8 for r in x['diagnostics']['ranked_candidates']))

    def test_final_shortfall_spends_discard(self):
        s = self.fixture()
        s['round']['hands_left'] = 1
        s['blinds']['big']['score'] = 10000
        result = g.choose(s, {'samples': 8, 'time_budget': 60})
        self.assertEqual(result['method'], 'discard')

    def test_unsupported_nonplain_routes_to_existing_solver(self):
        s = self.fixture()
        s['hand']['cards'][0]['modifier'] = {'enhancement': 'STEEL'}
        with patch.object(g.prior, 'choose', return_value={'method': 'existing'}) as call:
            self.assertEqual(g.choose(s)['method'], 'existing')
            call.assert_called_once()


if __name__ == '__main__':
    unittest.main()
