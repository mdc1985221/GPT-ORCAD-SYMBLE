import sys,json,hashlib,tempfile,shutil,unittest,io
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant_core as core
from history_catalog import HistoryCatalog
from library_manager import Library
class HistoryImportTests(unittest.TestCase):
 def fixture(self,base):
  source=base/'review'/'DIP2';a=source/'pcb/allegro';a.mkdir(parents=True)
  project=core.new_project();project.update(device='DIP2',footprint='DIP2',profile='connector',pins=[dict(id=str(i),name=str(i),type='PASS',side='LEFT' if i==1 else 'RIGHT',group='',part='A') for i in (1,2)],expected_count=2,library_category='connector-dip');core.auto_layout(project)
  spec=dict(kind='pth_connector',name='DIP2',body=[5,5],drill=1,pad=1.8,mask_diameter=2,positions=[dict(id='1',x=0,y=-1.27),dict(id='2',x=0,y=1.27)])
  (source/'project.json').write_text(json.dumps(project));(source/'spec.json').write_text(json.dumps(spec));(source/'DIP2.OLB').write_bytes(b'OLB fixture')
  for n in ['dip2.psm','dip2.pad','dip2.dra']:(a/n).write_bytes(n.encode())
  model=source/'model3d';model.mkdir();(model/'DIP2.step').write_bytes(b'STEP storage fixture');(model/'mesh.json').write_text(json.dumps(dict(bounds=[-1,-1,-3,1,1,8.5],meshes=[])))
  (model/'verification.json').write_text(json.dumps(dict(status='PASS',step='DIP2.step',file_hashes={n:hashlib.sha256((model/n).read_bytes()).hexdigest() for n in ['DIP2.step','mesh.json']})))
  hist=HistoryCatalog([('test',base/'review')]);record=hist.get(hist.list()['items'][0]['id']);return source,record
 def test_persistent_complete_copy_and_idempotent_import(self):
  with tempfile.TemporaryDirectory() as t:
   base=Path(t);source,record=self.fixture(base);lib=Library(base/'library',base/'output');item=lib.import_history(record)
   self.assertEqual(lib.import_history(record)['id'],item['id']);self.assertEqual(len(lib.list()),1);self.assertEqual(item['status'],'HISTORY_IMPORTED')
   shutil.rmtree(source)
   self.assertEqual(len(lib.detail(item['id'])['pads']),2);self.assertIsNotNone(lib.model_mesh(item['id']))
   with ZipFile(io.BytesIO(lib.design_bytes(item['id']))) as z:
    self.assertIn('3d/DIP2.step',z.namelist());self.assertIn('symbol/DIP2.OLB',z.namelist());self.assertIn('pcb/psm/dip2.psm',z.namelist());self.assertFalse(any(n.endswith('.dra') for n in z.namelist()))
 def test_reject_external_paths_and_changed_mesh(self):
  with tempfile.TemporaryDirectory() as t:
   base=Path(t);source,record=self.fixture(base);lib=Library(base/'library',base/'output')
   outsider=base/'outside.OLB';outsider.write_bytes(b'x');original=dict(record['_files']);record['_files']={'symbol/outside.OLB':str(outsider)}
   with self.assertRaises(ValueError):lib.import_history(record)
   record['_files']=original;(source/'model3d/mesh.json').write_text('{}')
   with self.assertRaises(ValueError):lib.import_history(record)
   self.assertEqual(lib.list(),[])
if __name__=='__main__':unittest.main()
