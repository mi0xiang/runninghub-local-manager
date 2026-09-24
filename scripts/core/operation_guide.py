import portable_runtime
"""Render the single authoritative operation guide on every hub render."""
import html

def render(root):
 source=(portable_runtime.APP/'docs/local-controls-and-versions.md').read_text(encoding='utf-8')
 parts=[]
 for line in source.splitlines():
  if not line.strip():continue
  if line.startswith('# '):parts.append('<h1>'+html.escape(line[2:])+'</h1>')
  elif line.startswith('## '):parts.append('<h2>'+html.escape(line[3:])+'</h2>')
  else:parts.append('<p>'+html.escape(line)+'</p>')
 page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>网页操作指引</title><style>body{background:#10212c;color:#e7eef2;font:16px/1.8 system-ui;max-width:1000px;margin:30px auto;padding:20px}h2{color:#88dbe8;margin-top:32px}a{color:#7de0ef}p{margin:10px 0}</style><a href="index.html">← 返回追踪首页</a>'+''.join(parts)+'</html>'
 (root/'使用指引.html').write_text(page,encoding='utf-8')
