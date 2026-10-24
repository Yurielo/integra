"""Use canonical retention authority to retain the frozen, tested I01 source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE = Path('/private/tmp/integra-issue-279-k2-canonical-knowledge')
GOVERNOR = Path('/private/tmp/integra-issue279-k2-supersession')
OUT = Path(__file__).parent
EXPECTED_SOURCE = '6e6978a5f88930158058df8e90dbe4275f11c29a'
EXPECTED_CANDIDATE = 'candidate-v1-e8064cba8acad3282d86b9d7eea043f85c5eed54ac7db015ccdf089943dee943'
EXPECTED_BUNDLE = '1fe98fb2822b50077f78f22db960dc1f457f5b6374736a3dace704e99e8fe7e0'
EXPECTED_MANIFEST = '25255077dfd65185268ba152c50a1a5ba66d1a425ff9bcab342263f6fbb2c58e'
EXPECTED_CURRENT = {
    'state/current_product_baseline_v2.json': 'bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2',
    'state/current_canonical_baseline_v1.json': '0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840',
}

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

def current():
    for root in (SOURCE, GOVERNOR):
        for path, digest in EXPECTED_CURRENT.items():
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest, (root, path)

def run(args, name, **kwargs):
    with (OUT / name).open('w') as output:
        subprocess.run(list(map(str, args)), check=True, text=True, stdout=output, **kwargs)

assert subprocess.check_output(['git', '-C', SOURCE, 'rev-parse', 'HEAD'], text=True).strip() == EXPECTED_SOURCE
assert not subprocess.check_output(['git', '-C', SOURCE, 'status', '--porcelain'], text=True)
assert subprocess.check_output(['git', '-C', GOVERNOR, 'rev-parse', 'HEAD'], text=True).strip() == subprocess.check_output(['git', '-C', GOVERNOR, 'rev-parse', 'origin/main'], text=True).strip()
assert not subprocess.check_output(['git', '-C', GOVERNOR, 'status', '--porcelain'], text=True)
save('governor-source.json', {
    'commit_sha': subprocess.check_output(['git', '-C', GOVERNOR, 'rev-parse', 'HEAD'], text=True).strip(),
    'tree_sha': subprocess.check_output(['git', '-C', GOVERNOR, 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
    'dirty': False,
})
sys.path.insert(0, str(GOVERNOR))
from scripts import candidate_retention, candidate_archive

current()
workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE']).resolve(strict=True)
archive_root = Path.home() / 'Library/Application Support/Integra/Build Archive'
catalog_path = candidate_retention.catalog_path(archive_root)
save('catalog-before.json', json.loads(catalog_path.read_bytes()))
save('build-preflight.json', candidate_retention.build_preflight(archive_root, 2516582400, archive_copy=True))
with candidate_retention.reserved_build(archive_root, 2516582400, archive_copy=True):
    app = workspace / 'candidate/Integra.app'
    print('I01_FROZEN_SOURCE_BUILD_START', flush=True)
    run([SOURCE / 'scripts/build_macos_app.sh', app.parent], 'fresh-build.log')
    run([sys.executable, '-B', SOURCE / 'scripts/candidate_manifest.py', 'validate', app], 'candidate-validation.json')
    run([sys.executable, '-B', SOURCE / 'tests/test_packaged_knowledge_view.py', '--app', app], 'packaged-schema.log')
    run([app / 'Contents/MacOS/Integra', '--self-test'], 'native-self-test.log', env={**os.environ, 'INTEGRA_APP_DATA_ROOT': str(workspace / 'self-test-data')})
    with (OUT / 'packaged-k2.stderr').open('w') as errors:
        run([sys.executable, '-B', SOURCE / 'tests/packaged_k2_probe.py', '--app', app, '--data-root', workspace / 'k2-qa'], 'packaged-k2.json', stderr=errors)
    manifest_path = app / 'Contents/Resources/candidate-manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest['candidate_id'] == EXPECTED_CANDIDATE
    assert manifest['bundle']['digest'] == EXPECTED_BUNDLE
    assert hashlib.sha256(manifest_bytes).hexdigest() == EXPECTED_MANIFEST
    (OUT / 'candidate-manifest.json').write_bytes(manifest_bytes)
    current()
    print('I01_EXACT_CANDIDATE_REPRODUCED_ARCHIVE_START', flush=True)
    receipt = candidate_archive.create_archive(app, archive_root)
    save('candidate-archive.json', receipt)
    save('candidate-archive-verification.json', candidate_archive.verify_archive(Path(receipt['archive_path']), {
        'candidate_id': EXPECTED_CANDIDATE, 'bundle_digest': EXPECTED_BUNDLE, 'manifest_digest': EXPECTED_MANIFEST}))
    current()
save('catalog-after.json', json.loads(catalog_path.read_bytes()))
save('current-unchanged.json', EXPECTED_CURRENT)
print('I01_ARCHIVE_VERIFIED_CURRENT_UNCHANGED', flush=True)
