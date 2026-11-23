import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant_core as c
class LayoutTemplateTests(unittest.TestCase):
 def project(self):
  p=c.new_project();p.update(device='TPS543620',footprint='RPY0014A')
  rows=[('1','SYNC/FSEL','IN'),('2','MODE','IN'),('3','PGOOD','OUT'),('4','FB','IN'),('5','AGND','GND'),('6','BP5','OUT'),('7','EN','IN'),('8','VIN','PWR'),('9','PGND','GND'),('10','SW','OUT'),('11','PGND','GND'),('12','VIN','PWR'),('13','SW','OUT'),('14','BOOT','PWR')]
  p['pins']=[dict(id=i,name=n,type=t,side='',group='',part='A',confidence=1.,conflicts=[]) for i,n,t in rows];return p
 def test_power_recommendation_and_all_four_sides(self):
  p=self.project();before={q['id']:(q['name'],q['type']) for q in p['pins']};c.auto_layout(p)
  self.assertEqual(c.effective_profile(p),'power')
  self.assertEqual({side:{q['id'] for q in p['pins'] if q['side']==side} for side in c.SIDES},dict(TOP={'8','12','6','14'},BOT={'5','9','11'},LEFT={'1','2','3','7'},RIGHT={'4','10','13'}))
  self.assertEqual(before,{q['id']:(q['name'],q['type']) for q in p['pins']})
  self.assertEqual([q['id'] for q in p['pins'] if q['side']=='TOP'],['8','12','6','14'])
  cfg,pins=c.layout(p,c.DEFAULT_ENV);self.assertTrue(all(v%10==0 for q in pins for v in q[3:]))
 def test_manual_selection_wins_over_recommendation(self):
  p=self.project();p['profile']='generic';c.auto_layout(p)
  self.assertEqual(c.effective_profile(p),'generic');self.assertEqual(next(q['side'] for q in p['pins'] if q['name']=='BP5'),'RIGHT')
  p['profile']='sensor';c.auto_layout(p);self.assertEqual(next(q['side'] for q in p['pins'] if q['name']=='SW'),'LEFT')
 def test_sensor_recommendation_preserves_original_mipi_rules(self):
  p=self.project();p.update(device='GC5613',footprint='CSP43');p['pins']=[dict(id='A1',name='MCP',type='OUT',part='A')]
  c.auto_layout(p);self.assertEqual(c.effective_profile(p),'sensor');self.assertEqual(p['pins'][0]['side'],'RIGHT')
 def test_persist_every_template_and_reject_unknown(self):
  for profile in c.LAYOUT_PROFILES:
   p=self.project();p['profile']=profile;c.auto_layout(p)
   with tempfile.TemporaryDirectory() as folder:
    f=Path(folder)/'p.json';c.atomic_json(f,p);self.assertEqual(c.load_project(f)['profile'],profile)
  p=self.project();p['profile']='invalid'
  with self.assertRaises(ValueError):c.auto_layout(p)
