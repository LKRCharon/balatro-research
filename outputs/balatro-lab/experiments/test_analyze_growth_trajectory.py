import copy
import json
from pathlib import Path
import tempfile
import unittest
import analyze_growth_trajectory as analysis


class Tests(unittest.TestCase):
    def test_deduplicates_offers_but_counts_reroll_and_actual_purchase(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'train-1'
            root.mkdir()
            card = {'key': 'j_joker', 'id': 10, 'cost': {'buy': 4}}
            before = {'state': 'SHOP', 'money': 5, 'shop': {'cards': [card]}}
            second = copy.deepcopy(before)
            second['shop']['cards'][0]['id'] = 11
            decisions = [
                {'sequence': 1, 'method': 'rearrange', 'before': before},
                {'sequence': 2, 'method': 'reroll', 'before': before},
                {'sequence': 3, 'method': 'buy', 'params': {'card': 0}, 'before': second}]
            (root / 'result.json').write_text(json.dumps({'status': 'loss'}))
            (root / 'decisions.jsonl').write_text('\n'.join(map(json.dumps, decisions)))
            events = [{'event': 'result', 'id': i, 'after': {'state': 'SHOP'}} for i in (1, 2, 3)]
            (root / 'transitions.jsonl').write_text('\n'.join(map(json.dumps, events)))
            out = analysis.analyze([folder])
            self.assertEqual(out['offers'][0]['unique_observed'], 2)
            self.assertEqual(out['offers'][0]['cash_affordable'], 2)
            self.assertEqual(out['offers'][0]['purchases'], 1)

    def test_unexecuted_buy_is_not_a_purchase_and_idless_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'train-1'
            root.mkdir()
            before = {'state': 'SHOP', 'money': 5, 'shop': {'cards': [{'key': 'j_joker', 'cost': {'buy': 4}}]}}
            (root / 'result.json').write_text(json.dumps({'status': 'loss'}))
            (root / 'decisions.jsonl').write_text(json.dumps({'sequence': 1, 'method': 'buy', 'params': {'card': 0}, 'before': before}))
            (root / 'transitions.jsonl').write_text(json.dumps({'event': 'result', 'id': 1, 'accepted': False, 'after': before}))
            out = analysis.analyze([folder])
            self.assertFalse(out['offers'])
            self.assertEqual(out['unexecuted_decisions'], 1)
            self.assertEqual(out['omitted_idless_observation_records'], 1)

    def test_round_equal_weight_and_excludes_active_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'train-1'
            root.mkdir()
            (Path(folder) / 'train-2').mkdir()
            entry = {'state': 'BLIND_SELECT', 'money': 8}
            entered = {'ante_num': 1, 'jokers': {'cards': []}, 'hand': {'limit': 8},
                'round': {'hands_left': 5}, 'blinds': {'small': {'status': 'CURRENT', 'name': 'Small Blind', 'type': 'SMALL', 'score': 300}}}
            decisions = [
                {'sequence': 1, 'method': 'select', 'before': entry},
                {'sequence': 2, 'method': 'play', 'before': {'state': 'SELECTING_HAND'}},
                {'sequence': 3, 'method': 'cash_out', 'before': {'state': 'ROUND_EVAL'}}]
            events = [
                {'event': 'result', 'id': 1, 'after': entered},
                {'event': 'result', 'id': 2, 'after': {'round': {'chips': 320}}},
                {'event': 'result', 'id': 3, 'after': {'money': 12, 'state': 'SHOP'}}]
            (root / 'result.json').write_text(json.dumps({'status': 'win'}))
            (root / 'decisions.jsonl').write_text('\n'.join(map(json.dumps, decisions)))
            (root / 'transitions.jsonl').write_text('\n'.join(map(json.dumps, events)))
            out = analysis.analyze([folder])
            self.assertEqual(out['completed'], 1)
            self.assertEqual(out['stages'][0]['observed_blinds'], 1)
            self.assertEqual(out['stages'][0]['mean_entry_cash'], 8)
            self.assertEqual(out['stages'][0]['mean_exit_cash'], 12)
            self.assertEqual(out['stages'][0]['mean_plays'], 1)

            events[1]['after'].update(won=True, overlay='win', money=8)
            (root / 'decisions.jsonl').write_text('\n'.join(map(json.dumps, decisions[:2])))
            (root / 'transitions.jsonl').write_text('\n'.join(map(json.dumps, events[:2])))
            final = analysis.analyze([folder])
            self.assertEqual(final['stages'][0]['observed_blinds'], 1)
            self.assertEqual(final['stages'][0]['clears'], 1)


if __name__ == '__main__':
    unittest.main()
