"""Synthetic public states only; no game executable, traces or held-out data."""
import copy
import sys
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'policies/route_v4'),str(HERE.parent/'cli')]
import advisor as a
import combat
from belief import base_deck

def state():
    deck=base_deck()
    hand=[deck[k] for k in ('C_A','H_K','D_9','S_7','H_3')]
    unseen=[deck[k] for k in ('H_A','D_A','S_A','S_K','D_K')]
    bases=[(5,1),(10,2),(20,2),(30,3),(30,4),(35,4),(40,4),(60,7),(100,8),(120,12),(140,14),(160,16)]
    return {'state':'SELECTING_HAND','money':4,'ante_num':1,'round_num':2,
        'hands':{n:{'chips':c,'mult':m,'level':1,'played':0,'played_this_round':0} for n,(c,m) in zip(a.NAMES,bases)},
        'jokers':{'cards':[],'limit':5},'hand':{'cards':hand,'count':5,'limit':5},
        'consumables':{'cards':[],'limit':2},'round':{'hands_left':2,'discards_left':0,'hands_played':0,'chips':0},
        'blinds':{'big':{'status':'CURRENT','name':'Big Blind','score':160}},
        '_belief':{'deck':hand+unseen,'unseen':unseen},'cards':{'count':5,'limit':10},'used_vouchers':[]}

class CombatRegression(unittest.TestCase):
    def test_equal_score_junk_cycles_toward_next_hand(self):
        s=state();chosen=combat.choose(s,('play',{'cards':[0],'reason':'v3 single high card'}))
        self.assertEqual(chosen[0],'play');self.assertEqual(chosen[1]['cards'],[0,1,2,3,4])
        self.assertTrue(combat.last_diagnostics['used'])
        self.assertTrue(combat.last_diagnostics['action_changed'])
        self.assertEqual(combat.last_diagnostics['estimated_two_action_clear_fraction'],1)

    def test_one_hand_left_can_discard_without_spending_last_play(self):
        s=state();s['round']['hands_left']=1;s['round']['discards_left']=1
        chosen=combat.choose(s,('play',{'cards':[0],'reason':'v3'}))
        self.assertEqual(chosen[0],'discard')

    def test_no_replacement_and_input_immutable(self):
        s=state();before=copy.deepcopy(s);world=combat.scenarios(s,1)[0]
        after,remaining,_=combat.transition(s,'play',[0,1],world)
        self.assertEqual(len(remaining),3)
        self.assertEqual([c['key'] for c in after['hand']['cards'][-2:]],[c['key'] for c in world[:2]])
        again,unused,_=combat.transition(after,'play',[0],remaining)
        self.assertEqual(len(unused),2)
        self.assertEqual(again['hand']['cards'][-1]['key'],remaining[0]['key'])
        self.assertEqual(s,before)

    def test_seed_hidden_order_and_permutation_not_inputs(self):
        s=state();other=copy.deepcopy(s)
        other['seed']='PRIVATE';other['future_draw_order']=['S_2'];other['_belief']['unseen'].reverse()
        self.assertEqual(combat.scenarios(s),combat.scenarios(other))
        fallback=('play',{'cards':[0],'reason':'baseline'})
        self.assertEqual(combat.choose(s,fallback),combat.choose(other,fallback))

    def test_unsupported_mutation_falls_back_with_reason(self):
        s=state();s['jokers']['cards']=[{'key':'j_dna','state':{},'modifier':{}}]
        fallback=('play',{'cards':[0],'reason':'baseline'})
        out=combat.choose(s,fallback)
        self.assertEqual(out[0],fallback[0]);self.assertEqual(out[1]['cards'],[0])
        self.assertIn('j_dna',combat.last_diagnostics['fallback_reason'])
        self.assertFalse(combat.last_diagnostics['used'])

    def test_psychic_requires_five_cards(self):
        s=state();s['blinds']['big']['name']='The Psychic'
        after,_,score=combat.transition(s,'play',[0],s['_belief']['unseen'])
        self.assertEqual(score,0)
        self.assertEqual(after['round']['hands_left'],1)

    def test_eye_and_mouth_history_updates(self):
        s=state();s['blinds']['big']['name']='The Eye'
        after,_,_=combat.transition(s,'play',[0],s['_belief']['unseen'])
        self.assertEqual(a.score(after,[0])[0],0)
        s['blinds']['big']['name']='The Mouth'
        after,_,_=combat.transition(s,'play',[0],s['_belief']['unseen'])
        self.assertEqual(after['round']['mouth_hand'],'High Card')

    def test_already_winning_preserved_without_search(self):
        s=state();s['blinds']['big']['score']=10
        fallback=('play',{'cards':[0],'reason':'baseline'})
        self.assertEqual(combat.choose(s,fallback),fallback)
        self.assertEqual(combat.last_diagnostics['candidate_count'],0)
        self.assertFalse(combat.last_diagnostics['used'])

    def test_candidate_and_sample_bounds(self):
        s=state();s['round']['discards_left']=2
        self.assertLessEqual(len(combat.candidates(s,('play',{'cards':[0]}))),10)
        self.assertEqual(len(combat.scenarios(s)),6)

    def test_gold_seal_cash_transition_falls_back(self):
        s=state();s['hand']['cards'][0]['modifier']['seal']='GOLD'
        self.assertEqual(combat.support_reason(s),'random_or_mutating_card_effect')

    def test_shop_implementation_unchanged(self):
        old=(HERE/'policies/route_v3/policy.py').read_text(encoding='utf-8')
        new=(HERE/'policies/route_v4/policy.py').read_text(encoding='utf-8')
        def shop(source):
            return source.split("    if state=='SHOP':",1)[1].split("    raise ValueError('Unhandled state",1)[0]
        self.assertEqual(shop(old),shop(new))

if __name__=='__main__':unittest.main()
