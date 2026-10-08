"""Explicit read-only cloud collection. No upload/submission imports or calls."""
import json,datetime,os,uuid
from pathlib import Path
def read(p,default=None):
 import durable_store
 return durable_store.read(p,default)
def save(p,v):
 import durable_store
 durable_store.save(p,v)
def fetch(root,pid,collect,key):
 entries=read(root/'projects.json')['projects'];selected=next((e for e in entries if e['id']==pid),None)
 if not selected:raise ValueError('Unknown project')
 pid=selected.get('source_project') or pid;results=[];secret=None
 for entry in entries:
  if entry['id']!=pid and entry.get('source_project')!=pid:continue
  folder=(root/entry['path']).resolve()
  if not folder.is_relative_to((root/'projects').resolve()):raise ValueError('Invalid project path')
  for name in read(folder/'batches.json',[]):
   d=(folder/name).resolve()
   if d.parent!=folder:raise ValueError('Invalid batch path')
   state=read(d/'task_state.json',{})
   if not state.get('taskId') or state.get('status') in ('FAILED','CANCELLED','ARCHIVED'):continue
   try:
    secret=secret or key();state.update(collect(d,secret));state['lastCheckedAt']=datetime.datetime.now().astimezone().isoformat(timespec='seconds');save(d/'task_state.json',state)
    results.append({'project':entry['id'],'batch':name,'status':state.get('status'),'taskId':state['taskId']})
   except Exception as exc:results.append({'project':entry['id'],'batch':name,'error':type(exc).__name__})
  states={n:read(folder/n/'task_state.json',{}).get('status','APPROVED') for n in read(folder/'batches.json',[])}
  status=read(folder/'tracker_status.json',{});status.update(batches=states,updatedAt=datetime.datetime.now().astimezone().isoformat(timespec='seconds'));save(folder/'tracker_status.json',status)
 return results
