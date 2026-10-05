import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import isolation as iso


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'source'
        for name in ('windows.just', 'justfile', 'scripts/run_agent.py',
                     'mods/lab_cli/main.lua', 'game/version.jkr',
                     'game/main.lua', 'vendor/runtime.dll', 'dist/private.save',
                     'mods/__pycache__/junk.pyc'):
            p = self.source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('original', encoding='utf-8')

    def stage(self, name='one', port=12461):
        return iso.stage(self.source, self.base / 'instances', name, port)

    def test_two_instances_no_shared_mutable_files_or_saves(self):
        a, b = self.stage(), self.stage('two', 12462)
        self.assertNotEqual(a['identity'], b['identity'])
        ap = Path(a['checkout']) / 'game/main.lua'
        ap.write_text('changed')
        self.assertEqual((Path(b['checkout']) / 'game/main.lua').read_text(), 'original')
        self.assertEqual((self.source / 'game/main.lua').read_text(), 'original')
        self.assertFalse((Path(a['checkout']) / 'dist').exists())
        self.assertFalse((Path(a['checkout']) / 'mods/__pycache__').exists())
        self.assertEqual(iso.load(Path(a['root']) / 'instance.json')['identity'], a['identity'])

    def test_refuses_live_port_existing_instance_and_unsafe_path(self):
        with self.assertRaises(ValueError): self.stage(port=12346)
        with self.assertRaises(ValueError): self.stage(name='../escape')
        with self.assertRaises(ValueError): iso.stage(self.source, self.source / 'child', 'one', 12461)
        self.stage()
        with self.assertRaises(ValueError): self.stage('another', 12461)
        with self.assertRaises(FileExistsError): self.stage('one', 12462)

    def test_environment_clears_inherited_replay_and_audio(self):
        m = self.stage()
        env = iso.environment(m, {'BALATROBOT_REPLAY': 'evil', 'BALATROBOT_AUDIO': '1',
                                 'BALATROBOT_HOST': '0.0.0.0', 'PATH': 'untouched'})
        self.assertNotIn('BALATROBOT_REPLAY', env)
        self.assertNotIn('BALATROBOT_HOST', env)
        self.assertEqual(env['BALATROBOT_AUDIO'], '0')
        self.assertEqual(env['BALATRO_SAVE_IDENTITY'], m['identity'])
        self.assertEqual(env['PATH'], 'untouched')

    def test_wrong_owner_never_receives_stop(self):
        m = self.stage()
        with patch.object(iso, 'rpc', return_value={'identity': 'Balatro'}) as call:
            with self.assertRaises(RuntimeError): iso.stop(m)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[1], 'lab_info')

    def test_verified_stop_requires_private_muted_save(self):
        m = self.stage()
        info = {'identity': m['identity'], 'headless': True, 'audio': False,
                'master_volume': 0, 'graphics_active': False, 'desktop': 'BalatroLab-42',
                'save_directory': 'C:/private/' + m['identity']}
        with patch.object(iso, 'rpc', side_effect=[info, {'stopping': True}]) as call:
            self.assertTrue(iso.stop(m)['stopping'])
            self.assertEqual(call.call_args.args[1], 'lab_stop')
        info['master_volume'] = 1
        with patch.object(iso, 'rpc', return_value=info) as call:
            with self.assertRaises(RuntimeError): iso.stop(m)
            self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
