#!/usr/bin/env python3
"""Keep a published Candidate's source branch reachable without rewriting it.

The local Git hook is a process guard, not lifecycle authority. A new branch
may be used after a governed withdrawal; this guard never releases archives.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def marker(repo):
    path = Path(git(repo, 'rev-parse', '--git-path', 'integra-candidate-source-freeze.json'))
    return path if path.is_absolute() else Path(repo) / path


def check_rebase(repo, target_branch=None):
    path = marker(repo)
    if not path.exists():
        return
    frozen = json.loads(path.read_text())
    branch = (git(repo, 'rev-parse', '--symbolic-full-name', target_branch)
              if target_branch else git(repo, 'symbolic-ref', '--quiet', 'HEAD'))
    if not isinstance(frozen.get('branch'), str):
        raise ValueError('Candidate source freeze metadata is invalid')
    if branch == frozen['branch']:
        raise ValueError('CANDIDATE_SOURCE_FROZEN: rebase would rewrite published Candidate ancestry')


def freeze(repo, manifest):
    repo = Path(repo).resolve()
    source = manifest['identity']['source']
    if (git(repo, 'rev-parse', 'HEAD') != source['commit_sha']
            or git(repo, 'rev-parse', 'HEAD^{tree}') != source['tree_sha']
            or git(repo, 'status', '--porcelain')):
        raise ValueError('Candidate freeze requires its exact clean product HEAD')
    path = marker(repo)
    if path.exists():
        raise ValueError('Candidate source is already frozen; do not replace the freeze')
    hook = Path(git(repo, 'rev-parse', '--git-path', 'hooks/pre-rebase'))
    if not hook.is_absolute():
        hook = repo / hook
    command = ('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' -B '
               + shlex.quote(str(Path(__file__).resolve()))
               + ' check-rebase --repo "$PWD" --target-branch "${2-}"\n')
    if hook.exists() and hook.read_text() != command:
        raise ValueError('Existing pre-rebase hook must be preserved; automatic installation refused')
    hooks_config = subprocess.run(
        ['git', '-C', str(repo), 'config', '--get', 'core.hooksPath'],
        capture_output=True)
    if hooks_config.returncode == 0:
        raise ValueError('Custom hook configuration requires explicit integration')
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(command)
    hook.chmod(0o755)
    with path.open('x') as handle:
        json.dump({'branch': git(repo, 'symbolic-ref', 'HEAD'),
                   'source': source, 'candidate_id': manifest['candidate_id']}, handle, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['freeze', 'check-rebase'])
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--target-branch')
    args = parser.parse_args()
    try:
        if args.operation == 'freeze':
            freeze(args.repo, json.loads(args.manifest.read_text()))
        else:
            check_rebase(args.repo, args.target_branch)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
