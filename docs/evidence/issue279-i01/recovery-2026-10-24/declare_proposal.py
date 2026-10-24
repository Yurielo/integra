"""Prepare the strict A -> evidence B -> declaration C record, without promotion."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/private/tmp/integra-issue279-k2-evidence')
LOCAL = Path(__file__).parent
PREFIX = 'docs/evidence/issue279-i01/recovery-2026-10-24/'
sys.path.insert(0, str(ROOT))
from scripts import proposed_baseline_lite as p

def binding(path):
    return {'path': path, 'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}

assert not subprocess.check_output(['git', '-C', ROOT, 'status', '--porcelain'], text=True), 'B must be clean and committed before declaration'
accounting = json.loads((LOCAL / 'proposal-accounting.json').read_bytes())
manifest = json.loads((ROOT / PREFIX / 'candidate-manifest.json').read_bytes())
assert manifest['identity']['source']['dirty'] is False
assert {k: manifest['identity']['source'][k] for k in ('commit_sha', 'tree_sha')} == accounting['source']
head = p._commit_identity(ROOT, p._git(ROOT, 'rev-parse', 'HEAD'))
overlay_paths = p._changed_paths(ROOT, accounting['source']['commit_sha'], head['commit_sha'])
proposal = {
    'schema_version': '1.0',
    'artifact_type': 'integra.proposed_product_baseline',
    'proposal_id': 'proposal-issue279-i01-k2-e8064cba',
    'status': 'PROPOSED_BASELINE_VALID',
    'base_current_id': accounting['base_current_id'],
    'base_main': accounting['base_main'],
    'proposed_source': accounting['source'],
    'proposed_head': head,
    'intended_scope': {
        'wp': 'Issue #279 I01: packaged Knowledge View schema repair and K2 continuation',
        'journey': 'Source -> Transcript -> Reviewed Evidence -> explicit review -> Canonical Knowledge -> Concepts/Relations -> provenance -> persistence/reopen',
    },
    'candidate': {
        'candidate_id': manifest['candidate_id'],
        'identity_sha256': manifest['identity_sha256'],
        'bundle_digest': manifest['bundle']['digest'],
        'manifest_digest': binding(PREFIX + 'candidate-manifest.json')['sha256'],
    },
    'delta': accounting['delta'],
    'historical_test_successors': accounting['historical_test_successors'],
    'gates': [
        {'name': name, 'result': 'PASS', 'evidence_ref': ref}
        for name, ref in [
            ('fresh-exact-candidate-validation', PREFIX + 'candidate-validation.json'),
            ('packaged-knowledge-view-schema', PREFIX + 'packaged-schema.log'),
            ('native-self-test', PREFIX + 'native-self-test.log'),
            ('packaged-k2-bridge', PREFIX + 'packaged-k2.json'),
            ('native-gui-review-reopen-navigation', 'docs/evidence/issue279-i01/gui-2026-10-24/result.json'),
            ('independent-native-gui-qa', 'docs/evidence/issue279-i01/gui-2026-10-24/independent-review.json'),
            ('independent-code-governance-review', 'docs/evidence/issue279-i01/independent-review.json'),
            ('verified-permanent-archive', PREFIX + 'candidate-archive-verification.json'),
            ('authorized-exact-withdrawal-retirement', PREFIX + 'rotation-receipt.json'),
            ('supported-unit-regression-with-exact-accounting-fixture', PREFIX + 'regression-result.json'),
        ]
    ],
    'evidence': {
        'candidate_manifest': binding(PREFIX + 'candidate-manifest.json'),
        'candidate_evidence': binding(PREFIX + 'candidate-evidence.json'),
        'report': binding(PREFIX + 'README.md'),
    },
    'owner_acceptance': None,
    'allowed_overlay_paths': sorted(overlay_paths),
}
refs = {gate['evidence_ref'] for gate in proposal['gates']} | {value['path'] for value in proposal['evidence'].values()}
for ref in refs:
    assert p._regular_blob_hash(ROOT, head['commit_sha'], ref) == binding(ref)['sha256'], 'evidence is not frozen in B: ' + ref
current = json.loads((ROOT / 'state/current_product_baseline_v2.json').read_bytes())
regression = json.loads((ROOT / PREFIX / 'regression-result.json').read_bytes())
assert regression['status'] == 'PASS' and regression['failures'] == 0 and regression['errors'] == 0
errors = p.validate_proposal(proposal, current, ROOT)
assert not errors, errors
path = ROOT / 'state/proposed_baseline_lite_v1.json'
assert not path.exists(), 'do not overwrite an existing declaration'
path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
print(json.dumps({'path': str(path), 'structural_errors': errors, 'evidence_head': head, 'overlay_paths': len(overlay_paths),
                  'git_lineage_validated': False}))
