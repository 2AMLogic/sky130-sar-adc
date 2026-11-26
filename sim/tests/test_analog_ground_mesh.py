"""Geometry checks for the top-level analog ground mesh."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "layout/sar-adc-top/bin/build_layout.py"
spec = importlib.util.spec_from_file_location("sar_adc_top_layout", SCRIPT)
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class TestAnalogGroundMesh(unittest.TestCase):
    def test_halflsb_shapes_and_segments_use_the_resolved_member_origin(self):
        member = ("halflsb_offset", "GND")
        resolve = layout.global_pin
        # Move the recorded pin on its first lookup. A separate lookup by the
        # drawing helper would still see the original position.
        original = resolve(*member)
        x, y, layer = original
        moved = (x + 1.0, y + 2.0, layer)
        origins = iter((moved, original))

        def resolve_member(block, pin):
            return next(origins) if (block, pin) == member else resolve(block, pin)

        canvas = layout.Canvas()
        with patch.object(layout, "global_pin", resolve_member):
            segments = layout.analog_ground_mesh(canvas)

        x, y, _ = moved
        row = layout.HALFLSB_ROW_Y["GND"]
        dest = layout.HALFLSB_DEST_X["GND"]
        half = layout.WIRE_W / 2
        column = (x - half, row - half, x + half, y + half)
        self.assertEqual(segments["halflsb_column"], column)
        self.assertIn((layout.MET3, column), canvas.shapes)
        self.assertEqual(
            segments["halflsb_row"], (dest - half, row - half, x + half, row + half)
        )
        escape = layout.ESCAPE_W / 2
        row_wire = (dest - escape, row - escape, x + escape, row + escape)
        self.assertIn((layout.MET1, row_wire), canvas.shapes)
