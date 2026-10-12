"""Native test admission and immutable archive import checks with tiny fixtures."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_candidate_archive as fixtures
from integra_core.candidate_identity import tree_sha256
from scripts import build_macos_candidate as builder, candidate_archive as archive


class NativeTestAdmissionTests(unittest.TestCase):
    def test_owned_candidate_build_resolves_ignored_pinned_runtime_from_registered_worktree(self):
        """Disposable workspaces must not lose checked runtime build inputs."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, primary = root / "source", root / "primary"
            source.mkdir(); primary.mkdir()
            for relative in (
                ".runtime-components/seminartext-pinned",
                ".runtime-components/videotext-pinned",
                ".runtime-components/booktext-pinned",
                ".runtime-components/review-wheels",
                ".runtime-word-alignment/lib/python3.13/site-packages",
            ):
                (primary / relative).mkdir(parents=True)
            listing = SimpleNamespace(stdout=f"worktree {source}\nworktree {primary}\n")
            def git(command, **_kwargs):
                if "worktree" in command:
                    return listing
                return SimpleNamespace(stdout=builder.PINNED_COMPONENT_COMMITS[
                    "INTEGRA_SEMINARTEXT_BUILD_CHECKOUT"
                    if "seminartext" in command[2]
                    else "INTEGRA_VIDEOTEXT_BUILD_CHECKOUT"
                    if "videotext" in command[2]
                    else "INTEGRA_BOOKTEXT_BUILD_CHECKOUT"
                ])
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith("INTEGRA_")}
            with patch.object(builder, "ROOT", source), \
                    patch.object(builder.subprocess, "run", side_effect=git), \
                    patch.dict(os.environ, environment, clear=True):
                builder._bind_pinned_runtime_environment()
                self.assertEqual(os.environ["INTEGRA_SEMINARTEXT_BUILD_CHECKOUT"],
                                 str((primary / ".runtime-components/seminartext-pinned").resolve()))
                self.assertEqual(os.environ["INTEGRA_REVIEW_WHEELS"],
                                 str((primary / ".runtime-components/review-wheels").resolve()))

    def test_packaging_child_requires_shared_admission_and_fresh_output(self):
        active = []
        @contextmanager
        def reservation(root, expected, *, archive_copy):
            self.assertFalse(archive_copy); active.append(True)
            try:
                yield
            finally:
                active.pop()
        def launch(command, **kwargs):
            self.assertTrue(active)
            self.assertEqual(command[-1], str(Path(directory).resolve() / 'candidate'))
            self.assertTrue(command[0].endswith('/package_ready_app.sh'))
            self.assertEqual(kwargs['env']['PYTHONDONTWRITEBYTECODE'], '1')
            return SimpleNamespace(stdout=str(Path(directory).resolve() / 'candidate/Integra.app')+'\n')
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(builder.candidate_retention, 'reserved_build', reservation), \
                patch.dict(os.environ, INTEGRA_OWNED_WORKSPACE=directory), \
                patch.object(builder.subprocess, 'run', side_effect=launch):
            self.assertEqual(builder._build_inside_workspace(None, package_tests=True), 0)

    def test_native_tests_execute_only_with_live_reservation_and_no_bytecode(self):
        active = []

        @contextmanager
        def reservation(root, expected, *, archive_copy):
            self.assertFalse(archive_copy)
            self.assertEqual(expected, builder.DEFAULT_EXPECTED_BYTES)
            active.append(True)
            try:
                yield
            finally:
                active.pop()

        def launch(command, **kwargs):
            self.assertTrue(active)
            self.assertEqual(command[-1], '--owned-workspace')
            self.assertEqual(kwargs['env']['PYTHONDONTWRITEBYTECODE'], '1')
            return SimpleNamespace(returncode=0)

        with patch.object(builder.candidate_retention, 'reserved_build', reservation), \
                patch.object(builder.subprocess, 'run', side_effect=launch):
            self.assertEqual(builder._build_inside_workspace(None, native_tests=True), 0)
        self.assertFalse(active)

    def test_failed_admission_never_launches_native_tests(self):
        with patch.object(builder.candidate_retention, 'reserved_build', side_effect=ValueError('cap exceeded')), \
                patch.object(builder.subprocess, 'run') as launch:
            with self.assertRaisesRegex(ValueError, 'cap exceeded'):
                builder._build_inside_workspace(None, native_tests=True)
        launch.assert_not_called()


class ArchivedPythonImportTests(unittest.TestCase):
    def setUp(self):
        if self._testMethodName == 'test_real_output_guard_accepts_fresh_descendant_and_rejects_workspace_root':
            from test_retention_repair_cycle import RealRetentionFixture
            self.retention_fixture = RealRetentionFixture(self)
            for label in ('recovery', 'current'):
                self.retention_fixture.record(self.retention_fixture.bootstrap_archive(label))
            self.retention_fixture.publish_state()
            self.retention_fixture.refresh()
            self.root = self.retention_fixture.root
            self.destination = self.retention_fixture.archive_root
        else:
            fixtures.CandidateArchiveTests.setUp(self)
    _manifest = fixtures.CandidateArchiveTests._manifest
    _create = fixtures.CandidateArchiveTests._create
    _package = fixtures.CandidateArchiveTests._package
    _expected_path = fixtures.CandidateArchiveTests._expected_path

    def test_real_output_guard_accepts_fresh_descendant_and_rejects_workspace_root(self):
        from scripts import temp_workspace_lifecycle as lifecycle, candidate_retention as retention
        workspace, _ = lifecycle.create_workspace(purpose='admission-fixture', base=self.root,
                                                   expected_bytes=1, reserve_bytes=0)
        try:
            with patch.dict(os.environ, INTEGRA_OWNED_WORKSPACE=str(workspace)):
                with retention.reserved_build(self.destination, 1, archive_copy=False):
                    retention.require_build_lease(self.destination, output=workspace / 'candidate')
                    with self.assertRaisesRegex(ValueError, 'reserved owned workspace'):
                        retention.require_build_lease(self.destination, output=workspace)
        finally:
            lifecycle.cleanup_workspace(workspace, reason='TEST_COMPLETED', allow_live_owner=True)

    def test_import_cache_does_not_change_identity_but_invalidates_archive_inventory(self):
        resources = self.app / 'Contents/Resources'
        (resources / 'retention_cache_probe.py').write_text('VALUE = 205\n')
        self._manifest()
        package = self._package()
        app = package / archive.APP
        before = tree_sha256(app, exclude={archive.EMBEDDED})
        environment = dict(os.environ, PYTHONPATH=str(app / 'Contents/Resources'))
        environment.pop('PYTHONDONTWRITEBYTECODE', None)
        environment.pop('PYTHONPYCACHEPREFIX', None)
        command = [sys.executable, '-c', 'import retention_cache_probe; assert retention_cache_probe.VALUE == 205']
        subprocess.run([command[0], '-B', *command[1:]], env=environment, check=True, timeout=15)
        self.assertEqual(archive.verify_archive(package)['status'], 'COMPLETE')
        subprocess.run(command, env=environment, check=True, timeout=15)
        self.assertTrue(list((app / 'Contents/Resources/__pycache__').glob('retention_cache_probe*.pyc')))
        self.assertEqual(tree_sha256(app, exclude={archive.EMBEDDED}), before)
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            archive.verify_archive(package)
