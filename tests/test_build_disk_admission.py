import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_disk_admission as admission


class DiskAdmissionTests(unittest.TestCase):
    def test_ledger_path_is_portable_and_independent_of_child_tmpdir(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(admission.sys, 'platform', 'linux'), patch.dict(
                    admission.os.environ, {'TMPDIR': directory}):
                _, lock, ledger = admission._paths(directory)
            self.assertEqual(lock.parent, Path('/tmp'))
            self.assertEqual(ledger.parent, Path('/tmp'))
            with patch.object(admission.sys, 'platform', 'darwin'):
                _, lock, _ = admission._paths(directory)
            self.assertEqual(lock.parent, Path('/private/tmp'))

    def test_same_volume_different_roots_share_atomic_reservations(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            first, second = base / 'first', base / 'second'
            first.mkdir()
            second.mkdir()
            # Isolate the ledger, while retaining production device selection.
            original = admission._paths
            def paths(target):
                anchor, lock, ledger = original(target)
                return anchor, base / lock.name, base / ledger.name
            with patch.object(admission, '_paths', side_effect=paths), patch.object(
                    admission.shutil, 'disk_usage', return_value=SimpleNamespace(free=100)):
                identity, _, _ = admission.reserve(first, 60, 10)
                try:
                    with self.assertRaisesRegex(ValueError, 'live reservations'):
                        admission.reserve(second, 40, 10)
                    with self.assertRaisesRegex(ValueError, 'identity already exists'):
                        admission.reserve(second, 0, 0, reservation_id=identity)
                finally:
                    admission.release(first, identity)
                other, _, live = admission.reserve(second, 80, 10)
                self.assertEqual(live, 0)
                admission.release(second, other)

    def test_dead_owner_workspace_remains_reserved_until_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(admission._live({'pid': 99999999, 'start_token': 'gone',
                                            'workspace': directory, 'process_group': None}))
        self.assertFalse(admission._live({'pid': 99999999, 'start_token': 'gone',
                                         'workspace': directory, 'process_group': None}))
