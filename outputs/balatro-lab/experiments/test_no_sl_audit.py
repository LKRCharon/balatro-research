"""Failure-oriented tests of TRAIN/replay separation and no-SL provenance."""
import copy
import tempfile
from pathlib import Path
import unittest
from audit_no_sl_campaign import REPLAY_IDS,NEW_IDS,validate_jobs,validate_action_boundaries,capture_baseline,check_hidden_stubs


class NoSlAuditTest(unittest.TestCase):
    def spec(self):
        return {'partition':'train','strategy_winrate_eligible':False,'automatic_gameplay':True,
            'automatic_methods':['play','discard','rearrange'],
            'conditions':{'no_restart':True,'no_mutation_retry':True},
            'jobs':[{'seed_id':i,'seed_commitment':str(i),'cohort':'hindsight_replay' if i in REPLAY_IDS else 'new_train'} for i in sorted(REPLAY_IDS|NEW_IDS)]}

    def test_valid_separate_cohorts(self):
        self.assertEqual(len(validate_jobs(self.spec())),13)

    def test_replay_cannot_be_fresh(self):
        spec=self.spec();spec['jobs'][0]['cohort']='new_train'
        with self.assertRaises(AssertionError):validate_jobs(spec)

    def test_duplicate_or_other_seed_rejected(self):
        for seed_id in (32,99):
            spec=self.spec();spec['jobs'][-1]['seed_id']=seed_id
            with self.assertRaises(AssertionError):validate_jobs(spec)

    def test_test_partition_and_winrate_claim_rejected(self):
        for key,value in [('partition','test'),('strategy_winrate_eligible',True)]:
            spec=self.spec();spec[key]=value
            with self.assertRaises(AssertionError):validate_jobs(spec)

    def test_baseline_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'baseline.json';path.write_text('preserve')
            with self.assertRaises(ValueError):capture_baseline(path)
            self.assertEqual(path.read_text(),'preserve')

    def test_script_combat_allowed(self):
        intents={1:{'id':1,'method':'start'},2:{'id':2,'method':'play'}}
        decisions=[{'sequence':1,'method':'start','origin':'controller'},
            {'sequence':2,'method':'play','origin':'script','before':{'state':'SELECTING_HAND'}}]
        validate_action_boundaries(intents,decisions,{'play','discard','rearrange'})

    def test_second_start_or_save_load_rejected(self):
        for method in ('start','load','save','restart','reset','load_run','load_state'):
            intents={1:{'id':1,'method':'start'},2:{'id':2,'method':method}}
            with self.assertRaises(AssertionError):validate_action_boundaries(intents,[],{'play','discard','rearrange'})

    def test_solver_cannot_shop_or_rearrange_in_shop(self):
        for method in ('buy','rearrange'):
            intents={1:{'id':1,'method':'start'},2:{'id':2,'method':method}}
            decisions=[{'sequence':2,'method':method,'origin':'script','before':{'state':'SHOP'}}]
            with self.assertRaises(AssertionError):validate_action_boundaries(intents,decisions,{'play','discard','rearrange'})

    def test_midgame_menu_rejected(self):
        intents={1:{'id':1,'method':'start'},2:{'id':2,'method':'menu','before':{'state':'GAME_OVER'}}}
        with self.assertRaises(AssertionError):validate_action_boundaries(intents,[],{'play','discard','rearrange'})

    def test_hidden_identity_rejected(self):
        card={'key':'hidden','value':{},'modifier':{},'state':{'hidden':True}}
        state={'hand':{'cards':[card]}}
        self.assertEqual(check_hidden_stubs(state),1)
        for key,value in [('key','S_A'),('value',{'rank':'A'}),('modifier',{'seal':'RED'})]:
            altered=copy.deepcopy(state);altered['hand']['cards'][0][key]=value
            with self.assertRaises(AssertionError):check_hidden_stubs(altered)


if __name__=='__main__':unittest.main()
