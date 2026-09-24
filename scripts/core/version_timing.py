import datetime

def timing(state,archive):
 status=state.get('status');submitted=state.get('submittedAt');last=state.get('lastCheckedAt');next_at=None
 if submitted and status not in {'ARCHIVED','FAILED','CANCELLED','REJECTED','CLOUD_SUCCEEDED','DOWNLOADING','DOWNLOAD_ERROR'}:
  try:
   first=datetime.datetime.fromisoformat(submitted)+datetime.timedelta(seconds=480)
   poll=datetime.datetime.fromisoformat(last)+datetime.timedelta(seconds=120) if last else first
   limit=datetime.datetime.fromisoformat(state['nextQueryAt']) if state.get('nextQueryAt') else first
   next_at=max(first,poll,limit).isoformat()
  except (ValueError,TypeError):pass
 return {'submittedAt':submitted,'lastCheckedAt':last,'receivedAt':archive.get('receivedAt'),'estimatedNextQueryAt':next_at,'platformGenerationSeconds':next((f.get('taskCostTime') for f in archive.get('files',[]) if f.get('taskCostTime') is not None),None)}
