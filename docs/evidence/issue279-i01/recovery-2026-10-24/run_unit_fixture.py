"""Run checkout accounting tests with an explicit non-Proposal fixture."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).parent
ROOT = Path('/private/tmp/integra-issue279-k2-evidence')
FIXTURE = ROOT / 'state/proposed_baseline_lite_v1.json'
raw = (OUT / 'regression-accounting-fixture.json').read_bytes()
fixture = json.loads(raw)
assert fixture['artifact_type'] == 'integra.regression_accounting_fixture'
assert fixture['purpose'] == 'UNIT_TEST_INPUT_ONLY_NOT_A_PROPOSAL_OR_ACCEPTANCE'
assert len(fixture['delta']) == 11 and fixture['historical_test_successors'] == []
assert not FIXTURE.exists()
assert not subprocess.check_output(['git', '-C', ROOT, 'status', '--porcelain'], text=True)
source = {
    'commit_sha': subprocess.check_output(['git', '-C', ROOT, 'rev-parse', 'HEAD'], text=True).strip(),
    'tree_sha': subprocess.check_output(['git', '-C', ROOT, 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
    'temporary_fixture_is_not_a_proposal': True,
}
(OUT / 'unit-suite-source.json').write_text(json.dumps(source, indent=2, sort_keys=True) + '\n')
FIXTURE.write_bytes(raw)
try:
    rejected = subprocess.run([sys.executable, '-B', ROOT / 'scripts/validate_governance.py'],
                              cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / 'fixture-strict-governance-rejection.log').write_text(rejected.stdout)
    assert rejected.returncode != 0 and 'PROPOSED baseline fields are invalid' in rejected.stdout
    with (OUT / 'full-suite.log').open('w') as output:
        result = subprocess.run([ROOT / 'scripts/run_review_tests.sh'], cwd=ROOT,
                                stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == 0, 'supported suite failed; retain and inspect full-suite.log'
finally:
    assert FIXTURE.read_bytes() == raw, 'fixture changed; preserve for investigation'
    FIXTURE.unlink()
    (OUT / 'fixture-removed.json').write_text(json.dumps({
        'removed': True, 'sha256': hashlib.sha256(raw).hexdigest(),
        'purpose': fixture['purpose'], 'source': source,
    }, indent=2, sort_keys=True) + '\n')
print('SUPPORTED_UNIT_SUITE_PASS_WITH_NON_PROPOSAL_FIXTURE_REMOVED', flush=True)
