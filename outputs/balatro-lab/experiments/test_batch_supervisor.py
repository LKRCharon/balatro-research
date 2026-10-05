import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import supervise_train as s

class SupervisorTests(unittest.TestCase):
    def exercise(self,partition,status):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        db=Path(folder.name)/'registry.sqlite'
        with sqlite3.connect(db) as con:
            con.executescript('CREATE TABLE campaigns(id TEXT,partition TEXT);CREATE TABLE jobs(campaign_id TEXT,status TEXT);')
            con.execute('INSERT INTO campaigns VALUES(?,?)',('c',partition));con.execute('INSERT INTO jobs VALUES(?,?)',('c',status))
        return db

    def test_heldout_never_launched(self):
        for role in ('validation','test'):
            with self.subTest(role=role),patch.object(s.p,'DEFAULT_DB',self.exercise(role,'planned')),patch.object(s.cli,'write'),patch.object(s.subprocess,'run') as proc,patch.object(s.cli,'call') as rpc:
                with self.assertRaisesRegex(ValueError,'Only training'):s.run('c')
                proc.assert_not_called();rpc.assert_not_called()

    def test_unresolved_stops_without_reset(self):
        for state in ('running','error'):
            with self.subTest(state=state),patch.object(s.p,'DEFAULT_DB',self.exercise('train',state)),patch.object(s.cli,'write'),patch.object(s.subprocess,'run') as proc,patch.object(s.cli,'call') as rpc:
                with self.assertRaisesRegex(RuntimeError,'no automatic retry'):s.run('c')
                proc.assert_not_called();rpc.assert_not_called()

    def test_finished_checks_environment_then_stops(self):
        with patch.object(s.p,'DEFAULT_DB',self.exercise('train','loss')),patch.object(s.cli,'write') as write,patch.object(s.subprocess,'run',return_value=Mock(returncode=0)) as proc,patch.object(s.cli,'call') as rpc:
            s.run('c');rpc.assert_called_once_with('lab_stop')
            self.assertEqual(proc.call_count,3);self.assertEqual(write.call_args.args[1]['state'],'complete')

if __name__=='__main__':unittest.main()
