"""Independent tiny-world oracles; no real seeds, engine, or held-out observations."""
import copy
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / 'policies/route_v4'), str(HERE.parent / 'cli')]
import advisor as a
import combat
from belief import base_deck


def tiny():
    deck = base_deck()
    bases = [(5,1),(10,2),(20,2),(30,3),(30,4),(35,4),(40,4),(60,7),(100,8),(120,12),(140,14),(160,16)]
    hand = [copy.deepcopy(deck[k]) for k in ('S_2','H_2','D_3','C_4')]
    unseen = [copy.deepcopy(deck[k]) for k in ('S_5','H_6')]
    return {'state':'SELECTING_HAND','money':5,'ante_num':1,
            'hand':{'cards':hand,'count':4,'limit':4},'jokers':{'cards':[],'limit':5},
            'cards':{'count':2,'limit':6},'consumables':{'cards':[],'limit':2},
            'hands':{name:{'chips':chips,'mult':mult,'level':1,'played':0,'played_this_round':0}
                     for name,(chips,mult) in zip(a.NAMES,bases)},
            'round':{'hands_left':2,'discards_left':1,'hands_played':0,'discards_used':0,'chips':0},
            'blinds':{'small':{'status':'CURRENT','name':'Small Blind','score':60}},
            '_belief':{'deck':hand+unseen,'unseen':unseen}}


def subsets(n):
    for size in range(1, min(5,n)+1):
        yield from itertools.combinations(range(n),size)


def oracle(s, root, world):
    """Independent exhaustive second-play enumeration for static no-Joker worlds."""
    method, selected = root
    remaining = copy.deepcopy(s)
    gained = a.score(s,selected)[0] if method == 'play' else 0
    need = s['blinds']['small']['score'] - s['round']['chips']
    if gained >= need:
        return {'clear':True,'score':need,'hands_used':1,'root_score':gained}
    hand = [copy.deepcopy(c) for i,c in enumerate(s['hand']['cards']) if i not in selected]
    draws = min(s['hand']['limit'] - len(hand),len(world))
    hand.extend(copy.deepcopy(world[:draws]))
    remaining['hand']['cards']=hand
    remaining['hand']['count']=len(hand)
    remaining['cards']['count']-=draws
    remaining['round']['hands_left']-=int(method=='play')
    remaining['round']['discards_left']-=int(method=='discard')
    remaining['round']['chips']+=gained
    follow=max((a.score(remaining,x)[0] for x in subsets(len(hand))),default=0) if remaining['round']['hands_left']>0 else 0
    return {'clear':gained+follow>=need,'score':min(need,gained+follow),
            'hands_used':int(method=='play')+int(follow>0),'root_score':gained}


class IndependentCombatAudit(unittest.TestCase):
    def test_every_tiny_root_world_matches_exhaustive_leaf(self):
        s=tiny()
        for world in itertools.permutations(s['_belief']['unseen']):
            for method in ('play','discard'):
                for selected in subsets(4):
                    root=(method,selected)
                    self.assertEqual(combat.scenario_value(s,root,world),oracle(s,root,world))

    def test_selected_root_optimal_only_in_declared_bounded_candidates(self):
        s=tiny();fallback=('play',{'cards':[0,1],'reason':'fixture'})
        roots=combat.candidates(s,fallback)
        worlds=list(itertools.permutations(s['_belief']['unseen']))
        def rank(index,root):
            values=[oracle(s,root,w) for w in worlds]
            scores=sorted(v['score'] for v in values)
            return (sum(v['clear'] for v in values)/len(values),scores[0],sum(scores)/len(scores),
                    -sum(v['hands_used'] for v in values)/len(values),-int(root[0]=='discard'),-index)
        expected=max(enumerate(roots),key=lambda item:rank(*item))[1]
        with patch.object(combat,'scenarios',return_value=worlds):
            chosen=combat.choose(s,fallback)
        self.assertEqual((chosen[0],tuple(chosen[1]['cards'])),expected)

    def test_unknown_mutation_falls_back_without_sampling(self):
        s=tiny();s['jokers']['cards']=[{'key':'j_dna','value':{},'modifier':{},'state':{}}]
        fallback=('play',{'cards':[0,1],'reason':'fixture'})
        with patch.object(combat,'scenarios',side_effect=AssertionError('unsupported must not sample')):
            chosen=combat.choose(s,fallback)
        self.assertEqual(chosen[0],fallback[0]);self.assertEqual(chosen[1]['cards'],[0,1])
        self.assertFalse(combat.last_diagnostics['supported'])

    def test_leaf_value_cannot_depend_on_unused_world_order(self):
        s=tiny();extra=copy.deepcopy(base_deck()['D_7'])
        first,second=s['_belief']['unseen']
        w1=[first,second,extra];w2=[first,extra,second]
        # Discard one => reveal same first card. Unused suffix must not affect a leaf choice.
        self.assertEqual(combat.scenario_value(s,('discard',(3,)),w1),
                         combat.scenario_value(s,('discard',(3,)),w2))
        after1,_,_=combat.transition(s,'discard',(3,),w1)
        after2,_,_=combat.transition(s,'discard',(3,),w2)
        self.assertEqual(after1['_belief']['unseen'],after2['_belief']['unseen'])

    def test_gold_seal_cash_transition_is_not_claimed_supported(self):
        s=tiny();s['hand']['cards'][0]['modifier']['seal']='GOLD'
        s['jokers']['cards']=[{'key':'j_bull','value':{},'modifier':{},'state':{}}]
        self.assertIsNotNone(combat.support_reason(s))


if __name__=='__main__':unittest.main()
