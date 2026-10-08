"""Offline business and fault acceptance; no production config or cloud transport."""
import importlib
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / 'scripts/core'))

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')

class BusinessAcceptance(unittest.TestCase):
    def setUp(self):
        self.s = importlib.import_module('supervision')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'projects/video'
        self.folder.mkdir(parents=True)
        self.entry = {'id':'video','path':'projects/video','title':'A video','version':'v1'}
        put(self.root/'projects.json', {'projects':[self.entry]})
        put(self.folder/'batches.json', ['part-one','part-two'])
        put(self.folder/'source_reference.json', {'source_key':'tiktok:0000011111222223333','record_id':'record-one'})

    def state(self, batch, status, **values):
        put(self.folder/batch/'task_state.json', dict(status=status, **values))

    def delivery(self):
        media = self.folder/'review/complete.mp4'
        media.parent.mkdir()
        media.write_bytes(b'fixture complete video')
        digest = hashlib.sha256(media.read_bytes()).hexdigest()
        put(self.folder/'presentation.json', {'schema_version':1,'result_video':'review/complete.mp4'})
        put(self.folder/'delivery.json', {'schema_version':1,'version':'v1','result_video':'review/complete.mp4','sha256':digest,'complete':True,'technical':{'media':True,'decode':True},'human_review':{'status':'PENDING'}})
        return media, digest

    def test_partial_archive_and_failed_segment_never_become_whole_delivery(self):
        self.state('part-one','ARCHIVED',taskId='known-one')
        self.state('part-two','FAILED',taskId='known-two')
        item=self.s.project_snapshot(self.root,self.entry)
        self.assertEqual(item['delivery']['state'],'NOT_DELIVERED')
        self.assertEqual(item['execution']['state'],'NEEDS_ATTENTION')
        self.assertFalse(item['actions']['may_create'])
        self.assertEqual(len(item['segments']),2)

    def test_complete_execution_does_not_hide_pending_human_review(self):
        self.delivery()
        for name in ('part-one','part-two'): self.state(name,'ARCHIVED',taskId=name)
        item=self.s.project_snapshot(self.root,self.entry)
        self.assertEqual(item['review']['state'],'PENDING')
        self.assertEqual(item['delivery']['state'],'READY_FOR_REVIEW')
        self.assertIn('待审核',item['stage_label'])

    def test_changed_final_video_invalidates_delivery_and_human_acceptance(self):
        video,_=self.delivery()
        video.write_bytes(b'changed fixture')
        item=self.s.project_snapshot(self.root,self.entry)
        self.assertEqual(item['delivery']['state'],'INVALID')
        self.assertNotEqual(item['review']['state'],'ACCEPTED')

    def test_archived_state_with_missing_original_is_a_recovery_alert(self):
        self.state('part-one','ARCHIVED',taskId='known')
        put(self.folder/'part-one/results/task-known/manifest.json',{'taskId':'known','files':[{'name':'missing.mp4','bytes':1,'sha256':'fake'}]})
        item=self.s.project_snapshot(self.root,self.entry)
        self.assertEqual(item['execution']['state'],'NEEDS_ATTENTION')
        self.assertTrue(item['anomalies'])

    def test_handoff_revision_files_are_immutable(self):
        data={'schema_version':1,'project_id':'video','source_key':'tiktok:0000011111222223333','record_id':'record-one','production_version':'v1','revision':1,'owner':'branch-one','stage':'PLANNING'}
        self.s.record_handoff(self.root,self.entry,data,expected_revision=0)
        with self.assertRaises(RuntimeError):self.s.record_handoff(self.root,self.entry,dict(data,stage='APPROVAL'),expected_revision=0)
        self.assertEqual(json.loads((self.folder/'handoffs-v1/000001.json').read_text())['stage'],'PLANNING')

    def test_known_task_and_unknown_submission_never_allow_create(self):
        for status,values in [('RUNNING',{'taskId':'known'}),('UPLOADING',{}),('SUBMITTING_OUTCOME_UNKNOWN',{})]:
            self.state('part-one',status,**values)
            self.assertFalse(self.s.project_snapshot(self.root,self.entry)['actions']['may_create'])

    def test_stale_heartbeat_is_unknown_not_failure(self):
        self.state('part-one','RUNNING',taskId='known',lastCheckedAt='2020-01-01T00:00:00+00:00')
        item=self.s.project_snapshot(self.root,self.entry)
        self.assertEqual(item['execution']['state'],'GENERATING')
        self.assertEqual(item['health']['state'],'STALE_UNKNOWN')
        self.assertFalse(item['actions']['may_create'])

    def test_stage_owners_timestamps_and_missing_heartbeat_do_not_authorize_work(self):
        from datetime import datetime,timezone
        stamp=datetime.now(timezone.utc).isoformat()
        put(self.folder/'handoff-state.json',{'owner':'branch-one','updated_at':stamp,'stages':{
            'PLANNING':{'owner':'writer-one','state':'IN_PROGRESS','updated_at':stamp,'next_step':'等待方案复核'}}})
        item=self.s.project_snapshot(self.root,self.entry)
        stages={s['key']:s for s in item['stages']}
        self.assertEqual(len(stages),10)
        self.assertEqual(stages['PLANNING']['owner'],'writer-one')
        self.assertEqual(stages['PLANNING']['updated_at'],stamp)
        self.assertEqual(stages['PLANNING']['next_step'],'等待方案复核')
        self.assertEqual(stages['PLANNING']['health']['state'],'OBSERVED')
        self.assertEqual(stages['GENERATING']['health']['state'],'NOT_OBSERVED')
        self.assertNotEqual(item['execution']['state'],'NEEDS_ATTENTION')
        self.assertFalse(item['actions']['may_create'])
        self.assertFalse(item['actions']['may_enqueue'])

    def test_blocked_project_does_not_block_other_project_preparation_or_registration(self):
        self.state('part-one','FAILED',taskId='failed')
        other=self.root/'projects/other'
        other.mkdir()
        put(other/'batches.json',['whole-film'])
        put(other/'approval.json',{'status':'APPROVED','upload_permitted':True,'submit_permitted':True,'approved_batches':[{'name':'whole-film','hashes':{}}]})
        entry={'id':'other','path':'projects/other','title':'Another video'}
        item=self.s.project_snapshot(self.root,entry)
        self.assertEqual(item['stage'],'READY_FOR_QUEUE')
        import global_queue
        put(self.root/'projects.json',{'projects':[self.entry,entry]})
        self.assertIn('other/whole-film',[j['id'] for j in global_queue.scan(self.root)['jobs']])

    def test_same_source_version_handoff_is_idempotent_and_identity_conflict_rejected(self):
        data={'schema_version':1,'project_id':'video','source_key':'tiktok:0000011111222223333','record_id':'record-one','production_version':'v1','revision':1,'owner':'branch-one','stage':'PLANNING','inputs':[],'artifacts':[]}
        first=self.s.record_handoff(self.root,self.entry,data,expected_revision=0)
        again=self.s.record_handoff(self.root,self.entry,data,expected_revision=1)
        self.assertEqual(first['revision'],again['revision'])
        changed=dict(data,record_id='wrong')
        with self.assertRaises(ValueError):self.s.record_handoff(self.root,self.entry,changed,expected_revision=1)

    def test_readonly_panel_escapes_titles_and_exposes_no_generation_controls(self):
        self.entry['title']='<script>bad()</script>'
        page=self.s.render_panel(self.s.snapshot(self.root))
        self.assertNotIn('<script>bad()',page)
        self.assertIn('编剧',page)
        self.assertIn('待审批',page)
        self.assertIn('原片',page)
        self.assertNotIn('HUB_CONTROL',page)
        self.assertNotIn('apiKey',page)

    def test_repeated_source_version_registration_is_one_project_and_queue_job(self):
        other=self.root/'projects/ready'
        other.mkdir()
        put(other/'batches.json',['whole-film'])
        put(other/'approval.json',{'status':'APPROVED','upload_permitted':True,'submit_permitted':True,'approved_batches':[{'name':'whole-film','hashes':{}}]})
        ready={'id':'ready','path':'projects/ready','title':'Ready video','source_key':'tiktok:0000011111222224444','record_id':'row-other','production_version':'v1'}
        first=self.s.register_ready_project(self.root,ready)
        second=self.s.register_ready_project(self.root,dict(ready,id='different-display-id'))
        self.assertEqual(first['project_id'],second['project_id'])
        import global_queue
        self.assertEqual(sum(j['project']=='ready' for j in global_queue.scan(self.root)['jobs']),1)

    def test_legacy_duplicate_registry_path_does_not_create_a_second_queue_job(self):
        put(self.folder/'approval.json',{'status':'APPROVED','upload_permitted':True,'submit_permitted':True,'approved_batches':[{'name':'part-one','hashes':{}},{'name':'part-two','hashes':{}}]})
        put(self.root/'projects.json',{'projects':[self.entry,dict(self.entry,id='duplicate-alias')]})
        import global_queue
        jobs=global_queue.scan(self.root)['jobs']
        self.assertEqual(len(jobs),2)
        self.assertEqual(len({j['path'] for j in jobs}),2)

    def test_unrelated_failure_does_not_serialize_cloud_jobs(self):
        import global_queue
        jobs=[{'id':'failed','status':'FAILED','taskId':'historical','order':0}]+[{'id':str(n),'status':'WAITING','order':n} for n in range(1,6)]
        self.assertEqual(len(global_queue.select(jobs,0)),3)
        self.assertEqual(len(global_queue.select(jobs,2)),1)

    def test_sync_unknown_is_a_local_alert_and_preserves_final_video(self):
        from test_lark_contract import fixture,receipt_for,BINDING
        import lark_diff
        self.delivery()
        item=self.s.project_snapshot(self.root,self.entry)
        payload,snap=fixture();payload['local_revision']=item['local_revision']
        req=lark_diff.build_request(payload,snap,binding=BINDING)['request'];request_id=req['request_id']
        path=self.root/f'coordination/lark-outbox/{request_id}.json';put(path,req)
        put(self.root/f'coordination/lark-receipts/{request_id}.json',receipt_for(req,'RECONCILE_REQUIRED',hashlib.sha256(path.read_bytes()).hexdigest()))
        updated=self.s.project_snapshot(self.root,self.entry)
        self.assertEqual(updated['sync']['state'],'RECONCILE_REQUIRED')
        self.assertEqual(updated['delivery']['state'],'READY_FOR_REVIEW')
        self.assertTrue(updated['anomalies'])

    def test_unchanged_observation_does_not_repeat_local_notifications(self):
        data=self.s.snapshot(self.root)
        self.assertTrue(self.s.persist_observation(self.root,data))
        self.assertFalse(self.s.persist_observation(self.root,self.s.snapshot(self.root)))

class RecoveryAcceptance(unittest.TestCase):
    def test_probe_unavailable_is_distinct_from_confirmed_missing_original(self):
        audit=importlib.import_module('archive_integrity')
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);target=folder/'results/task-known';target.mkdir(parents=True)
            media=target/'fixture.mp4';media.write_bytes(b'fixture')
            put(target/'manifest.json',{'taskId':'known','files':[{'name':'fixture.mp4','bytes':7,'sha256':hashlib.sha256(b'fixture').hexdigest()}]})
            def unavailable(path):raise FileNotFoundError('Synthetic missing ffprobe')
            self.assertEqual(audit.verify_archive(folder,'known',probe=unavailable)['issue'],'PROBE_UNAVAILABLE')
            media.unlink()
            self.assertEqual(audit.verify_archive(folder,'known',probe=unavailable)['issue'],'MISSING_OR_CORRUPT')

    def test_corrupt_missing_wrong_hash_and_invalid_media_archive_are_rejected(self):
        audit=importlib.import_module('archive_integrity')
        with tempfile.TemporaryDirectory() as td:
            batch=Path(td);target=batch/'results/task-known';target.mkdir(parents=True)
            media=target/'output.mp4';media.write_bytes(b'valid fixture')
            put(target/'manifest.json',{'taskId':'known','files':[{'name':'output.mp4','bytes':media.stat().st_size,'sha256':hashlib.sha256(media.read_bytes()).hexdigest()}]})
            good=lambda p:{'streams':[{'codec_type':'video'}],'format':{'duration':'1.0'}}
            self.assertTrue(audit.verify_archive(batch,'known',probe=good)['valid'])
            media.write_bytes(b'bad')
            self.assertFalse(audit.verify_archive(batch,'known',probe=good)['valid'])
            media.unlink()
            self.assertFalse(audit.verify_archive(batch,'known',probe=good)['valid'])
            media.write_bytes(b'valid fixture')
            self.assertFalse(audit.verify_archive(batch,'known',probe=lambda p:{'streams':[]})['valid'])

    def test_cached_manifest_does_not_bypass_collector_integrity(self):
        import collector
        with tempfile.TemporaryDirectory() as td:
            batch=Path(td);put(batch/'task_state.json',{'status':'ARCHIVED','taskId':'known'})
            put(batch/'results/task-known/manifest.json',{'taskId':'known','files':[{'name':'missing.mp4','bytes':5,'sha256':'bad'}]})
            with patch.object(collector,'post',side_effect=AssertionError('cloud forbidden')):
                result=collector.collect(batch,'fixture',query_only=True)
            self.assertEqual(result['status'],'DOWNLOAD_ERROR')

    def test_postproduction_needs_quality_and_music_authorization_and_frozen_inputs(self):
        post=importlib.import_module('postproduction_records')
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);video=folder/'raw.mp4';video.write_bytes(b'fixture video')
            spec={'schema_version':1,'version':'edit-v1','segments':[{'file':'raw.mp4','sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'start':0,'end':1}], 'audio':{'mode':'none'},'quality_review':{'status':'PENDING'}}
            self.assertEqual(post.validate_plan(folder,spec)['state'],'AWAITING_QUALITY_REVIEW')
            spec['quality_review']={'status':'ACCEPTED','evidence':'human-message'}
            spec['audio']={'mode':'bgm','file':'raw.mp4','sha256':spec['segments'][0]['sha256'],'authorized':False}
            self.assertEqual(post.validate_plan(folder,spec)['state'],'AWAITING_AUDIO_APPROVAL')
            spec['audio']['authorized']=True;spec['audio']['authorization_evidence']='human-message'
            self.assertEqual(post.validate_plan(folder,spec)['state'],'READY')
            video.write_bytes(b'changed')
            with self.assertRaises(ValueError):post.validate_plan(folder,spec)

class WriterAcceptance(unittest.TestCase):
    def test_project_owner_can_write_own_handoff_but_not_shared_queue(self):
        store=importlib.import_module('durable_store')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            put(root/'coordination/writer-authority.json',{'schema_version':1,'writer_id':'main','epoch':1,'code_version':store.CODE_VERSION,'project_writers':{'branch':{'paths':['projects/own']}}})
            with store.session(root,'branch',1):
                store.save(root/'projects/own/handoff-state.json',{'revision':1})
                with self.assertRaises(PermissionError):store.save(root/'queue_state.json',{'jobs':[]})
                with self.assertRaises(PermissionError):store.save(root/'projects/other/handoff-state.json',{'revision':1})

    def test_old_epoch_old_version_and_stale_revision_cannot_overwrite_shared_state(self):
        store=importlib.import_module('durable_store')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);put(root/'coordination/writer-authority.json',{'schema_version':1,'writer_id':'main','epoch':2,'code_version':store.CODE_VERSION})
            path=root/'queue_state.json';put(path,{'jobs':[]})
            with self.assertRaises(PermissionError):
                with store.session(root,'main',1):store.save(path,{'jobs':['old']})
            with self.assertRaises(PermissionError):
                with store.session(root,'main',2,code_version='old'):store.save(path,{'jobs':['old']})
            with store.session(root,'main',2):
                store.read(path)
                put(path,{'jobs':['other-writer']})
                with self.assertRaises(RuntimeError):store.save(path,{'jobs':['stale']})
            self.assertEqual(json.loads(path.read_text())['jobs'],['other-writer'])

    def test_unfenced_legacy_write_rejected_when_authority_active(self):
        store=importlib.import_module('durable_store')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);put(root/'coordination/writer-authority.json',{'schema_version':1,'writer_id':'main','epoch':1,'code_version':store.CODE_VERSION})
            with self.assertRaises(PermissionError):store.save(root/'projects.json',{'projects':[]})

class LarkAcceptance(unittest.TestCase):
    def test_diff_is_two_columns_only_stale_snapshot_never_authorizes_work(self):
        from test_lark_contract import fixture,BINDING
        sync=importlib.import_module('lark_diff')
        item,snap=fixture();snap['captured_at']='2020-01-01T00:00:00+00:00'
        request=sync.build_request(item,snap,binding=BINDING)
        self.assertEqual(request['status'],'STALE_SNAPSHOT')
        self.assertFalse(request['may_dispatch'])
        snap['captured_at']=sync.now()
        request=sync.build_request(item,snap,binding=BINDING)
        self.assertEqual(set(request['request']['desired']),{'复刻阶段','复刻任务'})
        self.assertNotIn('处理状态',json.dumps(request,ensure_ascii=False))
        self.assertFalse(request['may_dispatch'])

    def test_sync_failure_does_not_touch_local_delivery_and_receipt_is_version_bound(self):
        from test_lark_contract import fixture,receipt_for,BINDING
        sync=importlib.import_module('lark_diff')
        item,snap=fixture();request=sync.build_request(item,snap,binding=BINDING)['request'];receipt=receipt_for(request,'FAILED')
        result=sync.check_receipt(request,receipt,request_sha256='a'*64)
        self.assertEqual(result['sync_state'],'FAILED')
        self.assertTrue(result['preserve_local_results'])
        receipt.update(status='APPLIED',readback={'复刻阶段':'wrong','复刻任务':'视频'})
        self.assertEqual(sync.check_receipt(request,receipt,request_sha256='a'*64)['sync_state'],'CONFLICT')

    def test_unknown_cloud_write_requires_reconciliation_not_retry(self):
        from test_lark_contract import fixture,receipt_for,BINDING
        sync=importlib.import_module('lark_diff')
        item,snap=fixture();request=sync.build_request(item,snap,binding=BINDING)['request']
        result=sync.check_receipt(request,receipt_for(request,'UNKNOWN'),request_sha256='a'*64)
        self.assertEqual(result['sync_state'],'RECONCILE_REQUIRED')
        self.assertFalse(result['may_retry'])

if __name__=='__main__':unittest.main()
