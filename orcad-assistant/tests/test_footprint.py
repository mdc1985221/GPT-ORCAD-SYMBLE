import copy
import json
import unittest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from footprint_pipeline import geometry, verify, verify_import_checks, padstack_name, TEMPLATES


class FootprintGeometryTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((TEMPLATES/'gc4693.json').read_text(encoding='utf-8'))

    def test_gc4693_top_view_edge_closure_and_offsets(self):
        pads=geometry(self.spec)
        self.assertEqual(len(pads),35)
        self.assertEqual(pads[0],('A1',-1.8599,1.1153))
        self.assertEqual(pads[-1],('E7',1.9801,-1.2046))

    def test_mirrored_center_is_rejected(self):
        self.spec['centers']['BGA'][0]=-.06007
        with self.assertRaisesRegex(ValueError,'中心'):geometry(self.spec)

    def test_missing_balls_and_dimension_failures(self):
        self.spec['missing']=['B4']
        self.assertEqual(len(geometry(self.spec)),34)
        self.spec['edge']['left_to_col1']+=.01
        with self.assertRaisesRegex(ValueError,'闭合'):geometry(self.spec)

    def test_nan_and_overlapping_mask_rejected(self):
        self.spec['pad_dia']=float('nan')
        with self.assertRaises(ValueError):geometry(self.spec)
        self.setUp()
        self.spec['mask_margin']=.5
        with self.assertRaisesRegex(ValueError,'相交'):geometry(self.spec)

    def test_old_readback_without_units_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'spec.json').write_text(json.dumps(self.spec),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'缺少数据库单位'):verify(root)

    def test_mil_database_and_false_conversion_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'allegro').mkdir()
            (root/'spec.json').write_text(json.dumps(self.spec),encoding='utf-8')
            for row in ('mils,4,0.0254','millimeters,4,0.0254','millimeters,4,nan'):
                (root/'allegro'/'units.csv').write_text('units,accuracy,mm_per_unit\n'+row+'\n')
                with self.assertRaisesRegex(ValueError,'物理比例错误'):verify(root)

    def test_native_pad_names_cover_all_process_sizes_without_legacy_collision(self):
        name=padstack_name(self.spec)
        self.assertLessEqual(len(name),20)
        self.assertNotEqual(name,'BALL20')
        self.assertEqual(name,padstack_name(copy.deepcopy(self.spec)))
        for key in ('pad_dia','mask_margin','paste_dia'):
            changed=copy.deepcopy(self.spec);changed[key]+=.0001
            self.assertNotEqual(name,padstack_name(changed))

    def test_disk_pad_readback_rejects_point_two_mil_as_point_two_mm(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);check=root/'checks'/'pad-millimeters';check.mkdir(parents=True)
            (check/'units.csv').write_text('units,mm_per_unit\nmillimeters,1\n')
            (check/'complete.txt').write_text('COMPLETE')
            layers=[('ETCH/TOP','CIRCLE',.00508),('PIN/SOLDERMASK_TOP','CIRCLE',.3016),
                    ('PIN/PASTEMASK_TOP','CIRCLE',.2),('ETCH/BOTTOM','NULL',0)]
            (check/'readback.csv').write_text('id,x,y,layer,shape,width,height,drill\n'+
                '\n'.join(f'PAD,0,0,{layer},{shape},{size},{size},0' for layer,shape,size in layers))
            with self.assertRaisesRegex(ValueError,'物理焊盘尺寸'):verify_import_checks(self.spec,root)
