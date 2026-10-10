"""Non-mutating negative/positive tests of exact ninth-copy operator."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('exception227','/private/tmp/integra-227-one-time-retention.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ExceptionTests(unittest.TestCase):
    def publication_case(self,change=None,twice=False):
        original={str(i):{'hash':str(i)} for i in range(8)}
        authority=dict(original_packages=original,policy_hashes={'exact':'policy'})
        bound=dict(source=m.SOURCE_SHA,candidate_id='synthetic-new',bundle_digest='synthetic-bundle')
        audit=dict(canonical={'main_sha':m.MAIN_SHA},blockers=[],full_copies=8,
                   archive_bytes=m.BYTE_CAP-m.EXPECTED,free_bytes=m.FLOOR+m.EXPECTED)
        catalog=dict(leases={'owned':{'pid':1}})
        root=m.ARCHIVE
        actual=original
        if change=='source': bound=bound|{'source':'wrong'}
        if change=='root': root=m.ARCHIVE/'wrong'
        if change=='lease': catalog=dict(leases={'owned':{},'foreign':{}})
        if change=='owner': owner=False
        else: owner=True
        if change=='changed': actual=original|{'0':{'hash':'changed'}}
        if change=='extra': actual=original|{'extra':{}}
        if change=='blocker': audit=audit|{'blockers':['INTEGRITY_FAIL']}
        if change=='main': audit=audit|{'canonical':{'main_sha':'wrong'}}
        if change=='bytes': audit=audit|{'archive_bytes':m.BYTE_CAP}
        if change=='free': audit=audit|{'free_bytes':m.FLOOR}
        if change=='authority': changed_authority={}
        else: changed_authority=authority
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            path=Path(temp).resolve()/'catalog.json'
            path.write_text(json.dumps(catalog))  # isolated test fixture only
            stack.enter_context(patch.object(m,'read',side_effect=lambda name: bound if name=='incoming-identity.json' else changed_authority))
            stack.enter_context(patch.object(m.retention,'catalog_path',return_value=path))
            stack.enter_context(patch.object(m.retention,'_lease_caller',return_value=owner))
            stack.enter_context(patch.object(m,'fingerprints',return_value=actual))
            stack.enter_context(patch.object(m.gate,'_snapshot',return_value=({},audit)))
            stack.enter_context(patch.object(m,'policy_hashes',return_value={'exact':'policy'}))
            stack.enter_context(patch.dict(m.os.environ,{'INTEGRA_RETENTION_BUILD_LEASE':'owned'}))
            with m.scoped_exception(authority):
                m.gate.require_archive_publication(root,m.EXPECTED)
                if twice: m.gate.require_archive_publication(root,m.EXPECTED)

    def test_publication_exact_scope(self):
        self.publication_case()
        for change in ['source','root','lease','owner','changed','extra','blocker','main','bytes','free','authority']:
            with self.subTest(change=change), self.assertRaises(ValueError): self.publication_case(change)
        with self.assertRaisesRegex(ValueError,'second archive'): self.publication_case(twice=True)

    def test_wrong_source_or_main(self):
        for source,main in [('bad',m.MAIN_SHA),(m.SOURCE_SHA,'bad')]:
            with self.assertRaisesRegex(ValueError,'binding differs'):
                m.source_check(source,main)

    def test_capacity_bounds(self):
        m.capacity(8,m.BYTE_CAP-m.EXPECTED,m.EXPECTED,m.FLOOR+m.EXPECTED)
        for args in [(9,0,1,m.FLOOR+1),(7,0,1,m.FLOOR+1),
                     (8,m.BYTE_CAP,1,m.FLOOR+1),(8,0,1,m.FLOOR),
                     (8,0,m.EXPECTED+1,100*m.FLOOR),(8,0,0,100*m.FLOOR),
                     (8,0,True,100*m.FLOOR)]:
            with self.assertRaises(ValueError): m.capacity(*args)

    def test_preservation_and_single_new_identity(self):
        original={str(i):{'hash':str(i)} for i in range(8)}
        m.verify_preservation(original,original)
        m.verify_preservation(original,original|{'new':{}},'new')
        for actual,new in [(original|{'wrong':{}},'new'),
                           (original|{'new':{},'extra':{}},'new'),
                           (original|{'0':{'hash':'changed'}},None),
                           ({k:v for k,v in original.items() if k!='0'},None)]:
            with self.assertRaises(ValueError): m.verify_preservation(original,actual,new)

    def test_only_count_blocker_discharged(self):
        identity=dict(candidate_id='exact',bundle_digest='bundle',manifest_digest='manifest')
        original={str(i):{} for i in range(8)}
        actual=original|{str(m.ARCHIVE/'exact/bundle'):{}}
        raw=dict(full_copies=9,archive_bytes=m.BYTE_CAP,free_bytes=m.FLOOR,
                 blockers=['ARCHIVE_COPY_CAP_EXCEEDED'])
        before=json.dumps(raw,sort_keys=True)
        result=m.discharge(raw,identity,original,actual)
        self.assertEqual(result['status'],'PASS_EXACT_OWNER_EXCEPTION')
        self.assertEqual(json.dumps(raw,sort_keys=True),before)
        for change in [dict(blockers=['ARCHIVE_COPY_CAP_EXCEEDED','INTEGRITY_FAIL']),
                       dict(blockers=[]),dict(full_copies=10),dict(archive_bytes=m.BYTE_CAP+1),
                       dict(free_bytes=m.FLOOR-1)]:
            with self.assertRaises(ValueError): m.discharge(raw|change,identity,original,actual)
        with self.assertRaises(ValueError):
            m.discharge(raw,identity|{'bundle_digest':'substitute'},original,actual)

    def test_scoped_default_restored_and_deletion_forbidden(self):
        gate=m.gate.require_archive_publication
        with self.assertRaisesRegex(RuntimeError,'test interruption'):
            with m.scoped_exception({}):
                self.assertEqual(m.retention.MAX_COPIES,9)
                for call in [m.retention.maintenance,m.gate.require_deletion]:
                    with self.assertRaisesRegex(ValueError,'forbidden'): call(None)
                raise RuntimeError('test interruption')
        self.assertEqual(m.retention.MAX_COPIES,8)
        self.assertIs(m.gate.require_archive_publication,gate)

    def test_durable_consumption_no_reuse_or_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp).resolve()/'CONSUMED.json'
            m.exclusive(target,{'attempt':1})
            with self.assertRaises(FileExistsError): m.exclusive(target,{'attempt':2})
            self.assertEqual(json.loads(target.read_bytes()),{'attempt':1})
            link=Path(temp).resolve()/'link'
            link.symlink_to(target)
            with self.assertRaises(ValueError): m.exclusive(link,{'attempt':2})

if __name__=='__main__': unittest.main(verbosity=2)
