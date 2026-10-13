import copy
import unittest
from audit_shop_candidates import commitment,audit_rows


class ShopAuditTests(unittest.TestCase):
    def fixture(self):
        state={'state':'SHOP','money':4,'description':'公开'}
        action=['buy',{'card':0,'reason':'公开购买'}]
        record={'call':1,'phase':'SHOP','public_state_commitment':commitment(state),'selected_action':action,
            'diagnostics':{'selected_action':copy.deepcopy(action)},'strategy_winrate_eligible':False}
        decision={'sequence':7,'before':state,'method':'buy','params':action[1]}
        return record,decision

    def test_same_action_and_unicode_state_join(self):
        r,d=self.fixture();result=audit_rows([r],[d],True)
        self.assertEqual(result['selected_action_matches'],1)

    def test_changed_public_state_rejected(self):
        r,d=self.fixture();d['before']['money']=5
        with self.assertRaises(AssertionError):audit_rows([r],[d],True)

    def test_changed_action_rejected(self):
        r,d=self.fixture();d['params']=dict(d['params'],card=1)
        with self.assertRaises(AssertionError):audit_rows([r],[d],True)

    def test_diagnostic_disagrees_with_selection(self):
        r,d=self.fixture();r['diagnostics']['selected_action']=None
        with self.assertRaises(AssertionError):audit_rows([r],[d],True)

    def test_null_selection_is_fallthrough_not_matching_action(self):
        r,d=self.fixture();r['selected_action']=r['diagnostics']['selected_action']=None
        result=audit_rows([r],[d],True)
        self.assertEqual(result['selected_action_matches'],0)
        self.assertEqual(result['policy_fallthrough_calls'],1)

    def test_active_tail_can_wait_for_decision(self):
        r,d=self.fixture();result=audit_rows([r],[],False)
        self.assertEqual(result['unresolved_calls'],[1])

    def test_duplicate_call_not_silently_counted(self):
        r,d=self.fixture()
        with self.assertRaises(AssertionError):audit_rows([r,r],[d],False)

    def test_two_selected_calls_cannot_claim_one_decision(self):
        r,d=self.fixture();second=copy.deepcopy(r);second['call']=2
        with self.assertRaises(AssertionError):audit_rows([r,second],[d],True)


if __name__=='__main__':unittest.main()
