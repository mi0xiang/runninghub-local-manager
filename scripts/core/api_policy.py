"""Business-code policy. Explicit capacity rejection alone permits create retry."""
import datetime
WAITING={'WAITING_CAPACITY','WAITING_INSTANCE'}
MAX_SUBMIT_ATTEMPTS=6
CODES={
 415:('CAPACITY','等待可用独占实例','实例不足；当前版本稍后重新提交。'),
 421:('CAPACITY','等待并发名额','共享API并发已满；当前版本稍后重新提交。'),
 1003:('RATE_LIMIT','请求频率超限','降低请求频率；提交结果需核对，查询可退避。'),
 804:('RUNNING','云端生成中','继续查询已有任务，不重复提交。'),
 813:('QUEUED','云端排队中','任务已受理，继续查询原任务。'),
 808:('UPLOAD','素材上传失败','检查上传结果和网络；不自动提交生成。'),
 809:('FILE_SIZE','上传文件过大','调整文件后重新审核。'),
 810:('WORKFLOW','工作流未保存或未成功运行','先在平台保存并成功运行工作流。'),
 801:('AUTH','账户不支持API','检查账户权益。'),
 802:('AUTH','API密钥无效或未授权','检查密钥权限。'),
 811:('AUTH','企业密钥无效','检查企业密钥权限。'),
 812:('BALANCE','企业账户余额不足','检查企业余额。'),
 806:('ACCOUNT','密钥关联用户不存在','核对账户。'),
 807:('TASK','任务不存在','核对任务ID，不盲目重提。'),
 423:('TASK','任务不存在','核对任务ID及历史保留情况。'),
 433:('WORKFLOW','工作流校验失败','查看节点与连接详情。'),
 803:('WORKFLOW','节点参数不匹配','检查节点ID及字段。'),
 435:('INSTANCE','未找到对应API实例','核对实例类型和账户权益。'),
 436:('INSTANCE','独占服务到期','检查独占资源服务。'),
 500:('SERVER','服务端未知错误','核对提交结果，不能盲目重试。'),
 1000:('SERVER','服务端未知错误','核对提交结果，不能盲目重试。')}
def due(state,field='nextSubmitAt'):
 try:return datetime.datetime.now().astimezone()>=datetime.datetime.fromisoformat(state[field])
 except (KeyError,TypeError,ValueError):return False

def retryable(state):return state.get('status') in WAITING and not state.get('taskId') and due(state)
def next_time(attempt):
 delay=min(120*2**max(0,attempt-1),900)
 return (datetime.datetime.now().astimezone()+datetime.timedelta(seconds=delay)).isoformat(timespec='seconds')
def rejected(out,attempt):
 data=out.get('data');task=data.get('taskId') if isinstance(data,dict) else None
 if out.get('code') not in (415,421) or task or out.get('taskId'):return None
 return {'status':'WAITING_INSTANCE' if out['code']==415 else 'WAITING_CAPACITY','submitAttempts':attempt,'nextSubmitAt':next_time(attempt)}
