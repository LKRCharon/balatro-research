import copy
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from environment import Environment, sanitize
from env_cli import serve
from transport import TransportError
from vector_env import VectorEnv


class FakeClient:
    def __init__(self, identity, state=None):
        self.identity = identity
        self.state = state or {'state': 'MENU'}
        self.calls = []
        self.closed = False
        self.fail_play = False

    def call(self, method, params=None):
        self.calls.append((method, copy.deepcopy(params)))
        if method == 'lab_info':
            return {'identity': self.identity, 'headless': True, 'graphics_active': False,
                    'mute': True, 'master_volume': 0, 'desktop': 'BalatroLab-test',
                    'sound': dict(volume=0, music_volume=0, game_sounds_volume=0)}
        if method == 'play' and self.fail_play:
            raise TransportError('simulated uncertain outcome')
        if method == 'start':
            self.state = {'state': 'BLIND_SELECT', 'seed': params['seed']}
        return copy.deepcopy(self.state)

    def close(self):
        self.closed = True


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / 'train.sqlite'
        with sqlite3.connect(self.registry) as db:
            db.execute('CREATE TABLE seeds(seed TEXT, partition TEXT)')
            db.execute("INSERT INTO seeds VALUES ('TRAIN123', 'train')")

    def tearDown(self):
        self.tmp.cleanup()

    def make_env(self, name='one', state=None):
        client = FakeClient('Balatro-Lab-' + name, state)
        env = Environment(12400, client.identity, self.root / name,
                          registry=self.registry, client=client)
        self.addCleanup(env.close)
        return env, client

    def test_observation_strips_seed_rng_draw_pile_and_hidden_identity(self):
        raw = {'state': 'SELECTING_HAND', 'seed': 'PRIVATE',
               'nested': {'rng_state': 'PRIVATE', 'draw_order': ['PRIVATE'], 'money': 5},
               'cards': {'count': 52, 'limit': 52, 'cards': ['PRIVATE']},
               'hand': {'cards': [{'key': 'PRIVATE', 'value': {'rank': 'PRIVATE'},
                                  'modifier': {'enhancement': 'PRIVATE'},
                                  'state': {'hidden': True}},
                                 {'key': 'S_A', 'value': [], 'modifier': [], 'state': []}]}}
        safe = sanitize(raw)
        self.assertNotIn('PRIVATE', json.dumps(safe))
        self.assertEqual(safe['cards'], {'count': 52, 'limit': 52})
        self.assertEqual(safe['hand']['cards'][1]['key'], 'S_A')
        self.assertEqual(safe['hand']['cards'][1]['value'], {})
        self.assertEqual(raw['seed'], 'PRIVATE')

    def test_unfinished_episode_cannot_be_reset(self):
        env, client = self.make_env(state={'state': 'SHOP'})
        with self.assertRaisesRegex(ValueError, 'unfinished'):
            env.reset('TRAIN123')
        self.assertEqual([m for m, p in client.calls], ['lab_info', 'gamestate'])
        self.assertFalse(env.path.exists())

    def test_second_controller_rejected_and_close_releases_port(self):
        env, client = self.make_env()
        second = FakeClient('Balatro-Lab-two')
        with self.assertRaisesRegex(RuntimeError, 'controller'):
            Environment(12400, second.identity, self.root / 'two', client=second)
        self.assertEqual(second.calls, [])
        env.close()
        with Environment(12400, second.identity, self.root / 'two', client=second):
            self.assertEqual([m for m, p in second.calls], ['lab_info'])

    def test_bad_runtime_closes_client_and_releases_lease(self):
        bad = FakeClient('Balatro-Lab-wrong')
        with self.assertRaisesRegex(RuntimeError, 'isolation'):
            Environment(12400, 'Balatro-Lab-one', self.root / 'bad', client=bad)
        self.assertTrue(bad.closed)
        env, client = self.make_env()
        self.assertEqual([m for m, p in client.calls], ['lab_info'])

    def test_unregistered_seed_never_contacts_engine_for_reset(self):
        env, client = self.make_env()
        with self.assertRaisesRegex(ValueError, 'training seeds'):
            env.reset('UNKNOWN')
        self.assertEqual([m for m, p in client.calls], ['lab_info'])

    def test_reset_journals_only_commitment_and_returns_public_state(self):
        env, client = self.make_env()
        self.assertNotIn('seed', env.reset('TRAIN123'))
        text = env.path.read_text(encoding='utf8')
        self.assertNotIn('TRAIN123', text)
        records = [json.loads(line) for line in text.splitlines()]
        self.assertEqual([r['event'] for r in records], ['intent', 'result'])
        self.assertEqual(len(records[0]['params']['start_commitment']), 64)

    def test_timeout_persists_intent_blocks_restart_and_never_retries(self):
        state = {'state': 'SELECTING_HAND', 'hand': {'cards': [{'key': 'S_A'}]}}
        env, client = self.make_env(state=state)
        client.fail_play = True
        with self.assertRaises(TransportError):
            env.step('play', {'cards': [0], 'reason': 'test'})
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            env.step('play', {'cards': [0], 'reason': 'test'})
        self.assertEqual(sum(m == 'play' for m, p in client.calls), 1)
        self.assertEqual(json.loads(env.path.read_text(encoding='utf8'))['event'], 'intent')
        restarted = FakeClient(client.identity, state)
        with self.assertRaisesRegex(RuntimeError, 'Unresolved'):
            Environment(12400, restarted.identity, env.root,
                        registry=self.registry, client=restarted)
        self.assertEqual(restarted.calls, [])

    def test_jsonl_normal_output_contains_only_public_observation(self):
        env, client = self.make_env(state={'state': 'SHOP', 'seed': 'PRIVATE', 'money': 17})
        sink = io.StringIO()
        code = serve(env, io.StringIO('{"id":3,"method":"observe"}\n'), sink)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(sink.getvalue()),
                         {'id': 3, 'result': {'state': 'SHOP', 'money': 17}})

    def test_jsonl_ambiguous_mutation_stops_before_next_command(self):
        env, client = self.make_env(state={'state': 'SELECTING_HAND',
                                          'hand': {'cards': [{'key': 'S_A'}]}})
        client.fail_play = True
        first = {'id': 'a', 'method': 'step',
                 'params': {'method': 'play', 'params': {'cards': [0], 'reason': 'test'}}}
        second = {'id': 'b', 'method': 'observe'}
        sink = io.StringIO()
        code = serve(env, io.StringIO(json.dumps(first) + '\n' + json.dumps(second) + '\n'), sink)
        self.assertEqual(code, 2)
        response = json.loads(sink.getvalue())
        self.assertTrue(response['needs_reconciliation'])
        self.assertEqual(response['id'], 'a')
        self.assertEqual([m for m, p in client.calls], ['lab_info', 'gamestate', 'play'])

    def test_jsonl_malformed_request_recovers_without_contact_or_leak(self):
        env, client = self.make_env(state={'state': 'SHOP', 'seed': 'PRIVATE'})
        sink = io.StringIO()
        code = serve(env, io.StringIO('[]\n{"method":"observe","id":2}\n'), sink)
        self.assertEqual(code, 0)
        responses = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertIn('error', responses[0])
        self.assertEqual(responses[1], {'id': 2, 'result': {'state': 'SHOP'}})
        self.assertNotIn('PRIVATE', sink.getvalue())
        self.assertEqual([m for m, p in client.calls], ['lab_info', 'gamestate'])


class StubEnv:
    def __init__(self, port, identity, root, *, barrier=None, fail=False):
        self.port, self.identity, self.root = port, identity, Path(root)
        self.barrier, self.fail, self.calls = barrier, fail, 0

    def step(self, method, params):
        self.calls += 1
        self.barrier.wait(timeout=2)
        if self.fail:
            raise TransportError('one engine failed')
        return {'state': 'SHOP', 'money': 12}

    def close(self):
        pass


class VectorTests(unittest.TestCase):
    def test_duplicate_ports_identities_and_logs_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            a = StubEnv(12400, 'a', Path(root) / 'a')
            for b in (StubEnv(12400, 'b', Path(root) / 'b'),
                      StubEnv(12401, 'a', Path(root) / 'b'),
                      StubEnv(12401, 'b', Path(root) / 'a')):
                with self.subTest(port=b.port, identity=b.identity, root=b.root):
                    with self.assertRaises(ValueError):
                        VectorEnv([a, b])

    @unittest.skipUnless(os.name == 'nt', 'Windows paths are case insensitive')
    def test_windows_case_alias_logs_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            a = StubEnv(12400, 'a', Path(root) / 'Log')
            b = StubEnv(12401, 'b', Path(root) / 'log')
            with self.assertRaises(ValueError):
                VectorEnv([a, b])

    def test_parallel_failure_keeps_successful_peer_and_no_retry(self):
        with tempfile.TemporaryDirectory() as root:
            barrier = threading.Barrier(2)
            a = StubEnv(12400, 'a', Path(root) / 'a', barrier=barrier, fail=True)
            b = StubEnv(12401, 'b', Path(root) / 'b', barrier=barrier)
            with VectorEnv([a, b]) as vector:
                results = vector.step([('play', {}), ('play', {})])
            self.assertFalse(results[0]['ok'])
            self.assertEqual(results[0]['type'], 'TransportError')
            self.assertEqual(results[1], {'ok': True, 'result': {'state': 'SHOP', 'money': 12}})
            self.assertEqual((a.calls, b.calls), (1, 1))


if __name__ == '__main__':
    unittest.main()
