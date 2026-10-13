import unittest
from types import SimpleNamespace
from offline_scoring_regression import evaluate


class RegressionTest(unittest.TestCase):
    def fixture(self,uncertain=False):
        return [{'episode':'synthetic','sequence':1,'before':{},'cards':[0],'actual':100,'original_uncertain':uncertain}]

    def test_numeric_regression_fails(self):
        scorer=SimpleNamespace(score=lambda *_:(98,),uncertain=lambda _:False)
        result=evaluate(self.fixture(),scorer)
        self.assertFalse(result['passed_existing_exact'])
        self.assertEqual(result['counts']['mismatches'],1)

    def test_hiding_known_case_as_uncertain_fails(self):
        scorer=SimpleNamespace(score=lambda *_:(100,),uncertain=lambda _:True)
        result=evaluate(self.fixture(),scorer)
        self.assertFalse(result['passed_existing_exact'])
        self.assertEqual(result['counts']['coverage_regressions'],1)

    def test_original_uncertainty_is_not_false_accuracy(self):
        scorer=SimpleNamespace(score=lambda *_:(500,),uncertain=lambda _:True)
        result=evaluate(self.fixture(True),scorer)
        self.assertEqual(result['counts']['uncertain'],1)
        self.assertNotIn('checkable',result['counts'])

    def test_new_exact_claim_checked_against_engine(self):
        scorer=SimpleNamespace(score=lambda *_:(500,),uncertain=lambda _:False)
        result=evaluate(self.fixture(True),scorer)
        self.assertFalse(result['passed_existing_exact'])
        self.assertEqual(len(result['newly_declared_exact']),1)


if __name__=='__main__':unittest.main()
