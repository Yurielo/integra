"""Exact Issue227 Owner-authorized ninth-copy transaction; NOT a general policy.

No product-source edits, maintenance, deletion, or permanent cap change.
The common real reservation, ownership supervisor and archive publisher remain
authoritative. Raw ordinary audits are retained, never rewritten to PASS.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

SOURCE = Path('/private/tmp/integra-issue-227-k2')
MAIN_REPO = Path('/private/tmp/integra-issue-228-retention-repair')
SOURCE_SHA = 'e6cd7612a764fbfed5f8f713e838b39caac97f4a'
SOURCE_TREE = 'bf702d6bf9c188dec1a37b390160f0a26e372129'
MAIN_SHA = '7308d143badd58d593aa21c6e9eb02b18428c05a'
BASE = Path.home() / 'Library/Application Support/Integra'
ARCHIVE = BASE / 'Build Archive'
RECORD = BASE / 'Retention Exceptions/issue-227-e6cd761-one-use'
EXPECTED = 2684354560
BYTE_CAP = 20 * 1024**3
FLOOR = 15 * 1024**3
sys.path.insert(0, str(SOURCE))
from scripts import candidate_retention as retention
from scripts import candidate_archive as archive
from scripts import candidate_protection_gate as gate
from scripts import temp_workspace_lifecycle as lifecycle

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)+'\n').encode()

def exclusive(path, value):
    """Durable no-replace authority/evidence record; never retry consumption."""
    retention._safe(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        payload = encode(value)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # A partial receipt consumes the attempt too. Never silently erase it.
        raise

def read(name):
    path = RECORD / name
    retention._safe(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
            'foreign or linked exception receipt')
    return json.loads(path.read_bytes())

def command(*args):
    return subprocess.check_output(args, text=True).strip()

def source_check(source=SOURCE_SHA, main=MAIN_SHA):
    require(source == SOURCE_SHA and main == MAIN_SHA, 'exception source/main binding differs')
    require(command('git','-C',str(SOURCE),'rev-parse','HEAD') == SOURCE_SHA, 'source HEAD differs')
    require(command('git','-C',str(SOURCE),'rev-parse','HEAD^{tree}') == SOURCE_TREE, 'source tree differs')
    require(not command('git','-C',str(SOURCE),'status','--porcelain'), 'source is dirty')
    require(command('git','-C',str(MAIN_REPO),'rev-parse','HEAD') == MAIN_SHA, 'local main differs')
    require(not command('git','-C',str(MAIN_REPO),'status','--porcelain'), 'main is dirty')
    require(command('gh','api','repos/Yurielo/integra/git/ref/heads/main','--jq','.object.sha') == MAIN_SHA,
            'canonical main differs')

def policy_hashes():
    paths = ['state/candidate_retention_policy_v1.json',
             'state/candidate_lifecycle_retention_policy_v1.json',
             'state/candidate_protection_registry_v1.json',
             'state/current_product_baseline_v2.json',
             'scripts/candidate_retention.py', 'scripts/candidate_protection_gate.py',
             'scripts/candidate_protection_audit.py', 'scripts/candidate_archive.py']
    result = {}
    for path in paths:
        payload = (SOURCE/path).read_bytes()
        require(payload == (MAIN_REPO/path).read_bytes(), 'tooling/canonical binding differs: '+path)
        result[path] = sha(payload)
    return result

def fingerprints(catalog):
    result = {}
    for package in retention._packages(catalog):
        entries = [archive._entry(package,'.')] + archive._inventory(package)
        info = package.stat()
        result[str(package)] = dict(device=info.st_dev, inode=info.st_ino,
            inventory_sha256=sha(archive.canonical_bytes(entries)),
            file_count=sum(e['type']=='file' for e in entries),
            logical_bytes=sum(e.get('size',0) for e in entries))
    return result

def verify_preservation(original, actual, incoming=None):
    require(len(original) == 8, 'baseline is not eight packages')
    require(all(actual.get(path) == value for path,value in original.items()), 'protected package changed/missing')
    extras = set(actual)-set(original)
    require(extras == ({incoming} if incoming else set()), 'unexpected additional package')

def capacity(copies, allocated, estimate, free):
    require(type(estimate) is int and 0 < estimate <= EXPECTED, 'invalid or excessive archive estimate')
    require(copies == 8 and allocated + estimate <= BYTE_CAP and free - estimate >= FLOOR,
            'one-time count/byte/free admission rejected')

def discharge(raw, identity, original, actual):
    """Only exact copy-count deviation may be covered; keep raw report intact."""
    incoming = str(ARCHIVE/identity['candidate_id']/identity['bundle_digest'])
    verify_preservation(original, actual, incoming)
    require(raw['full_copies'] == 9 and raw['archive_bytes'] <= BYTE_CAP and raw['free_bytes'] >= FLOOR,
            'exception resource bounds differ')
    require(raw['blockers'] == ['ARCHIVE_COPY_CAP_EXCEEDED'], 'non-count protection blocker')
    return dict(status='PASS_EXACT_OWNER_EXCEPTION', permanent_max_copies=8,
                one_time_max_copies=9, exception_consumed=True, authority=str(RECORD/'authorization.json'),
                discharged_blocker='ARCHIVE_COPY_CAP_EXCEEDED', **identity)

def authorize(approval_path):
    source_check()
    require(retention.MAX_COPIES == 8 and retention.MAX_BYTES == BYTE_CAP and retention.FREE_FLOOR == FLOOR,
            'ordinary policy constants changed')
    catalog = json.loads(retention.catalog_path(ARCHIVE).read_bytes())
    require(not catalog['leases'] and not catalog['deletions'], 'live retention operation exists')
    require(retention.plan(catalog)['protection_context_valid'], 'stale protection context')
    registry,audit = gate._snapshot()
    require(audit['canonical']['main_sha'] == MAIN_SHA and audit['full_copies'] == 8 and not audit['blockers'],
            'pre-existing authority is incomplete')
    capacity(8,audit['archive_bytes'],EXPECTED,audit['free_bytes'])
    baseline = fingerprints(catalog)
    verify_preservation(baseline,baseline)
    require(baseline == json.loads(Path('/private/tmp/integra-238-evidence/after-fingerprints.json').read_bytes()),
            'baseline differs from preserved Issue238 packages')
    retention._safe(RECORD)
    RECORD.parent.mkdir(mode=0o700, exist_ok=True)
    RECORD.mkdir(mode=0o700)  # existing transaction never reused
    approval = Path(approval_path).read_text()
    exclusive(RECORD/'authorization.json', dict(issue=227, source=SOURCE_SHA, source_tree=SOURCE_TREE,
        main=MAIN_SHA, approval=approval, approval_sha256=sha(approval.encode()),
        approval_evidence='https://github.com/Yurielo/integra/issues/227#issuecomment-6095568381',
        operator_sha256=sha(Path(__file__).read_bytes()), policy_hashes=policy_hashes(),
        original_packages=baseline, before_catalog_sha256=sha(retention.catalog_path(ARCHIVE).read_bytes()),
        max_packages=9, permanent_max_packages=8, byte_cap=BYTE_CAP, free_floor=FLOOR,
        one_use=True, existing_packages_immutable=True, owner_acceptance=False, merge=False))
    exclusive(RECORD/'preflight-audit.json',audit)
    print(json.dumps(dict(status='ONE_USE_AUTHORITY_RECORDED',record=str(RECORD))))

def forbidden(*args, **kwargs):
    raise ValueError('maintenance/deletion forbidden by exact Issue227 exception')

@contextmanager
def scoped_exception(authority):
    """One process, one lease, one exact publication; no global/env bypass."""
    require(retention.MAX_COPIES == 8, 'default cap already changed')
    old_gate = gate.require_archive_publication
    old_delete = gate.require_deletion
    old_maintenance = retention.maintenance
    used = False
    def publication(root, estimated):
        nonlocal used
        require(not used, 'second archive publication forbidden')
        require(retention._safe(root) == ARCHIVE, 'different archive root forbidden')
        bound = read('incoming-identity.json')
        require(bound['source'] == SOURCE_SHA, 'incoming source differs')
        require(read('authorization.json') == authority, 'authorization receipt changed')
        current = json.loads(retention.catalog_path(ARCHIVE).read_bytes())
        token = os.environ.get('INTEGRA_RETENTION_BUILD_LEASE')
        require(set(current['leases']) == {token} and retention._lease_caller(current['leases'][token]),
                'publication lacks exclusive real owned build lease')
        verify_preservation(authority['original_packages'],fingerprints(current))
        registry,audit = gate._snapshot()
        require(audit['canonical']['main_sha'] == MAIN_SHA and not audit['blockers'], 'publication authority drift')
        require(policy_hashes() == authority['policy_hashes'], 'publication policy/CURRENT changed')
        capacity(audit['full_copies'],audit['archive_bytes'],estimated,audit['free_bytes'])
        require((ARCHIVE/bound['candidate_id']/bound['bundle_digest']).exists() is False,
                'incoming archive already exists')
        used = True
    retention.MAX_COPIES = 9  # lexical, approved predicate only; restored even on error
    retention.maintenance = forbidden
    gate.require_archive_publication = publication
    gate.require_deletion = forbidden
    try:
        yield
    finally:
        gate.require_archive_publication = old_gate
        gate.require_deletion = old_delete
        retention.maintenance = old_maintenance
        retention.MAX_COPIES = 8

def execute():
    authority = read('authorization.json')
    require(not os.environ.get('INTEGRA_RETENTION_BUILD_LEASE'), 'nested build lease forbidden')
    workspace = Path(os.environ['INTEGRA_OWNED_WORKSPACE']).resolve(strict=True)
    _,marker = lifecycle._load(workspace)
    require(marker['purpose'] == 'issue227-k2-repair', 'unrelated owned workspace purpose')
    source_check(authority['source'],authority['main'])
    require(authority['operator_sha256'] == sha(Path(__file__).read_bytes()), 'operator changed after authorization recording')
    require(policy_hashes() == authority['policy_hashes'], 'governance bytes changed')
    with retention.locked(retention.catalog_path(ARCHIVE)) as catalog:
        require(not catalog['leases'] and not catalog['deletions'], 'concurrent retention operation')
        require(sha(retention.catalog_path(ARCHIVE).read_bytes()) == authority['before_catalog_sha256'], 'catalog drift')
        verify_preservation(authority['original_packages'],fingerprints(catalog))
        exclusive(RECORD/'CONSUMED.json', dict(source=SOURCE_SHA, operator_sha256=authority['operator_sha256'],
            authorization_sha256=sha((RECORD/'authorization.json').read_bytes()),
            pid=os.getpid(), process_start=retention.admission._start(os.getpid()), attempt=1))
    app = workspace/'candidate/Integra.app'
    with scoped_exception(authority):
        with retention.reserved_build(ARCHIVE,EXPECTED,archive_copy=True):
            subprocess.run([str(SOURCE/'scripts/build_macos_app.sh'),str(app.parent)],check=True,cwd=SOURCE)
            subprocess.run([sys.executable,'-B',str(SOURCE/'scripts/candidate_manifest.py'),'validate',str(app)],
                           check=True,cwd=SOURCE,timeout=900)
            manifest = json.loads((app/'Contents/Resources/candidate-manifest.json').read_bytes())
            binding = manifest['identity']['source']
            require(binding['commit_sha'] == SOURCE_SHA and binding['tree_sha'] == SOURCE_TREE
                    and binding['dirty'] is False and binding['dirty_diff_sha256'] == sha(b''),
                    'built Candidate source differs from authorized repair')
            identity = archive._identity(app)
            exclusive(RECORD/'incoming-identity.json',dict(**identity,source=SOURCE_SHA,
                identity_sha256=manifest['identity_sha256']))
            receipt = archive.create_archive(app,ARCHIVE)
            require(all(receipt[key] == value for key,value in identity.items()), 'publication identity substitution')
            exclusive(RECORD/'publication.json',receipt)
    # Default cap is back to8. Report real ordinary state without concealing9.
    catalog = json.loads(retention.catalog_path(ARCHIVE).read_bytes())
    require(not catalog['leases'] and not catalog['deletions'], 'retention operation remains live')
    actual = fingerprints(catalog)
    registry,audit = gate._snapshot(for_deletion=True)
    current,proposals,canonical = gate.protection.fetch_canonical(registry)
    require(canonical == audit['canonical'] and canonical['main_sha'] == MAIN_SHA,
            'post-publication canonical capture changed')
    raw = gate.protection.resolve(registry,current,proposals,
        gate.protection.scan_local(registry,BASE), free_bytes=shutil.disk_usage(BASE).free,
        canonical=canonical)
    exception = discharge(raw,identity,authority['original_packages'],actual)
    require(policy_hashes() == authority['policy_hashes'], 'policy/CURRENT changed after publication')
    require(read('authorization.json') == authority and read('incoming-identity.json') ==
            dict(**identity,source=SOURCE_SHA,identity_sha256=manifest['identity_sha256']), 'exception record changed')
    require(retention.plan(catalog)['protection_context_valid'], 'protection context stale after publication')
    verified = archive.verify_archive(Path(receipt['archive_path']),identity)
    source_check()
    exclusive(RECORD/'post-publication.json',dict(raw_protection=raw,exception=exception,
        fingerprints=actual,verified_archive=verified,default_max_copies=retention.MAX_COPIES,
        protection_context_valid=True,existing_eight_byte_identical=True,maintenance=False,deletion=False))
    print(json.dumps(dict(status='COMPLETE',archive=verified,exception=exception),sort_keys=True),flush=True)

def main():
    require(not sys.flags.optimize,'optimized Python forbidden')
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=['authorize','run','child'])
    parser.add_argument('--approval')
    args = parser.parse_args()
    if args.phase == 'authorize':
        authorize(args.approval)
    elif args.phase == 'child':
        execute()
    else:
        require(not (RECORD/'CONSUMED.json').exists(),'one-time attempt already consumed')
        ns = argparse.Namespace(base='/private/tmp',purpose='issue227-k2-repair',expected_bytes=EXPECTED,
            reserve_bytes=FLOOR,timeout_seconds=3600,
            argv=[sys.executable,'-B',str(Path(__file__).resolve()),'child'])
        raise SystemExit(lifecycle.run_owned(ns))

if __name__ == '__main__':
    main()
