"""Offline selected-task supervision; synthetic IDs and temporary data only."""
import copy, datetime, hashlib, importlib, importlib.util, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP/'scripts/core'))
def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')
class ProjectRunner(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'projects/film'
        self.entry={'id':'film','path':'projects/film','title':'Synthetic film',
                    'production_version':'v1','conversation_id':'branch-one','owner':'branch-one',
                    'source_key':'tiktok:0000011111222223333','record_id':'recFixture'}
        other=dict(self.entry,id='other',path='projects/other',conversation_id='branch-two',owner='branch-two')
        put(self.root/'projects.json',{'projects':[self.entry,other]})
        put(self.folder/'batches.json',['S01'])
        put(self.folder/'S01/manifest.json',{'duration_seconds':1})
        put(self.folder/'S01/task_state.json',{'status':'RUNNING','taskId':'synthetic-one','batch':1,
                                             'submitAttempts':1,'submittedAt':'2026-01-01T00:00:00+00:00'})
        put(self.root/'projects/other/batches.json',['S01'])
        put(self.root/'projects/other/S01/task_state.json',{'status':'RUNNING','taskId':'synthetic-other'})
        self.plan={'schema_version':1,'project_id':'film','production_version':'v1','ownerThreadId':'branch-one',
                   'segments':[{'segment_id':'S01','global_range':[0,1],'requested_seconds':1,'depends_on':[]},
                               {'segment_id':'S02','global_range':[1,2],'requested_seconds':1,
                                'depends_on':['S01'],'requires_accepted_frame':True}]}
        self.selection={'schema_version':1,'projects':[{'project_id':'film','ownerThreadId':'branch-one',
                         'task_ids':['synthetic-one']}],'max_errors':2,'max_minutes':10,'poll_seconds':15}
        self.clock=datetime.datetime(2026,1,2,tzinfo=datetime.timezone.utc)
    def runner(self):
        self.assertIsNotNone(importlib.util.find_spec('project_runner'),
                             'Persistent branch-owned selected-task runner is missing')
        return importlib.import_module('project_runner')
    def test_register_full_plan_does_not_enqueue_or_submit_unapproved_dependency(self):
        runner=self.runner();runner.register_plan(self.root,'film',self.plan,0)
        item=runner.project_status(self.root,'film')
        self.assertEqual([s['segment_id'] for s in item['segments']],['S01','S02'])
        self.assertEqual(item['segments'][1]['status'],'WAITING_DEPENDENCY')
        self.assertFalse((self.folder/'S02/task_state.json').exists())
        self.assertFalse((self.root/'queue_state.json').exists())
        self.assertEqual(item['ownerThreadId'],'branch-one')
    def test_plan_idempotent_owner_revision_and_immutable_history(self):
        r=self.runner();first=r.register_plan(self.root,'film',self.plan,0)
        self.assertEqual(r.register_plan(self.root,'film',self.plan,first['revision']),first)
        with self.assertRaises(RuntimeError):r.register_plan(self.root,'film',self.plan,0)
        changed=copy.deepcopy(self.plan);changed['ownerThreadId']='another'
        with self.assertRaises(ValueError):r.register_plan(self.root,'film',changed,1)
        self.assertTrue((self.folder/'execution-plans/000001.json').exists())
    def test_cycles_and_overlong_new_segments_are_rejected(self):
        r=self.runner();bad=copy.deepcopy(self.plan);bad['segments'][0]['depends_on']=['S02']
        with self.assertRaises(ValueError):r.register_plan(self.root,'film',bad,0)
        bad=copy.deepcopy(self.plan);bad['segments'][0]['requested_seconds']=16
        with self.assertRaises(ValueError):r.register_plan(self.root,'film',bad,0)
    def test_selected_step_writes_original_status_and_leaves_other_project_bytes(self):
        r=self.runner();r.register_plan(self.root,'film',self.plan,0)
        other=self.root/'projects/other/S01/task_state.json';before=other.read_bytes()
        calls=[]
        def receive(folder,secret,**kwargs):
            calls.append(folder);return {'status':'CLOUD_SUCCEEDED','taskId':'synthetic-one'}
        result=r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock)
        self.assertEqual(len(calls),1)
        self.assertEqual(json.loads((self.folder/'S01/task_state.json').read_text())['status'],'CLOUD_SUCCEEDED')
        self.assertEqual(other.read_bytes(),before)
        self.assertEqual(result['jobs'][0]['ownerThreadId'],'branch-one')
        self.assertEqual(result['jobs'][0]['status'],'CLOUD_SUCCEEDED')
        self.assertEqual(json.loads((self.folder/'S01/task_state.json').read_text())['submitAttempts'],1)

    def test_scoped_receipt_refreshes_existing_queue_and_branch_todo_without_other_writes(self):
        r=self.runner();r.register_plan(self.root,'film',self.plan,0)
        selected={'id':'film/S01','project':'film','batch':'S01','path':'projects/film/S01',
                  'taskId':'synthetic-one','status':'RUNNING','order':4,'approvedFingerprint':'frozen'}
        other={'id':'other/S01','project':'other','taskId':'synthetic-other','status':'RUNNING','order':3}
        put(self.root/'queue_state.json',{'limit':3,'account':{'occupied':2},'jobs':[other,selected]})
        other_tracker=self.root/'projects/other/tracker_status.json';put(other_tracker,{'state':'WAITING'})
        original=other_tracker.read_bytes()
        r.step(self.root,self.selection,receive=lambda *a,**k:{'status':'CLOUD_SUCCEEDED','taskId':'synthetic-one'},
               secret='fixture',clock=self.clock)
        queue=json.loads((self.root/'queue_state.json').read_text())
        self.assertEqual(queue['jobs'][0],other)
        self.assertEqual(queue['jobs'][1]['status'],'CLOUD_SUCCEEDED')
        self.assertEqual(queue['jobs'][1]['order'],4)
        self.assertEqual(queue['jobs'][1]['approvedFingerprint'],'frozen')
        self.assertEqual(queue['account'],{'occupied':2})
        self.assertEqual(other_tracker.read_bytes(),original)
        tracker=json.loads((self.folder/'tracker_status.json').read_text(encoding='utf-8'))
        self.assertEqual(tracker['ownerThreadId'],'branch-one')
        self.assertFalse(tracker['whole_film_complete'])
        self.assertEqual(tracker['batches']['S02'],'WAITING_DEPENDENCY')

    def test_queue_identity_conflict_requires_reconciliation_and_never_replaces_task(self):
        r=self.runner()
        row={'project':'film','batch':'S01','path':'projects/film/S01','taskId':'conflicting-task','status':'RUNNING'}
        put(self.root/'queue_state.json',{'jobs':[row]})
        result=r.step(self.root,self.selection,receive=lambda *a,**k:{'status':'CLOUD_SUCCEEDED','taskId':'synthetic-one'},
                      secret='fixture',clock=self.clock)
        self.assertEqual(result['state'],'BLOCKED')
        self.assertEqual(result['jobs'][0]['status'],'RECONCILE_REQUIRED')
        self.assertEqual(json.loads((self.root/'queue_state.json').read_text())['jobs'],[row])

    def test_reused_local_body_over_fifteen_seconds_has_hash_and_is_never_a_generation(self):
        r=self.runner();asset=self.folder/'assets/body.mp4';asset.parent.mkdir();asset.write_bytes(b'local fixture')
        plan=copy.deepcopy(self.plan);plan['segments'][1]={'segment_id':'BODY','kind':'local_media',
            'global_range':[1,21],'file':'assets/body.mp4','sha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
            'depends_on':['S01']}
        r.register_plan(self.root,'film',plan,0)
        status=r.project_status(self.root,'film')
        self.assertEqual(status['segments'][1]['status'],'LOCAL_MEDIA_READY')
        self.assertFalse((self.folder/'BODY').exists())
        self.assertEqual(json.loads((self.folder/'batches.json').read_text()),['S01'])
        put(self.folder/'S01/task_state.json',{'status':'ARCHIVED','taskId':'synthetic-one'})
        import supervision
        with patch.object(supervision,'verify_archive',return_value={'valid':True,'files':[]}):
            self.assertEqual(supervision.project_snapshot(self.root,self.entry)['stage'],'POSTPRODUCTION')
        asset.write_bytes(b'changed')
        self.assertEqual(r.project_status(self.root,'film')['segments'][1]['status'],'INTEGRITY_BLOCKED')

    def test_supervision_uses_actual_latest_instant_across_timezones(self):
        r=self.runner();r.register_plan(self.root,'film',self.plan,0)
        plan=json.loads((self.folder/'execution-plan.json').read_text());plan['updated_at']='2026-01-02T02:00:00+00:00'
        put(self.folder/'execution-plan.json',plan)
        task=json.loads((self.folder/'S01/task_state.json').read_text());task['lastCheckedAt']='2026-01-02T09:00:00+08:00'
        put(self.folder/'S01/task_state.json',task)
        import supervision
        self.assertEqual(supervision.project_snapshot(self.root,self.entry)['updated_at'],'2026-01-02T02:00:00+00:00')
    def test_restart_respects_persisted_backoff_and_then_receives_original_id(self):
        r=self.runner();calls=[]
        def receive(folder,secret,**kw):
            calls.append(1);return {'status':'RUNNING','taskId':'synthetic-one'}
        first=r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock)
        again=r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock)
        self.assertEqual(len(calls),1)
        self.assertEqual(first['run_id'],again['run_id'])
        r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock+datetime.timedelta(seconds=16))
        self.assertEqual(len(calls),2)
    def test_finite_error_budget_persists_and_does_not_turn_query_error_into_generation_failure(self):
        r=self.runner()
        def receive(*args,**kw):raise TimeoutError('fixture only')
        r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock)
        last=r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock+datetime.timedelta(minutes=2))
        self.assertEqual(last['state'],'BLOCKED')
        self.assertEqual(json.loads((self.folder/'S01/task_state.json').read_text())['status'],'RUNNING')
        self.assertEqual(last['jobs'][0]['errors'],2)
        with patch('collector.collect',side_effect=AssertionError('Budget exhausted')):
            again=r.step(self.root,self.selection,clock=self.clock+datetime.timedelta(minutes=3))
        self.assertEqual(again['state'],'BLOCKED')
    def test_cancelled_and_failed_original_tasks_are_not_revived(self):
        r=self.runner()
        for status in ('CANCELLED','FAILED'):
            put(self.folder/'S01/task_state.json',{'status':status,'taskId':'synthetic-one'})
            with patch('collector.collect',side_effect=AssertionError('No revival')):
                result=r.step(self.root,self.selection,clock=self.clock)
            self.assertEqual(result['jobs'][0]['status'],status)
            self.assertEqual(result['state'],'TERMINAL')
    def test_unknown_id_or_wrong_owner_stops_before_contact(self):
        r=self.runner()
        for field,value in [('task_ids',['not-existing']),('ownerThreadId','another')]:
            bad=copy.deepcopy(self.selection);bad['projects'][0][field]=value
            with self.assertRaises(ValueError):r.step(self.root,bad,receive=lambda *a,**k:self.fail('Contacted transport'),secret='fixture')
    def test_mid_query_revision_change_is_not_overwritten(self):
        r=self.runner()
        def receive(folder,secret,**kw):
            state=json.loads((folder/'task_state.json').read_text());state['branch_note']='concurrent edit'
            put(folder/'task_state.json',state)
            return {'status':'RUNNING','taskId':'synthetic-one'}
        result=r.step(self.root,self.selection,receive=receive,secret='fixture',clock=self.clock)
        actual=json.loads((self.folder/'S01/task_state.json').read_text())
        self.assertEqual(actual['branch_note'],'concurrent edit')
        self.assertEqual(result['jobs'][0]['status'],'RECONCILE_REQUIRED')
    def test_duplicate_process_lock_refuses_second_runner(self):
        r=self.runner();run_id=r.selection_id(self.selection)
        with r.run_lock(self.root,run_id):
            with self.assertRaises(RuntimeError):r.step(self.root,self.selection,receive=lambda *a,**k:{},secret='fixture')
    def test_delivery_registration_needs_content_review_and_actual_page_binding(self):
        r=self.runner()
        media=self.folder/'review/final.mp4';media.parent.mkdir();media.write_bytes(b'fixture')
        sha=hashlib.sha256(media.read_bytes()).hexdigest()
        put(self.folder/'delivery.json',{'schema_version':1,'revision':1,'complete':True,'version':'v1',
            'result_video':'review/final.mp4','sha256':sha,'technical':{'media':True,'decode':True},
            'human_review':{'status':'PENDING'}})
        put(self.folder/'presentation.json',{'schema_version':1,'result_video':'review/final.mp4'})
        (self.folder/'index.html').write_text('<video src="review/final.mp4"></video>')
        with self.assertRaises(ValueError):r.register_delivery(self.root,'film','branch-one',1)
        evidence=self.folder/'review/content.md';evidence.write_text('Branch inspected product, speech and continuity.')
        delivery=json.loads((self.folder/'delivery.json').read_text())
        delivery['content_review']={'status':'ACCEPTED','sha256':sha,'ownerThreadId':'branch-one','evidence':['review/content.md']}
        put(self.folder/'delivery.json',delivery)
        record=r.register_delivery(self.root,'film','branch-one',1)
        self.assertEqual(record['state'],'REVIEW_PENDING')
        self.assertNotEqual(record['state'],'CONFIRMED')
        self.assertTrue((self.folder/'delivery-registration.json').exists())
        (self.folder/'index.html').write_text('<video src="other.mp4"></video>')
        with self.assertRaises(ValueError):r.register_delivery(self.root,'film','branch-one',1)



    def test_whole_film_plan_and_branch_todo_are_visible_in_existing_supervision(self):
        r=self.runner();r.register_plan(self.root,'film',self.plan,0)
        import supervision
        item=supervision.project_snapshot(self.root,self.entry)
        self.assertEqual([s['segment_id'] for s in item['segments']],['S01','S02'])
        self.assertEqual(item['ownerThreadId'],'branch-one')
        self.assertEqual(item['responsibility']['owner'],'BRANCH')
        self.assertFalse(item['responsibility']['agent_invoked'])

    def test_original_fifo_cannot_submit_a_dependency_without_content_acceptance(self):
        r=self.runner();r.register_plan(self.root,'film',self.plan,0)
        put(self.folder/'batches.json',['S01','S02'])
        put(self.folder/'S01/task_state.json',{'status':'ARCHIVED','taskId':'synthetic-one'})
        put(self.folder/'S02/manifest.json',{'duration_seconds':1,'depends_on':'S01'})
        put(self.folder/'approval.json',{'status':'APPROVED','upload_permitted':True,'submit_permitted':True,
            'approved_batches':[{'name':'S02','hashes':{}}]})
        import global_queue
        queue=global_queue.scan(self.root)
        self.assertEqual(global_queue.select(queue['jobs'],0),[])
        self.assertIn('内容验收',next(j for j in queue['jobs'] if j['id']=='film/S02')['blocked'])



    def test_manual_restart_gets_new_finite_session_without_resetting_error_budget(self):
        r=self.runner()
        # Existing run is older than its time allowance but original task is still running.
        record=r.step(self.root,self.selection,receive=lambda *a,**k:{'status':'RUNNING','taskId':'synthetic-one'},
                      secret='fixture',clock=self.clock)
        with patch('collector.key',return_value='fixture'),patch('collector.collect',return_value={'status':'RUNNING','taskId':'synthetic-one'}):
            result=r.run(self.root,self.selection,once=True)
        self.assertEqual(result['state'],'RUNNING')
        self.assertIn('session_started_at',result)

    def test_segment_review_binds_actual_original_and_frame_evidence(self):
        r=self.runner();r.register_plan(self.root,'film',self.plan,0)
        raw=self.folder/'S01/results/task-synthetic-one/video.mp4'
        raw.parent.mkdir(parents=True);raw.write_bytes(b'fixture raw')
        put(self.folder/'S01/task_state.json',{'status':'ARCHIVED','taskId':'synthetic-one'})
        (self.folder/'review').mkdir();(self.folder/'review/content.md').write_text('Inspected actual clip')
        record={'schema_version':1,'ownerThreadId':'branch-one','segment_id':'S01','taskId':'synthetic-one',
                'status':'ACCEPTED','file':raw.relative_to(self.folder).as_posix(),
                'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'evidence':['review/content.md']}
        r.record_segment_review(self.root,'film',record,0)
        self.assertIn('稳定帧',r.generation_gate(self.folder,'S02'))
        frame=self.folder/'review/frame.png';frame.write_bytes(b'fixture frame')
        record['stable_frame']={'file':'review/frame.png','sha256':hashlib.sha256(frame.read_bytes()).hexdigest(),
                                'human_accepted':True,'evidence':['review/content.md']}
        r.record_segment_review(self.root,'film',record,1)
        self.assertIsNone(r.generation_gate(self.folder,'S02'))
        self.assertFalse((self.folder/'S02/task_state.json').exists())


class CollectorOutputs(unittest.TestCase):
    def test_video_task_retains_separate_audio_nodes_and_explicit_node_identity(self):
        import io, collector
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'S01';folder.mkdir()
            put(folder/'task_state.json',{'status':'CLOUD_SUCCEEDED','taskId':'synthetic-media','batch':1})
            put(folder/'manifest.json',{'duration_seconds':1})
            put(folder/'outputs_response.json',{'code':0,'data':[
                {'nodeId':'video-node','fileType':'mp4','fileUrl':'https://fixture.example/video'},
                {'nodeId':'audio-node','fileType':'wav','fileUrl':'https://fixture.example/audio'}]})
            def probe(args):
                audio=str(args[-1]).endswith('.wav')
                return json.dumps({'format':{'duration':'1','size':'8'},
                                   'streams':[{'codec_type':'audio' if audio else 'video'}]}).encode()
            with patch.object(collector,'ROOT',folder.parent),patch.object(collector.local_control,'media',side_effect=probe), \
                 patch.object(collector.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(b'fixture media')):
                result=collector.collect(folder,'fixture',persist_task_state=False)
            self.assertEqual(result['status'],'ARCHIVED')
            archive=json.loads((folder/'results/task-synthetic-media/manifest.json').read_text())
            self.assertEqual({f['nodeId'] for f in archive['files']},{'video-node','audio-node'})
            self.assertEqual({f['fileType'] for f in archive['files']},{'mp4','wav'})
            self.assertEqual(json.loads((folder/'task_state.json').read_text())['status'],'CLOUD_SUCCEEDED')

    def test_expired_cached_output_url_refreshes_original_task_once_without_create(self):
        import io, collector, urllib.error
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'S01';folder.mkdir()
            put(folder/'task_state.json',{'status':'CLOUD_SUCCEEDED','taskId':'synthetic-media','batch':1})
            put(folder/'manifest.json',{'duration_seconds':1})
            put(folder/'outputs_response.json',{'code':0,'data':[
                {'nodeId':'video-node','fileType':'mp4','fileUrl':'https://fixture.example/expired'}]})
            calls=[]
            def opener(url,**kw):
                if 'expired' in url:raise urllib.error.HTTPError(url,403,'expired',{},None)
                return io.BytesIO(b'fixture')
            def post(endpoint,payload,secret):
                calls.append((endpoint,payload['taskId']))
                return {'code':0,'data':[{'nodeId':'video-node','fileType':'mp4','fileUrl':'https://fixture.example/fresh'}]}
            probe=json.dumps({'format':{'duration':'1'},'streams':[{'codec_type':'video'}]}).encode()
            with patch.object(collector,'ROOT',folder.parent),patch.object(collector.local_control,'media',return_value=probe), \
                 patch.object(collector.urllib.request,'urlopen',side_effect=opener),patch.object(collector,'post',side_effect=post):
                result=collector.collect(folder,'fixture')
            self.assertEqual(result['status'],'ARCHIVED')
            self.assertEqual(calls,[('/task/openapi/outputs','synthetic-media')])


if __name__=='__main__':unittest.main()
