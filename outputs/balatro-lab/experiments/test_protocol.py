"""Checks leakage, frozen-code drift, paired jobs, and result accounting using toy seeds only."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import protocol as p


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'registry.sqlite'
        p.initialize(self.db, ['v5vhkivn', 'V5VHKIVN', '69TO6TF1'], dict(train=3, validation=2, test=2))
        self.source = self.root / 'policy'
        self.source.mkdir()
        (self.source / 'policy.py').write_text('def action(s): return None\n')
        self.a = p.register_policy(self.db, 'baseline', self.source, {'weight': 1})
        self.b = p.register_policy(self.db, 'candidate', self.source, {'weight': 2})

    def jobs(self, campaign):
        with p.connect(self.db) as con:
            return [dict(r) for r in con.execute('SELECT * FROM jobs WHERE campaign_id=?', (campaign,))]

    def test_known_replays_are_one_training_group(self):
        report = p.public_summary(self.db)
        self.assertEqual(report['seen_training_seeds'], 2)
        self.assertEqual(report['counts'], {'train': 5, 'validation': 2, 'test': 2})
        p.assert_partition(self.db, ' v5vhkivn ', 'train')
        with self.assertRaises(ValueError):
            p.assert_partition(self.db, 'V5VHKIVN', 'test')
        self.assertNotIn('V5VHKIVN', json.dumps(report))

    def test_reinitializing_a_split_is_refused(self):
        with self.assertRaises(ValueError):
            p.initialize(self.db, [], dict(train=3, validation=2, test=2))

    def test_paired_design_and_duplicate_campaign(self):
        campaign = p.schedule(self.db, 'validation', [self.a, self.b], 2)
        jobs = self.jobs(campaign)
        self.assertEqual(len(jobs), 4)
        self.assertEqual({j['seed_id'] for j in jobs if j['policy_id'] == self.a},
                         {j['seed_id'] for j in jobs if j['policy_id'] == self.b})
        with self.assertRaises(ValueError):
            p.schedule(self.db, 'validation', [self.a, self.b], 2)

    def test_test_partition_requires_frozen_campaign_and_is_one_shot(self):
        with self.assertRaises(ValueError):
            p.schedule(self.db, 'test', [self.a], 2)
        p.schedule(self.db, 'test', [self.a, self.b], 2, final_test=True)
        with self.assertRaises(ValueError):
            p.schedule(self.db, 'test', [self.b], 2, final_test=True)

    def test_worker_cannot_take_test_job_as_training(self):
        campaign = p.schedule(self.db, 'test', [self.a], 1, final_test=True)
        job = self.jobs(campaign)[0]
        with self.assertRaises(ValueError):
            p.claim_job(self.db, job['id'], 'train')
        self.assertEqual(self.jobs(campaign)[0]['status'], 'planned')

    def test_source_drift_and_extra_source_file_are_refused(self):
        campaign = p.schedule(self.db, 'train', [self.a], 1)
        job = self.jobs(campaign)[0]
        (self.source / 'policy.py').write_text('def action(s): return "changed"\n')
        with self.assertRaises(ValueError):
            p.claim_job(self.db, job['id'], 'train')
        (self.source / 'policy.py').write_text('def action(s): return None\n')
        (self.source / 'extra.py').write_text('hidden_change = True\n')
        with self.assertRaises(ValueError):
            p.claim_job(self.db, job['id'], 'train')

    def test_model_weights_are_part_of_the_freeze(self):
        weights = self.source / 'weights.bin'
        weights.write_bytes(b'first')
        ident = p.register_policy(self.db, 'with-weights', self.source, {})
        campaign = p.schedule(self.db, 'train', [ident], 1)
        job = self.jobs(campaign)[0]
        weights.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            p.claim_job(self.db, job['id'], 'train')

    def test_reservations_are_disjoint_and_insufficient_sample_refused(self):
        report = p.public_summary(self.db)
        self.assertEqual(len(report['seeds']), len({s['commitment'] for s in report['seeds']}))
        with self.assertRaises(ValueError):
            p.schedule(self.db, 'validation', [self.a], 3)

    def test_mismatched_result_refused_and_error_retained(self):
        campaign = p.schedule(self.db, 'train', [self.a], 1)
        job = self.jobs(campaign)[0]
        claim = p.claim_job(self.db, job['id'], 'train')
        with self.assertRaises(ValueError):
            p.record_result(self.db, job['id'], 'test', claim['seed'], self.a, {'status': 'win'})
        p.record_result(self.db, job['id'], 'train', claim['seed'], self.a,
                        {'status': 'error', 'detail': 'unsupported mechanism'})
        self.assertEqual(p.public_summary(self.db)['job_status_counts'], {'error': 1})
        with self.assertRaises(ValueError):
            p.record_result(self.db, job['id'], 'train', claim['seed'], self.a, {'status': 'win'})


if __name__ == '__main__':
    unittest.main()
