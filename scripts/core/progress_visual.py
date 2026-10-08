"""Evidence-based progress colors and accessible local presentation; no execution."""
import hashlib
import html
import json
import business_lines

STEPS=[('COLLECTION','采集'),('MATCHING','素材匹配'),('PLANNING','编剧分镜'),('APPROVAL','审批'),
       ('QUEUE','上传排队'),('GENERATING','生成'),('DOWNLOADING','归档'),('POSTPRODUCTION','后期'),('REVIEW_SYNC','验收回写')]
TONES={'idle':('○','未执行'),'waiting':('◷','等待'),'running':('↻','执行中'),'done':('✓','已完成'),
       'error':('!','明确异常'),'human':('♙','待人工'),'unknown':('?','待核对')}
SUCCESS={'ARCHIVED','DOWNLOADED'}
ERRORS={'FAILED','REJECTED'}
UNKNOWN={'SUBMITTING_OUTCOME_UNKNOWN','REJECTED_OR_UNKNOWN','SUBMISSION_UNKNOWN','UNKNOWN','CONFLICT','RECONCILE_REQUIRED'}

def visual_progress(item):
    line=business_lines.classify(item)['line']
    steps=[('REQUIREMENTS','需求'),('PLANNING','编剧分镜'),('APPROVAL','审批'),('GENERATING','生成'),('POSTPRODUCTION','后期'),('DELIVERY_REVIEW','验收交付')] if line=='INDEPENDENT' else STEPS
    by_key={s['key']:s for s in item['stages']}
    segments=item['segments'];statuses=[s.get('status') for s in segments]
    checks=[s.get('archive_check') for s in segments]
    delivery=item['delivery'];review=item['review'];sync=item['sync']
    approval=by_key.get('APPROVAL',{}).get('state')=='APPROVED'
    active_fresh=item.get('health',{}).get('state')=='OBSERVED'
    decisions={}
    for key,_ in steps:
        state=by_key.get(key,{}).get('state','NOT_OBSERVED')
        tone='unknown';reason='没有足够记录，需核对；不代表未执行或失败'
        if key=='REQUIREMENTS':
            if state=='CONFIRMED' and by_key[key].get('artifacts'):tone,reason='done','需求已确认并有版本证据'
            elif state in ('AWAITING_APPROVAL','PENDING'):tone,reason='human','待用户确认需求'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','需求尚未开始'
        elif key=='DELIVERY_REVIEW':
            if review.get('state')=='ACCEPTED' and delivery.get('state')=='ACCEPTED' and delivery.get('technical')=='PASSED':tone,reason='done','完整成片已人工验收；自主项目无需 Lark 回写'
            elif delivery.get('video'):tone,reason='human','等待查看完整成片并记录人工验收'
            else:tone,reason='waiting','等待完整成片交付'
        elif key=='COLLECTION':
            if state=='AVAILABLE' and item.get('original_video'):tone,reason='done','参考原片文件可访问'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','记录明确尚未采集'
            else:reason='原片未匹配或文件缺失，需核对来源'
        elif key=='MATCHING':
            if state=='MATCHED' and item.get('original_video') and item.get('source_key') and item.get('record_id'):
                tone,reason='done','原片、来源键及记录身份已匹配'
            elif state=='CONFLICT':tone,reason='error','来源或记录身份冲突，等待决定'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','记录明确尚未匹配'
        elif key=='PLANNING':
            if state in ('EVIDENCE_AVAILABLE','COMPLETE','COMPLETED','DONE','APPROVED') and (approval or by_key.get(key,{}).get('artifacts')):
                tone,reason='done','已核对冻结审批或明确方案完成证据'
            elif state in ('AWAITING_APPROVAL','AWAITING_USER_APPROVAL','AWAITING_SOURCE_REVIEW'):
                tone,reason='human','方案或原片等待人工确认'
            elif state in ('RUNNING','IN_PROGRESS','PLANNING'):
                fresh=by_key.get(key,{}).get('health',{}).get('state')=='OBSERVED'
                tone,reason=('running','负责人记录显示正在准备方案') if fresh else ('unknown','方案进展记录缺失或过期，需核对')
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','记录明确方案尚未开始'
            elif state in ('FAILED','ERROR'):tone,reason='error','方案记录明确失败，等待决定'
        elif key=='APPROVAL':
            if approval:tone,reason='done','当前冻结批次审批核对通过'
            elif state in ('AWAITING_APPROVAL','AWAITING_USER_APPROVAL','PENDING'):
                tone,reason='human','待审批；没有新上传或付费授权'
            elif state in ('REJECTED','FAILED'):tone,reason='error','审批记录明确拒绝或冲突'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','审批尚未开始'
        elif key=='QUEUE':
            if any(s in UNKNOWN or s=='UPLOADING' for s in statuses):reason='上传或提交结果尚待核对，不自动重提'
            elif segments and all(s.get('task_id') for s in segments):tone,reason='done','全部生成片段已有原任务ID'
            elif state in ('ENQUEUED','READY','WAITING','WAITING_CAPACITY','WAITING_INSTANCE'):
                tone,reason='waiting','等待统一队列或前置条件'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','记录明确尚未进入队列'
        elif key=='GENERATING':
            if any(s in ERRORS for s in statuses):tone,reason='error','存在已确认失败的原任务；保留结果，等待决定'
            elif any(s in UNKNOWN or s=='UPLOADING' for s in statuses):reason='原提交结果未知，需核对，不自动生成或重试'
            elif line=='INDEPENDENT' and any(c is not None and not c.get('valid') for c in checks):
                tone,reason=('unknown','原片归档校验工具不可用，待核对') if all(c.get('issue')=='PROBE_UNAVAILABLE' for c in checks if c and not c.get('valid')) else ('error','原片归档缺失或损坏，待主协调诊断')
            elif line=='INDEPENDENT' and statuses and all(s in SUCCESS for s in statuses) and not all(c and c.get('valid') for c in checks):reason='生成记录已完成，原片归档证据待核对'
            elif statuses and all(s in SUCCESS for s in statuses):tone,reason='done','全部原任务已记录生成成功；不等于整片验收'
            elif any(s in ('RUNNING','QUERY_RATE_LIMITED','RETRY_QUERY_OR_DOWNLOAD') for s in statuses):
                tone,reason=('running','已有任务正在生成') if active_fresh else ('unknown','任务进展记录缺失或过期，当前情况待核对')
            elif any(s in ('QUEUED','WAITING_CAPACITY','WAITING_INSTANCE') for s in statuses):tone,reason='waiting','已有任务等待平台资源'
            elif statuses and all(s=='NOT_SUBMITTED' and segment.get('state_recorded') for s,segment in zip(statuses,segments)):
                tone,reason='idle','任务记录明确尚未提交'
            elif any(s=='CANCELLED' for s in statuses):tone,reason='waiting','任务已取消，等待人工决定'
        elif key=='DOWNLOADING':
            invalid=[c for c in checks if c is not None and not c.get('valid')]
            if invalid:
                if all(c.get('issue')=='PROBE_UNAVAILABLE' for c in invalid):reason='本机媒体校验不可用，不能确认归档质量'
                else:tone,reason='error','原件缺失、损坏或归档身份不符，需恢复核对'
            elif checks and all(c and c.get('valid') for c in checks):tone,reason='done','全部原件通过文件、哈希和媒体核验'
            elif any(s in ('CLOUD_SUCCEEDED','DOWNLOADING') for s in statuses):
                tone,reason=('running','正在接收已有任务的原件') if active_fresh else ('unknown','收片进展记录缺失或过期，需核对')
            elif any(s=='DOWNLOAD_ERROR' for s in statuses):reason='下载或校验需核对，不能当作完整归档'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','记录明确尚未收片'
        elif key=='POSTPRODUCTION':
            if delivery.get('video') and delivery.get('technical')=='PASSED':tone,reason='done','完整成片存在且技术证据通过；人工验收仍独立'
            elif delivery.get('video'):reason='完整文件存在，技术证据尚未重新确认'
            elif state in ('AWAITING_QUALITY_REVIEW','AWAITING_AUDIO_APPROVAL'):
                tone,reason='human','待人工质量验收或音轨授权'
            elif state in ('READY','WAITING'):tone,reason='waiting','后期方案准备好，等待执行'
            elif state in ('RUNNING','IN_PROGRESS'):
                fresh=by_key.get(key,{}).get('health',{}).get('state')=='OBSERVED'
                tone,reason=('running','负责人记录显示正在后期') if fresh else ('unknown','后期进展缺失或过期，需核对')
            elif state in ('FAILED','ERROR','INVALID') or delivery.get('state')=='INVALID':tone,reason='error','后期或完整交付记录明确异常'
            elif state in ('NOT_STARTED','NOT_EXECUTED'):tone,reason='idle','记录明确后期尚未开始'
        elif key=='REVIEW_SYNC':
            if review.get('state')=='ACCEPTED' and delivery.get('state')=='ACCEPTED' and delivery.get('technical')=='PASSED':
                if sync.get('state') in ('APPLIED','NO_CHANGE') and sync.get('verified_at'):tone,reason='done','当前成片已人工确认，表格回读证据对应本地版本'
                elif sync.get('state')=='FAILED':tone,reason='error','表格同步失败；本机已验成果保留'
                elif sync.get('state') in UNKNOWN:reason='表格同步结果待核对；不自动重试'
                else:tone,reason='waiting','人工已确认，等待表格同步及真实回读'
            elif delivery.get('video'):tone,reason='human','完整成片待人工审核，不自动确认'
            else:tone,reason='waiting','等待完整成片，再进入人工验收'
        decisions[key]=(tone,reason)
    result=[]
    for key,label in steps:
        members=[by_key.get(k,{}) for k in (('REVIEW','LARK_SYNC') if key=='REVIEW_SYNC' else ('REVIEW',) if key=='DELIVERY_REVIEW' else (key,))]
        tone,reason=decisions[key];icon,status=TONES[tone]
        result.append({'key':key,'label':label,'tone':tone,'icon':icon,'status':status,'reason':reason,'members':members})
    complete=line!='UNCLASSIFIED' and all(s['tone']=='done' for s in result) and delivery.get('state')=='ACCEPTED' and review.get('state')=='ACCEPTED'
    return {'steps':result,'all_complete':complete}

CSS=r'''
:root{color-scheme:dark;--bg:#101b22;--panel:#192b34;--line:#34535e;--muted:#aec3cd}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#edf4f7;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1420px;margin:auto;padding:28px 32px}a{color:#8be1d6}h1{font-size:30px;margin:14px 0 4px}h2{font-size:20px;margin:0;line-height:1.4}h3{font-size:16px}.muted,.eyebrow{color:var(--muted);font-size:13px}.intro{margin:0 0 16px;color:var(--muted)}.legend{display:flex;flex-wrap:wrap;gap:7px 16px;align-items:center;padding:12px 16px;background:#14252e;border:1px solid var(--line);border-radius:12px;margin:16px 0}.legend-item{display:inline-flex;gap:7px;align-items:center;white-space:nowrap}.legend .icon{width:23px;height:23px;font-size:14px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}input,select,button{font:inherit;color:inherit;border:1px solid #557780;background:#203740;border-radius:8px;padding:9px 12px}input{flex:1;min-width:220px;max-width:100%}button,summary{cursor:pointer}button:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid #b8e7ff;outline-offset:4px}article{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin:14px 0}.card-top{display:flex;justify-content:space-between;gap:16px;align-items:start}.eyebrow{margin:0 0 4px}.version{white-space:nowrap;font-size:12px;border:1px solid var(--line);border-radius:20px;padding:4px 10px;color:var(--muted)}.all-complete{border-color:#58cb95;box-shadow:inset 4px 0 #58cb95}.all-complete .version{color:#96edbf;border-color:#58cb95}.line-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.line-tabs button[aria-pressed=true]{border-color:#8be1d6;background:#254c50}.identity{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}.source-badge{font-size:12px;background:#213b48;border-radius:6px;padding:2px 8px}.role-badge{font-size:12px;color:#dbc6ff}.next-action{font-size:13px;color:#beced6;margin:5px 0}.steps{display:grid;grid-template-columns:repeat(var(--step-count,9),minmax(0,1fr));gap:8px;list-style:none;padding:0;margin:20px 0 12px}.step{position:relative;min-width:0}.step button{display:flex;flex-direction:column;align-items:center;gap:7px;width:100%;padding:10px 3px;border-color:transparent;background:#14232b;font-size:12px;line-height:1.3}.step button:hover,.step button[aria-expanded=true]{border-color:currentColor}.icon{display:inline-flex;align-items:center;justify-content:center;flex:none;width:34px;height:34px;border:2px solid currentColor;border-radius:50%;font-size:21px;font-weight:700;line-height:1}.tone-idle{color:#84949c}.tone-waiting{color:#f3cd66}.tone-running{color:#7bc4ff}.tone-done{color:#83dfad}.tone-error{color:#ffa5a5}.tone-human{color:#ccafff}.tone-unknown{color:#cad2d7}.tone-unknown .icon{border-color:#d8b66a;background:repeating-linear-gradient(135deg,transparent,transparent 4px,#7a8b9833 4px,#7a8b9833 7px)}.tone-running .icon{animation:working 1.8s ease-in-out infinite;background:#244c6a}.tone-done .icon{background:#204c3d}.tone-error .icon{background:#553236}.tone-human .icon{background:#3e315a}.tone-waiting .icon{background:#4e432b}.step-tooltip{display:none;position:absolute;z-index:3;bottom:calc(100% + 8px);left:0;width:220px;max-width:calc(100vw - 48px);background:#0b141b;border:1px solid #68828d;border-radius:9px;padding:10px;color:#edf4f7;font-size:12px;box-shadow:0 6px 20px #0008;pointer-events:none;white-space:pre-line}.step:last-child .step-tooltip{left:auto;right:0}.step button:hover+.step-tooltip,.step button:focus-visible+.step-tooltip{display:block}.stage-detail{border:1px solid var(--line);border-radius:10px;background:#10232b;padding:16px;margin:12px 0}.stage-detail h3{margin:0 0 8px}.stage-detail p{margin:5px 0}dl{display:grid;grid-template-columns:100px 1fr;gap:5px 12px;font-size:13px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.card-actions{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:8px 0;font-size:13px}details{border-top:1px solid var(--line);padding:10px 0;margin-top:10px}summary{color:#badcdd;font-size:13px}.overview{background:#192b34;border:1px solid var(--line);border-radius:10px;padding:12px 16px}.overview summary{font-size:14px}.videos{display:grid;grid-template-columns:1fr 1fr;gap:20px}.media-state{margin:7px 0;color:#aec3cd;font-size:13px}.media-state.error{color:#ffa5a5}.media-retry{padding:5px 10px;font-size:13px}video{width:100%;height:360px;background:#0a141b;border-radius:8px;object-fit:contain}.empty{height:360px;display:grid;place-items:center;background:#0a141b;color:var(--muted);border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 monospace;color:var(--muted)}li.warning{color:#f4d092;margin:6px 0}[hidden]{display:none!important}@keyframes working{0%,100%{transform:scale(1);box-shadow:0 0 0 0 #75bcff00}50%{transform:scale(1.045);box-shadow:0 0 0 4px #75bcff20}}@media(max-width:760px){main{padding:18px 16px}h1{font-size:25px}article{padding:16px}.card-top{flex-direction:column;gap:6px}.steps{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.step:nth-child(3n) .step-tooltip{left:auto;right:0}.videos{grid-template-columns:1fr}video,.empty{height:320px}.version{white-space:normal}.legend{gap:8px 12px;font-size:12px}.toolbar>*{max-width:100%}}@media(prefers-reduced-motion:reduce){.tone-running .icon{animation:none}*{scroll-behavior:auto!important;transition:none!important}}
'''

JS=r'''
const cards=[...document.querySelectorAll('article')],search=document.getElementById('search'),stage=document.getElementById('stage'),batch=document.getElementById('batch');
cards.sort((a,b)=>(Date.parse(b.dataset.created)||0)-(Date.parse(a.dataset.created)||0));
const cardParent=cards[0]?.parentElement,cardAnchor=document.getElementById('project-list-end');
if(cardParent)for(const card of cards)cardParent.insertBefore(card,cardAnchor);
for(const [control,key] of [[stage,'stage'],[batch,'batch']]){for(const value of [...new Set(cards.map(c=>c.dataset[key]))].sort()){const option=document.createElement('option');option.value=value;option.textContent=value;control.append(option)}}
let saved={};try{saved=JSON.parse(sessionStorage.getItem('h3-supervision-list')||'{}')}catch{}
const urlLine=new URLSearchParams(location.search).get('line');
let lineFilter=urlLine||saved.line||'ALL';if(!['ALL','LARK','INDEPENDENT','UNCLASSIFIED'].includes(lineFilter))lineFilter='ALL';
search.value=typeof saved.search==='string'?saved.search:'';stage.value=saved.stage||'';batch.value=saved.batch||'';
let page=Math.max(1,Math.floor(Number(saved.page)||1));if(urlLine&&urlLine!==saved.line)page=1;
const pageSize=30,lineButtons=[...document.querySelectorAll('[data-line-filter]')],pagination=document.getElementById('project-pagination');
function filter(reset=false){
 if(reset)page=1;
 for(const button of lineButtons)button.setAttribute('aria-pressed',String(button.dataset.lineFilter===lineFilter));
 const found=cards.filter(card=>(lineFilter==='ALL'||card.dataset.line===lineFilter)&&card.dataset.search.toLowerCase().includes(search.value.toLowerCase())&&(!stage.value||card.dataset.stage===stage.value)&&(!batch.value||card.dataset.batch===batch.value));
 const pages=Math.max(1,Math.ceil(found.length/pageSize));page=Math.min(pages,Math.max(1,page));
 const shown=new Set(found.slice((page-1)*pageSize,page*pageSize));
 for(const card of cards){card.hidden=!shown.has(card);if(card.hidden)for(const video of card.querySelectorAll('video'))video.pause();}
 sessionStorage.setItem('h3-supervision-list',JSON.stringify({line:lineFilter,search:search.value,stage:stage.value,batch:batch.value,page}));
 const first=found.length?(page-1)*pageSize+1:0,last=Math.min(page*pageSize,found.length);
 document.getElementById('visible-count').textContent=found.length?`当前显示 ${first}–${last} 项 · 共 ${found.length} 个项目`:'没有匹配的项目，请调整筛选条件。';
 pagination.replaceChildren();const info=document.createElement('span');info.textContent=`每页30个 · 第 ${page} / ${pages} 页`;pagination.append(info);
 const add=(label,target,disabled=false,current=false)=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=disabled;if(current)button.setAttribute('aria-current','page');button.addEventListener('click',()=>{page=target;filter();pagination.scrollIntoView({block:'start'});});pagination.append(button);};
 add('上一页',page-1,page===1);
 const numbers=[...new Set([1,...Array.from({length:5},(_,i)=>page+i-2).filter(n=>n>0&&n<=pages),pages])].sort((a,b)=>a-b);
 let previous=0;for(const n of numbers){if(previous&&n-previous>1){const dots=document.createElement('span');dots.textContent='…';pagination.append(dots);}add(String(n),n,n===page,n===page);previous=n;}
 add('下一页',page+1,page===pages);
 document.dispatchEvent(new Event('h3-filter-change'));
}
for(const button of lineButtons)button.addEventListener('click',()=>{lineFilter=button.dataset.lineFilter;filter(true);});filter();
search.addEventListener('input',()=>filter(true));stage.addEventListener('change',()=>filter(true));batch.addEventListener('change',()=>filter(true));document.getElementById('refresh').addEventListener('click',()=>location.reload());
for(const card of cards){for(const button of card.querySelectorAll('[data-step]')){button.addEventListener('click',()=>{const opened=button.getAttribute('aria-expanded')==='true';for(const other of card.querySelectorAll('[data-step]')){other.setAttribute('aria-expanded','false');document.getElementById(other.getAttribute('aria-controls')).hidden=true;}if(!opened){button.setAttribute('aria-expanded','true');document.getElementById(button.getAttribute('aria-controls')).hidden=false;}});}const preview=card.querySelector('[data-role="preview"]');preview.addEventListener('toggle',()=>{if(!preview.open)for(const video of preview.querySelectorAll('video'))video.pause();});}

// Visible previews only. Metadata/first-frame loading is independent of playback and business actions.
const mediaQueue=[],mediaVideos=[...document.querySelectorAll('video[data-media-preview]')];let mediaActive=0;
window.__h3PreviewLoad={get active(){return mediaActive},max:4};
function mediaVisible(v){const r=v.getBoundingClientRect();return !v.closest('article').hidden&&v.closest('details').open&&r.width>0&&r.bottom>-180&&r.top<innerHeight+180;}
function mediaMessage(v,text,error=false){const p=v.parentElement.querySelector('.media-state'),b=v.parentElement.querySelector('[data-media-retry]');p.textContent=text;p.classList.toggle('error',error);b.hidden=!error;}
function mediaFinish(v,state){v.dataset.mediaPreviewState=state;if(v._previewTimer){clearTimeout(v._previewTimer);v._previewTimer=null;}if(v._previewRelease){v._previewRelease=false;mediaActive=Math.max(0,mediaActive-1);}mediaMessage(v,state==='ready'?'视频预览已就绪 · 点击播放':'视频预览暂不可用，可重试或使用原生播放控件',state==='error');mediaDrain();}
function mediaDrain(){while(mediaActive<4&&mediaQueue.length){const v=mediaQueue.shift();if(!mediaVisible(v)){v.dataset.mediaPreviewState='idle';continue;}if(v.readyState>=2&&!v.error){mediaFinish(v,'ready');continue;}v.dataset.mediaPreviewState='loading';mediaActive++;v._previewRelease=true;mediaMessage(v,'正在载入视频首帧…');v._previewTimer=setTimeout(()=>mediaFinish(v,v.readyState>=2&&!v.error?'ready':'error'),15000);v.preload='metadata';v.load();}}
function mediaEnqueue(v,retry=false){if(!retry&&['ready','loading','queued','error'].includes(v.dataset.mediaPreviewState))return;v.dataset.mediaPreviewState='queued';mediaQueue.push(v);mediaDrain();}
function mediaScan(){for(const v of mediaVideos)if(mediaVisible(v))mediaEnqueue(v);}
for(const v of mediaVideos){v.dataset.mediaPreviewState='idle';v.addEventListener('loadeddata',()=>mediaFinish(v,'ready'));v.addEventListener('loadedmetadata',()=>{if(v.dataset.mediaPreviewState==='loading')mediaMessage(v,'正在解码视频首帧…');});v.addEventListener('error',()=>mediaFinish(v,'error'));v.parentElement.querySelector('[data-media-retry]').addEventListener('click',()=>{v.pause();mediaEnqueue(v,true);});}
if('IntersectionObserver' in window){const io=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting)mediaEnqueue(e.target);},{rootMargin:'180px'});for(const v of mediaVideos)io.observe(v);}else{addEventListener('scroll',mediaScan,{passive:true});addEventListener('resize',mediaScan);}
document.addEventListener('h3-filter-change',mediaScan);for(const d of document.querySelectorAll('[data-role="preview"]'))d.addEventListener('toggle',()=>{if(d.open)mediaScan();});mediaScan();
'''

def render_panel(data):
    esc=lambda value:html.escape(str(value if value is not None else '尚无记录'),quote=True)
    cards=[]
    for item in sorted(data['projects'],key=__import__('project_order').sort_key,reverse=True):
        line=business_lines.classify(item)['line'];role=item.get('responsibility',{});visual=visual_progress(item);prefix='p'+hashlib.sha256(item['project_id'].encode()).hexdigest()[:20]
        buttons=[];panels=[]
        for step in visual['steps']:
            identifier=prefix+'-'+step['key'];members=step['members']
            owners=' / '.join(str(m.get('owner') or '待指定') for m in members)
            stamps=' / '.join(str(m.get('updated_at') or '无进展记录') for m in members)
            tooltip=step['status']+'：'+step['reason']+'\n负责人：'+owners+'\n最近记录：'+stamps
            buttons.append('<li class="step tone-'+step['tone']+'"><button type="button" data-step="'+step['key']+'" aria-expanded="false" aria-controls="'+identifier+'" aria-describedby="'+identifier+'-tip" aria-label="'+esc(step['label']+'，'+step['status'])+'"><span class="icon" aria-hidden="true">'+step['icon']+'</span><span>'+step['label']+'</span></button><span class="step-tooltip" role="tooltip" id="'+identifier+'-tip">'+esc(tooltip)+'</span></li>')
            rows=''.join('<dt>'+esc(m.get('label','阶段'))+'</dt><dd>'+esc(m.get('state','NOT_OBSERVED'))+' · '+esc(m.get('health',{}).get('state','NOT_OBSERVED'))+'</dd><dt>负责人</dt><dd>'+esc(m.get('owner','待指定'))+'</dd><dt>最近记录</dt><dd>'+esc(m.get('updated_at'))+'</dd><dt>输入版本</dt><dd>'+esc(m.get('input_version'))+'</dd><dt>下一步</dt><dd>'+esc(m.get('next_step','核对证据后接续'))+'</dd>' for m in members)
            panels.append('<section class="stage-detail" id="'+identifier+'" aria-label="'+step['label']+'详情" hidden><h3>'+step['label']+' · '+step['status']+'</h3><p>'+esc(step['reason'])+'</p><dl>'+rows+'</dl><pre>'+esc(json.dumps([{'artifacts':m.get('artifacts',[]),'anomaly':m.get('anomaly','')} for m in members],ensure_ascii=False,indent=2))+'</pre></section>')
        videos=[]
        reference_title='参考素材（可选）' if line=='INDEPENDENT' else '参考原片'
        for title,url in [(reference_title,item.get('original_video')),('完整成片',item['delivery'].get('video'))]:
            empty_text=('自主创作无需原片' if line=='INDEPENDENT' else '原片待匹配 / 核对') if title==reference_title else '完整成片尚未交付'
            videos.append('<div><h3>'+title+'</h3>'+('<video controls preload="none" src="'+esc(url)+'" aria-label="'+title+'"></video>' if url else '<p class="empty">'+empty_text+'</p>')+'</div>')
        for i,block in enumerate(videos):
            if '<video ' in block:
                videos[i]=block.replace('<video ', '<video data-media-preview ').rsplit('</div>',1)[0]+ '<p class="media-state" role="status" aria-live="polite">进入可视区域后载入视频首帧；不会自动播放</p><button class="media-retry" type="button" data-media-retry hidden>重试预览</button></div>'
        version=str(item.get('production_version',''))
        if version.startswith(('h3-','replica-')) or (version.isdigit() and len(version)>10):version='当前制作版'
        badge='全程已完成' if visual['all_complete'] else version
        technical={key:item.get(key) for key in ('business_line','creation_key','classification','responsibility','source_key','record_id','local_revision','production_version','execution','delivery','review','health','owner','updated_at','segments','sync')}
        warning='<details><summary>异常与待决定 · '+str(len(item['anomalies']))+'</summary><ul>'+''.join('<li class="warning">'+esc(message)+'</li>' for message in item['anomalies'])+'</ul></details>' if item['anomalies'] else ''
        assets={'脚本分镜':[m for m in item['stages'] if m['key'] in ('REQUIREMENTS','PLANNING')], '参考素材':item.get('reference_assets',[]), '分段与原任务':item.get('segments',[])}
        script_links=''.join('<a href="'+esc(a['url'])+'">'+esc(a['name'])+'</a>　' for a in item.get('script_files',[]) if a.get('url','').startswith('/projects/') and not a['url'].startswith('//'))
        asset_detail='<details><summary>脚本与参考素材 · 分段记录</summary><p>'+script_links+'</p><pre>'+esc(json.dumps(assets,ensure_ascii=False,indent=2))+'</pre></details>'
        identity='<div class="identity"><span class="source-badge">'+business_lines.LABELS[line]+'</span><span class="role-badge">'+esc(role.get('label','待主协调核对'))+'</span></div><p class="next-action">'+esc(role.get('next_action','核对当前证据后安排下一步'))+'</p>'
        cards.append('<article data-project="'+esc(item['project_id'])+'" data-created="'+esc(item.get('created_at') or '')+'" data-line="'+line+'" class="'+('all-complete' if visual['all_complete'] else '')+'" data-batch="'+esc(item['batch_title'])+'" data-stage="'+esc(item['stage_label'])+'" data-search="'+esc(item['title']+' '+str(item['production_version'])+' '+item['stage_label'])+'"><div class="card-top"><div><p class="eyebrow">'+esc(item['batch_title'])+'</p><h2>'+esc(item['title'])+'</h2></div><span class="version">'+esc(badge)+'</span></div>'+identity+'<ol style="--step-count:'+str(len(visual['steps']))+'" class="steps" aria-label="视频全流程进度">'+''.join(buttons)+'</ol>'+''.join(panels)+'<div class="card-actions"><a href="'+esc(item['project_url'])+'">制作详情 →</a><span class="muted">点阶段查看负责人与证据</span></div>'+warning+asset_detail+'<details data-role="preview" open><summary>原片与成片对照</summary><div class="videos">'+''.join(videos)+'</div></details><details><summary>运行记录与制作版本</summary><pre>'+esc(json.dumps(technical,ensure_ascii=False,indent=2))+'</pre></details></article>')
    legend=''.join('<span class="legend-item tone-'+tone+'"><span class="icon" aria-hidden="true">'+icon+'</span>'+label+'</span>' for tone,(icon,label) in TONES.items())
    alerts=''.join('<li class="warning"><strong>'+esc(a['title'])+'</strong>：'+esc(a['message'])+'</li>' for a in data['alerts'])
    overview='<details class="overview"><summary>待核对与待决定 · '+str(len(data['alerts']))+'</summary><ul>'+alerts+'</ul></details>' if alerts else ''
    tabs='<nav class="line-tabs" aria-label="业务线">'+''.join('<button type="button" data-line-filter="'+key+'" aria-pressed="'+('true' if key=='ALL' else 'false')+'">'+label+' · '+str(len(data['projects']) if key=='ALL' else sum(business_lines.classify(x)['line']==key for x in data['projects']))+'</button>' for key,label in [('ALL','全部'),*business_lines.LABELS.items()])+'</nav>'
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>视频制作任务面板 · 全流程</title><style>'+CSS+'</style></head><body><main><a href="/index.html">← 生成任务与历史</a><h1>全流程制作面板</h1><p class="intro">'+str(len(data['projects']))+' 个视频 · 从编剧、待审批到整片验收。点阶段看证据，展开预览看原片与成片。</p><div class="legend" aria-label="颜色与图标说明">'+legend+'</div>'+overview+tabs+'<p id="visible-count" class="muted" role="status"></p><div class="toolbar"><input id="search" aria-label="搜索视频" placeholder="搜索视频或制作版本"><select id="stage" aria-label="筛选阶段"><option value="">全部阶段</option></select><select id="batch" aria-label="筛选批次"><option value="">全部批次</option></select><button id="refresh" type="button">刷新记录</button></div><nav id="project-pagination" aria-label="项目分页" class="toolbar"></nav>'+''.join(cards)+'<div id="project-list-end"></div><p class="muted">全绿须各阶段有完成证据、完整交付、人工确认及表格回读。无记录或过期需核对，不等于失败。页面颜色是记录概览；浏览与刷新不会上传、生成、重试或回写表格。</p><details><summary>采集时间与监管边界</summary><p>'+esc(data['observed_at'])+' · 保留原30分钟协调机制。本页不执行监控派单，不代表写入围栏已启用。</p></details></main><script>'+JS+'</script></body></html>'
