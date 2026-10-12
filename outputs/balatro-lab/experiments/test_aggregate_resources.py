import unittest
from aggregate_resources import aggregate

class AggregateTests(unittest.TestCase):
    def report(self,n,status='loss'):
        return {'runs':[{'run_id':n,'status':status,'quoted_acquisition_costs':{'pack':4},'offer_exposures':[{'area':'packs','cash_covers_price_when_first_seen':True}],'resource_events':[]}]}
    def test_split(self):
        r=aggregate([self.report(32),self.report(42)])
        self.assertEqual(r['groups']['hindsight_replay']['completed'],1)
        self.assertEqual(r['groups']['new_train']['quoted_costs']['pack'],4)
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):aggregate([self.report(32),self.report(32)])
    def test_active_and_unknown_rejected(self):
        for n,status in ((42,'active'),(99,'loss')):
            with self.assertRaises(ValueError):aggregate([self.report(n,status)])

if __name__=='__main__':unittest.main()
