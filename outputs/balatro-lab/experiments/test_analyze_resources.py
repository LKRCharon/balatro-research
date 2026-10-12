import unittest
from analyze_resources import analyze, interest, target_card

class ResourceTests(unittest.TestCase):
    def test_interest_caps(self):
        self.assertEqual(interest(100),5)
        self.assertEqual(interest(100,['v_seed_money']),10)
        self.assertEqual(interest(-3),0)
    def test_price_not_net_and_offer_dedup(self):
        b={'money':10,'shop':{'cards':[{'id':4,'key':'j_test','set':'JOKER','cost':{'buy':6}}]}}
        rows=[{'event':'intent','id':1,'method':'buy','params':{'card':0},'before':b},
              {'event':'result','id':1,'after':{'money':7}},
              {'event':'intent','id':2,'method':'reroll','params':{},'before':b},
              {'event':'result','id':2,'after':{'money':5}}]
        r=analyze(rows,1)
        self.assertEqual(r['quoted_acquisition_costs']['joker'],6)
        self.assertEqual(r['resource_events'][0]['net_cash_delta'],-3)
        self.assertEqual(len(r['offer_exposures']),1)
    def test_rejected_is_not_expenditure(self):
        r=analyze([{'event':'intent','id':1,'method':'buy','params':{},'before':{'money':0}},
                   {'event':'result','id':1,'accepted':False,'after':{'money':-4}}],1)
        self.assertEqual(r['rejected_no_mutation'],1)
        self.assertEqual(r['resource_events'],[])
    def test_no_forward_power_fabrication(self):
        r=analyze([{'event':'intent','id':1,'method':'next_round','params':{},'before':{'money':7}},
                   {'event':'result','id':1,'after':{'money':7}}],1)
        self.assertIsNone(r['last_departure']['forward_power_estimate'])
    def test_unmatched_result_fails(self):
        with self.assertRaises(ValueError):analyze([{'event':'result','id':3}],1)

if __name__=='__main__':unittest.main()
