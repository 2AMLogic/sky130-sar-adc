"""Unit tests for the baseline half of docs/chipalooza/measure_metal_min_area.py.

Issue #338. The *measurement* half of that script needs KLayout and the pinned
sky130A deck, so it can only run in the PDK-gated `pdk-smoke` CI job. The
*bookkeeping* half -- which shapes a baseline waives, which it must not, and
what happens when a waived finding grows, shrinks, or disappears -- is pure
Python, and it is the half that decides whether the gate is a gate at all. So
it is tested here, headlessly, in the always-on `npm run test` path.

These live under sim/tests/ because that is this repo's only unittest root
(`npm run test:unit` discovers from there), matching
sim/tests/test_proposal_citations.py's convention for the other
docs/chipalooza/ checker.

The load-bearing tests are the two failure shapes the gate exists to tell
apart:

  - a NEW isolated sub-minimum pad in a flow whose geometry this repo
    hand-authors (`cdac-array`, `comparator`, `sampling-frontend`) -- exactly
    the defect issue #326 found and fixed -- must fail;
  - the 145 shapes `klt`'s own place-and-route emits (#333, upstream
    klayout-tools#2072) must not.

Plus the property that keeps the second from outliving its finding: when
#333's shapes go away, the gate stays GREEN (it must not red-line on a fixed
defect) but says out loud that the allowance is now stale.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
CHIPALOOZA_DIR = REPO_ROOT / "docs" / "chipalooza"
sys.path.insert(0, str(CHIPALOOZA_DIR))

import measure_metal_min_area as m  # noqa: E402

BASELINE_PATH = CHIPALOOZA_DIR / "metal_min_area_baseline.json"

#: The flows whose metal geometry this repo authors end to end. Nothing may be
#: waived for these: a sub-minimum shape here is always this repo's own bug.
HAND_AUTHORED_FLOWS = ("cdac-array", "comparator", "sampling-frontend")

#: The rule names the pinned sky130A deck carries minimum-area rules for.
#: Read from the deck at runtime by the script itself; restated here only so a
#: typo'd baseline key is caught headlessly, without a PDK.
RULE_NAMES = ("m1.6", "m2.6", "m3.6", "m4.4a", "m5.4")


def result(target: str, **counts: int) -> dict:
    """Build a measurement result for `target`, counts keyed by rule name."""
    layers = [
        {
            "rule": rule,
            "symbol": rule.split(".")[0],
            "below_min_area": counts.get(rule, 0),
            "shapes": [],
        }
        for rule in RULE_NAMES
    ]
    return {
        "target": target,
        "label": target,
        "layers": layers,
        "total_below_min_area": sum(layer["below_min_area"] for layer in layers),
    }


def write_baseline(tmpdir: str, allowances: list[dict], **overrides) -> Path:
    doc = {"schema": m.BASELINE_SCHEMA, "allowances": allowances}
    doc.update(overrides)
    path = Path(tmpdir) / "baseline.json"
    path.write_text(json.dumps(doc))
    return path


def allowance(target: str, rule: str, count: int, **overrides) -> dict:
    entry = {
        "target": target,
        "rule": rule,
        "max_below_min_area": count,
        "tracking_issue": "#333",
        "reason": "emitted by klt place-and-route, not drawn here",
    }
    entry.update(overrides)
    return entry


# --------------------------------------------------------------------------- #
# The repo's own committed baseline
# --------------------------------------------------------------------------- #
class TestCommittedBaseline(unittest.TestCase):
    """The waiver file itself: what it waives, and what it must never waive."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = m.load_baseline(BASELINE_PATH)

    def test_loads_and_validates(self) -> None:
        self.assertEqual(self.baseline["schema"], m.BASELINE_SCHEMA)
        self.assertTrue(self.baseline["allowances"])

    def test_every_allowance_is_tied_to_issue_333(self) -> None:
        """The gate may not carry an unattributed carve-out.

        Not merely "every entry names *an* issue" (load_baseline already
        enforces that): today every entry must name #333 specifically, because
        #333 is the only not-ours finding this repo has. A future allowance
        for some other finding is a deliberate act that has to update this
        test, which is the point.
        """
        for entry in self.baseline["allowances"]:
            self.assertEqual(
                entry["tracking_issue"],
                "#333",
                msg=f"unexpected tracking issue on {entry['target']}/{entry['rule']}",
            )
            self.assertIn("klayout-tools#2072", entry["reason"])

    def test_nothing_is_waived_for_a_hand_authored_flow(self) -> None:
        for entry in self.baseline["allowances"]:
            self.assertNotIn(
                entry["target"],
                HAND_AUTHORED_FLOWS,
                msg=(
                    f"{entry['target']} draws its own metal -- a sub-minimum shape there "
                    f"is this repo's bug (issue #326) and must never be waived"
                ),
            )

    def test_keys_match_real_targets_and_rules(self) -> None:
        labels = {label for label, _flow, _gds in m.DEFAULT_TARGETS}
        for entry in self.baseline["allowances"]:
            self.assertIn(entry["target"], labels)
            self.assertIn(entry["rule"], RULE_NAMES)

    def test_composed_allowance_is_exactly_the_sum_of_the_two_pnr_macros(self) -> None:
        """The attribution that makes these 145 shapes provably not-ours.

        Every waived shape in the composed top level is one of the two
        place-and-routed digital macros' own shapes carried up by the
        composition; the composition itself contributes none. If the composed
        allowance ever exceeded the macros' sum, the excess would be geometry
        `layout/sar-adc-top/bin/build_layout.py` drew -- which is #326's defect
        class and is not waivable.
        """
        by_key = {
            (e["target"], e["rule"]): e["max_below_min_area"] for e in self.baseline["allowances"]
        }
        for rule in RULE_NAMES:
            composed = by_key.get(("sar-adc-top (composed)", rule), 0)
            macros = by_key.get(("sar-sequencer", rule), 0) + by_key.get(
                ("seln-inverters", rule), 0
            )
            self.assertEqual(
                composed,
                macros,
                msg=f"{rule}: composed allowance {composed} != macro sum {macros}",
            )

    def test_todays_measurement_grades_clean(self) -> None:
        """The 145 #333 shapes, as measured on the records in the tree, pass."""
        verdict = m.apply_baseline(self.current_measurement(), self.baseline)
        self.assertEqual(verdict["exceeded"], [])
        self.assertEqual(verdict["stale"], [])
        self.assertEqual(verdict["unknown_allowances"], [])
        self.assertEqual(verdict["measured_total"], 290)

    def test_one_new_pad_in_a_hand_authored_flow_fails(self) -> None:
        """Issue #326's defect shape, reintroduced -- the gate must go red."""
        for flow in HAND_AUTHORED_FLOWS:
            with self.subTest(flow=flow):
                results = self.current_measurement()
                for entry in results:
                    if entry["target"] == flow:
                        entry["layers"][2]["below_min_area"] = 1  # m3.6
                verdict = m.apply_baseline(results, self.baseline)
                self.assertEqual(len(verdict["exceeded"]), 1)
                self.assertEqual(verdict["exceeded"][0]["target"], flow)
                self.assertEqual(verdict["exceeded"][0]["rule"], "m3.6")
                self.assertEqual(verdict["exceeded"][0]["allowed"], 0)

    def test_one_new_pad_in_the_composed_flow_fails(self) -> None:
        """#326's other half: the composition's own via risers are gated too.

        `sar-adc-top` is waived for #333's shapes, so this is the case a
        per-flow scoping mechanism would have missed -- the allowance is a
        ceiling, not a blanket exemption for the flow.
        """
        results = self.current_measurement()
        for entry in results:
            if entry["target"] == "sar-adc-top (composed)":
                entry["layers"][2]["below_min_area"] += 1  # m3.6: 8 -> 9
        verdict = m.apply_baseline(results, self.baseline)
        self.assertEqual(len(verdict["exceeded"]), 1)
        self.assertEqual(verdict["exceeded"][0]["target"], "sar-adc-top (composed)")
        self.assertEqual(verdict["exceeded"][0]["below_min_area"], 9)
        self.assertEqual(verdict["exceeded"][0]["allowed"], 8)

    def test_when_333_closes_the_gate_stays_green_and_says_so(self) -> None:
        """The waiver must not red-line CI the day the defect it tracks is fixed."""
        results = [result(label) for label, _flow, _gds in m.DEFAULT_TARGETS]
        verdict = m.apply_baseline(results, self.baseline)
        self.assertEqual(verdict["exceeded"], [])
        self.assertEqual(verdict["measured_total"], 0)
        self.assertEqual(
            len(verdict["stale"]),
            len(self.baseline["allowances"]),
            msg="every allowance should report itself stale once its shapes are gone",
        )

    def current_measurement(self) -> list[dict]:
        """The counts the committed records measure today (issue #338, PR gate).

        Re-derive with:
            layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py
        """
        return [
            result(
                "sar-adc-top (composed)", **{"m1.6": 114, "m2.6": 6, "m3.6": 8, "m5.4": 17}
            ),
            result("cdac-array"),
            result("comparator"),
            result("sampling-frontend"),
            result("sar-sequencer", **{"m1.6": 96, "m2.6": 6, "m3.6": 8, "m5.4": 2}),
            result("seln-inverters", **{"m1.6": 18, "m5.4": 15}),
        ]


# --------------------------------------------------------------------------- #
# apply_baseline semantics
# --------------------------------------------------------------------------- #
class TestApplyBaseline(unittest.TestCase):
    def test_no_baseline_gates_everything_at_zero(self) -> None:
        verdict = m.apply_baseline([result("cdac-array", **{"m1.6": 1})], None)
        self.assertEqual(len(verdict["exceeded"]), 1)
        self.assertEqual(verdict["exceeded"][0]["allowed"], 0)
        self.assertIsNone(verdict["exceeded"][0]["tracking_issue"])

    def test_no_baseline_and_no_shapes_is_clean(self) -> None:
        verdict = m.apply_baseline([result("cdac-array")], None)
        self.assertEqual(verdict["exceeded"], [])
        self.assertEqual(verdict["stale"], [])
        self.assertEqual(verdict["waived"], [])

    def test_equal_to_allowance_is_waived_not_failed(self) -> None:
        baseline = {"allowances": [allowance("sar-sequencer", "m1.6", 96)]}
        verdict = m.apply_baseline([result("sar-sequencer", **{"m1.6": 96})], baseline)
        self.assertEqual(verdict["exceeded"], [])
        self.assertEqual(len(verdict["waived"]), 1)
        self.assertEqual(verdict["waived"][0]["tracking_issue"], "#333")

    def test_one_over_allowance_fails(self) -> None:
        baseline = {"allowances": [allowance("sar-sequencer", "m1.6", 96)]}
        verdict = m.apply_baseline([result("sar-sequencer", **{"m1.6": 97})], baseline)
        self.assertEqual(len(verdict["exceeded"]), 1)
        self.assertEqual(verdict["over_allowance_total"], 1)

    def test_below_allowance_is_stale_not_failed(self) -> None:
        baseline = {"allowances": [allowance("sar-sequencer", "m1.6", 96)]}
        verdict = m.apply_baseline([result("sar-sequencer", **{"m1.6": 95})], baseline)
        self.assertEqual(verdict["exceeded"], [])
        self.assertEqual(len(verdict["stale"]), 1)
        self.assertEqual(verdict["stale"][0]["below_min_area"], 95)

    def test_allowance_is_per_rule_not_per_target(self) -> None:
        """A waiver for one rule must not cover a different rule on the same flow."""
        baseline = {"allowances": [allowance("sar-sequencer", "m1.6", 96)]}
        verdict = m.apply_baseline(
            [result("sar-sequencer", **{"m1.6": 96, "m4.4a": 1})], baseline
        )
        self.assertEqual([f["rule"] for f in verdict["exceeded"]], ["m4.4a"])

    def test_allowance_is_per_target_not_global(self) -> None:
        baseline = {"allowances": [allowance("sar-sequencer", "m1.6", 96)]}
        verdict = m.apply_baseline(
            [result("sar-sequencer", **{"m1.6": 96}), result("cdac-array", **{"m1.6": 1})],
            baseline,
        )
        self.assertEqual([f["target"] for f in verdict["exceeded"]], ["cdac-array"])

    def test_allowance_for_an_unmeasured_key_is_reported(self) -> None:
        """A typo'd or renamed key must never read as 'nothing to waive, fine'."""
        baseline = {"allowances": [allowance("sar-sequencor", "m1.6", 96)]}
        verdict = m.apply_baseline([result("sar-sequencer", **{"m1.6": 96})], baseline)
        self.assertEqual(verdict["unknown_allowances"], [{"target": "sar-sequencor", "rule": "m1.6"}])
        # ...and the real target is then gated at zero, i.e. it fails.
        self.assertEqual(len(verdict["exceeded"]), 1)


# --------------------------------------------------------------------------- #
# load_baseline validation
# --------------------------------------------------------------------------- #
class TestLoadBaseline(unittest.TestCase):
    def assert_rejects(self, allowances: list, needle: str, **overrides) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_baseline(tmp, allowances, **overrides)
            with self.assertRaises(m.MeasurementError) as ctx:
                m.load_baseline(path)
            self.assertIn(needle, str(ctx.exception))

    def test_missing_file(self) -> None:
        with self.assertRaises(m.MeasurementError):
            m.load_baseline(Path("/nonexistent/baseline.json"))

    def test_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.json"
            path.write_text("{not json")
            with self.assertRaises(m.MeasurementError) as ctx:
                m.load_baseline(path)
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_wrong_schema_tag(self) -> None:
        self.assert_rejects([], "schema", schema="something-else/9")

    def test_allowances_must_be_a_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.json"
            path.write_text(json.dumps({"schema": m.BASELINE_SCHEMA, "allowances": {}}))
            with self.assertRaises(m.MeasurementError):
                m.load_baseline(path)

    def test_allowance_without_a_tracking_issue_is_rejected(self) -> None:
        entry = allowance("sar-sequencer", "m1.6", 96)
        del entry["tracking_issue"]
        self.assert_rejects([entry], "tracking_issue")

    def test_allowance_with_an_empty_tracking_issue_is_rejected(self) -> None:
        self.assert_rejects(
            [allowance("sar-sequencer", "m1.6", 96, tracking_issue="  ")], "tracking_issue"
        )

    def test_allowance_without_a_reason_is_rejected(self) -> None:
        entry = allowance("sar-sequencer", "m1.6", 96)
        del entry["reason"]
        self.assert_rejects([entry], "reason")

    def test_negative_count_is_rejected(self) -> None:
        self.assert_rejects([allowance("sar-sequencer", "m1.6", -1)], "non-negative integer")

    def test_non_integer_count_is_rejected(self) -> None:
        self.assert_rejects(
            [allowance("sar-sequencer", "m1.6", 96, max_below_min_area="96")],
            "non-negative integer",
        )

    def test_boolean_count_is_rejected(self) -> None:
        self.assert_rejects(
            [allowance("sar-sequencer", "m1.6", 96, max_below_min_area=True)],
            "non-negative integer",
        )

    def test_duplicate_keys_are_rejected(self) -> None:
        self.assert_rejects(
            [allowance("sar-sequencer", "m1.6", 96), allowance("sar-sequencer", "m1.6", 97)],
            "duplicate allowance",
        )

    def test_entry_must_be_an_object(self) -> None:
        self.assert_rejects(["sar-sequencer m1.6 96"], "must be an object")


if __name__ == "__main__":
    unittest.main()
