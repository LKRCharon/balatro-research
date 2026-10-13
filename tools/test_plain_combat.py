import copy
import random
import sys
import unittest

from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'outputs/balatro-lab/headless'),str(ROOT/'outputs/balatro-lab/experiments'),str(ROOT/'outputs/balatro-lab/experiments/policies/route_v3'),str(ROOT/'outputs/balatro-lab/cli')]
from test_no_sl_solver import state
from belief import base_deck
import plain_combat as p


class Tests(unittest.TestCase):
    def test_matches_reference_subset_scores_and_boss_constraints(self):
        rng = random.Random(717)
        deck = list(base_deck().values())
        for boss in ('Big Blind', 'The Psychic', 'The Eye', 'The Mouth', 'The Arm', 'The Flint', 'The Head', 'Cerulean Bell'):
            s = state()
            s['blinds']['big']['name'] = boss
            s['hands']['Pair'].update(level=2, chips=25, mult=3, played_this_round=1)
            s['round']['mouth_hand'] = 'Pair'
            for _ in range(3):
                s['hand']['cards'] = copy.deepcopy(rng.sample(deck, 8))
                s['hand']['cards'][0]['state'] = {'debuff': True, 'highlight': True}
                self.assertEqual(p.options(s), p.a.options(s))

    def test_declines_mutating_and_nonplain_states(self):
        for field, value in (('modifier', {'enhancement': 'MULT'}),
                             ('modifier', {'edition': 'FOIL'}),
                             ('state', {'hidden': True}),
                             ('permanent_bonus', 5)):
            s = state()
            s['hand']['cards'][0][field] = value
            self.assertFalse(p.supported(s))
        s = state()
        s['jokers']['cards'] = [{'key': 'j_blueprint'}]
        self.assertFalse(p.supported(s))


if __name__ == '__main__':
    unittest.main()
