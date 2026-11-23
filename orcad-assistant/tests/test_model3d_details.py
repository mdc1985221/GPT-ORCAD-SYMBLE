import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import model3d_details as details


class AppearanceValidationTests(unittest.TestCase):
    def setUp(self):
        self.profile=dict(revision=1,accuracy='appearance_only',edge_features=[[.1,.01,.11,.03]],
                          perimeter_frames=[[.02,.04,.98,.96]],back_marker=[[.5,.3],[.48,.3],[.48,.35]],
                          lower_edge_inset_fraction=.022)

    def test_valid_relative_geometry_retains_accuracy_label(self):
        self.assertEqual(details.validate(self.profile),self.profile)

    def test_unbounded_or_malformed_appearance_is_rejected(self):
        for key,value in [('edge_features',[[.1,.1,float('nan'),.2]]),
                          ('edge_features',[[.5,.1,.4,.2]]),('back_marker',[[1.1,.2]]),
                          ('lower_edge_inset_fraction',float('inf')),('accuracy','datasheet_dimension')]:
            p=copy.deepcopy(self.profile);p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):details.validate(p)
