import unittest
from reconcile_rejected_pack import validate_rejection

class RejectedPackTests(unittest.TestCase):
    def intent(self):return {'event':'intent','id':62,'method':'pack','params':{'card':0,'cards':[7]},'before':{'state':'SMODS_BOOSTER_OPENED','pack':{'cards':[{'key':'c_chariot'}]}}}
    def test_explicit_target_guard_allowed(self):
        validate_rejection(self.intent(),"Card 'c_chariot' requires exactly 1 target card(s). Provided: 0")
    def test_ambiguous_error_not_reconciled(self):
        with self.assertRaises(ValueError):validate_rejection(self.intent(),'RPC timeout')
    def test_valid_target_request_not_reconciled(self):
        i=self.intent();i['params']['targets']=[7]
        with self.assertRaises(ValueError):validate_rejection(i,"Card 'c_chariot' requires exactly 1 target card(s). Provided: 0")
    def test_other_phase_not_reconciled(self):
        i=self.intent();i['before']['state']='SHOP'
        with self.assertRaises(ValueError):validate_rejection(i,"Card 'c_chariot' requires exactly 1 target card(s). Provided: 0")
    def test_pack_affordability_guard_allowed(self):
        i={'event':'intent','method':'buy','params':{'pack':0},'before':{'state':'SHOP','money':4,'packs':{'cards':[{'cost':{'buy':6}}]}}}
        validate_rejection(i,'Card is not affordable. Cost: 6, Available money: 4')
        with self.assertRaises(ValueError):validate_rejection(i,'RPC timeout')
        i['before']['money']=10
        with self.assertRaises(ValueError):validate_rejection(i,'Card is not affordable. Cost: 6, Available money: 10')

if __name__=='__main__':unittest.main()
