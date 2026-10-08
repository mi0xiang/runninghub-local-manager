"""Central entry point. Persistent project registry; no inferred approvals."""
from pathlib import Path
import argparse,datetime,hashlib,html,json,os,sys,msvcrt
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parent/'core'))
import portable_runtime
ROOT=portable_runtime.ROOT
ALLOW_EXPLICIT_CHILD_RENDER=True
def read(p,default=None):
    import durable_store
    return durable_store.read(p,default)
def save(p,data):
    import durable_store
    durable_store.save(p,data)
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def permitted(a):return a.get('status')=='APPROVED' and a.get('upload_permitted') is True and a.get('submit_permitted') is True
TERMINAL={'CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR','ARCHIVED','DOWNLOADED','FAILED','CANCELLED','REJECTED','NEEDS_REVIEW','EXCLUDED_BY_USER'}
UNKNOWN={'SUBMITTING_OUTCOME_UNKNOWN','UPLOADING','REJECTED_OR_UNKNOWN'}
def can_submit(states):
    return not any(s.get('status') in UNKNOWN for s in states) and sum(s.get('status') not in TERMINAL|{'WAITING_CAPACITY','WAITING_INSTANCE'} for s in states)<3
def project_path(root,entry):
    p=(root/entry['path']).resolve();base=(root/'projects').resolve()
    if not p.is_relative_to(base) or p==base:raise ValueError('Project must be beneath center/projects')
    return p
def index_html(items):
    esc=lambda x:html.escape(str(x),quote=True)
    cards=[]
    for p in sorted((x for x in items if not x.get('source_project')),key=__import__('project_order').sort_key,reverse=True):
        cards.append(f'<article hidden data-project="{esc(p["id"])}" data-completed="{p["completed"]}" data-created="{esc(p.get("created_at") or "")}" data-updated="{esc(p["updated"])}" data-search="{esc(p["title"]+" "+p["conversation"]+" "+p["id"])}"><h2><a href="{esc(p["path"])}/index.html">{esc(p["title"])}</a></h2><p><strong>{p.get("ended",p["completed"])} / {p["total"]} 已结束 · 成功 {p["completed"]} · 失败 {p.get("failed",0)}</strong> · {esc(p.get("stage_label",p["state"]))}</p><p>执行：{esc(p["state"])} · 交付：{esc(p.get("delivery_state","待核对"))} · 审核：{esc(p.get("review_state","待人工审核"))}</p><p>来源对话：{esc(p["conversation"])}</p><p class="muted">{esc(p["id"])} · 最近更新 {esc(p["updated"])}</p><a href="{esc(p["path"])}/index.html">分镜 / 进度 / 播放成片 →</a></article>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RunningHub 视频生成追踪</title><style>body{background:#0c1820;color:#e7eff4;font:16px/1.7 system-ui;margin:0}main{max-width:1120px;margin:auto;padding:36px}h1{font-size:34px}article{background:#162b36;border:1px solid #315260;padding:22px;border-radius:14px;margin:20px 0}a{color:#7de0ef}.muted{color:#9db1bc;font-size:13px}input{padding:13px;width:90%;background:#203a46;color:white;border:1px solid #527b8a;border-radius:8px}button{padding:10px;margin:8px 0}h2{margin:0;font-size:22px}</style><main><h1>RunningHub 视频生成追踪</h1><p><a href="/supervision.html" style="display:inline-block;padding:10px 16px;background:#204f55;border:1px solid #7de0ef;border-radius:8px;font-weight:700">全流程制作面板 →</a>　<a href="/supervision.html?line=LARK">Lark协作</a>　<a href="/supervision.html?line=INDEPENDENT">自主创作</a></p><input id="filter" placeholder="搜索项目名、对话名称或编号"><p><button onclick="location.reload()">刷新进度</button> <a href="使用指引.html">使用与新对话接手指引</a></p><p class="muted">生成后自动接收；运行状态以项目最后查询时间为准。页面本身不提交生成、不重复扣费。</p>'''+''.join(cards)+'''</main><script>const f=document.getElementById('filter');f.value=sessionStorage.getItem('hub-filter')||'';function filter(){sessionStorage.setItem('hub-filter',f.value);document.querySelectorAll('article').forEach(a=>a.hidden=!a.dataset.search.toLowerCase().includes(f.value.toLowerCase()))}f.oninput=filter;filter();setTimeout(()=>location.reload(),60000)</script></html>'''
def runtime():
    sys.path.insert(0,str(portable_runtime.APP/'scripts/core'))
    import tracker,collector,run_approved_queue
    return tracker,collector,run_approved_queue
def all_states(reg):
    states=[]
    for entry in reg['projects']:
        folder=project_path(ROOT,entry)
        for name in read(folder/'batches.json',[]):
            s=read(folder/name/'task_state.json',{})
            if s:states.append(s)
    return states
def validate_project(folder):
    a=read(folder/'approval.json',{})
    if not permitted(a):raise ValueError('Awaiting explicit user approval')
    flattened=sum(a['planned_waves'],[])
    if len(flattened)!=len(set(flattened)) or set(flattened)!={b['name'] for b in a['approved_batches']}:raise ValueError('Approval scope mismatch')
    if any(len(w)>3 for w in a['planned_waves']):raise ValueError('Concurrency exceeds three')
    if set(flattened)&set(a.get('excluded_batches',[])):raise ValueError('Excluded batch in approval')
    for batch in a['approved_batches']:
        d=(folder/batch['name']).resolve()
        if d.parent!=folder:raise ValueError('Batch path escape')
        for name,digest in batch['hashes'].items():
            if hashlib.sha256((d/name).read_bytes()).hexdigest()!=digest:raise ValueError('Approved asset changed')
    return a
def control_ui(page,entry=None):
    import control_server
    entry=entry or {}
    folder=project_path(ROOT,entry) if entry else ROOT
    config={'token':control_server.token(),'project':entry.get('id'),'pipeline':entry.get('pipeline'),'batches':read(folder/'batches.json',[]) if entry else []}
    if 'id="production-details"' in page:config['presentation']='comparison'
    config['retries']=[{'batch':x.get('source_batch'),'path':x['path'],'title':x['title']} for x in read(ROOT/'projects.json',{}).get('projects',[]) if entry.get('id') and x.get('source_project')==entry['id']]
    payload=json.dumps(config,ensure_ascii=False).replace('<','\\u003c')
    return page+'<script>window.HUB_CONTROL='+payload+';</script><script src="http://127.0.0.1:18765/ui_controls.js?v=20261002-projectorder30"></script>'

def render_project(entry,t):
    folder=project_path(ROOT,entry);t.R=folder
    if entry.get('pipeline')=='music':
        import music_page
        return music_page.render(ROOT,entry)
    rows=t.rows();status=read(folder/'tracker_status.json',{})
    if entry.get('mode')=='archive_only':status={'state':'COMPLETE','updatedAt':entry['updatedAt']}
    if not permitted(read(folder/'approval.json',{})) and entry.get('mode')!='archive_only':status={'state':'待批准 · 未启动','updatedAt':entry['updatedAt']}
    events=[]
    for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines() if (folder/'events.jsonl').exists() else []:
        try:events.append(json.loads(line))
        except ValueError:pass
    if entry.get('pipeline')=='continuous_speaker':
        import speaker_pipeline
        page=speaker_pipeline.render(folder,entry,rows,status,events)
    else:page=t.render_html(rows,status,events)
    page=page.replace('本地项目 · 独立批次',html.escape(entry['title'])+' · '+str(len(rows))+' 段 · 独立批次')
    page=page.replace('<h1>视频生成 · 过程与复核</h1>','<p><a href="/index.html">← 全部项目</a></p><h1>'+html.escape(entry['title'])+'</h1><p>来源对话：'+html.escape(entry['conversation'])+'</p>')
    page=page.replace('AWAITING_USER_APPROVAL','待你批准 · 尚未提交')
    if (folder/'color_review/index.html').exists():page=page.replace('</h1>','</h1><p><a href="color_review/index.html">打开色差对照：同步截帧、局部取样、原片播放 →</a></p>',1)
    for item in rows:
        if not (folder/item['name']/'task_state.json').exists():
            page=page.replace('<a href="'+quote(item['name'])+'/task_state.json">任务记录</a>','<span>任务记录：尚未提交</span>')
    if status['state'].startswith('待批准'):page=page.replace('age>360?', 'true?').replace('心跳已过期，后台可能中断','待批准，尚未启动后台')
    import project_reference
    page=project_reference.present(folder,page)
    if entry.get('source_project'):
        parent=next(x for x in read(ROOT/'projects.json')['projects'] if x['id']==entry['source_project'])
        url='http://127.0.0.1:18765/'+parent['path']+'/index.html'
        page='<meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+html.escape(url,quote=True)+'"><a href="'+html.escape(url,quote=True)+'">查看原片段版本</a>'
        (folder/'index.html').write_text(page,encoding='utf-8')
    else:(folder/'index.html').write_text(control_ui(page,entry),encoding='utf-8')
    meaningful=[entry['updatedAt']]+[r['updated'] for r in rows if r['updated']]+[v['receivedAt'] for r in rows for v in r['videos']]
    return dict(source_project=entry.get('source_project'),id=entry['id'],title=entry['title'],conversation=entry['conversation']+' · '+entry.get('conversation_id',''),path=entry['path'],state=status['state'],updated=max(meaningful),completed=sum(bool(r['videos']) for r in rows),ended=sum(r['state'] in ('ARCHIVED','DOWNLOADED','FAILED','CANCELLED') for r in rows),failed=sum(r['state'] in ('FAILED','CANCELLED') for r in rows),total=len(rows))
def run(tick=False):
    import shutil
    shutil.copy2(portable_runtime.APP/'web/ui_controls.js',ROOT/'ui_controls.js')
    reg=read(ROOT/'projects.json');t,c,q=runtime();summaries=[]
    import operation_guide,local_control,global_queue
    local_control.ENABLED=False
    operation_guide.render(ROOT)
    if tick:
        global_queue.schedule(ROOT)
        launch_downloads()
    else:global_queue.scan(ROOT)
    for entry in reg['projects']:
        folder=project_path(ROOT,entry);t.R=folder;rows=t.rows();status=read(folder/'tracker_status.json',{})
        summaries.append(dict(source_project=entry.get('source_project'),id=entry['id'],title=entry['title'],
                              conversation=entry.get('conversation',''),path=entry['path'],state=status.get('state','WAITING'),
                              updated=entry.get('updatedAt',now()),completed=sum(bool(r['videos']) for r in rows),
                              ended=sum(r['state'] in ('ARCHIVED','DOWNLOADED','FAILED','CANCELLED') for r in rows),
                              failed=sum(r['state'] in ('FAILED','CANCELLED') for r in rows),total=len(rows)))
    decorate_summaries(summaries)
    (ROOT/'index.html').write_text(control_ui(index_html(summaries)),encoding='utf-8')
    save(ROOT/'hub_status.json',{'updatedAt':now(),'action':'tick' if tick else 'render','projects':summaries})

def decorate_summaries(summaries):
    import supervision
    observed=supervision.snapshot(ROOT);items={x['project_id']:x for x in observed['projects']}
    for row in summaries:
        if row['id'] in items:
            item=items[row['id']]
            row.update(created_at=item['created_at'],stage_label=item['stage_label'],delivery_state=item['delivery']['state'],review_state='已确认' if item['review']['state']=='ACCEPTED' else '待人工审核')
    supervision.persist_observation(ROOT,observed)
    return summaries
def launch_downloads():
    import subprocess
    subprocess.Popen([portable_runtime.tool('pythonw'),str(portable_runtime.APP/'scripts/hub.py'),'download-results'],cwd=ROOT,creationflags=0x08000000)

def _main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['render','tick','status','serve','fetch-results','collect-results','download-results']);p.add_argument('--project');args=p.parse_args()
    portable_runtime.require_ready()
    if args.action=='serve':
        sys.path.insert(0,str(portable_runtime.APP/'scripts/core'))
        import control_server
        control_server.serve();return
    if args.action=='status':print(json.dumps(read(ROOT/'hub_status.json',{}),ensure_ascii=False,indent=2));return
    if args.action=='download-results':
        sys.path.insert(0,str(portable_runtime.APP/'scripts/core'))
        import global_queue,local_control
        local_control.ENABLED=False
        with (ROOT/'download.process.lock').open('a+b') as lock:
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:return
            try:
                global_queue.download(ROOT)
                import source_audio_delivery
                source_audio_delivery.process_all(ROOT)
                import speaker_versions
                for entry in read(ROOT/'projects.json')['projects']:
                    if entry.get('pipeline')=='continuous_speaker':
                        try:speaker_versions.process(ROOT,entry['id'])
                        except Exception:pass
            finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
        import subprocess
        subprocess.Popen([portable_runtime.tool('pythonw'),str(portable_runtime.APP/'scripts/hub.py'),'render'],cwd=ROOT,creationflags=0x08000000)
        return
    with (ROOT/'hub.process.lock').open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            if args.action=='fetch-results' and args.project:
                entry=next(x for x in read(ROOT/'projects.json')['projects'] if x['id']==args.project)
                save(project_path(ROOT,entry)/'manual_fetch_status.json',{'state':'BUSY','message':'中心正在处理，请稍后再点。'})
            return
        sys.path.insert(0,str(portable_runtime.APP/'scripts/core'))
        import local_control
        local_control.ENABLED=False
        local_control.phase('PROCESSING')
        try:
            if args.action=='fetch-results':
                import manual_fetch,collector
                entry=next(x for x in read(ROOT/'projects.json')['projects'] if x['id']==args.project)
                status_path=project_path(ROOT,entry)/'manual_fetch_status.json'
                save(status_path,{'state':'RUNNING','updatedAt':now(),'pid':os.getpid()})
                def receive(folder,secret):
                    collector.ROOT=folder.parent
                    return collector.collect(folder,secret)
                try:
                    import global_queue
                    results=global_queue.schedule(ROOT,force_project=args.project,submit=False)
                    launch_downloads()
                    run(False)
                    save(status_path,{'state':'DONE','updatedAt':now(),'results':results})
                except Exception as exc:
                    save(status_path,{'state':'ERROR','error':type(exc).__name__,'updatedAt':now()});raise
            elif args.action=='collect-results':
                import global_queue
                global_queue.schedule(ROOT,submit=False)
                launch_downloads()
                run(False)
            else:
                if args.action=='render' and ALLOW_EXPLICIT_CHILD_RENDER:
                    selected=[x for x in read(ROOT/'projects.json')['projects'] if not args.project or x['id']==args.project]
                    tracker,_,_=runtime()
                    for entry in selected:render_project(entry,tracker)
                run(args.action=='tick')
        except Exception as exc:
            save(ROOT/'hub_error.json',{'time':now(),'errorType':type(exc).__name__,'message':str(exc)[:200]});raise
        finally:
            local_control.phase('STOPPED' if local_control.paused() else 'IDLE')
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
def main():
    import durable_store
    with durable_store.configured_session(ROOT):_main()

if __name__=='__main__':main()
