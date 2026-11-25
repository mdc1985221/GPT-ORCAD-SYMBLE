import json,sys,unittest,copy,importlib.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant_core as c,footprint_pipeline as fp,polygon_native
class ConnectorTests(unittest.TestCase):
 def spec(self):return json.loads((Path(__file__).resolve().parents[1]/'templates/connector/shouhan_12502_12p.json').read_text(encoding='utf8'))
 def test_electrical_ids_exclude_unnumbered_mounts(self):
  s=self.spec();self.assertEqual(len(fp.geometry(s)),14);self.assertEqual(fp.electrical_ids(s),{str(i) for i in range(1,13)})
  self.assertEqual(s['pads'][-2]['xy'],[-9.425,-2.9]);self.assertEqual(s['pads'][-1]['xy'],[9.425,-2.9])
  self.assertFalse(s['orientation_confirmed']);self.assertFalse(s['draw_body']);self.assertTrue(s['unresolved'])
 def test_symbol_odd_left_even_right_without_type_conversion(self):
  p=c.new_project();p.update(device='CONNECTOR',footprint='PENDING',profile='connector',pins=[dict(id=str(i),name=str(i),type='PASS',side='',group='',part='A') for i in range(1,41)])
  c.auto_layout(p);cfg,pins=c.layout(p,c.DEFAULT_ENV)
  for side,first in [('LEFT',1),('RIGHT',2)]:
   wanted={q['id'] for q in p['pins'] if q['side']==side};ordered=sorted([q for q in pins if q[0] in wanted],key=lambda q:q[4]);self.assertEqual([int(q[0]) for q in ordered],list(range(first,41,2)))
  self.assertTrue(all(r[2]==1 and all(v%10==0 for v in r[3:]) for r in pins))
 def test_unknown_pdf_does_not_match_connector(self):
  import connector_profile
  self.assertIsNone(connector_profile.profile('missing-test.pdf'))
 def test_dip_connector_classification_requires_through_hole_metadata(self):
  from library_manager import suggest_category
  for rows in (1,2):
   self.assertEqual(suggest_category(dict(connector_rule=dict(mounting='PTH',rows=rows))),'connector-dip')
  self.assertEqual(suggest_category(dict(device='CONNECTOR',connector_rule=dict(mounting='SMT',rows=1))),'connector')
  self.assertNotEqual(suggest_category(dict(device='DIP8 IC',pins=[{}]*8)),'connector-dip')
 def test_native_generator_emits_mechanical_pin_as_nil(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   out,adir,_=polygon_native.prepare(self.spec(),Path(d)/'test');code=(adir/'package-code.txt').read_text()
   self.assertEqual(code.count(' nil) (error "Pin failed"))'),2)
   self.assertNotIn('ASSEMBLY_TOP',code.split('(setq tp (axlGetParam "paramTextBlock:2"))')[0])
