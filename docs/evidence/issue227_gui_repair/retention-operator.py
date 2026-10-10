"""Exact one-use Issue227 GUI repair exception. No permanent policy change.

Canonical protection must already be complete. Only the explicit resource
ceilings are scoped; protection predicates, reservations and publication remain
real. No maintenance/deletion, acceptance, promotion or merge is implemented.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

SOURCE = Path('/private/tmp/integra-issue-227-k2')
CANONICAL = Path('/private/tmp/integra-issue-228-retention-repair')
SOURCE_SHA = 'e504491fe5f09dae94ecdf9ebe179a08d945e8d8'
BASE = Path.home() / 'Library/Application Support/Integra'
ARCHIVE = BASE / 'Build Archive'
RECORD = BASE / 'Retention Exceptions/issue-227-e504491-gui-one-use'
EXPECTED = 2684354560
CAP = 22 * 1024**3
FLOOR = 15 * 1024**3
AUTHORITY = 'https://github.com/Yurielo/integra/issues/227#issuecomment-6096774200'
sys.path.insert(0, str(CANONICAL))
from scripts import candidate_retention as retention, candidate_archive as archive
from scripts import candidate_protection_gate as gate, temp_workspace_lifecycle as lifecycle

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def command(*args):
    return subprocess.check_output(args, text=True).strip()

def exclusive(path, value):
    retention._safe(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write((json.dumps(value, sort_keys=True, indent=2)+'\n').encode())
        handle.flush()
        os.fsync(handle.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def read(name):
    path = retention._safe(RECORD / name)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
            'foreign/linked receipt')
    return json.loads(path.read_bytes())

def defaults():
    require((retention.MAX_COPIES, retention.MAX_BYTES, retention.FREE_FLOOR) ==
            (8, 20*1024**3, FLOOR), 'permanent defaults changed')

def fingerprints(catalog):
    result = {}
    for package in retention._packages(catalog):
        entries = [archive._entry(package, '.')] + archive._inventory(package)
        info = package.stat()
        result[str(package)] = dict(device=info.st_dev, inode=info.st_ino,
            inventory_sha256=sha(archive.canonical_bytes(entries)),
            file_count=sum(e['type']=='file' for e in entries),
            logical_bytes=sum(e.get('size', 0) for e in entries))
    return result

def preserve(original, actual, incoming=None):
    require(len(original) == 9, 'baseline not nine packages')
    require(all(actual.get(path) == value for path, value in original.items()), 'retained bytes changed')
    require(set(actual)-set(original) == ({incoming} if incoming else set()), 'unexpected additional package')

def source_check(main):
    require(command('git','-C',str(SOURCE),'rev-parse','HEAD') == SOURCE_SHA, 'source HEAD changed')
    require(not command('git','-C',str(SOURCE),'status','--porcelain'), 'source dirty')
    require(command('git','-C',str(CANONICAL),'branch','--show-current') == 'main', 'canonical checkout not main')
    require(command('git','-C',str(CANONICAL),'rev-parse','HEAD') == main, 'canonical checkout changed')
    require(not command('git','-C',str(CANONICAL),'status','--porcelain'), 'canonical checkout dirty')
    require(command('gh','api','repos/Yurielo/integra/git/ref/heads/main','--jq','.object.sha') == main,
            'remote canonical main drift')

def hashes():
    paths = ['scripts/candidate_retention.py', 'scripts/candidate_protection_gate.py',
             'scripts/candidate_protection_audit.py', 'scripts/candidate_archive.py',
             'state/candidate_retention_policy_v1.json', 'state/candidate_lifecycle_retention_policy_v1.json',
             'state/candidate_protection_registry_v1.json', 'state/current_product_baseline_v2.json']
    return {p: sha((CANONICAL/p).read_bytes()) for p in paths}

def fresh(authority=None):
    registry, audit = gate._snapshot(for_deletion=True)
    require(audit['authority_state'] == 'COMPLETE' and not audit['blockers'], 'canonical protection incomplete')
    if authority:
        source_check(authority['main'])
        require(hashes() == authority['canonical_hashes'], 'canonical protection/policy bytes drift')
        require(audit['canonical']['main_sha'] == authority['main'], 'canonical capture differs')
    return registry, audit

def capacity(audit, estimate):
    require(type(estimate) is int and 0 < estimate <= EXPECTED, 'excessive publication estimate')
    require(audit['full_copies'] == 9 and audit['archive_bytes'] + estimate <= CAP
            and audit['free_bytes'] - 3*EXPECTED >= FLOOR, 'one-use resource predicate rejected')

def authorize():
    defaults()
    main = command('git','-C',str(CANONICAL),'rev-parse','HEAD')
    source_check(main)
    registry, audit = fresh()
    require(audit['canonical']['main_sha'] == main, 'canonical snapshot mismatch')
    capacity(audit, EXPECTED)
    path = retention.catalog_path(ARCHIVE)
    catalog = json.loads(path.read_bytes())
    require(not catalog['leases'] and not catalog['deletions'], 'live retention operation')
    require(retention.plan(catalog)['protection_context_valid'], 'catalog is not fresh')
    original = fingerprints(catalog)
    preserve(original, original)
    require(retention._safe(RECORD) == RECORD, 'receipt path differs')
    RECORD.parent.mkdir(mode=0o700, exist_ok=True)
    RECORD.mkdir(mode=0o700)
    exclusive(RECORD/'authorization.json', dict(issue=227, source=SOURCE_SHA, main=main,
        source_tree=command('git','-C',str(SOURCE),'rev-parse','HEAD^{tree}'),
        authority_ref=AUTHORITY, one_use=True, max_packages=10, max_bytes=CAP,
        permanent_max_packages=8, permanent_max_bytes=20*1024**3, free_floor=FLOOR,
        operator_sha256=sha(Path(__file__).read_bytes()), canonical_hashes=hashes(),
        original_packages=original, catalog_sha256=sha(path.read_bytes()),
        owner_acceptance=False, promotion=False, merge=False))
    exclusive(RECORD/'preflight.json', audit)
    print(json.dumps(dict(status='EXACT_ONE_USE_AUTHORITY_RECORDED', record=str(RECORD))))

def forbidden(*args, **kwargs):
    raise ValueError('maintenance/deletion forbidden: preserve all existing nine packages')

@contextmanager
def scoped(authority):
    defaults()
    old = gate.require_archive_publication, gate.require_deletion, retention.maintenance
    used = False
    def publication(root, estimate):
        nonlocal used
        require(not used and retention._safe(root) == ARCHIVE, 'second or foreign publication')
        require(read('authorization.json') == authority, 'authority changed')
        incoming = read('incoming.json')
        require(incoming['source'] == SOURCE_SHA, 'incoming source differs')
        catalog = json.loads(retention.catalog_path(ARCHIVE).read_bytes())
        token = os.environ.get('INTEGRA_RETENTION_BUILD_LEASE')
        require(set(catalog['leases']) == {token} and retention._lease_caller(catalog['leases'][token]),
                'exclusive real build lease missing')
        preserve(authority['original_packages'], fingerprints(catalog))
        _, audit = fresh(authority)
        capacity(audit, estimate)
        require(not (ARCHIVE/incoming['candidate_id']/incoming['bundle_digest']).exists(), 'archive exists')
        used = True
    retention.MAX_COPIES, retention.MAX_BYTES = 10, CAP
    gate.require_archive_publication, gate.require_deletion, retention.maintenance = publication, forbidden, forbidden
    try:
        yield
    finally:
        gate.require_archive_publication, gate.require_deletion, retention.maintenance = old
        retention.MAX_COPIES, retention.MAX_BYTES = 8, 20*1024**3

def execute():
    require(sys.dont_write_bytecode and not sys.flags.optimize, 'unsafe Python flags')
    authority = read('authorization.json')
    require(authority['operator_sha256'] == sha(Path(__file__).read_bytes()), 'operator changed')
    fresh(authority)
    workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE']).resolve(strict=True)
    _, marker = lifecycle._load(workspace)
    require(marker['purpose'] == 'issue227-gui-repair', 'wrong owned workspace')
    with retention.locked(retention.catalog_path(ARCHIVE)) as catalog:
        require(not catalog['leases'] and not catalog['deletions'], 'live operation')
        require(sha(retention.catalog_path(ARCHIVE).read_bytes()) == authority['catalog_sha256'], 'catalog drift')
        preserve(authority['original_packages'], fingerprints(catalog))
        exclusive(RECORD/'CONSUMED.json', dict(source=SOURCE_SHA, attempt=1,
            authorization_sha256=sha((RECORD/'authorization.json').read_bytes())))
    app = workspace/'candidate/Integra.app'
    with scoped(authority):
        with retention.reserved_build(ARCHIVE, EXPECTED, archive_copy=True):
            subprocess.run([str(SOURCE/'scripts/build_macos_app.sh'),str(app.parent)],cwd=SOURCE,check=True)
            subprocess.run([sys.executable,'-B',str(SOURCE/'scripts/candidate_manifest.py'),'validate',str(app)],
                           cwd=SOURCE,check=True,timeout=900)
            manifest = json.loads((app/'Contents/Resources/candidate-manifest.json').read_bytes())
            require(manifest['identity']['source'] == dict(commit_sha=SOURCE_SHA, tree_sha=authority['source_tree'],
                dirty=False, dirty_diff_sha256=sha(b'')), 'Candidate source substitution')
            identity = archive._identity(app)
            exclusive(RECORD/'incoming.json', dict(**identity, source=SOURCE_SHA,
                identity_sha256=manifest['identity_sha256']))
            receipt = archive.create_archive(app, ARCHIVE)
            exclusive(RECORD/'publication.json', receipt)
    defaults()
    catalog = json.loads(retention.catalog_path(ARCHIVE).read_bytes())
    require(not catalog['leases'] and not catalog['deletions'], 'remaining operation')
    actual = fingerprints(catalog)
    preserve(authority['original_packages'], actual, receipt['archive_path'])
    _, audit = fresh(authority)
    require(audit['full_copies'] == 10 and audit['archive_bytes'] <= CAP and audit['free_bytes'] >= FLOOR,
            'post-publication exception bounds exceeded')
    require(retention.plan(catalog)['protection_context_valid'], 'post-publication protection stale')
    verified = archive.verify_archive(Path(receipt['archive_path']), identity)
    exclusive(RECORD/'post-publication.json', dict(status='COMPLETE_EXACT_OWNER_EXCEPTION',
        archive=verified, all_ten_fingerprints=actual, preserved_nine=True,
        canonical_protection=audit, permanent_policy_unchanged=True))
    print(json.dumps(dict(status='COMPLETE', archive=verified, record=str(RECORD)),sort_keys=True),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['authorize','run','child'])
    args = parser.parse_args()
    if args.phase == 'authorize':
        authorize()
    elif args.phase == 'child':
        execute()
    else:
        require(not (RECORD/'CONSUMED.json').exists(), 'one-use attempt already consumed')
        ns = argparse.Namespace(base='/private/tmp',purpose='issue227-gui-repair',expected_bytes=EXPECTED,
            reserve_bytes=FLOOR,timeout_seconds=3600,argv=[sys.executable,'-B',str(Path(__file__).resolve()),'child'])
        raise SystemExit(lifecycle.run_owned(ns))
