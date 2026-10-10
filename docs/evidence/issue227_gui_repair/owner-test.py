"""Exact Issue227 GUI repair Candidate on a disposable synthetic QA notebook.

Uses the one-use transaction receipt, never the protected app in-place.
No Owner acceptance, CURRENT promotion, real projects, or new Candidate build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS = Path('/private/tmp/integra-issue-228-retention-repair')
sys.path.insert(0, str(TOOLS / 'scripts'))
from candidate_archive import verify_archive
from archive_execution_guard import require_execution_path
import k2_qa_fixture as fixture
import temp_workspace_lifecycle as lifecycle

RECORD = Path.home() / 'Library/Application Support/Integra/Retention Exceptions/issue-227-e504491-gui-one-use'

def expected():
    receipt = json.loads((RECORD / 'incoming.json').read_bytes())
    assert receipt['source'] == 'e504491fe5f09dae94ecdf9ebe179a08d945e8d8'
    value = {key: receipt[key] for key in ('candidate_id', 'bundle_digest', 'manifest_digest')}
    assert len(value) == 3
    return value

def child(require_applied=False):
    identity = expected()
    workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE'])
    os.close(fixture.workspace_fd(workspace))
    archive = Path.home() / 'Library/Application Support/Integra/Build Archive' / identity['candidate_id'] / identity['bundle_digest']
    before = verify_archive(archive, identity)
    app = workspace / 'execution/Integra.app'
    app.parent.mkdir(mode=0o700)
    shutil.copytree(archive / 'Integra.app', app, symlinks=True)
    require_execution_path(app)
    manifest = (app / 'Contents/Resources/candidate-manifest.json').read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == identity['manifest_digest']
    env = {key: value for key, value in os.environ.items() if not key.startswith('INTEGRA_') and key != 'PYTHONPATH'}
    env.update(INTEGRA_APP_DATA_ROOT=str(workspace), INTEGRA_OWNED_WORKSPACE=str(workspace), PYTHONDONTWRITEBYTECODE='1')
    validation = subprocess.run([sys.executable, '-B', str(TOOLS / 'scripts/candidate_manifest.py'), 'validate', str(app)], capture_output=True, text=True, timeout=900)
    print('GUI_MANIFEST_VALIDATION ' + json.dumps(dict(exit_status=validation.returncode, stdout=validation.stdout, stderr=validation.stderr)), file=sys.stderr, flush=True)
    assert validation.returncode == 0
    validated = json.loads(validation.stdout)
    assert validated['candidate_id'] == identity['candidate_id'] and validated['bundle']['digest'] == identity['bundle_digest']
    test = subprocess.run([str(app / 'Contents/MacOS/Integra'), '--self-test'], capture_output=True, text=True, env=env, timeout=240)
    print('GUI_SELF_TEST ' + json.dumps(dict(exit_status=test.returncode, stdout=test.stdout, stderr=test.stderr)), file=sys.stderr, flush=True)
    assert test.returncode == 0 and 'INTEGRA_MACOS_SELF_TEST: PASS' in test.stdout
    fixture.prepare(workspace)
    def bridge(op, request):
        reply = subprocess.run(['/usr/bin/python3', '-B', str(app / 'Contents/Resources/bridge.py'), op], input=json.dumps(request, ensure_ascii=False), capture_output=True, text=True, env=env, timeout=240)
        print('GUI_BRIDGE_DIAGNOSTIC ' + json.dumps(dict(operation=op, request=request, exit_status=reply.returncode, stdout=reply.stdout, stderr=reply.stderr), ensure_ascii=False), file=sys.stderr, flush=True)
        assert reply.returncode == 0
        value = json.loads(reply.stdout)
        assert value['ok']
        return value['result']
    coverage = fixture.exercise(bridge)
    assert coverage['reviewed_units'] >= 2 and coverage['relations'] == 1 and not coverage['k2_applied']
    assert bridge('knowledge-k2-open', fixture.IDENTITY)['revision_sha256'] is None
    print(json.dumps(dict(status='NATIVE_GUI_READY', app=str(app), workspace=str(workspace), **identity, coverage=coverage), sort_keys=True), flush=True)
    print('Откройте «База знаний» → тестовый конспект → «Структурировать знания / открыть принятую версию» → «Проверить смысловые предложения».', flush=True)
    code = subprocess.run([str(app / 'Contents/MacOS/Integra')], env=env).returncode
    assert code == 0
    result = bridge('knowledge-k2-open', fixture.IDENTITY)
    if require_applied:
        records = (result.get('knowledge_view') or {}).get('records', {})
        assert result['revision_sha256'] and result['package_applied']
        assert len(records.get('concepts', [])) == 2 and len(records.get('relations', [])) == 1
        print(json.dumps(dict(status='NATIVE_GUI_REOPEN_READY', app=str(app), revision_sha256=result['revision_sha256'])), flush=True)
        assert subprocess.run([str(app / 'Contents/MacOS/Integra')], env=env).returncode == 0
        assert bridge('knowledge-k2-open', fixture.IDENTITY) == result
    assert manifest == (app / 'Contents/Resources/candidate-manifest.json').read_bytes()
    assert verify_archive(archive, identity) == before
    records = (result.get('knowledge_view') or {}).get('records', {})
    print(json.dumps(dict(status='NATIVE_GUI_CLOSED', revision_sha256=result['revision_sha256'], view_status=result['status'], concepts=len(records.get('concepts', [])), relations=len(records.get('relations', [])), candidate_unchanged=True, semantic_product_acceptance=False), sort_keys=True), flush=True)

def main():
    assert not sys.flags.optimize
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--require-applied', action='store_true')
    args = parser.parse_args()
    if args.child:
        child(args.require_applied)
    else:
        expected()
        argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--child']
        if args.require_applied:
            argv.append('--require-applied')
        ns = argparse.Namespace(base='/private/tmp', purpose=fixture.PURPOSE, expected_bytes=2684354560, reserve_bytes=15*1024**3, timeout_seconds=7200, argv=argv)
        raise SystemExit(lifecycle.run_owned(ns))

if __name__ == '__main__':
    main()
