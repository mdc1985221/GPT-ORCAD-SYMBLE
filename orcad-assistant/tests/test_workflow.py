import copy
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant_core as core
import build_pipeline as pipeline


def project(rows):
    p = core.new_project()
    p.update(device='TEST', footprint='TEST_PKG', pins=[dict(id=i, name=n, type=t, side='', group='', confidence=1., conflicts=[]) for i, n, t in rows])
    core.auto_layout(p)
    return p


class WorkflowTests(unittest.TestCase):
    def test_indexed_mipi_default_sides(self):
        p = project([('1', 'M1D0P', 'OUT'), ('2', 'M0D0P', 'OUT'),
                     ('3', 'M0CP', 'OUT'), ('4', 'M0CN', 'OUT'),
                     ('5', 'M0D0N', 'OUT'), ('6', 'AVDD', 'PWR'),
                     ('7', 'AGND', 'GND'), ('8', 'XSHUTDN', 'IN')])
        self.assertEqual([x['name'] for x in p['pins'] if x['side']=='RIGHT'],
                         ['M0CN', 'M0CP', 'M0D0N', 'M0D0P', 'M1D0P'])
        self.assertEqual({x['name']:x['side'] for x in p['pins'] if not x['name'].startswith('M')},
                         {'AVDD':'TOP','AGND':'BOT','XSHUTDN':'LEFT'})

    def test_numeric_ep_analog_large_bga_no_loss(self):
        p = project([('1', 'VIN', 'PWR'), ('EP', 'GND', 'GND'), ('F1', 'VREF', 'ANA'), ('AA12', 'RESET', 'IN')])
        cfg, pins = core.layout(p, core.DEFAULT_ENV)
        self.assertEqual({r[0] for r in pins}, {'1', 'EP', 'F1', 'AA12'})
        self.assertEqual(cfg['PITCH'], 10)
        self.assertTrue(all(v % 10 == 0 for pin in pins for v in pin[3:]))

    def test_differential_lane_order_and_groups(self):
        p = project([('A1', 'MD2P', 'OUT'), ('A2', 'MD0P', 'OUT'), ('A3', 'MD2N', 'OUT'), ('A4', 'MCN', 'OUT'), ('A5', 'MCP', 'OUT'), ('A6', 'MD0N', 'OUT'), ('A7', 'AGND', 'GND'), ('A8', 'NC', 'NC')])
        right = [p['name'] for p in p['pins'] if p['side'] == 'RIGHT']
        self.assertEqual(right, ['MCN', 'MCP', 'MD0N', 'MD0P', 'MD2N', 'MD2P'])
        cfg, _ = core.layout(p, core.DEFAULT_ENV)
        self.assertEqual([g[0] for g in cfg['BOT']], ['AGND', 'NC'])

    def test_repeated_names_and_suffix_collision(self):
        p = project([('1', 'GND', 'GND'), ('2', 'GND', 'GND')])
        _, pins = core.layout(p, core.DEFAULT_ENV)
        self.assertEqual({r[1] for r in pins}, {'GND_1', 'GND_2'})
        p = project([('1', 'GND', 'GND'), ('2', 'GND', 'GND'), ('3', 'GND_1', 'GND')])
        with self.assertRaises(ValueError):
            core.layout(p, core.DEFAULT_ENV)

    def test_duplicate_ids_block(self):
        p = project([('1', 'A', 'IN'), ('1', 'B', 'OUT')])
        self.assertTrue(any(i['blocking'] for i in core.issues(p)))
        with self.assertRaises(ValueError):
            core.layout(p, core.DEFAULT_ENV)

    def test_simple_exposed_pad_does_not_displace_pin_one(self):
        p = project([(str(i), 'IO'+str(i), 'IO') for i in range(1, 11)] + [('EP', 'GND', 'GND')])
        p['profile'] = 'simple'
        core.auto_layout(p)
        self.assertEqual([p['id'] for p in p['pins'] if p['side']=='LEFT'], ['5', '4', '3', '2', '1'])
        self.assertEqual(next(p for p in p['pins'] if p['id']=='EP')['side'], 'BOT')

    def test_multipart_partition_global_names_and_pair_integrity(self):
        p = project([(str(i),'GND','GND') for i in range(1,20)] + [('20','MCN','OUT'),('21','MCP','OUT')])
        core.split_parts(p,8)
        layouts = core.section_layouts(p,core.DEFAULT_ENV)
        self.assertGreater(len(layouts),1)
        flattened = [pin for _,_,pins in layouts for pin in pins]
        self.assertEqual(len(flattened),21)
        self.assertEqual(len({pin[0] for pin in flattened}),21)
        self.assertEqual(len({pin[1] for pin in flattened}),21)
        self.assertEqual(next(pin for pin in p['pins'] if pin['id']=='20')['part'],next(pin for pin in p['pins'] if pin['id']=='21')['part'])

    def test_screenshot_matching_never_changes_identity(self):
        from reference_layout import match_words, apply
        p=project([('1','RESET','IN'),('2','MCP','OUT'),('3','AVDD','PWR')])
        observations=[dict(text='RESET',cx=205,cy=200),dict(text='MCP',cx=695,cy=200),dict(text='AVDD',cx=400,cy=105)]
        proposals, ambiguous=match_words(p['pins'],observations,(200,100,700,500))
        before={pin['id']:pin['name'] for pin in p['pins']}
        result=dict(id='fixture',proposals=proposals,matched=3,unmatched=0)
        apply(p,result,'A')
        self.assertEqual({pin['id']:pin['name'] for pin in p['pins']},before)
        self.assertEqual({pin['id']:pin['side'] for pin in p['pins']},{'1':'LEFT','2':'RIGHT','3':'TOP'})
        self.assertTrue(any(i['key']=='reference:fixture' for i in core.issues(p)))

    def test_ambiguous_screenshot_name_is_not_guessed(self):
        from reference_layout import match_words
        pins=[dict(id='1',name='GND'),dict(id='2',name='GND')]
        proposals,ambiguous=match_words(pins,[dict(text='GND',cx=400,cy=500)],(200,100,700,500))
        self.assertFalse(proposals)
        self.assertEqual(ambiguous,['GND'])

    def test_coverage_confirmation_invalidated_by_edits(self):
        p = project([('A1', 'VDD', 'PWR')])
        p['sources'] = [dict(path='source.pdf', sha256='abc')]
        pending = core.issues(p)
        p['reviewed'] = [i['key'] for i in pending]
        self.assertFalse(core.issues(p))
        p['pins'][0]['name'] = 'AVDD'
        self.assertTrue(core.issues(p))

    def test_project_roundtrip_and_csv_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            csv = Path(directory) / 'pins.csv'
            csv.write_text('ball,name,type,edge\n1,VDD,PWR,TOP\nEP,GND,GND,BOT\n', encoding='utf-8-sig')
            p = core.new_project()
            p['pins'] = core.import_csv(csv)
            path = Path(directory) / 'project.json'
            core.atomic_json(path, p)
            self.assertEqual(core.load_project(path), p)

    def test_generation_escapes_tcl_and_does_not_change_cwd(self):
        p = project([('1', 'DATA[0]$x"\\', 'IO')])
        cfg, expected = core.layout(p, core.DEFAULT_ENV)
        before = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            script, csv = core.generator.build(cfg, directory)
            text = Path(script).read_text(encoding='utf-8')
            self.assertIn('DATA\\[0\\]\\$x\\"\\\\', text)
            self.assertTrue(Path(csv).exists())
        self.assertEqual(os.getcwd(), before)

    def test_large_layout_140_pins_no_diagnostic_cutoff(self):
        p = project([(str(i), 'IO_'+str(i), 'IO') for i in range(1, 141)])
        p['profile'] = 'simple'
        core.auto_layout(p)
        cfg, pins = core.layout(p, core.DEFAULT_ENV)
        self.assertEqual(len(pins), 140)
        self.assertEqual(p['pins'][0]['id'], '70')
        self.assertTrue(all(pin[4] >= cfg['Y0'] for pin in pins))

    def test_failed_build_preserves_previous_output(self):
        p = project([('1', 'VDD', 'PWR')])
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'existing.OLB'
            old.write_bytes(b'previous-known-good')
            with patch.object(pipeline, 'check_environment', return_value=[]), patch.object(pipeline, 'run_tcl', side_effect=RuntimeError('simulated failure')):
                with self.assertRaises(RuntimeError):
                    pipeline.build(p, core.DEFAULT_ENV, directory)
            self.assertEqual(old.read_bytes(), b'previous-known-good')
            reports = list(Path(directory).glob('.building-*/verification.json'))
            self.assertEqual(json.loads(reports[0].read_text())['status'], 'FAILED')

    def test_chinese_pdf_headers_and_types(self):
        from unittest.mock import MagicMock
        table = MagicMock()
        table.bbox = (0, 0, 400, 600)
        table.extract.return_value = [
            ['序号', '编\n号', '信号名', '引脚类型', '描述'],
            ['1', 'A1', 'AGND', '地线', '模拟地'],
            ['2', 'A4', 'SDA', '输入/输出', 'I2C'],
            ['3', 'C5', 'MD2N_DOGND', '-', 'NC 或 I/O 地'],
        ]
        page = MagicMock()
        page.find_tables.return_value = [table]
        page.extract_text.return_value = '引脚描述'
        pdf = MagicMock()
        pdf.__enter__.return_value.pages = [page]
        with patch('pdfplumber.open', return_value=pdf):
            pins = core.extract_pdf('chinese.pdf')
        self.assertEqual([(p['id'], p['name'], p['type']) for p in pins],
                         [('A1', 'AGND', 'GND'), ('A4', 'SDA', 'IO'), ('C5', 'MD2N_DOGND', '')])
        page.find_tables.assert_called_once_with({'snap_tolerance': 4})

    def test_pdf_cross_page_conflict_and_numeric_ep(self):
        from reportlab.pdfgen import canvas
        from reportlab.platypus import Table, TableStyle
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'datasheet.pdf'
            document = canvas.Canvas(str(path))
            for rows in [[['Pin', 'Name', 'Type'], ['1', 'VDD', 'Power'], ['EP', 'GND', 'Ground']],
                         [['Pin', 'Name', 'Type'], ['F1', 'VREF', 'Analog'], ['1', 'AVDD', 'Power']]]:
                document.drawString(40, 800, 'Pin Descriptions')
                table = Table(rows, colWidths=[80, 100, 100], rowHeights=25)
                table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, (0,0,0))]))
                table.wrapOn(document, 500, 700)
                table.drawOn(document, 40, 650)
                document.showPage()
            document.save()
            pins = core.extract_pdf(path)
            self.assertEqual({p['id'] for p in pins}, {'1', 'EP', 'F1'})
            self.assertEqual(next(p for p in pins if p['id']=='F1')['page'], 2)
            self.assertTrue(next(p for p in pins if p['id']=='1')['conflicts'])


if __name__ == '__main__':
    unittest.main()
