import copy
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
from test_no_sl_solver import state
from belief import base_deck
import combat_candidate_v12 as g


class Tests(unittest.TestCase):
    def fixture(self):
        s = state()
        deck = base_deck()
        s['hand']['cards'] = [deck[k] for k in ('H_K', 'D_K', 'C_2', 'S_3', 'D_4')]
        s['money'] = 8
        s['jokers']['cards'] = [{'key': 'j_green_joker', 'value': {'effect': '当前 8'}, 'modifier': {}, 'state': {}}]
        s['round'].update(hands_left=2, hands_played=2)
        s['blinds']['big'].update(name='Big Blind', score=200)
        return s

    def test_farms_late_in_round_and_keeps_winning_pair(self):
        s = self.fixture()
        before = copy.deepcopy(s)
        x = g.growth_action(s)
        self.assertIsNotNone(x)
        self.assertEqual(s, before)
        self.assertEqual(x['diagnostics']['mode'], 'v12_retained_core_growth')
        self.assertFalse(set(x['params']['cards']) & {0, 1})
        self.assertGreaterEqual(x['diagnostics']['retained_model_clear_bound'], 200)

    def test_never_farms_last_hand_or_below_cash_floor(self):
        for field, value in (('last', 1), ('money', 4)):
            s = self.fixture()
            if field == 'last': s['round']['hands_left'] = value
            else: s['money'] = value
            self.assertIsNone(g.growth_action(s))

    def test_no_growth_when_no_independent_winning_core(self):
        s = self.fixture()
        s['blinds']['big']['score'] = 10000
        self.assertIsNone(g.growth_action(s))


if __name__ == '__main__':
    unittest.main()
