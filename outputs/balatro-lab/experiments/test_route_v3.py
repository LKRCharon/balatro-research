"""Game-free regression states; no held-out seeds or recorded states required."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE/'policies/route_v3'), str(HERE.parent/'cli')]
import advisor as a
import policy
import shop_planning as planner
from belief import base_deck

def joker(key, buy=4, edition=None):
    return {'key':key, 'set':'JOKER', 'value':{'effect':''}, 'state':{},
            'modifier':{'edition':edition} if edition else {}, 'cost':{'buy':buy,'sell':2}}

def state():
    base = [(5,1),(10,2),(20,2),(30,3),(30,4),(35,4),(40,4),(60,7),(100,8),(120,12),(140,14),(160,16)]
    return {'state':'SHOP','money':7,'ante_num':1,'round_num':2,
        'hands':{n:{'chips':c,'mult':m,'level':1,'played':0,'played_this_round':0} for n,(c,m) in zip(a.NAMES,base)},
        'jokers':{'cards':[],'limit':5},'hand':{'cards':[],'limit':8},
        'consumables':{'cards':[],'limit':2},'shop':{'cards':[]},'packs':{'cards':[]},'vouchers':{'cards':[]},
        'round':{'hands_left':5,'discards_left':2,'hands_played':0,'chips':0,'reroll_cost':5},
        'blinds':{'small':{'status':'DEFEATED','name':'Small Blind','score':300},
                  'big':{'status':'DEFEATED','name':'Big Blind','score':450},
                  'boss':{'status':'UPCOMING','name':'The Club','score':600}},
        '_belief':{'deck':list(base_deck().values())},'cards':{'count':52,'limit':52},'used_vouchers':[]}

class ShopRegression(unittest.TestCase):
    def test_satellite_cannot_spend_last_cash_under_pressure(self):
        s=state();s['shop']['cards']=[joker('j_satellite',6)]
        self.assertIsNone(planner.choose(s,policy.utility,policy.XMULT))

    def test_jupiter_beats_generators_without_flush_route_lock(self):
        s=state();s['money']=5
        s['shop']['cards']=[joker('j_8_ball',5),joker('j_hallucination',4),
                            {'key':'c_jupiter','set':'PLANET','cost':{'buy':3}}]
        self.assertNotEqual(policy.main_hand(s),'Flush')
        chosen=planner.choose(s,policy.utility,policy.XMULT)
        self.assertEqual(chosen[0],'buy');self.assertEqual(chosen[1]['card'],2)
        self.assertTrue(chosen[1]['use'])

    def test_all_affordable_jokers_compared_by_immediate_lineup(self):
        s=state();s['shop']['cards']=[joker('j_dna',6),joker('j_joker',2)]
        chosen=planner.choose(s,policy.utility,policy.XMULT)
        self.assertEqual(chosen[1]['card'],1)

    def test_future_dna_preserved_when_safe_and_cash_available(self):
        s=state();s['money']=30;s['shop']['cards']=[joker('j_dna',6)]
        for hand in s['hands'].values(): hand['mult']*=100
        chosen=planner.choose(s,policy.utility,policy.XMULT)
        self.assertEqual(chosen[1]['card'],0)

    def test_planner_does_not_mutate_input(self):
        s=state();s['shop']['cards']=[joker('j_joker',2)]
        before=copy.deepcopy(s);planner.choose(s,policy.utility,policy.XMULT)
        self.assertEqual(before,s)

    def test_negative_replacement_cannot_remove_required_slot(self):
        s=state();s['jokers']={'limit':1,'cards':[joker('j_satellite',edition='NEGATIVE')]}
        s['shop']['cards']=[joker('j_joker',2)]
        self.assertIsNone(planner.choose(s,policy.utility,policy.XMULT))

    def test_replacement_can_use_sale_proceeds(self):
        s=state();s['money']=1;s['jokers']={'limit':1,'cards':[joker('j_satellite')]}
        s['shop']['cards']=[joker('j_joker',3)]
        chosen=planner.choose(s,policy.utility,policy.XMULT)
        self.assertEqual(chosen[0],'sell');self.assertEqual(chosen[1]['joker'],0)

    def test_work_is_bounded(self):
        s=state();s['shop']['cards']=[joker('j_joker') for _ in range(30)]
        outcome={'q25':1,'median':1,'hands':5,'pressure':True,'coverage':.1}
        with patch.object(planner.forecast,'estimate',return_value=outcome) as forecast:
            planner.choose(s,policy.utility,policy.XMULT)
        self.assertLessEqual(forecast.call_count,1+planner.MAX_OFFERS*planner.MAX_REPLACEMENTS)

if __name__=='__main__': unittest.main()
