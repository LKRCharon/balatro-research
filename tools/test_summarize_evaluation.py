import unittest
from summarize_evaluation import summarize_job

class AccountingTest(unittest.TestCase):
    def test_repeated_observation_purchase_reroll_and_failure(self):
        card = {'id': 7, 'key': 'j_joker', 'set': 'JOKER'}
        shop = {'state': 'SHOP', 'ante_num': 1, 'round_num': 1, 'money': 8,
                'shop': {'cards': [card]}, 'vouchers': {'cards': [{'id': 8, 'key': 'v_x'}]}}
        bought = {**shop, 'money': 6, 'shop': {'cards': []}}
        events = [
            {'event': 'intent', 'id': 1, 'method': 'buy', 'params': {'card': 0}, 'before': shop},
            {'event': 'result', 'id': 1, 'after': bought},
            {'event': 'intent', 'id': 2, 'method': 'reroll', 'before': bought},
            {'event': 'result', 'id': 2, 'after': shop},
            {'event': 'intent', 'id': 3, 'method': 'next_round', 'before': shop},
            {'event': 'result', 'id': 3, 'after': {'state': 'GAME_OVER', 'ante_num': 1, 'round_num': 2,
             'money': 2, 'round': {'chips': 400}, 'blinds': {'big': {'status': 'CURRENT', 'name': 'Big Blind', 'score': 450}}}}
        ]
        out = summarize_job(events, {'j_joker': 1}, {'status': 'loss'})
        self.assertEqual(out['shop_joker_rarity_offers'], {'1': 2})
        self.assertEqual(out['offers_by_area_key']['vouchers:v_x'], 1)
        self.assertEqual(out['resolved_buy_actions_by_area_key'], {'shop:j_joker': 1})
        self.assertEqual(out['failure']['score'], 400)
        self.assertEqual(out['failure']['target'], 450)
        self.assertEqual(out['unresolved_intents'], 0)

if __name__ == '__main__':
    unittest.main()
