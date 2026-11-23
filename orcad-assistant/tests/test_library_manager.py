import copy
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant_core as core
import footprint_pipeline as fp
from library_manager import Library


class LibraryManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / 'output'
        self.output.mkdir()
        self.library_root = self.base / 'library'
        self.library = Library(self.library_root, self.output)

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf8')

    def hashes(self, root, paths):
        return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths}

    def fixture(self, joint=False, multipart=False):
        project = core.new_project()
        project.update(device='TEST_PART', footprint='TEST_CSP', profile='simple',
                       expected_count=4,
                       pins=[dict(id=pid, name='SIGNAL_' + pid, type='IN',
                                  side='LEFT', group='signals', part='A')
                             for pid in ('A1', 'A2', 'B1', 'B2')])
        if multipart:
            project['parts'] = {'A': '第一单元', 'B': '第二单元'}
            for pin in project['pins'][2:]:
                pin['part'] = 'B'
        symbol_report = dict(status='PASS', pins=4, checks=['independent OLB readback'])
        if multipart:
            symbol_report.update(parts=2, sections=[dict(part=part, pins=2) for part in ('A', 'B')])
        root = self.output / ('device-build' if joint else 'TEST_PART-build')
        symbol = root / 'symbol' / 'TEST_PART-build' if joint else root
        symbol.mkdir(parents=True)
        olb = symbol / 'TEST_PART.OLB'
        olb.write_bytes(b'fixture OLB: TEST_PART')
        generated = dict(directory=str(root), olb=str(olb), report=copy.deepcopy(symbol_report))
        verified_files = [olb, symbol / 'project.json']
        if joint:
            spec = dict(name='TEST_CSP', descr='synthetic test footprint',
                        body=[2.0, 2.0], pitch=[0.5, 0.5],
                        edge=dict(left_to_col1=0.75, right_to_colN=0.75,
                                  top_to_rowA=0.75, bottom_to_rowN=0.75),
                        rows='AB', cols=2, missing=[], ball_dia=0.25,
                        pad_dia=0.2, mask_margin=0.05, paste_dia=0.2,
                        courtyard_excess=0.25, centers=dict(BGA=[0, 0], OPT=[0, 0]),
                        height_min=0.6, height_max=0.73)
            project['pcb'] = dict(spec=spec, confirmed=True, needs=[])
            pcb_report = dict(status='PASS', pins=4, units='millimeters', accuracy=4,
                              mm_per_database_unit=1,
                              pad_imports=dict(status='PASS', padstack=fp.padstack_name(spec)),
                              drawing=dict(status='PASS', revision=2))
            generated.update(pcb_directory=str(root / 'pcb'),
                             report=dict(status='PASS', pins=4, pcb=pcb_report,
                                         symbol=copy.deepcopy(symbol_report)))
            self.write_json(root / 'pcb' / 'spec.json', spec)
            self.write_json(root / 'pcb' / 'verification.json', pcb_report)
            allegro = root / 'pcb' / 'allegro'
            allegro.mkdir()
            (allegro / 'test_csp.psm').write_bytes(b'fixture PSM: TEST_CSP')
            (allegro / (fp.padstack_name(spec).lower() + '.pad')).write_bytes(b'fixture PAD')
            (allegro / 'TEST_CSP.dra').write_bytes(b'fixture source DRA')
            verified_files.extend([root / 'pcb' / 'spec.json', allegro / 'test_csp.psm',
                                   allegro / (fp.padstack_name(spec).lower() + '.pad'),
                                   allegro / 'TEST_CSP.dra'])
            # These are build internals, never usable library deliverables.
            (allegro / '_seed_blank.dra').write_bytes(b'wrong drawing')
            (allegro / 'build.scr').write_bytes(b'not a deliverable')
            (allegro / 'build.log').write_bytes(b'local paths and diagnostic output')
            checks = root / 'pcb' / 'checks' / 'psm-mils'
            checks.mkdir(parents=True)
            (checks / 'test_csp.psm').write_bytes(b'wrong PSM copy')
            (checks / 'seed.dra').write_bytes(b'wrong seed drawing')
        self.write_json(symbol / 'project.json', project)
        symbol_report['file_hashes'] = self.hashes(symbol, [olb, symbol / 'project.json'])
        self.write_json(symbol / 'verification.json', symbol_report)
        if joint:
            generated['report']['symbol'] = copy.deepcopy(symbol_report)
            generated['report']['file_hashes'] = self.hashes(root, verified_files)
        else:
            generated['report'] = copy.deepcopy(symbol_report)
        self.write_json(root / 'verification.json', generated['report'])
        return project, generated

    def add_joint(self, project, generated, **kwargs):
        with patch('library_manager.fp.verify', return_value=copy.deepcopy(generated['report']['pcb'])) as verify:
            item = self.library.add(project, generated, **kwargs)
        verify.assert_called_once()
        return item

    def archive(self, item_id, include_source=False):
        with ZipFile(io.BytesIO(self.library.design_bytes(item_id, include_source))) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    def test_symbol_download_contains_only_olb(self):
        project, generated = self.fixture()
        item = self.library.add(project, generated)
        expected = {'symbol/TEST_PART.OLB': b'fixture OLB: TEST_PART'}
        self.assertEqual(self.archive(item['id']), expected)
        self.assertEqual(self.archive(item['id'], include_source=True), expected)
        self.assertFalse(item['pcb'])
        self.assertEqual(item['model3d_status'], 'pending')

    def test_joint_download_curates_assets_and_makes_dra_optional(self):
        project, generated = self.fixture(joint=True)
        item = self.add_joint(project, generated)
        pad_name = fp.padstack_name(project['pcb']['spec']).lower() + '.pad'
        expected = {'symbol/TEST_PART.OLB': b'fixture OLB: TEST_PART',
                    'pcb/psm/test_csp.psm': b'fixture PSM: TEST_CSP',
                    'pcb/pad/' + pad_name: b'fixture PAD'}
        self.assertEqual(self.archive(item['id']), expected)
        expected['pcb/source/TEST_CSP.dra'] = b'fixture source DRA'
        self.assertEqual(self.archive(item['id'], include_source=True), expected)

    def test_copied_paths_are_separate_usable_directories(self):
        project, generated = self.fixture(joint=True)
        item = self.add_joint(project, generated, category='ic-sensor')
        folder = self.library_root / 'ic-sensor' / item['id']
        for key, relative in [('capture', 'symbol'), ('psmpath', 'pcb/psm'), ('padpath', 'pcb/pad')]:
            with self.subTest(key=key):
                self.assertEqual(Path(item['paths'][key]), folder / relative)
                self.assertTrue(Path(item['paths'][key]).is_dir())
        self.assertIsNone(item['paths']['model3d'])
        self.assertNotEqual(item['paths']['psmpath'], item['paths']['padpath'])

    def test_readding_same_built_result_is_idempotent(self):
        project, generated = self.fixture()
        first = self.library.add(project, generated, category='ic-sensor')
        second = self.library.add(project, generated, category='ic-sensor')
        self.assertEqual(first['id'], second['id'])
        reopened = Library(self.library_root, self.output)
        self.assertEqual([item['id'] for item in reopened.list()], [first['id']])
        self.assertEqual(self.archive(first['id'])['symbol/TEST_PART.OLB'], b'fixture OLB: TEST_PART')

    def test_changed_built_asset_creates_an_independent_version(self):
        project, generated = self.fixture()
        first = self.library.add(project, generated)
        Path(generated['olb']).write_bytes(b'fixture OLB: second version')
        # A separately verified next build records the changed binary's new hash.
        generated['report']['file_hashes']['TEST_PART.OLB'] = hashlib.sha256(
            Path(generated['olb']).read_bytes()).hexdigest()
        self.write_json(Path(generated['directory']) / 'verification.json', generated['report'])
        second = self.library.add(project, generated)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(self.library.list()), 2)
        self.assertEqual(self.archive(first['id'])['symbol/TEST_PART.OLB'], b'fixture OLB: TEST_PART')
        self.assertEqual(self.archive(second['id'])['symbol/TEST_PART.OLB'], b'fixture OLB: second version')

    def test_classification_moves_storage_and_persists(self):
        project, generated = self.fixture()
        item = self.library.add(project, generated, category='ic-sensor')
        original = self.library_root / 'ic-sensor' / item['id']
        before = self.archive(item['id'])
        moved = self.library.classify(item['id'], 'ic-memory')
        reopened = Library(self.library_root, self.output)
        self.assertFalse(original.exists())
        self.assertEqual(reopened.get(item['id'])['category'], 'ic-memory')
        self.assertEqual(Path(moved['paths']['capture']), self.library_root / 'ic-memory' / item['id'] / 'symbol')
        self.assertEqual(before, self.archive(item['id']))
        self.assertEqual(len(reopened.list()), 1)

    def test_unregistered_categories_cannot_escape_library(self):
        project, generated = self.fixture()
        for category in ('../outside', '..\\outside', 'ic-sensor/../../outside', 'CON'):
            with self.subTest(category=category), self.assertRaises(ValueError):
                self.library.add(project, generated, category=category)
        self.assertEqual(self.library.list(), [])
        item = self.library.add(project, generated)
        with self.assertRaises(ValueError):
            self.library.classify(item['id'], '../outside')
        self.assertEqual(len(self.library.list()), 1)

    def test_source_olb_outside_generated_output_is_rejected(self):
        project, generated = self.fixture()
        outside = self.base / 'outside' / 'TEST_PART.OLB'
        outside.parent.mkdir()
        outside.write_bytes(Path(generated['olb']).read_bytes())
        generated['olb'] = str(outside)
        with self.assertRaises(ValueError):
            self.library.add(project, generated)
        self.assertEqual(self.library.list(), [])

    def test_modified_stored_asset_cannot_be_downloaded(self):
        project, generated = self.fixture()
        item = self.library.add(project, generated)
        stored = Path(item['paths']['capture']) / 'TEST_PART.OLB'
        stored.write_bytes(b'externally modified library')
        with self.assertRaisesRegex(ValueError, '修改'):
            self.library.design_bytes(item['id'])

    def test_preview_uses_built_multipart_snapshot_not_live_draft(self):
        built, generated = self.fixture(multipart=True)
        draft = copy.deepcopy(built)
        draft['device'] = 'UNBUILT_DRAFT'
        draft['footprint'] = 'UNBUILT_FOOTPRINT'
        draft['pins'][0]['name'] = 'UNSAVED_NAME'
        draft['pins'][0]['side'] = 'RIGHT'
        item = self.library.add(draft, generated)
        detail = self.library.detail(item['id'])
        expected = [dict(part=part, width=cfg['W'], height=cfg['H'], pins=pins)
                    for part, cfg, pins in core.section_layouts(built, core.DEFAULT_ENV)]
        self.assertEqual(detail['device'], 'TEST_PART')
        self.assertEqual(detail['footprint'], 'TEST_CSP')
        self.assertEqual(detail['sections'], expected)
        self.assertEqual(len(detail['sections']), 2)
        built.pop('generated', None)
        self.assertEqual(self.library.project(item['id']), built)

    def test_legacy_pcb_reports_are_rejected_before_verification(self):
        project, generated = self.fixture(joint=True)
        for defect in ('units', 'pad_imports', 'drawing'):
            old = copy.deepcopy(generated)
            if defect == 'units':
                old['report']['pcb'].pop('units')
            elif defect == 'pad_imports':
                old['report']['pcb'].pop('pad_imports')
            else:
                old['report']['pcb']['drawing']['revision'] = 1
            self.write_json(Path(old['directory']) / 'verification.json', old['report'])
            with self.subTest(defect=defect), patch('library_manager.fp.verify') as verify:
                with self.assertRaises(ValueError):
                    self.library.add(project, old)
                verify.assert_not_called()
        self.assertEqual(self.library.list(), [])

    def test_disk_symbol_report_failure_cannot_be_hidden_by_generated_metadata(self):
        project, generated = self.fixture()
        self.write_json(Path(generated['olb']).parent / 'verification.json', dict(status='FAILED', pins=4))
        with self.assertRaises(ValueError):
            self.library.add(project, generated)
        self.assertEqual(self.library.list(), [])

    def test_disk_joint_report_failure_is_rejected(self):
        project, generated = self.fixture(joint=True)
        self.write_json(Path(generated['directory']) / 'verification.json', dict(status='FAILED'))
        with patch('library_manager.fp.verify', return_value=generated['report']['pcb']):
            with self.assertRaises(ValueError):
                self.library.add(project, generated)
        self.assertEqual(self.library.list(), [])

    def test_pcb_spec_must_match_built_symbol_snapshot(self):
        project, generated = self.fixture(joint=True)
        changed = copy.deepcopy(project['pcb']['spec'])
        changed['pad_dia'] = 0.21
        self.write_json(Path(generated['pcb_directory']) / 'spec.json', changed)
        with patch('library_manager.fp.verify', return_value=generated['report']['pcb']):
            with self.assertRaises(ValueError):
                self.library.add(project, generated)
        self.assertEqual(self.library.list(), [])

    def test_native_footprint_verification_failure_blocks_storage(self):
        project, generated = self.fixture(joint=True)
        with patch('library_manager.fp.verify', side_effect=ValueError('physical pad mismatch')):
            with self.assertRaisesRegex(ValueError, 'physical pad mismatch'):
                self.library.add(project, generated)
        self.assertEqual(self.library.list(), [])

    def test_deliverables_from_a_different_successful_build_are_rejected(self):
        project, generated = self.fixture(joint=True)
        other = self.output / 'another-successful-build'
        other_symbol = other / 'symbol' / 'TEST_PART-build'
        shutil.copytree(Path(generated['olb']).parent, other_symbol)
        shutil.copytree(Path(generated['pcb_directory']), other / 'pcb')
        self.write_json(other / 'verification.json', generated['report'])
        swaps = dict(olb=str(other_symbol / 'TEST_PART.OLB'),
                     pcb_directory=str(other / 'pcb'), directory=str(other))
        for field, different_build_path in swaps.items():
            mismatched = copy.deepcopy(generated)
            mismatched[field] = different_build_path
            with self.subTest(field=field), patch('library_manager.fp.verify') as verify:
                with self.assertRaisesRegex(ValueError, '同一次构建'):
                    self.library.add(project, mismatched)
                verify.assert_not_called()
        self.assertEqual(self.library.list(), [])

    def test_failed_nested_symbol_report_blocks_joint_result(self):
        project, generated = self.fixture(joint=True)
        symbol_report = Path(generated['olb']).parent / 'verification.json'
        self.write_json(symbol_report, dict(status='FAILED', pins=4))
        # The outer manifest still claims that both components passed.
        self.assertEqual(generated['report']['symbol']['status'], 'PASS')
        with patch('library_manager.fp.verify') as verify:
            with self.assertRaisesRegex(ValueError, '原理符号验证记录'):
                self.library.add(project, generated)
            verify.assert_not_called()
        self.assertEqual(self.library.list(), [])

    def test_pre_import_file_tampering_is_rejected_before_verification(self):
        project, generated = self.fixture(joint=True)
        root = Path(generated['directory'])
        for relative in generated['report']['file_hashes']:
            file = root / relative
            original = file.read_bytes()
            # Whitespace preserves valid project/spec JSON while changing its bytes.
            changed = original + (b'\n ' if file.suffix == '.json' else b' tampered')
            with self.subTest(file=relative), patch('library_manager.fp.verify') as verify:
                try:
                    file.write_bytes(changed)
                    with self.assertRaises(ValueError):
                        self.library.add(project, generated)
                    verify.assert_not_called()
                finally:
                    file.write_bytes(original)
        self.assertEqual(self.library.list(), [])

    def test_missing_or_partial_build_hash_records_require_rebuild(self):
        for joint in (False, True):
            project, generated = self.fixture(joint=joint)
            root = Path(generated['directory'])
            valid_report = copy.deepcopy(generated['report'])
            variants = [None, *valid_report['file_hashes']]
            for omitted in variants:
                report = copy.deepcopy(valid_report)
                if omitted is None:
                    report.pop('file_hashes')
                else:
                    report['file_hashes'].pop(omitted)
                self.write_json(root / 'verification.json', report)
                with self.subTest(joint=joint, omitted=omitted), patch('library_manager.fp.verify') as verify:
                    with self.assertRaises(ValueError):
                        self.library.add(project, generated)
                    verify.assert_not_called()
        self.assertEqual(self.library.list(), [])


if __name__ == '__main__':
    unittest.main()
