"""Real tiny media fixtures test ordered, frozen local assembly; no cloud calls."""
import copy, hashlib, importlib, importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP/'scripts/core'))
import portable_runtime, postproduction_records
def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf-8')
class PostproductionExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
        self.ff=portable_runtime.tool('ffmpeg');self.fp=portable_runtime.tool('ffprobe')
        for name,color in [('first','red'),('second','blue')]:
            target=self.folder/(name+'.mp4')
            subprocess.run([self.ff,'-v','error','-f','lavfi','-i',f'color=c={color}:s=64x64:r=24:d=1',
                '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(target)],
                check=True,capture_output=True)
        self.spec={'schema_version':1,'version':'fixture-v1','segments':[
            {'segment_id':'S01','taskId':'first-task','file':'first.mp4','sha256':self.digest('first.mp4'),'start':0,'end':0.5},
            {'segment_id':'S02','taskId':'second-task','file':'second.mp4','sha256':self.digest('second.mp4'),'start':0,'end':0.5}],
            'quality_review':{'status':'ACCEPTED','evidence':['content-review.md']},'audio':{'mode':'generated'}}
        (self.folder/'content-review.md').write_text('Fixture branch content review')
    def digest(self,name):return hashlib.sha256((self.folder/name).read_bytes()).hexdigest()
    def executor(self):
        self.assertIsNotNone(importlib.util.find_spec('postproduction_executor'),'Frozen ordered assembly executor is missing')
        return importlib.import_module('postproduction_executor')
    def test_order_duration_audio_decode_and_repeated_execution(self):
        e=self.executor();postproduction_records.register_plan(self.folder,self.spec,0)
        first=e.assemble(self.folder)
        path=self.folder/first['result_video']
        self.assertTrue(path.is_file());self.assertEqual(first['state'],'ASSEMBLED')
        self.assertAlmostEqual(first['duration_seconds'],1,delta=0.12)
        self.assertTrue(first['technical']['decode'])
        self.assertFalse(first['content_accepted'])
        info=json.loads(subprocess.check_output([self.fp,'-v','error','-show_streams','-of','json',str(path)]))
        self.assertTrue(any(x['codec_type']=='audio' for x in info['streams']))
        def pixel(at):
            return subprocess.check_output([self.ff,'-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
        red,blue=pixel(0.1),pixel(0.7)
        self.assertGreater(red[0],red[2]);self.assertGreater(blue[2],blue[0])
        old=path.read_bytes();second=e.assemble(self.folder)
        self.assertEqual(second['sha256'],first['sha256']);self.assertEqual(path.read_bytes(),old)
        self.assertFalse((self.folder/'delivery.json').exists())
    def test_unaccepted_content_and_unapproved_audio_never_run_media(self):
        e=self.executor();bad=copy.deepcopy(self.spec);bad['quality_review']['status']='PENDING'
        postproduction_records.register_plan(self.folder,bad,0)
        with self.assertRaises(ValueError):e.assemble(self.folder)
        bad=copy.deepcopy(self.spec);bad['audio']={'mode':'source','file':'first.mp4','sha256':self.digest('first.mp4'),'authorized':False}
        postproduction_records.register_plan(self.folder,bad,1)
        with self.assertRaises(ValueError):e.assemble(self.folder)
    def test_wrong_order_input_hash_and_out_of_bounds_trim_are_blocked(self):
        e=self.executor()
        put(self.folder/'execution-plan.json',{'schema_version':1,'segments':[{'segment_id':'S01'},{'segment_id':'S02'}]})
        bad=copy.deepcopy(self.spec);bad['segments'].reverse()
        postproduction_records.register_plan(self.folder,bad,0)
        with self.assertRaises(ValueError):e.assemble(self.folder)
        good=postproduction_records.register_plan(self.folder,self.spec,1)
        (self.folder/'first.mp4').write_bytes(b'changed')
        with self.assertRaises(ValueError):e.assemble(self.folder)
    def test_none_audio_mode_produces_no_unrequested_audio(self):
        e=self.executor();spec=copy.deepcopy(self.spec);spec['audio']={'mode':'none'}
        postproduction_records.register_plan(self.folder,spec,0);out=e.assemble(self.folder)
        info=json.loads(subprocess.check_output([self.fp,'-v','error','-show_streams','-of','json',str(self.folder/out['result_video'])]))
        self.assertFalse(any(x['codec_type']=='audio' for x in info['streams']))
    def test_external_audio_offset_cannot_silently_shorten_soundtrack(self):
        e=self.executor();spec=copy.deepcopy(self.spec)
        spec['audio']={'mode':'source','file':'first.mp4','sha256':self.digest('first.mp4'),'authorized':True,
                       'authorization_evidence':['content-review.md'],'start':0.75}
        postproduction_records.register_plan(self.folder,spec,0)
        with self.assertRaises(ValueError):e.assemble(self.folder)
        self.assertFalse((self.folder/'assembly.json').exists())
    def test_actual_trim_bounds_are_checked_before_encoding(self):
        e=self.executor();spec=copy.deepcopy(self.spec);spec['segments'][0]['end']=3
        postproduction_records.register_plan(self.folder,spec,0)
        with self.assertRaises(ValueError):e.assemble(self.folder)
        self.assertFalse((self.folder/'assembly.json').exists())
if __name__=='__main__':unittest.main()
