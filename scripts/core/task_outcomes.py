"""Terminal task outcomes and readable RunningHub errors."""
import json,re
SUCCESS={'ARCHIVED','DOWNLOADED'}
FAILED={'FAILED','CANCELLED'}
def counts(states):
 states=list(states);success=sum(s in SUCCESS for s in states);failed=sum(s in FAILED for s in states);ended=success+failed
 return {'total':len(states),'ended':ended,'success':success,'failed':failed,'state':('COMPLETE_WITH_FAILURES' if failed else 'COMPLETE') if states and ended==len(states) else 'WAITING'}
def failure_info(out):
 data=out.get('data') or {};raw=data.get('failedReason') if isinstance(data,dict) else None
 raw=raw or out.get('failedReason') or {}
 if isinstance(raw,str):
  try:raw=json.loads(raw)
  except ValueError:raw={'exception_message':raw}
 if not isinstance(raw,dict):raw={'exception_message':str(raw)}
 detail={k:raw.get(k,'') for k in ('exception_type','node_name','node_id','exception_message','traceback')}
 text=str(detail['exception_type'])+' '+str(detail['exception_message']);lower=text.lower();code=out.get('code')
 category='UNKNOWN';summary=str(detail['exception_message'] or out.get('msg') or '平台未提供具体原因')[:300];advice='展开详情核对错误；未知原因不要自动重试。'
 if 'outofmemory' in lower or 'out of memory' in lower or '显存' in text or 'vram grow failed' in lower:
  category='OOM';summary='显存不足，工作流运行失败';advice='可尝试 Plus（48GB）重跑；是否足够取决于工作流。保留原参数，不自动降分辨率或缩短时长。'
 elif code in (433,803) or 'validation' in lower:
  category='WORKFLOW';summary='工作流节点参数或连接校验失败';advice='先修正节点或参数，升级 Plus 通常不能解决。'
 elif code in (802,811):category='AUTH';summary='API 密钥无效或权限不足';advice='检查密钥权限；升级 Plus 不能解决。'
 elif code==812:category='BALANCE';summary='账户余额不足';advice='检查账户余额后再提交。'
 elif code in __import__('api_policy').CODES:
  category,summary,advice=__import__('api_policy').CODES[code]
 elif 'timeout' in lower:
  category='NETWORK';summary='上传、网络或请求频率异常';advice='先核对任务是否已受理，不要盲目重复提交。'
 elif code==805 and not text.strip():summary='任务已失败、中断或取消，平台未提供详细原因'
 detail.update(code=code,platform_message=out.get('msg',''))
 # Never include current_inputs/current_outputs, credentials or signed media URLs.
 serialized=json.dumps(detail,ensure_ascii=False,indent=2)
 serialized=re.sub(r'(?i)(api[_-]?key|authorization|token|secret)([\s\"\:=]+)[^\s\",]+',r'\1\2[REDACTED]',serialized)
 return {'category':category,'summary':summary,'advice':advice,'detail':serialized,'code':code,'node':str(raw.get('node_id',''))+' / '+str(raw.get('node_name',''))}
