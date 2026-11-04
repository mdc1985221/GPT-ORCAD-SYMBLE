import copy
import json
import unittest
from pathlib import Path
from templates.footprint.drawing import presentation


class CenterAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((Path(__file__).resolve().parents[1]/'templates/footprint/gc4693.json').read_text(encoding='utf8'))

    def test_coincident_centers_keep_three_independent_arrows(self):
        marks=presentation(self.spec)['annotations']
        self.assertEqual([m['name'] for m in marks],['BODY','BGA','OPTICAL'])
        self.assertEqual(marks[1]['point'],marks[2]['point'])
        self.assertNotEqual(marks[1]['label'],marks[2]['label'])
        for mark in marks:
            self.assertEqual(len(mark['segments']),4)
            for segment in [mark['segments'][0],*mark['segments'][2:]]:
                self.assertEqual(segment[0],[round(v,4) for v in mark['point']])

    def test_distinct_optical_center_is_not_snapped_to_bga(self):
        spec=copy.deepcopy(self.spec)
        spec['centers']['OPT']=[.17,-.28]
        optical=presentation(spec)['annotations'][2]
        self.assertEqual(optical['point'],[.17,-.28])
        self.assertEqual(optical['segments'][0][0],[.17,-.28])
        self.assertEqual(spec['centers']['OPT'],[.17,-.28])
