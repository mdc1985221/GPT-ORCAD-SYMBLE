import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import datasheet_archive as d,footprint_naming as naming
import fitz
class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.archive=d.Archive(self.temp.name)
  doc=fitz.open();doc.new_page();self.raw=doc.tobytes();doc.close()
 def test_same_model_different_manufacturer_and_dedup(self):
  a={'device':'AON7544','manufacturer':'TECH PUBLIC'};b=dict(a,manufacturer='AOS')
  sha=self.archive.attach(a,self.raw,'TP.pdf');self.archive.attach(a,self.raw,'TP-copy.pdf')
  self.assertEqual(len(self.archive.list(a)),1);self.assertEqual(self.archive.list(b),[])
  self.assertEqual(self.archive.pdf(sha),self.raw)
  with self.assertRaises(ValueError):self.archive.pdf('../index')
  (Path(self.temp.name)/'pdf'/(sha+'.pdf')).write_bytes(b'broken')
  with self.assertRaises(ValueError):self.archive.pdf(sha)
 def test_source_remains_available_after_original_moved(self):
  p=Path(self.temp.name)/'source.pdf';p.write_bytes(self.raw);project={'device':'ABC','sources':[{'path':str(p)}]}
  self.assertEqual(self.archive.capture(project),[]);p.unlink()
  self.assertTrue(self.archive.list(project)[0]['available'])
  self.assertEqual(self.archive.pdf(self.archive.list(project)[0]['sha256']),self.raw)
 def test_history_identity_and_pdf_validation(self):
  p={'device':'AON7544','_project':{'manufacturer':'TECH PUBLIC'}}
  self.archive.attach(p,self.raw,'source.pdf');self.assertEqual(len(self.archive.list({'device':'AON7544','manufacturer':'TECH PUBLIC'})),1)
  for raw in (b'not pdf',b'%PDF-broken'):
   with self.assertRaises(Exception):self.archive.attach(p,raw,'bad.pdf')
 def test_safe_names(self):
  for n in ('AON7544_TP_DFN8_3X3_P0650','NTMFS5C430NL_DFN5_5X6_P1270'):naming.validate(n)
  for n in ('DFN-8(3x3)','CON','1ABC','ABC/DEF','A'*32):
   with self.assertRaises(ValueError):naming.validate(n)
if __name__=='__main__':unittest.main()
