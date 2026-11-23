import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistant_core as core
import pcb_workflow as pcb
import model3d_pipeline as model
import footprint_pipeline as fp


class ChinesePinTableTests(unittest.TestCase):
    def test_row_serial_is_not_pin_and_reserved_ball_survives(self):
        rect=lambda x0,x1:SimpleNamespace(x0=x0,x1=x1,y0=50,y1=60)
        headers={'编号':[rect(100,120)],'信号名':[rect(150,180)],'引脚类型':[rect(220,260)]}
        words=[(40,80,45,90,'1'),(100,80,115,90,'B2'),(140,80,210,90,'RESERVED'),
               (220,80,225,90,'-'),(300,80,320,90,'NC'),
               (40,110,45,120,'2'),(100,110,115,120,'B6'),(145,110,200,120,'EFSYNC'),
               (220,110,250,120,'输入')]
        page=SimpleNamespace(get_text=lambda _:words,search_for=lambda s:headers.get(s,[]),rect=SimpleNamespace(height=800))
        pins=core.chinese_signal_pins(page,9,'sample.pdf')
        self.assertEqual([(p['id'],p['name'],p['type']) for p in pins],
                         [('B2','RESERVED','NC'),('B6','EFSYNC','IN')])


class Sc8238MechanicalTests(unittest.TestCase):
    def setUp(self):
        entries=[('Package Body Dimension X','A',6.816,6.791,6.841),
            ('Package Body Dimension Y','B',4.6479,4.6229,4.6729),
            ('Package Height','C',.710,.650,.770),('Ball Height','C1',.150,.120,.180),
            ('Package Body Thickness','C2',.560,.525,.595),
            ('Thickness from top glass surface to wafer','C3',.345,.325,.365),
            ('Glass Thickness','C4',.300,.270,.330),('Ball Diameter','D',.300,.270,.330),
            ('Pins Pitch X axis','J1',.730,'-','-'),('Pins Pitch Y axis','J2',.650,'-','-'),
            ('Edge to Pin Center Distance along X1','S1',1.174584,1.144584,1.204584),
            ('Edge to Pin Center Distance along Y1','S2',.726576,.696576,.756576),
            ('Edge to Pin Center Distance along X1','S3',1.261416,1.231416,1.291416),
            ('Edge to Pin Center Distance along Y1','S4',.671324,.641324,.701324)]
        self.texts=['像素阵列：3872H x 2180V 像素尺寸：1.5 μm x 1. 5 μm',
            'Pixel center (43.416,-238.626) BGA center (43.416,-27.626)',
            'Millimeters\n'+'\n'.join(' '.join(map(str,e)) for e in entries)]
        self.pins=[dict(id=r+str(c)) for r in 'ABCDEF' for c in range(1,8) if (r,c)!=('B',4)]

    def test_nominal_order_missing_ball_centers_and_optical_stack(self):
        result=pcb.inspect_sc8238_csp(self.texts,self.pins)
        self.assertEqual(result['needs'],[])
        s=result['spec'];self.assertEqual(s['height_nominal'],.710)
        self.assertEqual(s['height_min'],.650);self.assertEqual(s['height_max'],.770)
        self.assertIsNone(s['mechanical_dimensions']['J1']['min'])
        self.assertEqual(s['missing'],['B4']);self.assertEqual(s['sensor_array'],[5.808,3.27])
        self.assertAlmostEqual(s['centers']['BGA'][0],.043416)
        self.assertAlmostEqual(s['centers']['OPT'][1],-.238626)
        self.assertEqual(s['kicad_version'],6)
        p=model.plan(s,dict(confirmed=True,total_height=.710,ball_height=.150))
        self.assertEqual(p['pads'],fp.geometry(s));self.assertEqual(len(p['pads']),41)
        self.assertAlmostEqual(p['total_height']-p['optical']['top_to_wafer'],.365)
        self.assertEqual(p['optical']['glass_thickness'],.3)
        for bad in (.2,.6,None,float('nan'),'0.345'):
            with self.subTest(depth=bad),self.assertRaises(ValueError):
                model.plan(dict(s,top_to_wafer=bad),dict(confirmed=True,total_height=.710,ball_height=.150))

    def test_wrong_ball_set_blocks_instead_of_assuming_grid(self):
        self.pins[-1]['id']='B4'
        result=pcb.inspect_sc8238_csp(self.texts,self.pins)
        self.assertIsNone(result['spec']);self.assertTrue(result['needs'])
