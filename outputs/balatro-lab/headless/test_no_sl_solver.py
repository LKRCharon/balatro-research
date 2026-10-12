"""Independent synthetic no-SL boundary tests; no engine or reserved seed access."""
import copy
import unittest
from unittest.mock import patch
import no_sl_solver as n
from belief import base_deck


def state():
    deck=base_deck();hand=[deck[k] for k in ('C_A','H_K','D_9','S_7','H_3')]
    unseen=[deck[k] for k in ('H_A','D_A','S_A','S_K','D_K')]
    bases=[(5,1),(10,2),(20,2),(30,3),(30,4),(35,4),(40,4),(60,7),(100,8),(120,12),(140,14),(160,16)]
    return {'state':'SELECTING_HAND','money':4,'ante_num':1,'round_num':2,
        'hands':{name:{'chips':c,'mult':m,'level':1,'played':0,'played_this_round':0} for name,(c,m) in zip(n.a.NAMES,bases)},
        'jokers':{'cards':[],'limit':5},'hand':{'cards':hand,'count':5,'limit':5},
        'consumables':{'cards':[],'limit':2},'round':{'hands_left':2,'discards_left':0,'hands_played':0,'chips':0},
        'blinds':{'big':{'status':'CURRENT','name':'Big Blind','score':160}},
        '_belief':{'deck':hand+unseen,'unseen':unseen},'cards':{'count':5,'limit':10},'used_vouchers':[]}


class SolverTests(unittest.TestCase):
    def test_immediate_clear_avoids_chance_search(self):
        s=state();s['blinds']['big']['score']=10
        with patch.object(n.static,'scenarios',side_effect=AssertionError('No rollouts needed')):
            out=n.choose(s)
        self.assertEqual(out['method'],'play');self.assertEqual(out['diagnostics']['mode'],'current_model_immediate_clear')
        self.assertFalse(out['diagnostics']['optimality_claim'])

    def test_scenarios_ignore_real_seed_order_and_unseen_permutation(self):
        s=state();t=copy.deepcopy(s);t['seed']='SHOULD_NOT_BE_READ';t['future_draw_order']=['PRIVATE'];t['_belief']['unseen'].reverse()
        self.assertEqual(n.static.scenarios(s),n.static.scenarios(t))
        config={'samples':2,'max_candidates':5,'time_budget':60}
        x=n.choose(s,config);y=n.choose(t,config)
        self.assertEqual((x['method'],x['params']),(y['method'],y['params']))
        self.assertEqual(x['diagnostics']['ranked_candidates'],y['diagnostics']['ranked_candidates'])

    def test_input_state_not_mutated(self):
        s=state();before=copy.deepcopy(s);n.choose(s,{'samples':1,'max_candidates':3,'time_budget':60});self.assertEqual(s,before)

    def test_continuation_cannot_see_sample_tail_order(self):
        s=state();w=copy.deepcopy(s['_belief']['unseen']);v=[w[0]]+list(reversed(w[1:]))
        x,_=n.transition(s,'play',[0],w);y,_=n.transition(s,'play',[0],v)
        self.assertEqual(x['hand'],y['hand']);self.assertEqual(n.continuation(x),n.continuation(y))

    def test_serpent_has_one_card_discard_and_draws_three(self):
        s=state();s['blinds']['big']['name']='The Serpent';s['round']['discards_left']=1
        roots=n.roots(s,n.a.options(s),10)
        self.assertTrue(any(method=='discard' and len(indices)==1 for method,indices in roots))
        after,_=n.transition(s,'discard',[0],s['_belief']['unseen'])
        self.assertEqual(len(after['hand']['cards']),7);self.assertEqual(after['round']['hands_left'],2)

    def test_hidden_cards_no_forward_certainty(self):
        s=state();s['hand']['cards'][0]={'key':'hidden','state':{'hidden':True},'value':{},'modifier':{}}
        s['_belief']['hidden_identity_approximation']=True
        out=n.choose(s)
        self.assertFalse(out['diagnostics']['forward_supported']);self.assertIn('hidden',out['diagnostics']['fallback_reason'])

    def test_mutable_joker_falls_back_explicitly(self):
        s=state();s['jokers']['cards']=[{'key':'j_hiker','state':{},'modifier':{},'value':{}}]
        out=n.choose(s)
        self.assertIn('j_hiker',out['diagnostics']['fallback_reason']);self.assertFalse(out['diagnostics']['forward_supported'])

    def test_reordered_play_materializes_rearrangement(self):
        out=n.action_for(state(),'play',[1,0],{})
        self.assertEqual(out['method'],'rearrange');self.assertEqual(out['params']['hand'],[1,0,2,3,4])

    def test_shop_is_not_a_solver_action_space(self):
        s=state();s['state']='SHOP'
        with self.assertRaises(ValueError):n.choose(s)

    def test_soft_budget_does_not_compare_partial_samples(self):
        out=n.choose(state(),{'samples':64,'time_budget':1e-9})
        self.assertEqual(out['diagnostics']['ranked_candidates'],[])
        self.assertEqual(out['diagnostics']['fallback_reason'],'time_budget_before_complete_candidate')

    def test_mutable_needle_pressure_uses_remaining_discard(self):
        s=state();s['blinds']['big'].update(name='The Needle',score=1000)
        s['round'].update(hands_left=1,discards_left=1)
        s['jokers']['cards']=[{'key':'j_hiker','state':{},'modifier':{},'value':{}}]
        out=n.choose(s)
        self.assertEqual(out['method'],'discard')
        self.assertEqual(out['diagnostics']['heuristic_reason'],'visible_score_capacity_pressure')

    def test_hidden_cards_discarded_without_assuming_identity(self):
        s=state();s['round']['discards_left']=1
        s['hand']['cards'][2]={'key':'hidden','state':{'hidden':True},'modifier':{},'value':{}}
        s['_belief']['hidden_identity_approximation']=True
        out=n.choose(s)
        self.assertEqual(out['method'],'discard');self.assertEqual(out['params']['cards'],[2])

    def test_expensive_discard_preserved_if_current_capacity_suffices(self):
        s=state();s['round']['discards_left']=1
        s['jokers']['cards']=[{'key':'j_green_joker','state':{},'modifier':{},'value':{'effect':'+0'}}]
        options=n.a.options(s);need=options[0][0]*s['round']['hands_left']/1.05
        out=n.heuristic_fallback(s,options,need,{'mode':'test'})
        self.assertIn(out['method'],('play','rearrange'))

    def test_burnt_first_discard_targets_pair(self):
        s=state();s['hand']['cards'][1]=copy.deepcopy(base_deck()['H_A']);s['round']['discards_left']=1
        s['jokers']['cards']=[{'key':'j_burnt','state':{},'modifier':{},'value':{}}]
        out=n.choose(s)
        self.assertEqual(out['method'],'discard');self.assertEqual(out['params']['cards'],[0,1])

    def test_bell_discard_includes_forced_highlight(self):
        s=state();s['blinds']['big']['name']='Cerulean Bell';s['round']['discards_left']=1
        s['hand']['cards'][0]['state']['highlight']=True
        out=n.heuristic_fallback(s,n.a.options(s),10000,{'mode':'test'})
        self.assertEqual(out['method'],'discard');self.assertIn(0,out['params']['cards'])

if __name__=='__main__':unittest.main()
