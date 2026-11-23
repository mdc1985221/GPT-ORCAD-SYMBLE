import copy
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant_core as core
import pcb_workflow as pcb
import footprint_pipeline as fp
import model3d_pipeline as model


class GC5613Tests(unittest.TestCase):
    def setUp(self):
        entries=[('Package Body Dimension X', 'A', 6.917, 6.892, 6.942), ('Package Body Dimension Y', 'B', 4.165, 4.14, 4.19), ('Package Height', 'C', 0.68, 0.625, 0.735), ('Ball Height', 'C1', 0.15, 0.12, 0.18), ('Package Body Thickness', 'C2', 0.53, 0.495, 0.565), ('Thickness from top glass surface to wafer', 'C3', 0.345, 0.33, 0.36), ('Glass Thickness', 'C4', 0.3, 0.29, 0.31), ('Ball Diameter', 'D', 0.3, 0.27, 0.33), ('Pins pitch X axis', 'J1', 0.66, 0.65, 0.67), ('Pins pitch Y axis', 'J2', 0.75, 0.74, 0.76), ('Edge to Pin Center Distance along X1', 'S1', 0.822, 0.792, 0.852), ('Edge to Pin Center Distance along Y1', 'S2', 0.46, 0.43, 0.49), ('Edge to Pin Center Distance along X2', 'S3', 0.815, 0.785, 0.845), ('Edge to Pin Center Distance along Y2', 'S4', 0.705, 0.675, 0.735), ('BGA ball center to package center offset in X-direction', 'X', 0.0035, -0.0215, 0.0285), ('BGA ball center to package center offset in Y-direction', 'Y', 0.1225, 0.0975, 0.1475), ('BGA ball center to chip center offset in X-direction', 'X1', 0.0035, -0.0215, 0.0285), ('BGA ball center to chip center offset in Y-direction', 'Y1', 0.1225, 0.0975, 0.1475)]
        self.texts=['GC5613 Pixel size: 2μm x 2μm BSI Active image size: 2960 x 1666',
            'Top View Image Size Bottom View BGA Size',
            'Millimeters\n'+'\n'.join(' '.join(map(str,e)) for e in entries)+
            '\nTotal Ball Count N 43(2NC) Ball Count X axis N1 9 Ball Count Y axis N2 5 '+
            'BGA center coordinate is (-3.5, 122.5), the optical center coordinate is (-14.685, -62.52), with μm unit']
        self.pins=[dict(id=r+str(c)) for r in 'ABCDE' for c in range(1,10) if r+str(c) not in ('B6','B7')]

    def test_centers_tolerances_nc_balls_and_shared_3d_coordinates(self):
        r=pcb.inspect_gc5613_csp(self.texts,self.pins)
        self.assertEqual(r['needs'],[]);self.assertFalse(r['confirmed'])
        s=r['spec'];self.assertEqual(s['centers']['BGA'],[-.0035,.1225])
        self.assertEqual(s['centers']['OPT'],[-.014685,-.06252])
        self.assertEqual(s['sensor_array'],[5.92,3.332])
        self.assertEqual(s['mechanical_dimensions']['C']['max'],.735)
        pads=fp.geometry(s);self.assertEqual(len(pads),43)
        self.assertTrue({'A5','B8'}<={p[0] for p in pads})
        plan=model.plan(s,dict(confirmed=True,total_height=.680,ball_height=.150))
        self.assertEqual(plan['pads'],pads)
        self.assertAlmostEqual(plan['total_height']-plan['optical']['top_to_wafer'],.335)

    def test_missing_nc_and_unexpected_ball_block(self):
        for pins in [self.pins[:-1],self.pins+[dict(id='B6')]]:
            r=pcb.inspect_gc5613_csp(self.texts,pins)
            self.assertIsNone(r['spec']);self.assertTrue(r['needs'])

    def test_wrong_center_unit_and_direction_block(self):
        for old,new in [('with μm unit','with mm unit'),('(-3.5, 122.5)','(3.5, 122.5)')]:
            texts=[t.replace(old,new) for t in self.texts]
            r=pcb.inspect_gc5613_csp(texts,self.pins)
            self.assertIsNone(r['spec']);self.assertTrue(r['needs'])

    def test_native_description_blank_ad_and_backslash_io(self):
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'table.pdf'
            with fitz.open() as doc:
                page=doc.new_page()
                page.insert_text((50,50),'Pin Descriptions\nPin\nName\nType\nA/D\nDescription\n'
                    'A5\nNC\nNC\n\nNC\nB2\nSBDA\nInput\\ Output\nD\nSerial data\n'
                    'B3\nFSYNC\nInput/Output\nD\nFrame sync\nB6\n\\\n\\\n\n\\\n')
                doc.save(path)
            pins=core.extract_pdf(path)
        self.assertEqual({p['id']:(p['name'],p['type']) for p in pins},
            {'A5':('NC','NC'),'B2':('SBDA','IO'),'B3':('FSYNC','IO')})
