import sys,json,hashlib,tempfile,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import standard_smd as sm,polygon_smd,model3d_pipeline as model
class StandardSmdTests(unittest.TestCase):
 def fixture(self,device):
  r=copy.deepcopy(next(r for r in sm.catalog() if r['device']==device));temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);p=Path(temp.name)/'reviewed.pdf';p.write_bytes(b'%PDF-test-fixture');r['source']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();return r,sm.specification(r,p),p
 def test_series_specific_pads_and_inductor_layout(self):
  _,r,_=self.fixture('R0402_CRCW');_,c,_=self.fixture('C0402_VJ');self.assertNotEqual(r['pads'][0]['copper'],c['pads'][0]['copper']);self.assertEqual(c['height_selection'],'maximum_envelope')
  rec,s,_=self.fixture('L_SRN2012T_4R7K');self.assertEqual(rec['pad'],[1.02,1.78]);self.assertAlmostEqual(2*rec['pad'][0]+rec['gap'],2.80)
  self.assertEqual(len(polygon_smd.validate(s)),2)
 def test_changed_source_rejected_and_height_not_silently_overridden(self):
  r,s,path=self.fixture('C0603_VJ');path.write_bytes(b'%PDF-new-version')
  with self.assertRaises(ValueError):sm.specification(r,path)
  with self.assertRaises(ValueError):model.plan(s,{'confirmed':True,'total_height':2.0})
  self.assertEqual(model.plan(s,{'confirmed':True})['total_height'],.97)
 def test_native_project_endpoints_on_grid_and_diode_polarity(self):
  import assistant_core as core
  r,s,_=self.fixture('D_1N4148WT_SOD523');p=sm.project(r,s);cfg,pins=core.layout(p,core.DEFAULT_ENV)
  self.assertEqual({pin[0]:pin[1] for pin in pins},{'1':'K','2':'A'})
  self.assertTrue(all(v%10==0 for pin in pins for v in pin[3:]));self.assertEqual(p['symbol_graphics']['designator'],'D')
 def test_all_recipes_have_sources_and_separate_copper_mask_paste(self):
  for recipe in sm.catalog():
   r,s,_=self.fixture(recipe['device']);polygon_smd.validate(s);self.assertTrue(r['source']['url'].startswith('https://'));self.assertEqual(len(r['source']['sha256']),64);self.assertEqual(s['pads'][0]['id'],'1')
 def test_package_text_only_on_rc_and_short_pins_keep_connectivity(self):
  import assistant_core as core
  import xml.etree.ElementTree as ET
  for name in ('R0402_CRCW','C0603_VJ','L_SRN2012T_4R7K','D_1N4148WT_SOD523'):
   r,s,_=self.fixture(name);p=sm.project(r,s);cfg,pins=core.layout(p,core.DEFAULT_ENV);g=p['symbol_graphics'];rc=r['category'] in ('resistor','capacitor')
   self.assertEqual({x[0]:x[1] for x in pins},{x['id']:x['name'] for x in p['pins']})
   self.assertTrue(all(v%10==0 for pin in pins for v in pin[3:]))
   self.assertEqual({abs(x-hx)+abs(y-hy) for _,_,_,x,y,hx,hy in pins},{10 if rc else 30})
   with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'preview.svg';core.export_svg(cfg,pins,path,g);svg=ET.fromstring(path.read_text(encoding='utf8'));texts=[e for e in svg.iter() if e.tag.endswith('text')];sizes=[e.text for e in texts if e.get('data-package-size')]
    self.assertEqual(sizes,[name[1:5]] if rc else [])
    # Names can be hidden without deleting numbers or diode polarity.
    self.assertEqual(len(texts),4 if rc else 5)
   if rc:
    self.assertFalse(g['pin_names_visible']);self.assertEqual(g['pin_length_style'],'short')
    self.assertLess(cfg['REF_POS'][1],0);self.assertLess(cfg['VAL_POS'][1],0)
  r,s,_=self.fixture('R0402_CRCW');r['device']='R0201_EXAMPLE'
  self.assertEqual(sm.project(r,s)['symbol_graphics']['texts'][0]['text'],'0201')
if __name__=='__main__':unittest.main()
