import unittest
from growth_policy_v5 import choose,candidate_states

class GrowthTests(unittest.TestCase):
    def state(self):return {'money':10,'round':{'reroll_cost':5},'jokers':{'limit':1,'cards':[{'key':'old','cost':{'sell':2},'modifier':{}}]},'shop':{'cards':[{'key':'new','set':'JOKER','cost':{'buy':7},'modifier':{}}]}}
    def evaluate(self,s):return {'verified':True,'capacity':200 if s['jokers']['cards'][0]['key']=='new' else 50,'target':100}
    def test_replacement_all_and_reobserve(self):
        r=choose(self.state(),self.evaluate);self.assertEqual(r['action'],('sell',{'joker':0}));self.assertTrue(r['must_reobserve'])
    def test_unknown_not_safe(self):self.assertTrue(choose(self.state(),lambda s:{'verified':False})['requires_review'])
    def test_eternal_not_sellable(self):
        s=self.state();s['jokers']['cards'][0]['modifier']['eternal']=True;self.assertEqual(list(candidate_states(s)),[])
    def test_bounded_refresh_keeps_purchase_cash(self):
        s=self.state();s['shop']['cards']=[];s['money']=11
        self.assertEqual(choose(s,self.evaluate)['action'][0],'reroll')
        self.assertIsNone(choose(s,self.evaluate,rerolls_this_shop=2)['action'])
    def test_expiry_stress_used(self):
        s=self.state();s['shop']['cards']=[];s['jokers']['cards'][0]['modifier']['perishable']=1
        def score(t):return {'verified':True,'capacity':20 if t['jokers']['cards'][0].get('state',{}).get('debuff') else 200,'target':100}
        self.assertEqual(choose(s,score)['baseline_coverage'],.2)

if __name__=='__main__':unittest.main()
