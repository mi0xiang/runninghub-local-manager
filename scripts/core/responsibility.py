"""Read existing handoff evidence; TODO labels never invoke an AI or grant approval."""
FIELDS={'category','evidence','next_action','owner','decision_required','attempts','last_progress'}

def validate(record):
    if not isinstance(record,dict) or not FIELDS.issubset(record) or set(record)-FIELDS-{'ownerThreadId'}:raise ValueError('Exact decision fields required; approval is separate')
    if record['owner'] not in ('SCRIPT','COORDINATOR','USER','BRANCH'):raise ValueError('Unknown responsibility')
    if record['owner']=='BRANCH' and not record.get('ownerThreadId'):raise ValueError('Branch ownerThreadId required')
    if type(record['decision_required']) is not bool or type(record['attempts']) is not int or record['attempts']<0:raise ValueError('Invalid decision values')
    if not all(isinstance(record[k],str) and record[k] for k in ('category','next_action')):raise ValueError('Category and next action required')
    if not isinstance(record['evidence'],list):raise ValueError('Evidence list required')
    if record['last_progress'] is not None:
        import datetime
        stamp=datetime.datetime.fromisoformat(record['last_progress'].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise ValueError('Timezone required')
    return record

def derive(item,handoff):
    lifecycle=item.get('lifecycle')
    if lifecycle:
        owner='USER' if item.get('review',{}).get('state')=='ACCEPTED' or lifecycle['phase']=='REVIEW_PENDING' else 'BRANCH'
        return {'category':lifecycle['phase'],'evidence':[{'segment_id':s['segment_id'],'task_id':s.get('taskId'),'status':s['status']} for s in lifecycle['segments']],
                'owner':owner,'ownerThreadId':lifecycle['ownerThreadId'],'decision_required':owner=='USER',
                'next_action':lifecycle['next_action'],'attempts':0,'last_progress':item.get('updated_at'),
                'status':'WAITING_USER' if owner=='USER' else 'WAITING_BRANCH',
                'label':'待用户验收' if owner=='USER' else '待负责子对话接续',
                'agent_invoked':False,'may_generate':False}
    supplied=handoff.get('decision')
    if supplied:
        try:record=dict(validate(supplied))
        except (ValueError,TypeError):supplied=None
    if not supplied:
        problems=[s for s in item.get('segments',[]) if s.get('status') in ('FAILED','REJECTED','SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN','UPLOADING') or (s.get('archive_check') and not s['archive_check'].get('valid'))]
        issue=bool(problems or item.get('anomalies') or item.get('sync',{}).get('state') in ('FAILED','CONFLICT','RECONCILE_REQUIRED'))
        if issue:owner,category,next_action='COORDINATOR','DIAGNOSIS','核对原任务、错误和已有证据，提出修复方案；涉及新费用或改创意再请用户决定'
        elif item.get('delivery',{}).get('video') and item.get('review',{}).get('state')!='ACCEPTED':owner,category,next_action='USER','FINAL_REVIEW','查看完整成片后记录人工验收'
        elif item.get('stage')=='AWAITING_APPROVAL':owner,category,next_action='USER','APPROVAL','确认当前创意、素材和费用范围后提供单独审批'
        elif item.get('stage')=='PLANNING':owner,category,next_action='COORDINATOR','CREATIVE','完成脚本与分镜，提交明确方案供审批'
        else:owner,category,next_action='SCRIPT','DETERMINISTIC','按已有冻结参数和原任务记录推进可确定的步骤'
        record={'category':category,'evidence':[{'segment_id':s.get('segment_id'),'task_id':s.get('task_id'),'status':s.get('status'),'reason':s.get('reason')} for s in problems],
                'next_action':next_action,'owner':owner,'decision_required':owner=='USER',
                'attempts':sum(s.get('attempt_count') or 0 for s in item.get('segments',[])),
                'last_progress':item.get('updated_at') or None}
    owner=record['owner']
    return dict(record,status={'COORDINATOR':'WAITING_COORDINATOR','USER':'WAITING_USER','SCRIPT':'SCRIPT_RULES'}[owner],
                label={'COORDINATOR':'待主协调','USER':'待用户验收' if record['category']=='FINAL_REVIEW' else '待用户决定','SCRIPT':'脚本执行 / 规则待推进'}[owner],
                agent_invoked=False,may_generate=False)
