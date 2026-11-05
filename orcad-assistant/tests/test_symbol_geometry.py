import copy
import json
import tempfile
import unittest
from pathlib import Path
import assistant_core as core


class SymbolGeometryTests(unittest.TestCase):
    def project(self):
        p=core.new_project()
        p.update(device='GRID_TEST',footprint='TEST',pins=core.import_csv(Path(__file__).resolve().parents[1]/'examples/GC4693_ballmap.csv'))
        core.auto_layout(p)
        return p

    def test_move_snaps_and_preserves_other_pins_and_export(self):
        p=self.project();_,before=core.layout(p,core.DEFAULT_ENV)
        pin=before[0][0]
        core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(id=pin,side='LEFT',offset=23.2))
        cfg,after=core.layout(p,core.DEFAULT_ENV)
        moved=next(v for v in after if v[0]==pin)
        self.assertEqual({v[0]:v[:3] for v in before},{v[0]:v[:3] for v in after})
        self.assertEqual(moved[3:],(0,20,-30,20))
        self.assertEqual([v for v in before if v[0]!=pin],[v for v in after if v[0]!=pin])
        self.assertTrue(all(v%10==0 for pin in after for v in pin[3:]))
        with tempfile.TemporaryDirectory() as tmp:
            script,_=core.generator.build(cfg,tmp)
            self.assertIn('20',Path(script).read_text(encoding='utf8'))
            path=Path(tmp)/'project.json';core.atomic_json(path,p)
            self.assertEqual(core.layout(core.load_project(path),core.DEFAULT_ENV)[1],after)

    def test_resize_keeps_offsets_and_moves_right_bottom_connections(self):
        p=self.project();cfg,before=core.layout(p,core.DEFAULT_ENV)
        core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(frame=[cfg['W']+33,cfg['H']+27]))
        new,after=core.layout(p,core.DEFAULT_ENV)
        self.assertEqual([new['W'],new['H']],[cfg['W']+30,cfg['H']+30])
        for old,pin in zip(before,after):
            self.assertEqual(old[:3],pin[:3])
            if old[5]>old[3]:self.assertEqual(pin[3:],(new['W'],old[4],new['W']+30,old[6]))
            elif old[6]>old[4]:self.assertEqual(pin[3:],(old[3],new['H'],old[5],new['H']+30))
            else:self.assertEqual(old,pin)

    def test_reject_collision_and_frame_that_cuts_off_pin(self):
        p=self.project();core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(id='A1',side='LEFT',offset=20))
        with self.assertRaisesRegex(ValueError,'重叠'):
            core.edit_symbol_geometry(copy.deepcopy(p),core.DEFAULT_ENV,dict(id='A2',side='LEFT',offset=20))
        with self.assertRaises(ValueError):core.edit_symbol_geometry(copy.deepcopy(p),core.DEFAULT_ENV,dict(frame=[100,100]))

    def test_off_grid_import_rejected_and_auto_layout_resets(self):
        p=self.project();core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(id='A1',side='LEFT',offset=20))
        bad=copy.deepcopy(p);bad['symbol_layout']['pins']['A1']['offset']=21
        with self.assertRaisesRegex(ValueError,'10 MIL'):core.layout(bad,core.DEFAULT_ENV)
        core.auto_layout(p);self.assertNotIn('symbol_layout',p)

    def test_batch_move_preserves_names_spacing_and_grid(self):
        p=self.project()
        core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(frame=[600,600]))
        before=core.layout(p,core.DEFAULT_ENV)[1]
        left=[v for v in before if v[5]<v[3]][:3]
        moves=[dict(id=v[0],side='LEFT',offset=v[4]+203) for v in left]
        core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(moves=moves))
        after={v[0]:v for v in core.layout(p,core.DEFAULT_ENV)[1]}
        for v in left:
            self.assertEqual(after[v[0]][:3],v[:3])
            self.assertEqual(after[v[0]][4],v[4]+200)
            self.assertEqual(after[v[0]][6],v[6]+200)
        selected={v[0] for v in left}
        for v in before:
            if v[0] not in selected:self.assertEqual(v,after[v[0]])

    def test_batch_collision_is_rejected_atomically_in_web_action(self):
        import web_app
        w=web_app.Workspace();w.project=self.project()
        before=copy.deepcopy(w.project)
        with self.assertRaisesRegex(ValueError,'重叠'):
            w.action(dict(action='symbol-geometry',moves=[dict(id='A1',side='LEFT',offset=20),dict(id='A2',side='LEFT',offset=20)]))
        self.assertEqual(w.project,before)

    def test_multipart_can_share_coordinates_without_cross_part_collision(self):
        p=self.project();core.split_parts(p,16)
        core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(frame=[500,500]))
        pins=[next(pin for pin in p['pins'] if pin.get('part','A')==part) for part in core.part_ids(p)]
        for pin in pins:core.edit_symbol_geometry(p,core.DEFAULT_ENV,dict(id=pin['id'],side='LEFT',offset=20))
        sections=core.section_layouts(p,core.DEFAULT_ENV)
        self.assertGreater(len(sections),1)
        self.assertTrue(all(cfg['W']==500 and cfg['H']==500 for _,cfg,_ in sections))
