import copy,json,sys,tempfile,unittest,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import polygon_smd as q
import polygon_native as native
import polygon_model3d as model
from shapely.geometry import Polygon
class PolygonQFNTests(unittest.TestCase):
 def setUp(self):self.spec=json.loads((q.BASE/'templates/qfn/tps543620.json').read_text(encoding='utf8'))
 def test_distinct_copper_mask_and_manufacturer_paste_coverage(self):
  s=self.spec;self.assertEqual(len(q.validate(s)),14)
  by={p['id']:p for p in s['pads']};self.assertEqual(by['10']['mask_type'],'SMD')
  self.assertNotEqual(by['10']['copper'],by['10']['mask'])
  for pid,wanted in [('1',93),('5',93),('9',91),('11',91),('10',96)]:
   p=by[pid];a=Polygon(p['copper'][0]).intersection(Polygon(p['mask'][0])).area
   self.assertEqual(round(Polygon(p['paste'][0]).area/a*100),wanted)
 def test_invalid_duplicate_overlap_and_self_intersection_block(self):
  for mode in ['duplicate','overlap','cross','anchor','paste']:
   s=copy.deepcopy(self.spec)
   if mode=='duplicate':s['pads'][1]['id']='1'
   if mode=='overlap':s['pads'][1]['copper']=s['pads'][0]['copper']
   if mode=='cross':s['pads'][0]['copper']=[[[0,0],[1,1],[0,1],[1,0]]]
   if mode=='anchor':s['pads'][0]['xy']=[50,50]
   if mode=='paste':s['pads'][0]['paste']=[[[5,5],[6,5],[6,6],[5,6]]]
   with self.subTest(mode=mode),self.assertRaises(ValueError):q.validate(s)
 def test_terminal_model_uses_package_not_board_land(self):
  p=model.plan(self.spec,dict(confirmed=True,total_height=.9));self.assertEqual(len(p['terminal_profile']['contours']),14)
  self.assertNotEqual(p['terminal_profile']['contours'][0]['outline'],self.spec['pads'][0]['copper'][0])
  for value in [False,-1,1.1,float('nan')]:
   with self.assertRaises(ValueError):model.plan(self.spec,dict(confirmed=True,total_height=value))
 def test_unconfirmed_or_missing_terminal_data_blocks_3d(self):
  for s,opts in [(self.spec,dict(confirmed=False)),({k:v for k,v in self.spec.items() if k!='terminal_profile'},dict(confirmed=True))]:
   with self.assertRaises(ValueError):model.plan(s,opts)
 def test_native_layer_multiwindow_not_silently_dropped(self):
  s=copy.deepcopy(self.spec);p=s['pads'][0];old=Polygon(p['paste'][0]);a,b,c,d=old.bounds
  p['paste']=[[[a+.02,b+.01],[a+.05,b+.01],[a+.05,b+.04],[a+.02,b+.04]],[[a+.08,b+.01],[a+.11,b+.01],[a+.11,b+.04],[a+.08,b+.04]]]
  with tempfile.TemporaryDirectory() as folder,self.assertRaisesRegex(ValueError,'多窗口'):
   native.prepare(s,Path(folder)/'result')
 def test_profile_asset_names_change_when_shape_changes(self):
  a=q.native_assets(self.spec);s=copy.deepcopy(self.spec);s['pads'][0]['paste'][0][0][0]+=.001
  b=q.native_assets(s);self.assertNotEqual(a['1'],b['1']);self.assertEqual(a['2'],b['2'])

 def test_polygon_report_does_not_trigger_legacy_ball_migration(self):
  import assistant_core as core
  p=dict(generated=dict(report=dict(status='PASS',pcb=dict(status='PASS',kind='polygon_smd',revision=1,units='millimeters',imports=['millimeters','mils']))))
  core.invalidate_legacy_pcb(p);self.assertEqual(p['generated']['report']['status'],'PASS')
