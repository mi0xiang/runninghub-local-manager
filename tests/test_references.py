import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/core'))
import native_references as n
class ReferenceSlots(unittest.TestCase):
 def test_all_audio_video_counts(self):
  template={'265':{'inputs':{}}}
  for node in n.AUDIO:template[node]={'class_type':'LoadAudio','inputs':{'audio':'placeholder'}}
  for node in n.VIDEO:template[node]={'class_type':'VHS_LoadVideo','inputs':{'video':'placeholder'}}
  for a in range(4):
   for v in range(4):
    g,m=n.configure(template,[f'assets/a{i}.wav' for i in range(a)],[f'assets/v{i}.mp4' for i in range(v)])
    n.verify(g,m)
    self.assertEqual(m['audio_node_ids'],n.AUDIO[:a]);self.assertEqual(m['video_node_ids'],n.VIDEO[:v])
 def test_video_native_field(self):
  self.assertEqual(n.video_field({'class_type':'VHS_LoadVideo','inputs':{'video':'x'}}),'video')
if __name__=='__main__':unittest.main()
