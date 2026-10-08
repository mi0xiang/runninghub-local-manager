"""Two explicit business identities, shared existing queue, bounded responsibility handoff."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_progress_visual import complete_item

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/core'))

class BusinessLines(unittest.TestCase):
    def classifier(self,*records):return importlib.import_module('business_lines').classify(*records)

    def test_missing_lark_id_alone_never_implies_independent(self):
        self.assertEqual(self.classifier({'id':'legacy'})['line'],'UNCLASSIFIED')
        self.assertEqual(self.classifier({'business_line':'INDEPENDENT','creation_key':'own-script'})['line'],'INDEPENDENT')
        self.assertEqual(self.classifier({'source_key':'tiktok:0000011111222223333','record_id':'recFixture'})['line'],'LARK')

    def test_conflicting_line_or_source_identity_stays_unclassified_and_preserved(self):
        source={'source_key':'tiktok:0000011111222223333','record_id':'recFixture'}
        original=copy.deepcopy(source)
        self.assertEqual(self.classifier(source,{'business_line':'INDEPENDENT'})['line'],'UNCLASSIFIED')
        self.assertEqual(source,original)
        self.assertEqual(self.classifier(source,dict(source,record_id='recOther'))['line'],'UNCLASSIFIED')

    def test_independent_can_complete_without_lark_or_tiktok(self):
        import progress_visual
        item=complete_item();item.update(business_line='INDEPENDENT',source_key=None,record_id=None,original_video=None,
                                         creation_key='own-script',sync={'state':'NOT_APPLICABLE','verified_at':None})
        item['stages'].insert(0,{'key':'REQUIREMENTS','state':'CONFIRMED','artifacts':['brief.json'],'owner':'creator','updated_at':None})
        visual=progress_visual.visual_progress(item)
        self.assertTrue(visual['all_complete'])
        self.assertEqual([s['label'] for s in visual['steps']],['需求','编剧分镜','审批','生成','后期','验收交付'])
        self.assertNotIn('REVIEW_SYNC',[s['key'] for s in visual['steps']])
        item['business_line']='UNCLASSIFIED'
        self.assertFalse(progress_visual.visual_progress(item)['all_complete'])

    def test_lark_write_failure_is_local_final_step_block_not_lost_delivery(self):
        import progress_visual
        item=complete_item();item['sync']={'state':'FAILED','verified_at':None}
        result=progress_visual.visual_progress(item)
        self.assertFalse(result['all_complete'])
        self.assertEqual(result['steps'][-1]['tone'],'error')
        self.assertEqual(next(s for s in result['steps'] if s['key']=='POSTPRODUCTION')['tone'],'done')
        self.assertEqual(item['delivery']['state'],'ACCEPTED')

    def test_independent_registration_is_idempotent_in_same_existing_queue(self):
        import supervision,global_queue
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'projects/own';folder.mkdir(parents=True)
            (folder/'batches.json').write_text('["whole"]')
            (folder/'approval.json').write_text(json.dumps({'status':'APPROVED','upload_permitted':True,'submit_permitted':True,
                'approved_batches':[{'name':'whole','hashes':{}}]}))
            (root/'projects.json').write_text('{"projects":[]}')
            entry={'id':'own','path':'projects/own','title':'自主fixture','business_line':'INDEPENDENT',
                   'creation_key':'own-script-v1','production_version':'v1'}
            supervision.register_ready_project(root,entry)
            self.assertTrue(supervision.register_ready_project(root,entry)['duplicate'])
            self.assertEqual(len(global_queue.scan(root)['jobs']),1)
            with patch.object(supervision,'snapshot',return_value={'projects':[dict(entry,source_key=None,record_id=None)]}):
                self.assertEqual(supervision.generate_lark_requests(root,{}),[])

    def test_role_waiting_is_a_todo_and_never_implies_agent_or_paid_approval(self):
        responsibility=importlib.import_module('responsibility')
        item=complete_item();item['segments'][0]['status']='FAILED';item['delivery']['video']=None;item['review']['state']='PENDING'
        result=responsibility.derive(item,{})
        self.assertEqual(result['owner'],'COORDINATOR')
        self.assertEqual(result['status'],'WAITING_COORDINATOR')
        self.assertFalse(result['agent_invoked']);self.assertFalse(result['may_generate'])
        for key in ('category','evidence','next_action','owner','decision_required','attempts','last_progress'):
            self.assertIn(key,result)
        record={k:result[k] for k in ('category','evidence','next_action','owner','decision_required','attempts','last_progress')}
        self.assertEqual(responsibility.validate(record),record)
        with self.assertRaises(ValueError):responsibility.validate(dict(record,approved=True))

    def test_independent_handoff_uses_creation_identity_and_preserves_owner(self):
        import supervision
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'projects/own';folder.mkdir(parents=True)
            entry={'id':'own','path':'projects/own','business_line':'INDEPENDENT','creation_key':'script-one','production_version':'v1'}
            data=dict(entry,schema_version=1,project_id='own',owner='creator',stage='PLANNING')
            data.pop('id');data.pop('path')
            result=supervision.record_handoff(root,entry,data,0)
            self.assertNotIn('record_id',result)
            self.assertEqual(supervision.record_handoff(root,entry,data,1),result)
            with self.assertRaises(ValueError):supervision.record_handoff(root,entry,dict(data,owner='another'),1)
            item=supervision.project_snapshot(root,entry)
            self.assertEqual(item['business_line'],'INDEPENDENT')
            self.assertEqual(item['sync']['state'],'NOT_APPLICABLE')
            self.assertFalse(item['actions']['may_create'])

    def test_invalid_business_identity_is_not_registered_as_new_lark_work(self):
        import supervision
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'projects/own').mkdir(parents=True)
            entry={'id':'own','path':'projects/own','business_line':'UNCLASSIFIED','source_key':'tiktok:123','record_id':'recOne','production_version':'v1'}
            with self.assertRaises(ValueError):supervision.register_ready_project(root,entry)
            self.assertFalse((root/'projects.json').exists())

    def test_line_tabs_badges_and_delivery_detail_are_explicit(self):
        import supervision
        item=complete_item();item['responsibility']={'owner':'USER','label':'待用户验收'}
        page=supervision.render_panel({'projects':[item],'alerts':[],'observed_at':'fixture'})
        for token in ('data-line-filter="LARK"','data-line-filter="INDEPENDENT"','data-line="LARK"',
                      'Lark协作','自主创作','待分类','待用户验收','脚本与参考素材'):
            self.assertIn(token,page)

if __name__=='__main__':unittest.main()
