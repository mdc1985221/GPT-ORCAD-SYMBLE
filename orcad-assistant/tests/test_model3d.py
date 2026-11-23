import copy
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import model3d_pipeline as model
import test_library_manager as fixtures


class ModelPlanTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((model.BASE/'templates/footprint/gc4693.json').read_text(encoding='utf8'))
        self.options=dict(confirmed=True,total_height=.67,ball_height=.25)

    def test_gc4693_uses_pcb_ball_positions_and_plane(self):
        p=model.plan(self.spec,self.options)
        self.assertEqual(len(p['pads']),35)
        self.assertEqual(p['pads'][0],('A1',-1.8599,1.1153))
        self.assertEqual(p['units'],'mm')
        self.assertEqual(p['total_height'],.67)

    def test_missing_or_nonfinite_dimensions_block(self):
        for key in ('total_height','ball_height'):
            for value in (None,0,-1,float('nan'),float('inf'),True,'0.2'):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    model.plan(self.spec,dict(self.options,**{key:value}))
        with self.assertRaises(ValueError):model.plan(self.spec,dict(self.options,confirmed=False))

    def test_height_cannot_invert_body_or_exceed_ball(self):
        for opts in (dict(ball_height=.26),dict(total_height=.2),dict(total_height=101)):
            with self.assertRaises(ValueError):model.plan(self.spec,dict(self.options,**opts))

    def test_missing_balls_preserved(self):
        self.spec['missing']=['A1','B2']
        self.assertEqual(len(model.plan(self.spec,self.options)['pads']),33)

    def test_optical_window_dimensions_and_cover_fit(self):
        self.spec.update(sensor_array=[3.,2.],glass_thickness=.3,die_size=[4.,2.5])
        p=model.plan(self.spec,self.options)
        self.assertEqual(p['optical']['size'],[3.,2.])
        self.assertEqual(p['optical']['center'],self.spec['centers']['OPT'])
        self.spec['glass_thickness']=.5
        with self.assertRaises(ValueError):model.plan(self.spec,self.options)


class ModelLibraryTests(unittest.TestCase):
    setUp=fixtures.LibraryManagerTests.setUp
    fixture=fixtures.LibraryManagerTests.fixture
    hashes=fixtures.LibraryManagerTests.hashes
    write_json=fixtures.LibraryManagerTests.write_json
    def test_model_is_new_version_and_curated_zip(self):
        p,g=self.fixture(joint=True)
        with unittest.mock.patch('footprint_pipeline.verify'):
            old=self.library.add(p,g)
        opts=dict(confirmed=True,total_height=.67,ball_height=.25)
        out=self.output/'model-build';out.mkdir()
        (out/'TEST_CSP.step').write_bytes(b'fixture STEP')
        (out/'mesh.json').write_text('{"meshes":[]}',encoding='utf8')
        report=dict(status='PASS',revision=1,plan=json.loads(json.dumps(model.plan(p['pcb']['spec'],opts))),
            step='TEST_CSP.step',file_hashes=self.hashes(out,[out/'TEST_CSP.step',out/'mesh.json']))
        self.write_json(out/'model3d.json',report)
        new=self.library.with_model(old['id'],dict(directory=str(out)),opts)
        self.assertNotEqual(old['id'],new['id'])
        self.assertEqual(self.library.get(old['id'])['model3d_status'],'pending')
        self.assertEqual(new['model3d_status'],'generated')
        self.assertTrue(Path(new['paths']['model3d']).is_dir())
        with ZipFile(io.BytesIO(self.library.design_bytes(new['id']))) as z:
            self.assertEqual(len(z.namelist()),4)
            self.assertIn('3d/TEST_CSP.step',z.namelist())
        self.assertEqual(new['id'],self.library.with_model(old['id'],dict(directory=str(out)),opts)['id'])
        with self.assertRaises(ValueError):self.library.with_model(old['id'],dict(directory=str(out)),dict(opts,total_height=.8))
        (out/'TEST_CSP.step').write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.library.with_model(old['id'],dict(directory=str(out)),opts)
