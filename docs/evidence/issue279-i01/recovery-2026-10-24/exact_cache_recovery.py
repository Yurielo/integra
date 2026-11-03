"""Execute only the owner-authorized Issue279 three-tree recovery exception."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import uuid

PLAN_SHA = 'd89bed43693b767fc510076ff9a8330a9222c63af960173241137d134fa89b50'
AUTH_SHA = '3ac38c3a469cac0bc77bb02ec00007be2a08307564faafdef612d01e08206093'
AUTH_REF = 'https://github.com/Yurielo/integra/issues/279#issuecomment-6380883524'
GOVERNOR = Path('/private/tmp/integra-issue279-k2-supersession')
PRODUCT = Path('/private/tmp/integra-issue-279-k2-canonical-knowledge')
OUT = Path(__file__).parent
INPUT = PRODUCT / 'docs/evidence/issue279-i01/handoff-2026-10-24'
CURRENT = {
    'current_product_baseline_v2.json': 'bdd2ea30b3102c59cd8e47bc56a0d53c6b57d3bfb0347e667663b1be951e52e2',
    'current_canonical_baseline_v1.json': '0493fbad50f1a5518b01be90e3ffb0cd10d3d8b7a97ae12918fc4595c4438840',
}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def sync(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def atomic_json(path, data):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex)
    with temp.open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path); sync(path.parent)

def safe(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'parent traversal')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'linked path')
    return path

def canonical_entry(entry):
    keys = ('path', 'type', 'mode', 'size', 'sha256') if entry['type'] == 'file' else ('path', 'type', 'mode')
    return {key: entry[key] for key in keys}

def under(path, root):
    return path == root or path.startswith(root + '/')

def recover_exact(archive, expected, extras, roots, parent, authority, *, inventory, inactive, mover, verifier):
    """Caller supplies verified exact authority and the canonical byte verifier."""
    archive, parent = safe(archive), safe(parent)
    require(archive.is_dir() and archive.stat().st_uid == os.getuid(), 'archive owner/type differs')
    require(parent != archive and archive not in parent.parents and parent not in archive.parents,
            'quarantine and archive must have disjoint trees')
    require(authority.get('authority_ref') and authority.get('plan_sha256'), 'missing exact authority')
    require(len(roots) == 3 and len(set(roots)) == 3, 'requires exactly three distinct roots')
    for root in roots:
        parts = PurePosixPath(root).parts
        require(parts and not root.startswith('/') and all(p not in ('.', '..') for p in parts), 'unsafe relative root')
        require(str(PurePosixPath(root)) == root, 'noncanonical relative root')
        require(all(other == root or not under(root, other) for other in roots), 'overlapping move roots')
    require(all(sum(under(e['path'], root) for root in roots) == 1 for e in extras), 'extra entry outside exact roots')
    require(set(roots) == {e['path'] for e in extras if e['type'] == 'directory'}, 'unexpected directory domain')
    expected_map = {e['path']: e for e in expected}
    require(len(expected_map) == len(expected), 'duplicate recorded entry')
    extra_map = {e['path']: canonical_entry(e) for e in extras}
    extra_attributes = {e['path']: e for e in extras}
    require(len(extra_map) == len(extras) and not set(expected_map) & set(extra_map), 'duplicate/recorded extra path')
    require(all(not any(under(e['path'], root) for root in roots) for e in expected), 'move includes recorded payload')
    actual = {e['path']: e for e in inventory(archive)}
    require(actual == {**expected_map, **extra_map}, 'archive differs from exact recorded-plus-extra inventory')
    for entry in extras:
        s = (archive / entry['path']).lstat()
        require(s.st_uid == os.getuid() == entry['uid'], 'extra ownership differs')
        require(stat.S_IMODE(s.st_mode) == entry['mode'], 'extra mode differs')
        require(s.st_nlink == entry['nlink'], 'extra link count differs')
        if entry['type'] == 'file':
            require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'nonregular/hardlinked extra')
    require(inactive(archive), 'archive has active or unproven consumers')
    if not parent.exists():
        parent.mkdir(mode=0o700)
        sync(parent.parent)
    require(parent.is_dir() and parent.stat().st_uid == os.getuid(), 'quarantine parent owner/type differs')
    require(parent.stat().st_dev == archive.stat().st_dev, 'quarantine must be on same volume')
    quarantine = parent / ('issue279-' + uuid.uuid4().hex)
    quarantine.mkdir(mode=0o700); sync(parent)
    preserved = quarantine / 'preserved'; preserved.mkdir(mode=0o700)
    journal_path = quarantine / 'recovery-journal.json'
    journal = dict(schema_version='1.0', artifact_type='integra.exact_archive_recovery',
                   authority=authority, archive_path=str(archive), quarantine_path=str(quarantine),
                   roots=roots, state='PREPARED', moved=[], unexpected_files=sum(e['type']=='file' for e in extras),
                   unexpected_file_bytes=sum(e.get('size', 0) for e in extras if e['type']=='file'),
                   quarantine_deletion_authorized=False)
    identities = {root: ((archive/root).stat().st_dev, (archive/root).stat().st_ino) for root in roots}
    atomic_json(journal_path, journal)
    try:
        for root in roots:
            source, destination = safe(archive / root), safe(preserved / root)
            require(inactive(archive), 'archive activity changed')
            source_stat = source.lstat()
            require((source_stat.st_dev, source_stat.st_ino) == identities[root], 'cache tree identity changed')
            attributes = extra_attributes[root]
            require(stat.S_ISDIR(source_stat.st_mode) and source_stat.st_uid == attributes['uid']
                    and stat.S_IMODE(source_stat.st_mode) == attributes['mode']
                    and source_stat.st_nlink == attributes['nlink'], 'cache root attributes changed')
            subtree = {e['path']: e for e in inventory(source)}
            intended = {path[len(root)+1:]: {**entry, 'path': path[len(root)+1:]}
                        for path, entry in extra_map.items() if path.startswith(root + '/')}
            require(subtree == intended, 'cache subtree changed immediately before move')
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            journal.update(state='MOVING', pending_root=root); atomic_json(journal_path, journal)
            mover(source, destination)
            sync(source.parent); sync(destination.parent)
            journal['moved'].append(root); journal.pop('pending_root', None)
            atomic_json(journal_path, journal)
        preserved_entries = {e['path']: e for e in inventory(preserved)}
        recovered = {path: e for path, e in preserved_entries.items() if any(under(path, root) for root in roots)}
        require(recovered == extra_map, 'quarantined byte/mode inventory differs')
        for path, e in preserved_entries.items():
            require(path in extra_map or (e['type']=='directory' and any(root.startswith(path+'/') for root in roots)), 'foreign quarantine entry')
        require({e['path']:e for e in inventory(archive)} == expected_map, 'recorded archive changed after moves')
        receipt = verifier(archive)
        atomic_json(quarantine/'preserved-inventory.json', sorted(recovered.values(), key=lambda e:e['path']))
        journal.update(state='VERIFIED', archive_verification=receipt,
                       preserved_inventory_sha256=sha(quarantine/'preserved-inventory.json'))
        atomic_json(journal_path, journal)
        return journal
    except BaseException as error:
        journal.update(state='PARTIAL_PRESERVED', error=str(error))
        atomic_json(journal_path, journal)
        raise

def main():
    for root in (GOVERNOR, PRODUCT):
        require(not subprocess.check_output(['git','-C',root,'status','--porcelain'], text=True), 'dirty control checkout')
    head = subprocess.check_output(['git','-C',GOVERNOR,'rev-parse','HEAD'], text=True).strip()
    require(head == subprocess.check_output(['git','-C',GOVERNOR,'rev-parse','origin/main'], text=True).strip(), 'governor not canonical')
    sys.path.insert(0, str(GOVERNOR))
    from scripts import candidate_retention as retention, candidate_archive as archive, candidate_protection_gate as gate
    from scripts import candidate_protection_audit as protection
    plan_path = INPUT / 'exact-recovery-plan.json'
    require(sha(plan_path) == PLAN_SHA, 'plan bytes changed')
    plan = json.loads(plan_path.read_bytes())
    diff_path = INPUT / 'outgoing-integrity-diff.json'
    require(sha(diff_path) == plan['integrity_diff_sha256'], 'exact extra inventory changed')
    diff = json.loads(diff_path.read_bytes()); target = safe(plan['archive_path'])
    identity = {k:plan[k] for k in ('candidate_id','bundle_digest','manifest_digest')}
    def current():
        for root in (GOVERNOR, PRODUCT):
            for name, digest in CURRENT.items():
                require(sha(root/'state'/name)==digest, 'CURRENT changed')
    current()
    comment = protection._api('repos/Yurielo/integra/issues/comments/6380883524')
    require(comment['html_url']==AUTH_REF and comment['user']['login']=='Yurielo' and hashlib.sha256(comment['body'].encode()).hexdigest()==AUTH_SHA, 'recovery authority changed')
    with retention.locked(retention.catalog_path(target.parent.parent)) as catalog:
        registry, audit = gate._snapshot(for_deletion=True)
        require(audit['canonical']['main_sha']==head, 'canonical head advanced')
        relative = target.relative_to(Path.home()/'Library/Application Support/Integra').as_posix()
        grant = registry['withdrawal_deletion_authorizations'][relative]
        require(all(grant[k]==identity[k] for k in identity) and grant['lifecycle']=='WITHDRAWN_SUPERSEDED', 'exact supersession grant changed')
        record = catalog['artifacts'][str(target)]
        require(record['device']==target.stat().st_dev and record['inode']==target.stat().st_ino and record['status']=='WITHDRAWN_SUPERSEDED', 'publisher/lifecycle identity differs')
        for filename, digest in [('inventory.json',plan['inventory_sha256']),('COMPLETE.json',plan['complete_sha256']),('candidate-manifest.json',plan['manifest_digest']),('Integra.app/Contents/Resources/candidate-manifest.json',plan['manifest_digest'])]:
            require(sha(target/filename)==digest, 'bound metadata changed: '+filename)
        authority = dict(authority_ref=AUTH_REF, authority_body_sha256=AUTH_SHA, plan_sha256=PLAN_SHA,
                         governor_commit=head, canonical_withdrawal_grant=grant)
        inventory = lambda root: archive._inventory(root, exclude={'inventory.json','COMPLETE.json'} if root==target else set())
        result = recover_exact(target, json.loads((target/'inventory.json').read_bytes()), diff['extra'],
                               plan['move_roots'], Path(plan['quarantine_parent']), authority,
                               inventory=inventory, inactive=retention._inactive, mover=archive._publish,
                               verifier=lambda path: archive.verify_archive(path,identity))
        for filename, digest in [('inventory.json',plan['inventory_sha256']),('COMPLETE.json',plan['complete_sha256']),('candidate-manifest.json',plan['manifest_digest']),('Integra.app/Contents/Resources/candidate-manifest.json',plan['manifest_digest'])]:
            require(sha(target/filename)==digest, 'bound metadata changed after recovery: '+filename)
        current()
        atomic_json(OUT/'recovery-receipt.json',result)
    print(json.dumps(dict(state=result['state'],quarantine_path=result['quarantine_path'],current_unchanged=True)),flush=True)

if __name__ == '__main__':
    main()
