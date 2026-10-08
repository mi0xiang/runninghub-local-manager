"""Only loopback HTTP fixtures; never production media, service or cloud endpoints."""
import json
import ast
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP/'scripts/core'))
import control_server

class ReadOnlyRoutes(unittest.TestCase):
    def test_home_and_supervision_have_clear_bidirectional_navigation(self):
        sys.path.insert(0,str(APP/'scripts'))
        import hub,supervision
        homepage=hub.index_html([])
        self.assertIn('<a href="/supervision.html"',homepage)
        self.assertIn('全流程制作面板',homepage)
        self.assertIn('id="filter"',homepage)
        panel=supervision.render_panel({'projects':[],'alerts':[],'observed_at':'fixture'})
        self.assertIn('<a href="/index.html">← 生成任务与历史</a>',panel)

    @unittest.skipUnless(os.environ.get('H3_SCOPED_ADAPTER'),'Set H3_SCOPED_ADAPTER for machine adapter fixture')
    def test_machine_adapter_adds_business_summary_without_rendering_children(self):
        sys.path.insert(0,str(APP/'scripts'))
        import hub
        tree=ast.parse(Path(os.environ['H3_SCOPED_ADAPTER']).read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP' for t in node.targets):
                node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(APP))],keywords=[])
        ast.fix_missing_locations(tree)
        prior=hub.ALLOW_EXPLICIT_CHILD_RENDER
        try:
            module={'__name__':'scoped_adapter_fixture'}
            exec(compile(tree,'scoped_adapter_fixture','exec'),module)
            self.assertFalse(hub.ALLOW_EXPLICIT_CHILD_RENDER)
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);folder=root/'projects/video';folder.mkdir(parents=True)
                (root/'projects.json').write_text(json.dumps({'projects':[{'id':'video','path':'projects/video','title':'Synthetic','updatedAt':'2026-01-01T00:00:00+00:00','conversation':'Fixture'}]}))
                (folder/'batches.json').write_text('[]');(folder/'index.html').write_text('KEEP CHILD')
                with patch.object(hub,'ROOT',root),patch.object(hub,'control_ui',side_effect=lambda p,*args:p):
                    module['inventory']()
                self.assertEqual((folder/'index.html').read_text(),'KEEP CHILD')
                self.assertIn('待人工审核',(root/'index.html').read_text(encoding='utf-8'))
        finally:hub.ALLOW_EXPLICIT_CHILD_RENDER=prior

    def test_panel_api_and_range_read_only_server_never_launches_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'projects.json').write_text('{"projects":[]}')
            media=root/'projects/example/original.mp4';media.parent.mkdir(parents=True);media.write_bytes(b'0123456789')
            server=ThreadingHTTPServer(('127.0.0.1',0),control_server.Handler)
            server.read_only=True
            port=server.server_address[1]
            with patch.object(control_server,'ROOT',root),patch.object(control_server,'PORT',port),patch.object(control_server,'launch',side_effect=AssertionError('No execution')):
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    base=f'http://127.0.0.1:{port}'
                    with urllib.request.urlopen(base+'/supervision.html') as response:
                        self.assertEqual(response.status,200)
                        self.assertIn('视频制作任务面板',response.read().decode())
                    with urllib.request.urlopen(base+'/api/supervision') as response:
                        self.assertTrue(json.load(response)['read_only'])
                    request=urllib.request.Request(base+'/projects/example/original.mp4',headers={'Range':'bytes=2-5'})
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(response.status,206)
                        self.assertEqual(response.read(),b'2345')
                    request=urllib.request.Request(base+'/api/control',data=b'{"action":"resume"}',headers={'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code,403)
                finally:server.shutdown();thread.join();server.server_close()
            self.assertFalse((root/'control_token.json').exists())

    def test_background_summary_refresh_does_not_rewrite_child_pages(self):
        sys.path.insert(0,str(APP/'scripts'))
        import hub
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);folder=root/'projects/video';folder.mkdir(parents=True)
            (root/'projects.json').write_text(json.dumps({'projects':[{'id':'video','path':'projects/video','title':'Synthetic','updatedAt':'2026-01-01T00:00:00+00:00','conversation':'Fixture'}]}))
            (folder/'batches.json').write_text('[]')
            (folder/'index.html').write_text('KEEP CHILD PAGE')
            with patch.object(hub,'ROOT',root),patch.object(hub,'control_ui',side_effect=lambda p,*args:p):
                hub.run(False)
            self.assertEqual((folder/'index.html').read_text(encoding='utf-8'),'KEEP CHILD PAGE')
            self.assertIn('待人工审核',(root/'index.html').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
