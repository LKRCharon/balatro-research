import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_seeds

class AttemptTests(unittest.TestCase):
    def test_previous_result_never_overwritten_or_restarted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);episode=root/'episode';episode.mkdir();result=episode/'result.json';result.write_text('original evidence')
            with patch.object(run_seeds.sqlite3,'connect') as db,patch.object(run_seeds,'Environment') as env:
                with self.assertRaises(FileExistsError):run_seeds.episode(({'root':d},17,32))
                db.assert_not_called();env.assert_not_called()
            self.assertEqual(result.read_text(),'original evidence')

if __name__=='__main__':unittest.main()
