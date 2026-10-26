#!/usr/bin/env python3
"""One owner-authorized 721d publisher-device repair; never archive adoption.

The canonical withdrawal, exact deletion grant and this executable must already
be on main. The device transaction changes only the original target record's
device and its dedicated journal. A separate target-only reconciliation mirrors
the canonical withdrawal and verified protection context through the established
reconciler. Candidate bytes, CURRENT and general ownership/hold predicates stay
unchanged. Retirement remains a separate call to the existing exact executor.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import tempfile

try:
    from scripts import candidate_archive as archive, candidate_retention as retention
    from scripts import candidate_protection_gate as gate, candidate_protection_audit as protection
    from scripts import candidate_lifecycle as lifecycle
except ModuleNotFoundError:
    import candidate_archive as archive
    import candidate_retention as retention
    import candidate_protection_gate as gate
    import candidate_protection_audit as protection
    import candidate_lifecycle as lifecycle

ROOT = Path(__file__).resolve().parents[1]
BASE = Path.home() / 'Library/Application Support/Integra'
IDENTITY = {
    'candidate_id': 'candidate-v1-721d5a88393dc361bb72d6ca1abab70d3fa2a6ba3e420737ca3b1bedc89136f5',
    'bundle_digest': 'f7c053a536e1c415adcc2e32b2f5a52248edfea17afaebc6cbca6c716d65cfa9',
    'manifest_digest': '241b9ae31d16d28d3ba7d174f0776f31fb148bb4c52df2a6545c94e2c0130282',
}
RELATIVE = 'Build Archive/' + IDENTITY['candidate_id'] + '/' + IDENTITY['bundle_digest']
AUTHORIZATION = 'state/candidate_721d_ownership_recovery_v1.json'
WITHDRAWAL = 'state/history/candidate_721d_withdrawal_v1.json'
REQUEST = 'docs/evidence/ISSUE_293_721D_OWNER_DECISION_REQUEST.txt'
REQUEST_SHA256 = '0f2b9483cd791163b6d2ea97f2f23ec897baa30ee4cbf6e949a07c54b19920ff'
SCRIPT = 'scripts/candidate_721d_ownership_recovery.py'
SCOPE = 'EXACT_721D_DEVICE_BINDING_RECOVERY_ONLY'
TOKEN = 'PRODUCT_OWNER_AUTHORIZATION: EXACT_721D_WITHDRAWAL_OWNERSHIP_RECOVERY_RETIREMENT'
JOURNAL = 'exact_721d_ownership_recovery'
TRANSACTION = 'exact-721d-device-recovery-v1'
PREVIOUS_DEVICE = 16777233
EXPECTED_DEVICE = 16777232
EXPECTED_INODE = 45635682
OWNER_UID = 501


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _remote_bytes(path, main):
    value = protection._api(f'repos/{protection.REPOSITORY}/contents/{path}?ref={main}')
    if value.get('type') != 'file' or value.get('encoding') != 'base64':
        raise ValueError('exact recovery canonical file is unavailable: ' + path)
    return base64.b64decode(value['content'], validate=False)


def _authority(*, with_snapshot=False):
    """Refresh the complete protection graph and exact merged execution scope."""
    registry, audit = gate._snapshot(for_deletion=True)
    canonical = audit.get('canonical') or {}
    main = canonical.get('main_sha')
    if audit.get('authority_state') != 'COMPLETE' or not re.fullmatch(r'[0-9a-f]{40}', str(main)):
        raise ValueError('exact recovery requires a fresh complete canonical snapshot')
    raw = _remote_bytes(AUTHORIZATION, main)
    local = retention._safe(ROOT / AUTHORIZATION)
    if local.read_bytes() != raw or _remote_bytes(SCRIPT, main) != Path(__file__).read_bytes():
        raise ValueError('exact recovery authorization and executable must be merged unchanged on canonical main')
    for name, module in (('candidate_retention', retention), ('candidate_archive', archive),
                         ('candidate_protection_gate', gate), ('candidate_protection_audit', protection),
                         ('candidate_lifecycle', lifecycle)):
        if _remote_bytes('scripts/' + name + '.py', main) != Path(module.__file__).read_bytes():
            raise ValueError('exact recovery dependency differs from canonical main: ' + name)
    auth = json.loads(raw)
    fields = {'schema_version', 'artifact_type', 'status', 'identity', 'path',
              'authority_ref', 'authority_body_sha256', 'owner_decision_request',
              'withdrawal_history', 'publisher_attestation_sha256', 'previous_device',
              'expected_device', 'expected_inode', 'owner_uid', 'scope', 'expected_volume'}
    if (set(auth) != fields or auth['schema_version'] != '1.0'
            or auth['artifact_type'] != 'integra.exact_721d_ownership_recovery_authorization'
            or auth['status'] != 'PRODUCT_OWNER_AUTHORIZED_ACTIVE'
            or auth['identity'] != IDENTITY or auth['path'] != RELATIVE or auth['scope'] != SCOPE
            or auth['previous_device'] != PREVIOUS_DEVICE or auth['expected_device'] != EXPECTED_DEVICE
            or auth['expected_inode'] != EXPECTED_INODE or auth['owner_uid'] != OWNER_UID
            or auth['owner_decision_request'] != {'path': REQUEST, 'sha256': REQUEST_SHA256}
            or not re.fullmatch(r'[0-9a-f]{64}', str(auth['publisher_attestation_sha256']))
            or set(auth['withdrawal_history']) != {'path', 'sha256'}
            or auth['withdrawal_history']['path'] != WITHDRAWAL
            or set(auth['expected_volume']) != {'mount_point', 'uuid', 'device'}
            or auth['expected_volume']['mount_point'] != '/System/Volumes/Data'
            or auth['expected_volume']['device'] != auth['expected_device']
            or not re.fullmatch(r'[0-9A-F-]{36}', str(auth['expected_volume']['uuid']))):
        raise ValueError('exact recovery authorization scope or identity differs')
    request = _remote_bytes(REQUEST, main)
    history_raw = _remote_bytes(WITHDRAWAL, main)
    if (_sha(request) != REQUEST_SHA256
            or _sha(history_raw) != auth['withdrawal_history']['sha256']):
        raise ValueError('exact recovery approved request or withdrawal history differs')
    reference = re.fullmatch(r'https://github\.com/Yurielo/integra/issues/293#issuecomment-([0-9]+)', auth['authority_ref'])
    if not reference:
        raise ValueError('exact recovery owner comment reference differs')
    comment = protection._api(f'repos/{protection.REPOSITORY}/issues/comments/{reference.group(1)}')
    body = comment.get('body', '')
    required = (TOKEN, REQUEST_SHA256, 'WITHDRAW_OWNER_ACCEPTANCE_REQUEST',
                'does not accept this Candidate', 'does not intend to promote', *IDENTITY.values())
    if (comment.get('html_url') != auth['authority_ref']
            or comment.get('user', {}).get('login', '').lower() != 'yurielo'
            or _sha(body.encode()) != auth['authority_body_sha256']
            or any(token not in body for token in required)):
        raise ValueError('exact recovery explicit owner authorization differs')
    withdrawals = [v for v in canonical.get('withdrawn_candidate_lifecycles', [])
                   if v.get('candidate_id') == IDENTITY['candidate_id']]
    grant = registry.get('withdrawal_deletion_authorizations', {}).get(RELATIVE)
    if (len(withdrawals) != 1 or any(withdrawals[0].get(k) != v for k, v in IDENTITY.items())
            or withdrawals[0].get('authority_ref') != auth['authority_ref']
            or withdrawals[0].get('authority_body_sha256') != auth['authority_body_sha256']
            or withdrawals[0].get('history_path') != WITHDRAWAL
            or withdrawals[0].get('history_sha256') != _sha(history_raw)
            or withdrawals[0].get('resulting_status') != 'WITHDRAWN_SUPERSEDED'
            or IDENTITY['candidate_id'] in audit.get('protected_identities', {})
            or IDENTITY['candidate_id'] in registry.get('selected_survivors', {})
            or not isinstance(grant, dict) or grant.get('path') != RELATIVE
            or any(grant.get(k) != v for k, v in IDENTITY.items())
            or grant.get('authority_ref') != auth['authority_ref']
            or grant.get('lifecycle') != 'WITHDRAWN_SUPERSEDED'):
        raise ValueError('exact recovery canonical withdrawal, hold release or deletion grant differs')
    if protection._api(f'repos/{protection.REPOSITORY}/git/ref/heads/main')['object']['sha'] != main:
        raise ValueError('canonical main changed during exact recovery authorization')
    binding = {'main_sha': main, 'authorization_sha256': _sha(raw),
               'registry_sha256': audit['registry_sha256'], 'withdrawal': withdrawals[0]}
    return (auth, binding, registry, audit) if with_snapshot else (auth, binding)


def _volume_identity():
    mount = Path('/System/Volumes/Data')
    value = plistlib.loads(subprocess.check_output(
        ['/usr/sbin/diskutil', 'info', '-plist', str(mount)], timeout=30))
    if value.get('MountPoint') != str(mount) or not value.get('VolumeUUID'):
        raise ValueError('current volume identity is unavailable')
    return {'mount_point': str(mount), 'uuid': value['VolumeUUID'], 'device': mount.stat().st_dev}


def _filesystem(package):
    info = retention._safe(package).lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError('exact recovery archive root is not a directory')
    return {'device': info.st_dev, 'inode': info.st_ino, 'owner_uid': info.st_uid,
            'mode': stat.S_IMODE(info.st_mode)}


def _verify(auth, catalog, record):
    package = retention._safe(BASE / RELATIVE)
    catalog_file = retention._safe(retention.catalog_path(BASE / 'Build Archive'))
    if (str(BASE / 'Build Archive') not in catalog.get('roots', [])
            or catalog.get('owner_uid') != os.getuid() or auth['owner_uid'] != os.getuid()
            or catalog.get('leases') or catalog.get('deletions')):
        raise ValueError('exact recovery catalog roots, owner or active transaction differs')
    matches = [name for name, row in catalog['artifacts'].items()
               if row.get('candidate_id') == IDENTITY['candidate_id']]
    if matches != [str(package)]:
        raise ValueError('exact recovery publisher target is absent or ambiguous')
    expected = _filesystem(package)
    if (expected['device'] != auth['expected_device'] or expected['inode'] != auth['expected_inode']
            or expected['owner_uid'] != auth['owner_uid']
            or BASE.stat().st_dev != expected['device'] or catalog_file.stat().st_dev != expected['device']
            or _volume_identity() != auth['expected_volume']):
        raise ValueError('exact recovery current volume, inode or UID changed')
    if (not isinstance(record, dict) or record.get('publisher_completed') is not True
            or record.get('historical') is not False
            or not record.get('publisher_run_id') or not record.get('publisher_start_token')
            or record.get('status') != 'AWAITING_OWNER_ACCEPTANCE'
            or any(record.get(k) != v for k, v in IDENTITY.items())):
        raise ValueError('exact recovery original publisher attestation differs')
    receipt = archive.verify_archive(package, IDENTITY)
    proposed = {**record, 'device': auth['expected_device']}
    if (not retention._ownership(package, proposed, receipt)
            or retention._publisher_live(record) or not retention._inactive(package)):
        raise ValueError('exact recovery publisher metadata, ownership or inactivity differs')
    return {'filesystem': expected, 'archive_verification': receipt,
            'complete_sha256': retention._sha(package / 'COMPLETE.json'),
            'inventory_sha256': retention._sha(package / 'inventory.json')}


def _immutable(path, data):
    """Publish a complete fsynced receipt without replacing an earlier one."""
    path = retention._safe(path)
    if path.exists():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or path.read_bytes() != data):
            raise ValueError('exact recovery immutable receipt differs: ' + path.name)
        return
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        # The archive publisher already supplies atomic no-replace rename.
        # A hard-link publication could leave nlink=2 after a process crash.
        archive._publish(Path(temporary), path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_receipt(path):
    path = retention._safe(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid()):
        raise ValueError('exact recovery receipt ownership/type differs')
    return path.read_bytes()


def _without_journal(catalog):
    value = deepcopy(catalog)
    value.pop(JOURNAL, None)
    return value


class _ReadOnlyResult(Exception):
    def __init__(self, result):
        self.result = result


def recover(*, apply=False):
    """Dry-run or resume the one exact metadata transaction under the old lock."""
    catalog_file = retention._safe(retention.catalog_path(BASE / 'Build Archive'))
    if not catalog_file.is_file() or not catalog_file.with_suffix('.lock').is_file():
        raise ValueError('exact recovery requires the existing shared catalog and lock')
    evidence = retention._safe(catalog_file.parent / 'evidence' / TRANSACTION)
    try:
        with retention.locked(catalog_file) as catalog:
            raw = catalog_file.read_bytes()
            if json.loads(raw) != catalog:
                raise ValueError('exact recovery refuses implicit catalog normalization')
            auth, authority = _authority()
            journal = catalog.get(JOURNAL)
            if journal:
                before_raw = _read_receipt(evidence / 'catalog-before.json')
                before_bytes = _read_receipt(evidence / 'BEFORE.json')
                before = json.loads(before_bytes)
                if (journal.get('transaction_id') != TRANSACTION
                        or journal.get('before_receipt_sha256') != _sha(before_bytes)
                        or before.get('catalog_before_sha256') != _sha(before_raw)
                        or before.get('authority') != authority):
                    raise ValueError('exact recovery journal, backup or canonical authority changed')
                baseline = json.loads(before_raw)
                if before['record_before'] != baseline['artifacts'].get(str(BASE / RELATIVE)):
                    raise ValueError('exact recovery original publisher backup differs')
                expected = deepcopy(baseline)
                if journal.get('state') in {'COMMITTED', 'COMPLETE'}:
                    expected['artifacts'][str(BASE / RELATIVE)]['device'] = auth['expected_device']
                elif journal.get('state') != 'PREPARED':
                    raise ValueError('exact recovery journal state is invalid')
                if _without_journal(catalog) != expected:
                    raise ValueError('exact recovery catalog changed outside its exact device update')
            else:
                before_raw = raw
                baseline = deepcopy(catalog)
                before = None
            original = baseline['artifacts'].get(str(BASE / RELATIVE))
            if (not isinstance(original, dict) or original.get('device') != auth['previous_device']
                    or retention._digest(original) != auth['publisher_attestation_sha256']):
                raise ValueError('exact recovery original publisher record is not the authorized attestation')
            verification = _verify(auth, catalog, original)
            proposed = {**original, 'device': auth['expected_device']}
            if before and (before['verification'] != verification or before['record_after'] != proposed):
                raise ValueError('exact recovery verified bytes or directory identity changed')
            result = {'transaction_id': TRANSACTION, 'identity': IDENTITY, 'path': RELATIVE,
                      'state': journal['state'] if journal else 'READY',
                      'previous_device': auth['previous_device'], 'expected_device': auth['expected_device'],
                      'evidence_directory': str(evidence), 'writes_performed': False}
            if not apply:
                raise _ReadOnlyResult(result)
            if journal and journal.get('state') == 'COMPLETE':
                completed_raw = _read_receipt(evidence / 'AFTER.json')
                completed = json.loads(completed_raw)
                if (journal.get('after_receipt_sha256') != _sha(completed_raw)
                        or completed.get('before_receipt_sha256') != journal['before_receipt_sha256']
                        or completed.get('record_after') != proposed
                        or completed.get('catalog_after_without_journal_sha256') != _sha(_bytes(_without_journal(catalog)))
                        or completed.get('verification') != verification):
                    raise ValueError('exact recovery completion receipt differs')
                raise _ReadOnlyResult({**result, 'state': 'ALREADY_APPLIED'})
            if not evidence.exists():
                evidence.mkdir(parents=True, mode=0o700)
            if evidence.stat().st_uid != os.getuid():
                raise ValueError('exact recovery receipt directory is foreign')
            if before is None:
                before = {'schema_version': '1.0', 'artifact_type': 'integra.exact_721d_ownership_recovery_before',
                          'transaction_id': TRANSACTION, 'identity': IDENTITY, 'path': RELATIVE,
                          'authority': authority, 'catalog_before_sha256': _sha(before_raw),
                          'record_before': original, 'record_after': proposed, 'verification': verification}
            _immutable(evidence / 'catalog-before.json', before_raw)
            _immutable(evidence / 'BEFORE.json', _bytes(before))
            if journal is None:
                journal = {'transaction_id': TRANSACTION, 'state': 'PREPARED',
                           'before_receipt_sha256': _sha(_bytes(before))}
                catalog[JOURNAL] = journal
                retention._persist(catalog_file, catalog)
            if journal['state'] == 'PREPARED':
                # Recheck only the bounded transaction, with no other record or
                # authority update between durable preparation and commit.
                if _authority() != (auth, authority) or _verify(auth, catalog, original) != verification:
                    raise ValueError('exact recovery precommit verification changed')
                catalog['artifacts'][str(BASE / RELATIVE)] = proposed
                journal['state'] = 'COMMITTED'
                retention._persist(catalog_file, catalog)
            after = {'schema_version': '1.0', 'artifact_type': 'integra.exact_721d_ownership_recovery_after',
                     'transaction_id': TRANSACTION, 'identity': IDENTITY,
                     'before_receipt_sha256': journal['before_receipt_sha256'],
                     'catalog_after_without_journal_sha256': _sha(_bytes(_without_journal(catalog))),
                     'record_after': proposed, 'verification': verification,
                     'changed_record_fields': ['device'], 'archive_payload_changed': False}
            _immutable(evidence / 'AFTER.json', _bytes(after))
            if journal.get('state') == 'COMPLETE' and journal.get('after_receipt_sha256') != _sha(_bytes(after)):
                raise ValueError('exact recovery completion receipt differs')
            journal.update(state='COMPLETE', after_receipt_sha256=_sha(_bytes(after)))
            retention._persist(catalog_file, catalog)
            return {**result, 'state': 'COMPLETE', 'writes_performed': True,
                    'before_receipt_sha256': journal['before_receipt_sha256'],
                    'after_receipt_sha256': journal['after_receipt_sha256']}
    except _ReadOnlyResult as outcome:
        return outcome.result


def _same_reconciliation_authority(previous, current):
    """Permit only a fresh canonical revision of the identical exact authority."""
    fields = {'main_sha', 'authorization_sha256', 'registry_sha256', 'withdrawal'}
    return (isinstance(previous, dict) and isinstance(current, dict)
            and set(previous) == fields == set(current)
            and all(isinstance(value['main_sha'], str)
                    and re.fullmatch(r'[0-9a-f]{40}', value['main_sha'])
                    for value in (previous, current))
            and all(previous[key] == current[key] for key in fields - {'main_sha'}))


def reconcile_target():
    """Mirror only 721d's canonical withdrawal after its complete device repair.

    The established reconciler still verifies every selected survivor and
    constructs the protection mirror. Its broad artifact replay runs only on a
    disposable copy; this operation admits exactly one withdrawn target record.
    """
    catalog_file = retention._safe(retention.catalog_path(BASE / 'Build Archive'))
    if not catalog_file.is_file() or not catalog_file.with_suffix('.lock').is_file():
        raise ValueError('exact reconciliation requires the existing shared catalog and lock')
    evidence = retention._safe(catalog_file.parent / 'evidence' / TRANSACTION)
    try:
        with retention.locked(catalog_file) as catalog:
            if json.loads(catalog_file.read_bytes()) != catalog:
                raise ValueError('exact reconciliation refuses implicit catalog normalization')
            auth, authority, registry, audit = _authority(with_snapshot=True)
            journal = catalog.get(JOURNAL) or {}
            before_raw = _read_receipt(evidence / 'catalog-before.json')
            before_bytes = _read_receipt(evidence / 'BEFORE.json')
            after_bytes = _read_receipt(evidence / 'AFTER.json')
            before, after = json.loads(before_bytes), json.loads(after_bytes)
            baseline = json.loads(before_raw)
            original = baseline.get('artifacts', {}).get(str(BASE / RELATIVE))
            if (journal.get('transaction_id') != TRANSACTION or journal.get('state') != 'COMPLETE'
                    or journal.get('before_receipt_sha256') != _sha(before_bytes)
                    or journal.get('after_receipt_sha256') != _sha(after_bytes)
                    or before.get('catalog_before_sha256') != _sha(before_raw)
                    or not _same_reconciliation_authority(before.get('authority'), authority)
                    or before.get('record_before') != original
                    or not isinstance(original, dict)
                    or original.get('device') != auth['previous_device']
                    or retention._digest(original) != auth['publisher_attestation_sha256']):
                raise ValueError('exact reconciliation requires a complete bound ownership transaction')
            repaired = {**original, 'device': auth['expected_device']}
            baseline['artifacts'][str(BASE / RELATIVE)] = repaired
            verification = _verify(auth, catalog, original)
            if (before.get('record_after') != repaired or before.get('verification') != verification
                    or after.get('record_after') != repaired or after.get('verification') != verification
                    or after.get('before_receipt_sha256') != journal['before_receipt_sha256']
                    or after.get('catalog_after_without_journal_sha256') != _sha(_bytes(baseline))
                    or after.get('changed_record_fields') != ['device']
                    or after.get('archive_payload_changed') is not False):
                raise ValueError('exact reconciliation ownership receipts or archive bytes changed')
            expected = lifecycle.replay_withdrawal(repaired, [authority['withdrawal']])
            current = catalog['artifacts'].get(str(BASE / RELATIVE))
            if (expected.get('status') != 'WITHDRAWN_SUPERSEDED'
                    or current not in (repaired, expected)):
                raise ValueError('exact reconciliation target differs from its authorized publisher or withdrawal')
            cloned = deepcopy(catalog)
            retention.reconcile_catalog(cloned, registry, audit, BASE)
            if cloned['artifacts'].get(str(BASE / RELATIVE)) != expected:
                raise ValueError('established reconciliation differs from the exact target withdrawal')
            # Recheck the physical and canonical boundary after the established
            # verifier's full survivor reads, before publishing any metadata.
            if (_authority() != (auth, authority)
                    or _verify(auth, catalog, original) != verification):
                raise ValueError('exact reconciliation authority or archive changed before commit')
            changed = (['protection'] if catalog.get('protection') != cloned.get('protection') else [])
            if current != expected:
                changed.append('artifacts[exact_721d]')
            result = {'transaction_id': TRANSACTION, 'identity': IDENTITY,
                      'state': 'TARGET_WITHDRAWAL_RECONCILED', 'writes_performed': True,
                      'changed_catalog_fields': changed}
            if current == expected and catalog.get('protection') == cloned.get('protection'):
                raise _ReadOnlyResult({**result, 'state': 'ALREADY_RECONCILED', 'writes_performed': False})
            catalog['protection'] = cloned['protection']
            catalog['artifacts'][str(BASE / RELATIVE)] = expected
            return result
    except _ReadOnlyResult as outcome:
        return outcome.result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--dry-run', action='store_true')
    operation.add_argument('--apply', action='store_true')
    operation.add_argument('--reconcile-target', action='store_true')
    arguments = parser.parse_args()
    try:
        result = reconcile_target() if arguments.reconcile_target else recover(apply=arguments.apply)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(2, 'EXACT_721D_RECOVERY_BLOCKED: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
