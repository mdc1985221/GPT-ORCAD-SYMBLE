import copy
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pcb_workflow as pcb

class Page:
    def __init__(self,text):self.text=text
    def get_text(self):return self.text
class Doc(list):
    def __enter__(self):return self
    def __exit__(self,*args):pass

class PCBWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.pins=[dict(id=r+str(c)) for r in 'ABCDE' for c in range(1,8)]
        self.text='GC4693\nMillimeters\nTop View(Bumps Down)\n'+ '\n'.join(
          f'{label}\n{symbol}\n{value}' for label,symbol,value in [
           ('Package Body Dimension X','A',5.805),('Package Body Dimension Y','B',3.635),
           ('Pins pitch X axis','J1',.640),('Pins pitch Y axis','J2',.580),
           ('Ball Count X axis','N1',7),('Ball Count Y axis','N2',5),('Total Ball Count','N',35),
           ('Ball Diameter','D',.250),('Edge to Pin Center Distance along X','S1',.92243),
           ('Edge to Pin Center Distance along X','S3',1.04257),('Edge to Pin Center Distance along Y','S2',.70215),
           ('Edge to Pin Center Distance along Y','S4',.61285)])+'\nPackage Height\nC\n0.670\n0.610\n0.730'
    def extract(self,text=None,pins=None):
        with patch('fitz.open',return_value=Doc([Page(text or self.text)])):
            return pcb.inspect_pdf('not-filename-GC4693.pdf',self.pins if pins is None else pins)
    def test_extract_nominal_and_provenance_without_implicit_confirmation(self):
        data=self.extract();self.assertFalse(data['confirmed']);self.assertEqual(data['needs'],[])
        self.assertEqual(data['spec']['body'],[5.805,3.635]);self.assertEqual(len(data['sources']),13)
        self.assertAlmostEqual(data['spec']['centers']['BGA'][0],.06007)
        self.assertAlmostEqual(data['spec']['edge']['left_to_col1'],1.04257)
        self.assertAlmostEqual(data['spec']['edge']['right_to_colN'],.92243)
        self.assertEqual(data['spec']['height_max'],.730)
    def test_missing_height_retains_preview_but_blocks_native_generation(self):
        data=self.extract(self.text.split('Package Height')[0])
        self.assertIsNotNone(data['spec'])
        self.assertTrue(any('高度' in n for n in data['needs']))
        with self.assertRaisesRegex(ValueError,'高度'):
            pcb.check(dict(pins=self.pins,pcb=data,footprint='GC4693'))

    def test_legacy_gc4693_top_orientation_is_migrated_once(self):
        data=self.extract();s=data['spec']
        s['edge']['left_to_col1'],s['edge']['right_to_colN']=.92243,1.04257
        s['centers']={'BGA':[-.06007,-.04465],'OPT':[-.06007,-.04465]}
        data['confirmed']=True
        project=dict(device='GC4693',pcb=data,generated={'archive':'old.zip'})
        pcb.enrich_project(project)
        self.assertEqual(s['centers']['BGA'],[.06007,-.04465])
        self.assertEqual(s['centers']['OPT'],[.06007,-.04465])
        self.assertEqual(s['edge']['left_to_col1'],1.04257)
        self.assertFalse(data['confirmed']);self.assertIsNone(project['generated'])
        before=copy.deepcopy(project);pcb.enrich_project(project);self.assertEqual(project,before)

    def test_orientation_migration_preserves_custom_optical_coordinate(self):
        data=self.extract();s=data['spec']
        s['edge']['left_to_col1'],s['edge']['right_to_colN']=.92243,1.04257
        s['centers']={'BGA':[-.06007,-.04465],'OPT':[.1,.2]}
        project=dict(device='GC4693',pcb=data)
        pcb.enrich_project(project)
        self.assertEqual(s['centers']['OPT'],[.1,.2])

    def test_orientation_migration_accepts_float_tail_in_optical_center(self):
        data=self.extract();s=data['spec']
        s['edge']['left_to_col1'],s['edge']['right_to_colN']=.92243,1.04257
        s['centers']={'BGA':[-.06007,-.04465],'OPT':[-.06007000000000001,-.04465000000000002]}
        pcb.enrich_project(dict(device='GC4693',pcb=data))
        self.assertEqual(s['centers']['OPT'],s['centers']['BGA'])

    def test_partially_migrated_optical_center_is_repaired_once(self):
        data=self.extract();s=data['spec']
        s['centers']={'BGA':[.06007,-.04465],'OPT':[-.06007000000000001,-.04465000000000002]}
        data['confirmed']=True
        project=dict(device='GC4693',pcb=data,generated={'archive':'stale.zip'})
        pcb.enrich_project(project)
        self.assertEqual(s['centers']['OPT'],s['centers']['BGA'])
        self.assertFalse(data['confirmed']);self.assertIsNone(project['generated'])
        before=copy.deepcopy(project);pcb.enrich_project(project);self.assertEqual(before,project)

    def test_correct_orientation_preserves_custom_optical_center(self):
        for optical in ([.1,.2],[-.06007,.1]):
            data=self.extract();data['spec']['centers']['OPT']=optical[:]
            project=dict(device='GC4693',pcb=data)
            pcb.enrich_project(project)
            self.assertEqual(data['spec']['centers']['OPT'],optical)

    def test_os04a10_extracts_nonuniform_rows_and_optical_center(self):
        mechanical='''OS04A10\ntable 9-1 package dimensions (sheet 1 of 2)\npackage body dimension x\nA\n10630\n10680\n10730\nµm\npackage body dimension y\nB\n8490\n8540\n8590\nµm\npackage heighta\nC\n649\n695\n741\nµm\nball height\nC1\n218\n240\n262\nµm\npackage body thickness\nC2\n431\n455\n479\nµm\nball diameter\nD\n306\n314\n322\nµm\nball pitch x axis\nJ1\n720\nµm\nball pitch y1 axis\nJ2\n600\nµm\nball pitch y2 axis\nJ3\n955\nµm\ntotal ball countb\nN\n72 (4 NC)\nedge to ball center distance along x\nS1\n225\n300\n375\nµm\nedge to ball center distance along y\nS2\n253\n328\n403\nµm\nball placement: solder ball diameter 300µm\nPCB design recommendations\nrecommended PCB NSMD ball pad size'''
        mechanical += '\ndie body dimension x\na\n8842\nµm\ndie body dimension y\nb\n5455\nµm\nglass material thickness is 400µm'
        optical='''OS04A10\n10.1 sensor array center\nfigure 10-1 sensor array center\n7841.6 µm\n4454.4 µm\ntop view\narray center and\npackage center and\nchip center\n(0 µm, 0 µm)'''
        ids={r+str(c) for r in 'ABJK' for c in range(1,16)}|{r+str(c) for r in 'CDEFGH' for c in (1,15)}
        pins=[dict(id=pid) for pid in sorted(ids)]
        with patch('fitz.open',return_value=Doc([Page(mechanical),Page(optical)])):
            data=pcb.inspect_pdf('os04a10.pdf',pins)
        spec=data['spec'];pads={p[0]:p[1:] for p in pcb.fp.geometry(spec)}
        self.assertEqual(data['needs'],[])
        self.assertEqual(spec['body'],[10.68,8.54]);self.assertEqual(spec['height_max'],.741)
        self.assertEqual(spec['glass_thickness'],.4)
        self.assertEqual(spec['die_size'],[8.842,5.455])
        self.assertIsNone(spec['mechanical_dimensions']['a']['min'])
        self.assertEqual(spec['mechanical_dimensions']['D']['min'],.306)
        self.assertEqual(spec['ball_height'],.240);self.assertEqual(spec['body_thickness'][1],.455)
        self.assertEqual(spec['centers'],{'BGA':[0,0],'OPT':[0,0]})
        self.assertEqual(spec['row_pitch_y'],[.6]+[.955]*7+[.6])
        self.assertEqual(spec['pad_dia'],.225);self.assertEqual(len(pads),72)
        self.assertAlmostEqual(pads['A1'][0],-5.04);self.assertAlmostEqual(pads['A1'][1],3.9425)
        self.assertAlmostEqual(pads['K15'][0],5.04);self.assertAlmostEqual(pads['K15'][1],-3.9425)
        from templates.footprint.reference_generator import compute
        generated=compute(spec)
        self.assertEqual(len(generated['pads']),72)
        self.assertAlmostEqual(generated['arr_c'][0],0);self.assertAlmostEqual(generated['arr_c'][1],0)
        self.assertTrue(any(x['field']=='光学中心与方向' and x['page']==2 for x in data['sources']))
    def test_conflicting_package_heights_are_not_guessed(self):
        data=self.extract(self.text+'\nPackage Height\nC\n0.700\n0.600\n0.800')
        self.assertNotIn('height_max',data['spec'])
    def test_missing_pin_not_silently_converted_to_missing_ball(self):
        data=self.extract(pins=self.pins[:-1]);self.assertIsNone(data['spec']);self.assertTrue(data['needs'])
    def test_wrong_units_and_unknown_orientation_not_silently_accepted(self):
        self.assertIsNone(self.extract(self.text.replace('Millimeters','Inches'))['spec'])
        self.assertTrue(self.extract(self.text.replace('GC4693','OTHER123'))['needs'])
    def test_conflicting_nominal_blocks_automatic_spec(self):
        data=self.extract(self.text+'\nPackage Body Dimension X\nA\n6.000')
        self.assertIsNone(data['spec']);self.assertTrue(any('冲突' in n for n in data['needs']))
    def test_joint_build_requires_confirmation_and_exact_ids(self):
        p=dict(pins=self.pins,pcb=self.extract(),footprint='GC4693')
        with self.assertRaisesRegex(ValueError,'确认'):pcb.check(p)
        p['pcb']['confirmed']=True;self.assertEqual(pcb.check(p)['name'],'GC4693')
        p['pins']=copy.deepcopy(p['pins']);p['pins'][0]['id']='A2'
        with self.assertRaisesRegex(ValueError,'脚号'):pcb.check(p)
