import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import audit_combat_regret as audit


def decision(*, hands=1, discards=1, reason='', method='play'):
    return {'sequence': 1, 'method': method, 'params': {'cards': [0], 'reason': reason},
        'before': {'state': 'SELECTING_HAND', 'ante_num': 1,
            'round': {'chips': 100, 'hands_left': hands, 'discards_left': discards},
            'blinds': {'small': {'status': 'CURRENT', 'name': 'Small Blind', 'score': 300}}}}


def advisor(selected=190, uncertain=False):
    return SimpleNamespace(options=lambda s, **kwargs: [(220, (1,), 'Pair', (1,))],
        score=lambda s, cards: (selected, 'High Card', cards), uncertain=lambda s: uncertain)


class Tests(unittest.TestCase):
    def test_final_hand_finish_and_unspent_discard_are_flagged(self):
        row = audit.inspect_hand(decision(), advisor())
        self.assertTrue(row['final_hand_missed_finish'])
        self.assertTrue(row['spent_final_hand_without_finish_with_discards'])
        self.assertEqual(row['immediate_score_gap'], 30)

    def test_growth_postponement_is_distinguished_from_final_hand_failure(self):
        row = audit.inspect_hand(decision(hands=3, reason='v12_retained_core_growth'), advisor())
        self.assertTrue(row['passed_available_finish'])
        self.assertTrue(row['explicit_growth_play'])
        self.assertFalse(row['final_hand_missed_finish'])

    def test_uncertain_finish_does_not_become_deterministic_failure(self):
        row = audit.inspect_hand(decision(), advisor(uncertain=True))
        self.assertFalse(row['final_hand_missed_finish'])
        self.assertTrue(row['passed_available_finish'])

    def test_discard_not_scored_as_play_and_successful_finish_not_flagged(self):
        self.assertIsNone(audit.inspect_hand(decision(method='discard'), advisor())['model_selected_score'])
        row = audit.inspect_hand(decision(), advisor(selected=220))
        self.assertFalse(row['passed_available_finish'])
        self.assertFalse(row['spent_final_hand_without_finish_with_discards'])

    def test_active_episode_never_opened_and_unexecuted_action_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            active = Path(folder) / 'train-2'
            active.mkdir()
            (active / 'decisions.jsonl').write_text('INVALID DO NOT READ', encoding='utf-8')
            complete = Path(folder) / 'train-1'
            complete.mkdir()
            (complete / 'result.json').write_text(json.dumps({'status': 'loss'}), encoding='utf-8')
            (complete / 'decisions.jsonl').write_text(json.dumps(decision()), encoding='utf-8')
            (complete / 'transitions.jsonl').write_text(json.dumps({'event': 'result', 'id': 1, 'accepted': False}), encoding='utf-8')
            out = audit.analyze([folder], advisor())
            self.assertEqual(out['counts']['active_episodes_not_read'], 1)
            self.assertEqual(out['counts']['unexecuted_actions_omitted'], 1)
            self.assertFalse(out['flagged_actions'])


if __name__ == '__main__':
    unittest.main()
