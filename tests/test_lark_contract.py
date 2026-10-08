"""Fixed-contract checks; optional peer integration uses temporary output and fake reads."""
import copy
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/core'))
import lark_diff

TARGET = {'base_token':'fixtureBaseToken','table_id':'tblFixture','view_id':'vewFixture'}
BINDING = {'schema_version':1,'target':TARGET,'fields':{
    '复刻阶段':{'field_id':'fldStageFixture','type':3},
    '复刻任务':{'field_id':'fldTaskFixture','type':1}}}
SOURCE = 'tiktok:0000011111222223333'

def fixture():
    item = {'project_id':'video','source_key':SOURCE,'record_id':'recFixture1',
            'local_revision':'review-v1','stage_label':'需处理','task_label':'等待人工决定'}
    snap = {'schema_version':1,'snapshot_id':str(uuid.uuid4()),'version':'lark-snapshot/v1',
            'target':copy.deepcopy(TARGET),'status':'ok','read_source':'live','captured_at':lark_diff.now(),
            'fields':[{'field_name':'复刻阶段','field_id':'fldStageFixture','type':3},
                      {'field_name':'复刻任务','field_id':'fldTaskFixture','type':1}],
            'records':[{'record_id':'recFixture1','fields':{'来源去重键':SOURCE,
                        '复刻阶段':'生成待审核','复刻任务':[{'text':'旧任务'}],'处理状态':'用户选择'}}]}
    snap['_file_sha256'] = hashlib.sha256(json.dumps(snap,ensure_ascii=False).encode()).hexdigest()
    return item,snap

def write_binding(root, binding=BINDING):
    path=Path(root)/'coordination/lark-target.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(binding),encoding='utf-8')


def receipt_for(req, status='APPLIED', digest='a'*64):
    return dict({key:copy.deepcopy(req[key]) for key in ('schema_version','request_id','target','project_id',
                'record_id','source_key','local_revision','snapshot_revision','input_snapshot')},
                request_sha256=digest,status=status,checked_at=lark_diff.now(),readback_at=lark_diff.now(),
                readback=copy.deepcopy(req['desired']),verified_record_ids=[req['record_id']])

class ContractTests(unittest.TestCase):
    def test_strict_envelope_separates_local_status_and_normalizes_old_text(self):
        item,snap=fixture(); result=lark_diff.build_request(item,snap,binding=BINDING)
        self.assertEqual(result['status'],'READY')
        req=result['request']
        self.assertEqual(set(req),{'schema_version','request_id','project_id','record_id','source_key',
            'local_revision','snapshot_revision','observed_at','created_at','expires_at','target',
            'input_snapshot','expected','desired'})
        self.assertEqual(str(uuid.UUID(req['request_id'])),req['request_id'])
        self.assertEqual(req['expected']['复刻任务'],'旧任务')
        self.assertEqual(req['target'],TARGET)
        self.assertEqual(req['input_snapshot']['sha256'],snap['_file_sha256'])
        self.assertFalse(result['may_dispatch'])
        self.assertNotIn('处理状态',json.dumps(req,ensure_ascii=False))
        self.assertLessEqual(datetime.datetime.fromisoformat(req['expires_at'])-
                             datetime.datetime.fromisoformat(req['created_at']),datetime.timedelta(minutes=15))

    def test_unbound_historical_stale_duplicate_and_schema_mismatch_snapshots_block(self):
        item,snap=fixture()
        cases=[]
        missing=copy.deepcopy(snap);missing.pop('_file_sha256');cases.append(missing)
        history=copy.deepcopy(snap);history['read_source']='historical';cases.append(history)
        stale=copy.deepcopy(snap);stale['captured_at']='2020-01-01T00:00:00+00:00';cases.append(stale)
        duplicate=copy.deepcopy(snap);duplicate['records']*=2;cases.append(duplicate)
        wrong=copy.deepcopy(snap);wrong['fields'][0]['type']=1;cases.append(wrong)
        for invalid in cases:
            with self.subTest(snapshot=invalid):
                result=lark_diff.build_request(item,invalid,binding=BINDING)
                self.assertNotEqual(result['status'],'READY')
                self.assertIsNone(result.get('request'))

    def test_receipt_success_requires_hash_all_identity_and_actual_readback(self):
        item,snap=fixture();req=lark_diff.build_request(item,snap,binding=BINDING)['request'];receipt=receipt_for(req)
        self.assertEqual(lark_diff.check_receipt(req,receipt,request_sha256='a'*64)['sync_state'],'APPLIED')
        for key,value in [('request_sha256','b'*64),('record_id','recOther'),('source_key','tiktok:9999999999999'),
                          ('snapshot_revision',str(uuid.uuid4())),('readback_at',None),('readback',{})]:
            bad=dict(receipt,**{key:value})
            self.assertEqual(lark_diff.check_receipt(req,bad,request_sha256='a'*64)['sync_state'],'CONFLICT')
        self.assertEqual(lark_diff.check_receipt(req,receipt)['sync_state'],'CONFLICT')

    def test_unknown_receipt_never_retries(self):
        item,snap=fixture();req=lark_diff.build_request(item,snap,binding=BINDING)['request']
        result=lark_diff.check_receipt(req,receipt_for(req,'UNKNOWN'),request_sha256='a'*64)
        self.assertEqual(result['sync_state'],'RECONCILE_REQUIRED')
        self.assertFalse(result['may_retry']);self.assertTrue(result['preserve_local_results'])

    def test_outbox_reuses_identical_request_bytes_and_uuid(self):
        import supervision
        item,snap=fixture();item.update(lark_stage=item['stage_label'])
        with tempfile.TemporaryDirectory() as td,patch.object(supervision,'snapshot',return_value={'projects':[item]}):
            write_binding(td)
            first=supervision.generate_lark_requests(td,snap)[0]
            path=Path(td)/'coordination/lark-outbox'/f"{first['request']['request_id']}.json"
            original=path.read_bytes()
            second=supervision.generate_lark_requests(td,snap)[0]
            self.assertEqual(second['request'],first['request']);self.assertEqual(path.read_bytes(),original)
            self.assertEqual(len(list(path.parent.glob('*.json'))),1)

    def test_uncertain_receipt_blocks_new_request_even_after_snapshot_refresh(self):
        import supervision
        item,snap=fixture();item.update(lark_stage=item['stage_label'])
        with tempfile.TemporaryDirectory() as td,patch.object(supervision,'snapshot',return_value={'projects':[item]}):
            write_binding(td)
            req=supervision.generate_lark_requests(td,snap)[0]['request']
            outbox=Path(td)/'coordination/lark-outbox';original=(outbox/f"{req['request_id']}.json").read_bytes()
            receipt=receipt_for(req,'UNKNOWN',hashlib.sha256(original).hexdigest())
            returned=Path(td)/'coordination/lark-receipts'/f"{req['request_id']}.json"
            returned.parent.mkdir(parents=True);returned.write_text(json.dumps(receipt),encoding='utf-8')
            snap['snapshot_id']=str(uuid.uuid4())
            result=supervision.generate_lark_requests(td,snap)[0]
            self.assertEqual(result['status'],'RECONCILE_REQUIRED')
            self.assertEqual(len(list(outbox.glob('*.json'))),1)

class LocalBindingTests(unittest.TestCase):
    def run_preview(self, root, item, snap):
        import supervision
        item=dict(item,lark_stage=item['stage_label'])
        with patch.object(supervision,'snapshot',return_value={'projects':[item]}):
            return supervision.generate_lark_requests(root,snap)[0]

    def test_missing_binding_does_not_infer_target_from_snapshot_or_create_outbox(self):
        item,snap=fixture()
        with tempfile.TemporaryDirectory() as td:
            result=self.run_preview(td,item,snap)
            self.assertEqual(result['status'],'LARK_NOT_CONFIGURED')
            self.assertIsNone(result['request'])
            self.assertFalse((Path(td)/'coordination/lark-outbox').exists())

    def test_local_binding_selects_target_and_still_rejects_wrong_table_or_fields(self):
        item,snap=fixture()
        snap['target']={'base_token':'syntheticBase','table_id':'tblSynthetic','view_id':'vewSynthetic'}
        snap['fields'][0]['field_id']='fldStageSynthetic'
        snap['fields'][1]['field_id']='fldTaskSynthetic'
        config={'schema_version':1,'target':snap['target'],
                'fields':{f['field_name']:{'field_id':f['field_id'],'type':f['type']} for f in snap['fields']}}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'coordination/lark-target.json';path.parent.mkdir()
            path.write_text(json.dumps(config),encoding='utf-8')
            result=self.run_preview(td,item,snap)
            self.assertEqual(result['status'],'READY')
            self.assertEqual(result['request']['target'],config['target'])
            for field in ('target','fields'):
                wrong=copy.deepcopy(snap)
                if field=='target':wrong[field]['table_id']='tblDifferent'
                else:wrong[field][0]['field_id']='fldDifferent'
                blocked=self.run_preview(td,item,wrong)
                self.assertEqual(blocked['status'],'IDENTITY_OR_SNAPSHOT_CONFLICT')
                self.assertIsNone(blocked['request'])

    def test_invalid_binding_preserves_existing_requests(self):
        item,snap=fixture()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'coordination/lark-target.json';path.parent.mkdir()
            original=path.parent/'lark-outbox/existing.json';original.parent.mkdir()
            original.write_bytes(b'{"preserve":"existing-request"}')
            for value in ('{broken',json.dumps({'schema_version':1,'target':snap['target'],'fields':{}})):
                path.write_text(value,encoding='utf-8')
                result=self.run_preview(td,item,snap)
                self.assertEqual(result['status'],'INVALID_LARK_CONFIGURATION')
                self.assertIsNone(result['request'])
                self.assertEqual(original.read_bytes(),b'{"preserve":"existing-request"}')


@unittest.skipUnless(os.environ.get('H3_LARK_ADAPTER'), 'Set H3_LARK_ADAPTER for offline peer fixture')
class PeerPreviewTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('H3_LARK_BINDING'),'Set H3_LARK_BINDING for the peer target fixture')
    def test_real_adapter_preview_accepts_h3_bytes_without_network_or_commit(self):
        spec=importlib.util.spec_from_file_location('peer_lark_fixture',os.environ['H3_LARK_ADAPTER'])
        peer=importlib.util.module_from_spec(spec);spec.loader.exec_module(peer)
        item,snap=fixture()
        binding=json.loads(Path(os.environ['H3_LARK_BINDING']).read_text(encoding='utf-8-sig'))
        target,fields=lark_diff.validate_binding(binding)
        snap['fields']=[dict(field_name=name,**field) for name,field in fields.items()]
        class FakeRead:
            def inspect(self):
                return dict(target,fields=snap['fields'],records=snap['records'],views=[],
                            primary_view={'view_id':target['view_id']})
        with tempfile.TemporaryDirectory() as td:
            adapter=peer.Adapter(td,FakeRead())
            captured=adapter.capture();captured['_file_sha256']=adapter.snapshot_reference(captured['snapshot_id'])['sha256']
            result=lark_diff.build_request(item,captured,binding=binding)
            self.assertEqual(result['status'],'READY')
            import durable_store
            req=result['request'];adapter.validate_request(req)
            original=Path(td)/'h3-outbox'/f"{req['request_id']}.json"
            durable_store.save(original,req)
            adapter.data_path('requests',req['request_id']).write_bytes(original.read_bytes())
            preview=adapter.preview(req['request_id'])
            self.assertEqual(preview['status'],'READY')
            self.assertEqual(preview['request_sha256'],hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertEqual(preview['patch']['expected'],req['expected'])
            self.assertEqual(preview['patch']['desired'],req['desired'])
            returned=receipt_for(req,digest=preview['request_sha256'])
            self.assertEqual(lark_diff.check_receipt(req,returned,request_sha256=preview['request_sha256'])['sync_state'],'APPLIED')
            self.assertEqual(lark_diff.check_receipt(req,dict(returned,status='UNKNOWN'),request_sha256=preview['request_sha256'])['sync_state'],'RECONCILE_REQUIRED')

    @unittest.skipUnless(os.environ.get('H3_LARK_EXAMPLE'),'Set H3_LARK_EXAMPLE for original-file comparison')
    def test_original_peer_example_and_snapshot_hash_match_offline_reconstruction(self):
        example_path=Path(os.environ['H3_LARK_EXAMPLE']);example=json.loads(example_path.read_text(encoding='utf-8'))
        adapter_root=example_path.parent
        old_path=adapter_root/'requests'/f"{example['request_id']}.json"
        old_bytes=old_path.read_bytes();old=json.loads(old_bytes)
        self.assertEqual(hashlib.sha256(old_bytes).hexdigest(),example['request_sha256'])
        snapshot_path=adapter_root/'snapshots'/f"{example['input_snapshot']['snapshot_id']}.json"
        snap_bytes=snapshot_path.read_bytes();snap=json.loads(snap_bytes)
        self.assertEqual(hashlib.sha256(snap_bytes).hexdigest(),example['input_snapshot']['sha256'])
        snap['_file_sha256']=hashlib.sha256(snap_bytes).hexdigest()
        item={key:old[key] for key in ('project_id','source_key','record_id','local_revision')}
        item.update(stage_label=old['desired']['复刻阶段'],task_label=old['desired']['复刻任务'])
        binding={'schema_version':1,'target':old['target'],'fields':{
            f['field_name']:{'field_id':f['field_id'],'type':f['type']} for f in snap['fields']
            if f['field_name'] in ('复刻阶段','复刻任务')}}
        # Frozen past time is an offline fixture only. The original snapshot is not refreshed or exported.
        with patch.object(lark_diff,'now',return_value=old['created_at']):
            result=lark_diff.build_request(item,snap,binding=binding)
        self.assertEqual(result['status'],'NO_CHANGE')
        req=result['request'];self.assertEqual(set(req),set(old))
        for key in ('target','input_snapshot','expected','desired','observed_at','snapshot_revision'):
            self.assertEqual(req[key],old[key])
        spec=importlib.util.spec_from_file_location('peer_lark_example',os.environ['H3_LARK_ADAPTER'])
        peer=importlib.util.module_from_spec(spec);spec.loader.exec_module(peer)
        with tempfile.TemporaryDirectory() as td:
            adapter=peer.Adapter(td,clock=lambda:datetime.datetime.fromisoformat(old['created_at']))
            adapter.data_path('snapshots',snap['snapshot_id']).write_bytes(snap_bytes)
            adapter.save_request(req)
            self.assertEqual(adapter.preview(req['request_id'])['status'],'NO_CHANGE')

if __name__=='__main__':unittest.main()
