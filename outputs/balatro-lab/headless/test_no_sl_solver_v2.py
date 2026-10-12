import copy
import unittest
from unittest.mock import patch
import no_sl_solver_v2 as v2
from test_no_sl_solver import state


def hidden_state():
    s = state()
    s['hand']['cards'][-1] = {'key': 'hidden', 'state': {'hidden': True}, 'value': {}, 'modifier': {}}
    s['round']['discards_left'] = 2
    return s


class V2Tests(unittest.TestCase):
    def test_visible_clear_before_hidden_discard(self):
        s = hidden_state(); s['blinds']['big']['score'] = 10
        out = v2.choose(s)
        self.assertEqual(out['method'], 'play')
        self.assertNotIn(4, out['params']['cards'])
        self.assertEqual(out['diagnostics']['mode'], 'v2_visible_only_model_clear')

    def test_misprint_uses_zero_not_expectation(self):
        s = hidden_state()
        s['jokers']['cards'] = [{'key': 'j_misprint', 'value': {}, 'modifier': {}, 'state': {}}]
        values = v2.visible_lower_options(s)
        self.assertEqual(max(o[0] for o in values), 16)
        s['blinds']['big']['score'] = 100
        self.assertEqual(v2.choose(s)['method'], 'discard')

    def test_hidden_identity_and_input_immutability(self):
        s = hidden_state(); s['blinds']['big']['score'] = 10
        t = copy.deepcopy(s)
        t['hand']['cards'][-1].update(key='S_A', value={'rank':'A','suit':'S'}, modifier={'enhancement':'STEEL'})
        t['seed'] = 'PRIVATE'; t['future_draw_order'] = ['PRIVATE']
        before = copy.deepcopy(t)
        x, y = v2.choose(s), v2.choose(t)
        self.assertEqual(x, y); self.assertEqual(t, before)

    def test_blackboard_unknown_predicate_not_certified(self):
        s = hidden_state()
        s['jokers']['cards'] = [{'key':k,'value':{},'modifier':{},'state':{}} for k in ('j_blackboard','j_smeared')]
        self.assertEqual(v2.visible_lower_options(s), [])

    def test_glass_scoring_core_survives_heuristic_discard(self):
        s = state(); s['hand']['cards'][0]['modifier'] = {'enhancement':'GLASS'}
        s['round']['discards_left'] = 1
        fake = {'method':'discard','params':{'cards':[0,3]},'diagnostics':{'fallback_is_heuristic':True,'mode':'fallback'}}
        with patch.object(v2.v1, 'choose', return_value=fake):
            out = v2.choose(s)
        self.assertEqual(out['params']['cards'], [3])
        self.assertIn(0, out['diagnostics']['protected_enhanced_indices'])

    def test_face_down_sanitized(self):
        s = state(); s['hand']['cards'][0]['state'] = {'face_down':True}
        public = v2.public_state(s)
        self.assertEqual(public['hand']['cards'][0]['value'], {})
        self.assertTrue(public['hand']['cards'][0]['state']['hidden'])

    def test_shop_rejected(self):
        s=state(); s['state']='SHOP'
        with self.assertRaises(ValueError): v2.choose(s)


if __name__ == '__main__': unittest.main()
