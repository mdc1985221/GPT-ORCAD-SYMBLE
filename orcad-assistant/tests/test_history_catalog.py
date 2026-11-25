import io,json,sys,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from history_catalog import HistoryCatalog

class HistoryTests(unittest.TestCase):
 def test_discovers_native_files_without_promoting_validation_and_downloads_only_design(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'old';a=p/'pcb/allegro';a.mkdir(parents=True)
   (a/'TEST.psm').write_bytes(b'psm');(a/'TEST.pad').write_bytes(b'pad');(a/'seed.dra').write_bytes(b'seed');(a/'TEST.dra').write_bytes(b'dra');(a/'private.pdf').write_bytes(b'pdf')
   (p/'pcb/verification.json').write_text('{"status":"PASS"}')
   (p/'spec.json').write_text(json.dumps(dict(kind='pth_connector',name='TEST',body=[5,3],pad=1.8,drill=1,positions=[dict(id='1',x=0,y=0)])))
   h=HistoryCatalog([('test',root)]);i=h.list()['items'][0]
   self.assertTrue(i['pcb']);self.assertEqual(i['status'],'HISTORY_REVIEW_REQUIRED');self.assertEqual(i['category'],'connector-dip')
   self.assertTrue(h.detail(i['id'])['presentation']['svg'])
   with ZipFile(io.BytesIO(h.download(i['id']))) as z:
    self.assertIn('pcb/psm/TEST.psm',z.namelist());self.assertFalse(any(n.endswith(('.pdf','.dra')) for n in z.namelist()))
   with ZipFile(io.BytesIO(h.download(i['id'],True))) as z:self.assertIn('pcb/source/TEST.dra',z.namelist())
   self.assertEqual((a/'TEST.psm').read_bytes(),b'psm')
 def test_legacy_file_manifest_cannot_escape_source_folder(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);outside=root/'outside.pad';outside.write_bytes(b'private');p=root/'items/old';p.mkdir(parents=True)
   (p/'verification.json').write_text(json.dumps(dict(files={'../../outside.pad':'hash'})))
   self.assertEqual(HistoryCatalog([('test',root/'items')]).list()['items'],[])
 def test_missing_mesh_is_distinct_from_step_preview(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'old';p.mkdir();(p/'model.step').write_bytes(b'step')
   h=HistoryCatalog([('test',Path(d))]);i=h.list()['items'][0]
   self.assertEqual(i['model3d_status'],'file_only')
   with self.assertRaises(ValueError):h.mesh(i['id'])
   with self.assertRaises(ValueError):h.detail('../outside')
 def test_refresh_finds_new_build_and_keeps_versions(self):
  with tempfile.TemporaryDirectory() as d:
   h=HistoryCatalog([('test',Path(d))]);self.assertFalse(h.list()['items'])
   for name in ('v1','v2'):
    p=Path(d)/name;p.mkdir();(p/'part.OLB').write_bytes(b'olb')
   self.assertEqual(len(h.list(refresh=True)['items']),2)
 def test_previews_built_snapshot_instead_of_later_draft(self):
  import assistant_core as core
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'old';symbol=p/'symbol/build';symbol.mkdir(parents=True)
   (symbol/'PART.OLB').write_bytes(b'olb')
   built=core.new_project();built.update(device='PART',footprint='PART',expected_count=1,profile='connector',pins=[dict(id='1',name='BUILT',type='PASS',side='LEFT',group='',part='A')]);core.auto_layout(built)
   (symbol/'project.json').write_text(json.dumps(built))
   draft=dict(built,pins=[dict(built['pins'][0],id='99',name='UNBUILT')]);(p/'project.json').write_text(json.dumps(draft))
   native=p/'pcb/allegro';native.mkdir(parents=True);(native/'PART.psm').write_bytes(b'psm')
   (p/'spec.json').write_text(json.dumps(dict(body=[99,99])))
   (p/'pcb/spec.json').write_text(json.dumps(dict(kind='pth_connector',body=[5,3],pad=1.8,drill=1,positions=[dict(id='1',x=0,y=0)])))
   h=HistoryCatalog([('test',root)]);i=h.list()['items'][0];detail=h.detail(i['id'])
   self.assertEqual(detail['sections'][0]['pins'][0][0],'1');self.assertEqual(detail['sections'][0]['pins'][0][1],'BUILT')
   self.assertEqual(detail['pcb_spec']['body'],[5,3])

