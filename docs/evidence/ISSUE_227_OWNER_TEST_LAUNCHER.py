"""Launch an immutable K2 Candidate via a disposable synthetic native UI copy.

No protected archive execution; no real projects or Product Owner decisions.
Closing the app lets the existing ownership supervisor remove only its copy.
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
sys.path.insert(0,str(TOOLS/'scripts'))
from candidate_archive import verify_archive
from archive_execution_guard import require_execution_path
import k2_qa_fixture as fixture
import temp_workspace_lifecycle as lifecycle

RECORD = Path.home()/'Library/Application Support/Integra/Retention Exceptions/issue-227-e6cd761-one-use'
EXPECTED = {k:v for k,v in json.loads((RECORD/'incoming-identity.json').read_bytes()).items()
            if k in {'candidate_id','bundle_digest','manifest_digest'}}

def child():
    workspace=Path(os.environ['INTEGRA_OWNED_WORKSPACE'])
    os.close(fixture.workspace_fd(workspace))
    archive=Path.home()/'Library/Application Support/Integra/Build Archive'/EXPECTED['candidate_id']/EXPECTED['bundle_digest']
    before=verify_archive(archive,EXPECTED)
    app=workspace/'execution/Integra.app'
    app.parent.mkdir(mode=0o700)
    shutil.copytree(archive/'Integra.app',app,symlinks=True)
    require_execution_path(app)
    manifest=(app/'Contents/Resources/candidate-manifest.json').read_bytes()
    assert hashlib.sha256(manifest).hexdigest()==EXPECTED['manifest_digest']
    fixture.prepare(workspace)
    env={k:v for k,v in os.environ.items() if not k.startswith('INTEGRA_') and k!='PYTHONPATH'}
    env.update(INTEGRA_APP_DATA_ROOT=str(workspace),INTEGRA_OWNED_WORKSPACE=str(workspace),PYTHONDONTWRITEBYTECODE='1')
    # The required packaged self-test precedes native UI/fixture execution.
    # Keep its actual stdout/stderr/exit evidence; never override a failure.
    self_test=subprocess.run([str(app/'Contents/MacOS/Integra'),'--self-test'],
        capture_output=True,text=True,env=env,timeout=240)
    print('OWNER_TEST_SELF_TEST '+json.dumps(dict(exit_status=self_test.returncode,
        stdout=self_test.stdout,stderr=self_test.stderr)),file=sys.stderr,flush=True)
    assert self_test.returncode==0 and 'INTEGRA_MACOS_SELF_TEST: PASS' in self_test.stdout
    def bridge(op,request):
        reply=subprocess.run(['/usr/bin/python3','-B',str(app/'Contents/Resources/bridge.py'),op],
            input=json.dumps(request,ensure_ascii=False),capture_output=True,text=True,env=env,timeout=240)
        print('OWNER_TEST_BRIDGE '+json.dumps(dict(operation=op,exit_status=reply.returncode,
            stdout=reply.stdout,stderr=reply.stderr),ensure_ascii=False),file=sys.stderr,flush=True)
        assert reply.returncode==0
        value=json.loads(reply.stdout)
        assert value['ok']
        return value['result']
    coverage=fixture.exercise(bridge)
    assert coverage['reviewed_units']>=2 and coverage['relations']==1 and not coverage['k2_applied']
    opened=bridge('knowledge-k2-open',fixture.IDENTITY)
    assert opened['revision_sha256'] is None
    print(json.dumps(dict(status='NATIVE_OWNER_TEST_LAUNCH',app=str(app),workspace=str(workspace),
        **EXPECTED,fixture=fixture.IDENTITY,coverage=coverage),sort_keys=True),flush=True)
    code=subprocess.run([str(app/'Contents/MacOS/Integra')],env=env).returncode
    assert code==0
    final=bridge('knowledge-k2-open',fixture.IDENTITY)
    assert manifest==(app/'Contents/Resources/candidate-manifest.json').read_bytes()
    assert verify_archive(archive,EXPECTED)==before
    print(json.dumps(dict(status='NATIVE_TEST_CLOSED',revision_sha256=final['revision_sha256'],
        view_status=final['status'],candidate_unchanged=True,semantic_product_acceptance=False),sort_keys=True),flush=True)

def main():
    assert not sys.flags.optimize
    parser=argparse.ArgumentParser()
    parser.add_argument('--child',action='store_true')
    args=parser.parse_args()
    if args.child:
        child()
    else:
        ns=argparse.Namespace(base='/private/tmp',purpose='issue236-k2-fixture',
            expected_bytes=2684354560,reserve_bytes=15*1024**3,timeout_seconds=3600,
            argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--child'])
        raise SystemExit(lifecycle.run_owned(ns))

if __name__=='__main__': main()
