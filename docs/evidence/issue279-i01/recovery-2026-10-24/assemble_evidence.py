"""Freeze actual receipts into the evidence overlay; never publishes a proposal."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

OUT = Path(__file__).parent
ROOT = Path('/private/tmp/integra-issue279-k2-evidence')
PREFIX = 'docs/evidence/issue279-i01/recovery-2026-10-24'
DEST = ROOT / PREFIX
SOURCE = {'commit_sha':'6e6978a5f88930158058df8e90dbe4275f11c29a',
          'tree_sha':'d6a4ba71a2939e62bf7d765270b148ea67034dae'}
OLD = 'candidate-v1-19e3438fea443e1d917b6575131fd67b47b5f44f71202a6940f85adda12b3b56'

def read(name): return json.loads((OUT/name).read_bytes())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(name, data): (OUT/name).write_text(json.dumps(data,indent=2,sort_keys=True,ensure_ascii=False)+'\n')

log = (OUT/'full-suite.log').read_text()
for required in ['candidate-manifest.json','candidate-archive-verification.json','catalog-after.json',
                 'catalog-before.json','build-preflight.json','current-unchanged.json','exact-retirement-receipt.json']:
    assert (OUT/required).is_file(), 'actual build/archive result not available: '+required
summary = re.search(r'Ran (\d+) tests in ([\d.]+)s\s+OK \(skipped=(\d+)\)\s*$',log)
assert summary, log[-1000:]
total, elapsed, skipped = int(summary[1]), float(summary[2]), int(summary[3])
fixture = ROOT/'state/proposed_baseline_lite_v1.json'
fixture_raw=(OUT/'regression-accounting-fixture.json').read_bytes()
if fixture.exists(): assert fixture.read_bytes() == fixture_raw
else: assert read('fixture-removed.json')['sha256']==sha(OUT/'regression-accounting-fixture.json')
assert 'PROPOSED baseline fields are invalid' in (OUT/'fixture-strict-governance-rejection.log').read_text()
save('regression-result.json',dict(status='PASS',scope='FULL_SUPPORTED_UNIT_SUITE_WITH_EXACT_ACCOUNTING_FIXTURE',
    tests=total,passed=total-skipped,skipped=skipped,failures=0,errors=0,elapsed_seconds=elapsed,
    checkout_head=read('unit-suite-source.json')['commit_sha'],product_source=SOURCE,
    command='./scripts/run_review_tests.sh',fixture_sha256=sha(OUT/'regression-accounting-fixture.json'),
    fixture_strict_governance='EXPECTED_FAIL_NOT_A_PROPOSAL',final_proposal_validated_by_this_run=False))

manifest=read('candidate-manifest.json'); receipt=read('candidate-archive-verification.json')
assert manifest['identity']['source']['dirty'] is False
assert {k:manifest['identity']['source'][k] for k in SOURCE} == SOURCE
assert receipt['candidate_id']==manifest['candidate_id'] and receipt['bundle_digest']==manifest['bundle']['digest']
assert receipt['manifest_digest']==sha(OUT/'candidate-manifest.json')
gui=json.loads((ROOT/'docs/evidence/issue279-i01/gui-2026-10-24/result.json').read_bytes())
assert gui['status']=='PASS_BOUNDED_NATIVE_K2_GUI_QA'
assert gui['candidate_id']==manifest['candidate_id']
assert gui['bundle_digest']==manifest['bundle']['digest']
assert gui['candidate_manifest_sha256']==receipt['manifest_digest']
assert {k:gui['source'][k] for k in SOURCE}==SOURCE and gui['source']['dirty'] is False
assert gui['bundle_validation_before_after_equal'] is True and gui['current_unchanged'] is True
assert Path(receipt['archive_path']).is_dir()
recovery=read('recovery-receipt.json'); assert recovery['state']=='VERIFIED'
before,after=read('catalog-before.json'),read('catalog-after.json')
new_publication=after['artifacts'][receipt['archive_path']]
assert type(new_publication['publication_sequence']) is int
assert after['publication_sequence_high_watermark']==new_publication['publication_sequence']
exact=read('exact-retirement-receipt.json');retirement=exact['physical_retirement']
assert exact['status']=='PASS' and retirement['candidate_id']==OLD
assert new_publication['publication_sequence'] > exact['publication_sequence']
assert retirement['state']=='RETIRED_NOT_AVAILABLE' and retirement['execution_result']=='PASS'
events=[]
for line in (OUT/'build-archive.log').read_text().splitlines():
    if line.startswith('{'):
        try: item=json.loads(line)
        except ValueError: continue
        if item.get('artifact_type')=='integra.lifecycle_event': events.append(item)
assert len(exact['paths'])==1 and OLD in exact['paths'][0]
assert not Path(exact['paths'][0]).exists()
workspace=next(e['root'] for e in events if e['event']=='WORKSPACE_CREATED' and e.get('purpose')=='issue279-i01-archive')
assert not Path(workspace).exists(), 'build supervisor has not yet cleaned owned workspace'
assert 'I01_ARCHIVE_VERIFIED_CURRENT_UNCHANGED' in (OUT/'build-archive.log').read_text()
packages=[]; seen=set(); allocated=0
for name in after['roots']:
    root=Path(name)
    if not root.exists(): continue
    for directory,dirs,files in os.walk(root):
        if 'Integra.app' in dirs: packages.append(str(Path(directory)))
        for item in [Path(directory),*(Path(directory)/n for n in files)]:
            s=item.lstat(); key=(s.st_dev,s.st_ino)
            if key not in seen: seen.add(key);allocated+=s.st_blocks*512
assert len(set(packages))==8
assert allocated <= 20*1024**3
assert shutil.disk_usage(OUT).free >= 15*1024**3
save('retention-after.json',dict(full_copies=8,allocated_bytes=allocated,
    free_bytes=shutil.disk_usage(OUT).free,packages=sorted(set(packages)),
    caps_unchanged={'max_full_copies':8,'max_attributed_bytes':20*1024**3,'minimum_free_after_reservations':15*1024**3}))
save('rotation-receipt.json',dict(status='PASS',strategy='EXACT_OWNER_AUTHORIZED_WITHDRAWAL_RETIREMENT',
    prior_publication_sequence=exact['publication_sequence'],
    replacement_publication_sequence=new_publication['publication_sequence'],
    publication_sequence_high_watermark=after['publication_sequence_high_watermark'],
    physical_retirement=retirement,paths=exact['paths'],
    full_copies_after_rotation=read('build-preflight.json')['full_copies'],full_copies_after_publication=8))
assert read('build-preflight.json')['full_copies']==7
q=Path(recovery['quarantine_path'])
assert sha(q/'preserved-inventory.json')==recovery['preserved_inventory_sha256']
shutil.copy2(q/'preserved-inventory.json',OUT/'quarantine-preserved-inventory.json')
save('candidate-evidence.json',dict(candidate_id=manifest['candidate_id'],
    manifest_identity_sha256=manifest['identity_sha256'],bundle_digest=manifest['bundle']['digest'],
    product_source=SOURCE,manifest_digest=receipt['manifest_digest'],archive_path=receipt['archive_path'],
    recovery='VERIFIED_OWNER_AUTHORIZED_EXACT_EXCEPTION',rotation='PASS',
    native_gui_evidence='docs/evidence/issue279-i01/gui-2026-10-24/result.json',
    gui_same_candidate_manifest_and_bundle=True,semantic_product_acceptance=False,owner_acceptance=None,
    regression_scope=read('regression-result.json')['scope'],current_unchanged=True))
names=['authorization-body.md','authorization-comment.json','exact_cache_recovery.py','test_exact_cache_recovery.py',
    'independent-helper-review.json','independent-qa.log','recovery-helper-tests.log','recovery-execution.log',
    'recovery-receipt.json','independent-recovery-review.json','quarantine-preserved-inventory.json',
    'build-archive.log','governor-source.json','build-preflight.json','fresh-build.log',
    'candidate-manifest.json','candidate-validation.json','packaged-schema.log','native-self-test.log',
    'packaged-k2.json','packaged-k2.stderr','candidate-archive.json','candidate-archive-verification.json',
    'current-unchanged.json','rotation-receipt.json','retention-after.json','candidate-evidence.json',
    'regression-accounting-fixture.json','fixture-strict-governance-rejection.log','full-suite.log','regression-result.json',
    'fixture-removed.json','run_unit_fixture.py','assemble_evidence.py','declare_proposal.py',
    'delivery-helper-review.json','declaration-dirty-B-rejection.log','unit-suite-source.json','publication-sequence-repair.json',
    'counterfix-focused.log','counterfix-full-suite.log','counterfix-governance.log','counterfix-independent-review.json',
    'counterfix-postmerge-focused.log','counterfix-postmerge-governance.log','counterfix-ci-watch.log',
    'first-post-recovery-build-cap-blocked.log','scan-local-after-recovery.json',
    'scan-inactivity-trace.json','retire_exact.py','exact-retirement-execution.log','exact-retirement-receipt.json','independent-retirement-review.json']
if fixture.exists(): fixture.unlink()
DEST.mkdir(parents=True,exist_ok=False)
for name in names: shutil.copy2(OUT/name,DEST/name)
report=f'''# I01 K2 recovery, archive and proposal evidence — 24 October 2026

Issue #279 / PR #280. This evidence overlay freezes actual recovery, rotation,
fresh application and regression receipts before the proposal-only declaration.
Final declaration validation and full CI are recorded separately at the exact
PR head; this overlay itself does not grant semantic acceptance or promotion.

## Exact Candidate

- Source A: `{SOURCE['commit_sha']}`, tree `{SOURCE['tree_sha']}`.
- Candidate: `{manifest['candidate_id']}`.
- Bundle: `{manifest['bundle']['digest']}`.
- Manifest: `{receipt['manifest_digest']}`.
- Permanent archive: `{receipt['archive_path']}`.

The fresh build reproduces the exact Candidate/bundle/manifest used for the
previous native GUI proof. Fresh bundle validation, the actual packaged schema
round trip, native self-test and isolated packaged K2 bridge probe passed again.
Actual application bytes were copied into the durable archive and independently
rehashed. A manifest alone is not being offered as retention evidence. The owned
execution workspace was cleaned only after archival verification.

## Authorized recovery and governed rotation

The prior unaccepted fixed K2 submission was explicitly superseded through owner
comment6380155631 and canonical PR #289, merge a3fb04e. Its exact lifecycle event
and grant remain unchanged. The first governed build attempt exposed extra cache
entries; the earlier failure and recovery plan remain in `../handoff-2026-10-24/`.

The owner authorized the exact recovery exception in
https://github.com/Yurielo/integra/issues/279#issuecomment-6380883524, plan SHA-256
`d89bed43693b767fc510076ff9a8330a9222c63af960173241137d134fa89b50`.
The reviewed helper passed 18 isolated preservation/failure/rejection tests.
Under the common catalog lock and fresh canonical checks, it preserved the three
exact cache trees, all 45 files / 1,568,777 bytes, in
`{recovery['quarantine_path']}`. Independent QA rehashed every quarantined file.
The quarantine, inventory and durable recovery journal remain retained; their
deletion is not authorized.

Strict verification of the original archive then passed all 29,626 recorded
files / 2,202,189,271 bytes. Original inventory, COMPLETE and manifest records
were not rewritten. Ordinary maintenance still retained it at an activity/unknown
classification; that failed attempt and the differing inactive-probe samples are
preserved here. The accepted canonical exact-withdrawal executor subsequently
rechecked the exact owner grant, integrity, ownership and inactivity under the
shared catalog lock. It retired only `{OLD}` and recorded a durable
`RETIRED_NOT_AVAILABLE` receipt. The old application is physically unavailable;
its exact lifecycle, source, manifest, ownership and verification evidence remain.
This is separate from the retained cache quarantine. This was an exact
owner-authorized withdrawal retirement, not an oldest-first selection claim.
The outgoing publisher sequence was 1. Before replacement publication, the
canonical control-tool repair recorded in `publication-sequence-repair.json`
preserved monotonic ordering through retirement receipts and a durable high
watermark; independent tests reproduce and prevent sequence reuse. Normal maintenance and capacity admission
then ran again for the fresh replacement build.

Capacity moved from eight full copies to seven, then back to eight after the new
publication. Final attributed allocation is {allocated} bytes. Limits remain
8 copies, 20 GiB allocation and a 15-GiB free reserve. No cap, publisher ordering,
ownership or integrity rule was relaxed. APFS exclusive physical reclaim is not
claimed by attributed allocation or the observed free-space change.

## Regression evidence and declaration boundary

The full supported unit suite ran {total} tests in {elapsed} seconds:
{total-skipped} passed, {skipped} skipped, zero failures/errors. It used the exact
temporary accounting fixture retained here, SHA-256
`{sha(OUT/'regression-accounting-fixture.json')}`. The four checkout-accounting
checks received the exact 11-file before/after delta as unit-test input.
Strict governance explicitly rejected that fixture as not a Proposal. It had no
PASS gates, acceptance, status or declaration claim, and was removed before this
evidence commit. Product bytes remain identical to frozen A. The evidence checkout also contains
the canonical publication-sequence repair and its independent regression tests;
the full suite was rerun after those control-tool changes.

The earlier source-A full log with four missing-proposal failures remains
unchanged. Those failures are not relabelled as passing. The actual strict
source A -> evidence B -> proposal-only C declaration must validate separately,
and full CI must run using the real declaration. The proposal will bind all 11
governed paths, no historical test successors, this exact manifest/archive and
candidate evidence, with `owner_acceptance: null`. A later registry-only canonical
binding protects the unchanged Proposal by its ID, file hash and exact tuple.

## Native GUI scope and retained boundaries

The unchanged binary's actual native GUI proof is in `../gui-2026-10-24/`: explicit
ACCEPT/EDIT/REJECT/DEFER, unchecked initial selectors/confirmation, two Concepts,
one Relation, no admitted rejected/deferred Topics, exact edited-label/revision
persistence through quit/relaunch/reopen, and generated-demo player navigation
with matching quote/hash at 0.080–5.728 seconds. Audible playback was not assessed.
These fixture choices are QA evidence, not Product Owner semantic acceptance.

CURRENT remains the accepted K1 baseline and both record hashes remain exact:

- `current_product_baseline_v2.json`:
  `bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2`.
- `current_canonical_baseline_v1.json`:
  `0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840`.

No source-product repository/pin, installed application or original project is
changed. No upstream Process/model rerun, live publication, signing/notarization,
release, semantic owner acceptance or CURRENT promotion is performed. New scope
is this receipt/evidence directory and dated pointers in the three earlier
reports; the one-off recovery helper is evidence, not packaged product code.
The next genuine gate is Product Owner review of the exact K2 Candidate.
'''
(DEST/'README.md').write_text(report)
for relative in ['docs/evidence/issue279-i01/README.md',
                 'docs/evidence/issue279-i01/gui-2026-10-24/README.md',
                 'docs/evidence/issue279-i01/handoff-2026-10-24/README.md']:
    path=ROOT/relative; text=path.read_text();heading,rest=text.split('\n',1)
    link='recovery-2026-10-24/README.md' if path.parent.name=='issue279-i01' else '../recovery-2026-10-24/README.md'
    path.write_text(heading+'\n\n**Latest recovery/archive evidence:** [owner-authorized recovery and actual verified retained replacement]('+link+'). Earlier pending/blocked statements below describe those earlier runs. Final strict proposal/CI checks are recorded separately.\n'+rest)
print(json.dumps(dict(evidence_directory=str(DEST),files=len(names)+1,unit_tests=total,archive=receipt['archive_path'])))
