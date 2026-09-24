import html,json
from pathlib import Path
from urllib.parse import quote
import local_control as lc

def render(root,entry):
 p=root/entry['path'];rows=[];success=failed=0;updated=entry['updatedAt'];esc=html.escape
 for name in lc.read(p/'batches.json',[]):
  d=p/name;s=lc.read(d/'task_state.json',{});status=s.get('status','WAITING');updated=max(updated,s.get('lastCheckedAt',s.get('submittedAt',updated)));success+=status=='ARCHIVED';failed+=status in ('FAILED','CANCELLED')
  body='<h2>'+esc(name)+'</h2><p>'+esc(status)+' · 任务 '+esc(str(s.get('taskId','尚未提交')))+'</p>'
  for manifest in d.glob('results/*/manifest.json'):
   a=lc.read(manifest)
   for f in a['files']:
    url=quote((manifest.parent/f['name']).relative_to(p).as_posix());body+='<audio controls preload="metadata" src="'+url+'"></audio><p><a href="'+url+'" download>下载原始音频</a></p>'
  if s.get('reason'):body+='<p>'+esc(s['reason'])+'</p>'
  prompt=(d/'H3_prompt.txt').read_text(encoding='utf-8');body+='<details><summary>音乐提示词与参数</summary><pre>'+esc(prompt)+'</pre></details>';rows.append('<section>'+body+'</section>')
 page='<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(entry['title'])+'</title><style>body{background:#10202a;color:#eef6fa;max-width:1000px;margin:auto;padding:30px;font:16px/1.7 system-ui}section{background:#1b3340;padding:24px;border-radius:12px;margin:20px 0}a{color:#7cdeec}pre{white-space:pre-wrap}audio{width:100%}</style><a href="../../index.html">返回追踪中心</a><h1>'+esc(entry['title'])+'</h1><p>Music3 文字生成纯音乐测试 · 无参考音频输入 · 最长45秒（模型可能提前结束）</p>'+''.join(rows)+'<script>setInterval(()=>{if(![...document.querySelectorAll("audio")].some(a=>!a.paused))location.reload()},30000)</script></html>'
 (p/'index.html').write_text(page,encoding='utf-8');return dict(source_project=None,id=entry['id'],title=entry['title'],conversation=entry.get('conversation',''),path=entry['path'],state='COMPLETE' if success==len(rows) else 'COMPLETE_WITH_FAILURES' if success+failed==len(rows) else 'WAITING',updated=updated,completed=success,ended=success+failed,failed=failed,total=len(rows))
