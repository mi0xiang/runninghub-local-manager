import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP/'scripts/core'))
import portable_runtime as rt

class CleanInstall(unittest.TestCase):
 def test_empty_and_idempotent(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'local data';rt.initialize(root)
   self.assertEqual(json.loads((root/'projects.json').read_text())['projects'],[])
   sentinel={'projects':[{'id':'synthetic'}]};(root/'projects.json').write_text(json.dumps(sentinel))
   rt.initialize(root);self.assertEqual(json.loads((root/'projects.json').read_text()),sentinel)
 def test_bound_configuration(self):
  with tempfile.TemporaryDirectory() as td:
   cfg={'data_dir':td,'ffmpeg':'ffmpeg'}
   self.assertFalse(rt.is_confirmed(cfg));cfg=rt.bind(cfg);self.assertTrue(rt.is_confirmed(cfg))
   cfg['data_dir']=td+'/moved';self.assertFalse(rt.is_confirmed(cfg))
 def test_repository_data_rejected(self):
  with self.assertRaises(ValueError):rt.validate_data_dir(APP/'data')
 def test_fresh_install_render_without_network(self):
  with tempfile.TemporaryDirectory() as td:
   temp=Path(td);cfg=temp/'config.json';data=temp/'data';env=dict(os.environ,RUNNINGHUB_CONFIG_FILE=str(cfg))
   subprocess.run([sys.executable,str(APP/'manage.py'),'init','--data-dir',str(data)],env=env,check=True,capture_output=True)
   blocked=subprocess.run([sys.executable,str(APP/'manage.py'),'tick'],env=env,capture_output=True)
   self.assertNotEqual(blocked.returncode,0)
   # Test-only configuration binding; production confirmation is interactive.
   cfg.write_text(json.dumps(rt.bind(json.loads(cfg.read_text()))))
   snippet="import sys,socket,runpy;sys.argv=[sys.argv[1],'render'];socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden'));runpy.run_path(sys.argv[0],run_name='__main__')"
   result=subprocess.run([sys.executable,'-c',snippet,str(APP/'scripts/hub.py')],env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertTrue((data/'index.html').exists())
   self.assertEqual(json.loads((data/'projects.json').read_text())['projects'],[])
   self.assertEqual(json.loads((data/'queue_state.json').read_text())['jobs'],[])
 def test_public_source_has_no_runtime_roots(self):
  for name in ('projects.json','queue_state.json','control_token.json','projects','workflow_baselines'):
   self.assertFalse((APP/name).exists(),name)

if __name__=='__main__':unittest.main()
