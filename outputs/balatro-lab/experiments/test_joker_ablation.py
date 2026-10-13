import copy
import unittest
from types import SimpleNamespace
import analyze_joker_ablation as audit


def scoring(state, selected):
    active = {c['key'] for c in state['jokers']['cards'] if not c['state'].get('debuff')}
    value = 10
    if 'chips' in active:
        value += 10
    if 'copy' in active and 'chips' in active:
        value += 10
    return value, 'High Card', selected


class Tests(unittest.TestCase):
    def test_copy_interaction_not_additive_and_state_not_mutated(self):
        state = {'jokers': {'cards': [{'key': k, 'state': {}, 'modifier': {}} for k in ('chips', 'copy', 'economy')]}}
        before = copy.deepcopy(state)
        advisor = SimpleNamespace(score=scoring, st=lambda c: c['state'], mod=lambda c: c['modifier'])
        rows = audit.ablate(state, [0], advisor)
        self.assertEqual([r['difference'] for r in rows], [20, 10, 0])
        self.assertEqual(state, before)
        self.assertTrue(all(r['sell_recommendation'] is False for r in rows))
        self.assertTrue(all(r['edition'] == 'NONE' for r in rows))

    def test_debuffed_ability_not_counted_and_negative_effect_retained(self):
        state = {'jokers': {'cards': [{'key': 'penalty', 'state': {}, 'modifier': {}},
            {'key': 'expired', 'state': {'debuff': True}, 'modifier': {}}]}}
        def penalty(s, selected):
            return (50 if s['jokers']['cards'][0]['state'].get('debuff') else 20), 'High Card', selected
        advisor = SimpleNamespace(score=penalty, st=lambda c: c['state'], mod=lambda c: c['modifier'])
        rows = audit.ablate(state, [0], advisor)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['difference'], -30)


if __name__ == '__main__':
    unittest.main()
