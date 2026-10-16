import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts import candidate_source_guard as guard


class CandidateSourceGuardTests(unittest.TestCase):
    def test_real_git_rebase_cannot_rewrite_frozen_candidate_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'QA')
            git('config', 'user.email', 'qa@example.invalid')
            (repo / 'file').write_text('base')
            git('add', 'file'); git('commit', '-qm', 'base')
            git('branch', 'upstream')
            git('checkout', '-qb', 'candidate')
            (repo / 'new').write_text('product')
            git('add', 'new'); git('commit', '-qm', 'product')
            head = git('rev-parse', 'HEAD')
            manifest = {'candidate_id': 'candidate-v1-' + 'a' * 64,
                        'identity': {'source': {'commit_sha': head,
                                               'tree_sha': git('rev-parse', 'HEAD^{tree}')}}}
            guard.freeze(repo, manifest)
            git('checkout', '-q', 'upstream')
            (repo / 'upstream').write_text('advance')
            git('add', 'upstream'); git('commit', '-qm', 'advance')
            guard.check_rebase(repo)  # Other branches are unaffected.
            git('checkout', '-q', 'candidate')
            result = subprocess.run(['git', '-C', str(repo), 'rebase', 'upstream'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('CANDIDATE_SOURCE_FROZEN', result.stderr)
            self.assertEqual(git('rev-parse', 'HEAD'), head)
            self.assertEqual(json.loads(guard.marker(repo).read_text())['source'],
                             manifest['identity']['source'])

    def test_existing_hook_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            path = repo / '.git/hooks/pre-rebase'
            path.write_text('existing hook')
            # Failure at source validation or hook integration preserves it.
            with self.assertRaises((KeyError, subprocess.CalledProcessError, ValueError)):
                guard.freeze(repo, {'identity': {'source': {'commit_sha': '0'*40, 'tree_sha':'0'*40}}})
            self.assertEqual(path.read_text(), 'existing hook')
