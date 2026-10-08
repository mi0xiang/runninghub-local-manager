"""Classify identities without migrating or filling historical records."""
import re

LABELS={'LARK':'Lark协作','INDEPENDENT':'自主创作','UNCLASSIFIED':'待分类'}

def classify(*records):
    records=[r for r in records if isinstance(r,dict)]
    explicit={r['business_line'] for r in records if r.get('business_line')}
    sources={r['source_key'] for r in records if r.get('source_key')}
    rows={r['record_id'] for r in records if r.get('record_id')}
    creations={r['creation_key'] for r in records if r.get('creation_key')}
    conflict=(len(explicit)>1 or len(sources)>1 or len(rows)>1 or len(creations)>1
              or bool(explicit-{'LARK','INDEPENDENT','UNCLASSIFIED'})
              or ('INDEPENDENT' in explicit and bool(sources or rows)))
    if conflict:return {'line':'UNCLASSIFIED','reason':'身份记录冲突，待主协调核对','conflict':True}
    if explicit=={'UNCLASSIFIED'}:line='UNCLASSIFIED'
    elif explicit=={'INDEPENDENT'} and creations:line='INDEPENDENT'
    elif sources and rows and re.fullmatch(r'tiktok:\d+',next(iter(sources))) and explicit<={'LARK'}:line='LARK'
    else:line='UNCLASSIFIED'
    return {'line':line,'reason':LABELS[line] if line!='UNCLASSIFIED' else '缺少可确认的业务身份，待分类','conflict':False}
