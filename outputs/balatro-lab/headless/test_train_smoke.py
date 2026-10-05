import sqlite3
import tempfile
import unittest
from pathlib import Path

from train_smoke import training_seed


class TrainingBoundaryTests(unittest.TestCase):
    def test_rejects_reserved_or_unknown_seed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'registry.sqlite'
            db = sqlite3.connect(path)
            with db:
                db.execute('CREATE TABLE seeds(id INTEGER,seed TEXT,commitment TEXT,partition TEXT)')
                db.executemany('INSERT INTO seeds VALUES(?,?,?,?)', [
                    (1, 'TRAIN', 'a', 'train'), (2, 'VAL', 'b', 'validation'), (3, 'TEST', 'c', 'test')])
            db.close()
            self.assertEqual(training_seed(path, 1), ('TRAIN', 'a'))
            for ident in (2, 3, 999):
                with self.subTest(seed_id=ident), self.assertRaises(ValueError):
                    training_seed(path, ident)


if __name__ == '__main__':
    unittest.main()
