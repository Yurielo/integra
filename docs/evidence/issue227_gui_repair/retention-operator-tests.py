"""Isolated negative tests for the exact GUI recovery operator; no real I/O."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('gui_operator', '/private/tmp/integra-227-gui-build-transaction.py')
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)


class OperatorTests(unittest.TestCase):
    def original(self):
        return {f'package-{n}': {'inventory_sha256': str(n), 'inode': n} for n in range(9)}

    def audit(self):
        return {'full_copies': 9, 'archive_bytes': op.CAP-op.EXPECTED,
                'free_bytes': op.FLOOR+3*op.EXPECTED}

    def test_exact_capacity_boundary(self):
        op.capacity(self.audit(), op.EXPECTED)

    def test_capacity_rejects_wrong_count(self):
        for count in (8, 10):
            with self.subTest(count=count), self.assertRaises(ValueError):
                op.capacity(dict(self.audit(), full_copies=count), op.EXPECTED)

    def test_capacity_rejects_byte_overflow(self):
        with self.assertRaises(ValueError):
            op.capacity(dict(self.audit(), archive_bytes=op.CAP-op.EXPECTED+1), op.EXPECTED)

    def test_capacity_rejects_reserve_deficit(self):
        with self.assertRaises(ValueError):
            op.capacity(dict(self.audit(), free_bytes=op.FLOOR+3*op.EXPECTED-1), op.EXPECTED)

    def test_capacity_rejects_invalid_estimates(self):
        for estimate in (True, 0, -1, op.EXPECTED+1):
            with self.subTest(estimate=estimate), self.assertRaises(ValueError):
                op.capacity(self.audit(), estimate)

    def test_preserve_accepts_only_exact_one_incoming(self):
        before = self.original()
        op.preserve(before, before)
        op.preserve(before, dict(before, incoming={'inventory_sha256': 'new'}), 'incoming')
        with self.assertRaises(ValueError):
            op.preserve(before, dict(before, incoming={}))
        with self.assertRaises(ValueError):
            op.preserve(before, dict(before, incoming={}, other={}), 'incoming')

    def test_preserve_rejects_changed_or_missing_old_package(self):
        before = self.original()
        altered = dict(before, **{'package-3': {'inventory_sha256': 'wrong', 'inode': 3}})
        with self.assertRaises(ValueError):
            op.preserve(before, altered)
        missing = dict(before)
        del missing['package-3']
        with self.assertRaises(ValueError):
            op.preserve(before, missing)

    def test_scoped_restores_defaults_even_on_exception(self):
        old = op.gate.require_archive_publication, op.gate.require_deletion, op.retention.maintenance
        with self.assertRaisesRegex(RuntimeError, 'abort'):
            with op.scoped({}):
                self.assertEqual((op.retention.MAX_COPIES, op.retention.MAX_BYTES), (10, op.CAP))
                with self.assertRaises(ValueError):
                    op.gate.require_deletion(Path('/unused'))
                with self.assertRaises(ValueError):
                    op.retention.maintenance(Path('/unused'), reason='unused')
                raise RuntimeError('abort')
        self.assertEqual((op.retention.MAX_COPIES, op.retention.MAX_BYTES), (8, 20*1024**3))
        self.assertEqual(old, (op.gate.require_archive_publication, op.gate.require_deletion, op.retention.maintenance))

    def test_publication_requires_real_protection_and_single_use(self):
        authority = {'original_packages': self.original()}
        catalog = {'leases': {'token': {'pid': 1}}}
        def read(name):
            if name == 'authorization.json':
                return authority
            return {'source': op.SOURCE_SHA, 'candidate_id': 'candidate-test', 'bundle_digest': 'bundle-test'}
        with patch.object(op, 'read', side_effect=read), \
             patch.object(op.retention, '_safe', side_effect=lambda path: path), \
             patch.object(Path, 'read_bytes', return_value=json.dumps(catalog).encode()), \
             patch.object(Path, 'exists', return_value=False), \
             patch.object(op.retention, '_lease_caller', return_value=True), \
             patch.object(op, 'fingerprints', return_value=self.original()), \
             patch.object(op, 'fresh', return_value=({}, self.audit())) as fresh, \
             patch.dict(op.os.environ, {'INTEGRA_RETENTION_BUILD_LEASE': 'token'}):
            with op.scoped(authority):
                op.gate.require_archive_publication(op.ARCHIVE, op.EXPECTED)
                fresh.assert_called_once_with(authority)
                with self.assertRaises(ValueError):
                    op.gate.require_archive_publication(op.ARCHIVE, op.EXPECTED)

    def test_publication_protection_failure_is_not_dispatched_as_pass(self):
        authority = {'original_packages': self.original()}
        catalog = {'leases': {'token': {'pid': 1}}}
        with patch.object(op, 'read', side_effect=lambda name: authority if name == 'authorization.json' else {'source': op.SOURCE_SHA}), \
             patch.object(op.retention, '_safe', side_effect=lambda path: path), \
             patch.object(Path, 'read_bytes', return_value=json.dumps(catalog).encode()), \
             patch.object(op.retention, '_lease_caller', return_value=True), \
             patch.object(op, 'fingerprints', return_value=self.original()), \
             patch.object(op, 'fresh', side_effect=ValueError('protection rejected')), \
             patch.dict(op.os.environ, {'INTEGRA_RETENTION_BUILD_LEASE': 'token'}):
            with op.scoped(authority), self.assertRaisesRegex(ValueError, 'protection rejected'):
                op.gate.require_archive_publication(op.ARCHIVE, op.EXPECTED)


if __name__ == '__main__':
    unittest.main(verbosity=2)
