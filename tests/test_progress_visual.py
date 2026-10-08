"""Evidence-first visual progress, independent of execution and cloud permissions."""
import copy
import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/core'))

def complete_item():
    states={'COLLECTION':'AVAILABLE','MATCHING':'MATCHED','PLANNING':'EVIDENCE_AVAILABLE',
            'APPROVAL':'APPROVED','QUEUE':'READY','GENERATING':'ORIGINALS_ARCHIVED',
            'DOWNLOADING':'ARCHIVED','POSTPRODUCTION':'COMPLETE_FILE_PRESENT','REVIEW':'ACCEPTED','LARK_SYNC':'APPLIED'}
    return {'project_id':'synthetic','business_line':'LARK','title':'合成验收项目','production_version':'v1','batch_title':'验收fixture',
        'source_key':'tiktok:0000011111222223333','record_id':'record','local_revision':'fixture','stage':'ACCEPTED','stage_label':'已确认',
        'task_label':'fixture','owner':'branch','updated_at':'2026-10-02T00:00:00+00:00',
        'health':{'state':'OBSERVED'},'original_video':'/projects/fixture/original.mp4',
        'execution':{'state':'ORIGINALS_ARCHIVED'},'delivery':{'state':'ACCEPTED','video':'/projects/fixture/final.mp4','technical':'PASSED'},
        'review':{'state':'ACCEPTED','evidence':'human-message'},'sync':{'state':'APPLIED','verified_at':'2026-10-02T00:00:00+00:00'},
        'segments':[{'status':'ARCHIVED','task_id':'known','state_recorded':True,'archive_check':{'valid':True}}],
        'stages':[{'key':key,'label':key,'state':value,'owner':'branch','updated_at':'2026-10-02T00:00:00+00:00',
            'input_version':'v1','artifacts':[],'anomaly':'','next_step':'检查证据','health':{'state':'OBSERVED'}} for key,value in states.items()],
        'project_url':'/projects/fixture/index.html','anomalies':[],'actions':{'may_create':False,'may_enqueue':False}}

class ProgressVisual(unittest.TestCase):
    def visual(self,item):return importlib.import_module('progress_visual').visual_progress(item)
    def step(self,item,key):return next(s for s in self.visual(item)['steps'] if s['key']==key)

    def test_only_full_evidence_and_human_acceptance_make_entire_row_complete(self):
        item=complete_item();self.assertTrue(self.visual(item)['all_complete'])
        self.assertEqual(len(self.visual(item)['steps']),9)
        item['review']['state']='PENDING';item['delivery']['state']='READY_FOR_REVIEW'
        self.assertFalse(self.visual(item)['all_complete'])
        self.assertEqual(self.step(item,'REVIEW_SYNC')['tone'],'human')
        item['review']['state']='ACCEPTED';item['delivery']['state']='ACCEPTED';item['sync']={'state':'NOT_RECORDED','verified_at':None}
        self.assertFalse(self.visual(item)['all_complete'])

    def test_archive_or_legacy_complete_cannot_make_missing_early_evidence_green(self):
        item=complete_item();item['stages'][2]['state']='NOT_OBSERVED'
        self.assertEqual(self.step(item,'PLANNING')['tone'],'unknown')
        self.assertFalse(self.visual(item)['all_complete'])
        item['delivery']['technical']='LEGACY_NOT_REVERIFIED'
        self.assertEqual(self.step(item,'POSTPRODUCTION')['tone'],'unknown')

    def test_running_waiting_explicit_unstarted_and_unknown_are_different(self):
        item=complete_item();item['segments']=[{'status':'RUNNING','task_id':'known','state_recorded':True,'archive_check':None}]
        self.assertEqual(self.step(item,'GENERATING')['tone'],'running')
        item['segments'][0]['status']='QUEUED'
        self.assertEqual(self.step(item,'GENERATING')['tone'],'waiting')
        item['segments'][0].update(status='NOT_SUBMITTED',task_id=None)
        self.assertEqual(self.step(item,'GENERATING')['tone'],'idle')
        item['segments'][0]['state_recorded']=False
        self.assertEqual(self.step(item,'GENERATING')['tone'],'unknown')
        item['segments'][0].update(status='SUBMITTING_OUTCOME_UNKNOWN',state_recorded=True)
        self.assertEqual(self.step(item,'GENERATING')['tone'],'unknown')

    def test_stale_or_missing_heartbeat_does_not_become_failure_or_authorize_work(self):
        item=complete_item();item['segments']=[{'status':'RUNNING','task_id':'known','state_recorded':True,'archive_check':None}]
        for health in ('STALE_UNKNOWN','NOT_OBSERVED'):
            item['health']['state']=health
            self.assertEqual(self.step(item,'GENERATING')['tone'],'unknown')
        self.assertEqual(item['actions'],{'may_create':False,'may_enqueue':False})

    def test_missing_original_archive_and_verified_failure_have_honest_alerts(self):
        item=complete_item();item['original_video']=None
        self.assertEqual(self.step(item,'COLLECTION')['tone'],'unknown')
        self.assertFalse(self.visual(item)['all_complete'])
        item['segments'][0]['archive_check']={'valid':False,'issue':'MISSING_OR_CORRUPT'}
        self.assertEqual(self.step(item,'DOWNLOADING')['tone'],'error')
        item['segments'][0]['archive_check']={'valid':False,'issue':'PROBE_UNAVAILABLE'}
        self.assertEqual(self.step(item,'DOWNLOADING')['tone'],'unknown')
        item['segments'][0]['status']='FAILED'
        self.assertEqual(self.step(item,'GENERATING')['tone'],'error')

    def test_render_has_keyboard_click_details_legend_reduced_motion_and_default_open_players(self):
        supervision=importlib.import_module('supervision')
        page=supervision.render_panel({'projects':[complete_item()],'alerts':[],'observed_at':'fixture'})
        for token in ('全流程制作面板','aria-expanded="false"','aria-controls=','role="tooltip"',
                      'prefers-reduced-motion','data-step=','data-role="preview" open','tone-done','tone-human','tone-unknown'):
            self.assertIn(token,page)
        self.assertIn('repeat(3,minmax(0,1fr))',page)
        self.assertNotIn('<p>执行：ORIGINALS_ARCHIVED',page)
        self.assertIn('← 生成任务与历史',page)
        self.assertNotIn('autoplay',page)
        self.assertIn('preload="none"',page)
        self.assertNotIn('fetch(',page)
        self.assertNotIn('HUB_CONTROL',page)

if __name__=='__main__':unittest.main()
