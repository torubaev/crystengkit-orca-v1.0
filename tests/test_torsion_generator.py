import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_DIR = Path(__file__).resolve().parents[1] / "tools" / "torsion_generator"
sys.path.insert(0, str(MODULE_DIR))

from torsion_generator import (  # noqa: E402
    ConfigurationError,
    angle_tag,
    generate,
    parse_config,
    read_xyz,
    rotate_coordinates,
    run,
    scan_plan,
)
from torsion_generator_gui import (  # noqa: E402
    molecule_from_atoms, parse_angles_text, parse_atom_numbers,
    rotating_side_for_axis,
)


XYZ = """4
test fragment
C 0.0 0.0 0.0
C 1.5 0.0 0.0
H -0.5 1.0 0.0
H 2.0 1.0 0.0
"""


def configuration(mode="single"):
    return {
        "mode": mode,
        "rotations": [{
            "name": "ring_1",
            "axis_atoms": [1, 2],
            "rotating_atoms": [2, 4],
            "angles_deg": [0, 90],
        }],
        "validation": {"collision_threshold_angstrom": 0.2},
    }


class TorsionGeneratorTests(unittest.TestCase):
    def _files(self, root, config=None):
        xyz = root / "molecule.xyz"
        cfg = root / "scan.json"
        xyz.write_text(XYZ, encoding="utf-8")
        cfg.write_text(json.dumps(config or configuration()), encoding="utf-8")
        return xyz, cfg

    def test_rodrigues_rotation_pins_axis_and_rotates_fragment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xyz, cfg = self._files(root)
            molecule = read_xyz(xyz)
            _raw, rotations, _settings = parse_config(cfg, molecule)
            result = rotate_coordinates(molecule.coordinates, rotations[0], 90.0)
            np.testing.assert_allclose(result[:2], molecule.coordinates[:2], atol=1e-12)
            np.testing.assert_allclose(result[3], [2.0, 0.0, 1.0], atol=1e-12)
            np.testing.assert_allclose(result[2], molecule.coordinates[2], atol=1e-12)

    def test_cli_writes_deterministic_xyz_orca_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xyz, cfg = self._files(root)
            output = root / "generated"
            args = type("Args", (), {
                "input": xyz, "config": cfg, "output": output, "write_orca": True,
                "orca_template": None, "overwrite": False, "verbose": False, "inspect": False,
            })()
            self.assertEqual(run(args), 0)
            self.assertTrue((output / "single-ring_1_000.xyz").is_file())
            self.assertTrue((output / "single-ring_1_p90.xyz").is_file())
            text = (output / "single-ring_1_p90.inp").read_text(encoding="utf-8")
            self.assertIn("* xyz 0 1", text)
            self.assertIn("H    2.0000000000", text)
            self.assertTrue((output / "torsion_scan_summary.csv").is_file())

    def test_fixed_side_atoms_are_rejected_when_axis_splits_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = configuration()
            bad["rotations"][0]["rotating_atoms"] = [2, 3, 4]
            xyz, cfg = self._files(root, bad)
            with self.assertRaisesRegex(ConfigurationError, "fixed-side"):
                parse_config(cfg, read_xyz(xyz))

    def test_combination_safety_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = configuration("combinations")
            data["rotations"].append({
                "name": "ring_2", "axis_atoms": [1, 2],
                "rotating_atoms": [2, 4], "angles_deg": [0, 30],
            })
            data["max_structures"] = 3
            xyz, cfg = self._files(root, data)
            molecule = read_xyz(xyz)
            raw, rotations, settings = parse_config(cfg, molecule)
            with self.assertRaisesRegex(ConfigurationError, "exceeds"):
                generate(molecule, raw, rotations, settings, root / "out", write_orca_files=False, template="")

    def test_angle_tags_follow_requested_style(self):
        self.assertEqual(angle_tag(5), "p05")
        self.assertEqual(angle_tag(-10), "m10")
        self.assertEqual(angle_tag(0), "000")

    def test_collective_alternating_and_seeded_random_plans(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = configuration("collective")
            data["rotations"].append({
                "name": "ring_2", "axis_atoms": [1, 2],
                "rotating_atoms": [2, 4], "angles_deg": [0, 90],
            })
            data["angles_deg"] = [10]
            xyz, cfg = self._files(root, data)
            molecule = read_xyz(xyz)
            raw, rotations, _settings = parse_config(cfg, molecule)
            self.assertEqual(scan_plan(raw, rotations)[0][1], (10.0, 10.0))
            raw["mode"] = "alternating"
            self.assertEqual(scan_plan(raw, rotations)[0][1], (10.0, -10.0))
            raw.update({"mode": "random", "random_count": 2, "random_seed": 42})
            raw["rotations"] = data["rotations"]
            random_rotations = [
                type(item)(item.name, item.axis, item.rotating, (), (-20.0, 20.0))
                for item in rotations
            ]
            self.assertEqual(scan_plan(raw, random_rotations), scan_plan(raw, random_rotations))

    def test_gui_entry_parsers_use_one_based_atom_syntax(self):
        self.assertEqual(parse_atom_numbers("2, 5-7; 10"), [2, 5, 6, 7, 10])
        self.assertEqual(parse_angles_text("-10, 0 5.5"), [-10.0, 0.0, 5.5])
        molecule = molecule_from_atoms([("C", 0, 0, 0), ("H", 1, 0, 0)], "builder")
        self.assertEqual(molecule.symbols, ("C", "H"))
        np.testing.assert_allclose(molecule.coordinates[1], [1, 0, 0])

    def test_visual_axis_selection_finds_second_atom_side(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); xyz, _cfg = self._files(root)
            molecule = read_xyz(xyz)
            self.assertEqual(rotating_side_for_axis(molecule, 0, 1), {1, 3})
            self.assertEqual(rotating_side_for_axis(molecule, 1, 0), {0, 2})


if __name__ == "__main__":
    unittest.main()
