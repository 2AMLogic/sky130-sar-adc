"""Unit tests for sim/supply-impedance-sensitivity/ (issue #378, DR-012's own
open item) -- pure deck assembly and arithmetic; no ngspice/PDK required, per
the PDK-free unit-test convention sim/tests/test_harness.py and
sim/tests/test_full_conversion.py established (sim/selftest.sh stage 1/4).

This campaign is unusually easy to get silently wrong, because every failure
mode below still *simulates cleanly* and still writes a plausible record. Each
test here pins one of them:

1. **The `GND` rename is load-bearing, not cosmetic.** ngspice aliases a node
   literally named `gnd` onto the global ground node `0`. A series element on a
   net still called `GND` is therefore shorted out, and every bonded arm would
   quietly reproduce the ideal case -- a whole campaign of four identical
   answers, with nothing in the log to say so. So: the rename happens on device
   cards, and no bare `GND` token survives on one.

2. **The package values must match the decision record that ratifies them.**
   `spec/decision-records/DR-015-package-parasitic-assumption.md` states the
   R/L table; the runner computes it. A transcription drift between the two is
   exactly the "folklore" failure mode DR-015's own Context section names, and
   the draft of that record shipped with precisely that bug (its bond-wire row
   quoted the package total, 1.914 nH, instead of the wire's own 1.414 nH).
   So: the numbers in the record are parsed back out of the Markdown and
   compared against the code that produced them.

3. **The textbook formulas must be the textbook formulas.** Recomputed here
   from the constants, independently of the runner's own helpers.

4. **`package` and `package-r-only` must differ in exactly one element.** The
   bond-inductance ablation the record reports is only an ablation if that is
   true; if a later edit changed the resistance too, the record would keep
   calling a two-element difference a single-mechanism number.

5. **The control arm must really be zero-impedance.** `ideal` must place every
   source on the die node itself, and must leave the committed fragment's own
   supply cards untouched -- otherwise the baseline this campaign measures
   everything against is not the baseline every other `sim/` campaign runs.

6. **The stimulus must be the committed fragment, verbatim.** The value of this
   campaign is that it changes the supply network and nothing else, so the
   assembled deck is checked to still carry the fragment's `.tran` card and its
   code-reading `.meas` cards unmodified.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = SIM_DIR / "supply-impedance-sensitivity"
FULL_CONVERSION_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(FULL_CONVERSION_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import run_supply_impedance as si  # noqa: E402

DR015 = REPO_ROOT / "spec" / "decision-records" / "DR-015-package-parasitic-assumption.md"
DR012 = REPO_ROOT / "spec" / "decision-records" / "DR-012-analog-ground-pad.md"


class TestGroundRename(unittest.TestCase):
    """The rename that keeps a series element in the ground return from being
    shorted onto ngspice's global node 0."""

    def setUp(self) -> None:
        self.dut = si.fc.dut_text()

    def test_rename_happens_on_device_cards(self) -> None:
        patched, hits = si.patch_dut_ground(self.dut)
        self.assertGreater(hits, 0, "no GND net reference was renamed")
        self.assertIn(si.GND_DIE, patched)

    def test_no_bare_gnd_token_survives_on_a_device_card(self) -> None:
        """The whole campaign rests on this: a surviving bare `GND` token on a
        device card is a node ngspice silently merges with `0`."""
        patched, _hits = si.patch_dut_ground(self.dut)
        offenders = [
            line
            for line in patched.splitlines()
            if not line.lstrip().startswith("*")
            and re.search(r"(?<![\w.$])GND(?![\w.$])", line, re.IGNORECASE)
        ]
        self.assertEqual(offenders, [], f"bare GND token survived on: {offenders[:3]}")

    def test_vgnd_is_not_collateral_damage(self) -> None:
        """`VGND` is the *digital* ground and a different net; the rename must
        not touch it, or the two domains DR-010 partitions would be merged."""
        patched, _hits = si.patch_dut_ground(self.dut)
        self.assertIn("VGND", patched)
        self.assertNotIn("V" + si.GND_DIE, patched)

    def test_a_netlist_without_a_gnd_port_is_refused(self) -> None:
        """If `design/sar_adc_top.spice` ever stops declaring the `GND` port,
        DR-012's subject has changed and this campaign must be re-derived
        rather than quietly run against a different interface."""
        with self.assertRaises(RuntimeError):
            si.patch_dut_ground("**.subckt sar_adc_top VDD VPWR VGND\nM1 a b c d nfet\n.end\n")


class TestPdkBareGndGuard(unittest.TestCase):
    """The PDK is the one body of SPICE this campaign includes but does not
    rewrite. A `GND`-named node in there would reach global `0` directly and
    bypass the series network, so the guard is exercised here against a fake
    PDK tree -- no real PDK needed, per this file's PDK-free convention."""

    class _FakePdk:
        def __init__(self, variant_dir: Path) -> None:
            self.variant_dir = variant_dir

    def _tree(self, tmp: Path, stdcell_body: str, model_body: str) -> "_FakePdk":  # type: ignore[name-defined]
        spice = tmp / "libs.ref" / "sky130_fd_sc_hd" / "spice"
        spice.mkdir(parents=True)
        (spice / "sky130_fd_sc_hd.spice").write_text(stdcell_body)
        models = tmp / "libs.tech" / "ngspice"
        models.mkdir(parents=True)
        (models / "sky130.lib.spice").write_text(model_body)
        return self._FakePdk(tmp)

    def test_a_clean_pdk_reports_no_offenders(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            info = self._tree(
                Path(d),
                ".subckt inv A Y VPWR VGND VPB VNB\nM1 Y A VGND VNB nfet\n.ends\n",
                ".model nfet nmos level=54\n",
            )
            self.assertEqual(si.check_pdk_has_no_bare_gnd_node(info), [])

    def test_a_gnd_node_in_the_standard_cells_is_caught(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            info = self._tree(
                Path(d),
                ".subckt inv A Y VPWR VGND\nM1 Y A GND GND nfet\n.ends\n",
                ".model nfet nmos level=54\n",
            )
            self.assertTrue(si.check_pdk_has_no_bare_gnd_node(info))

    def test_a_gnd_node_in_the_model_library_is_caught(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            info = self._tree(
                Path(d),
                ".subckt inv A Y VPWR VGND\n.ends\n",
                ".subckt nfet_01v8 d g s\nM1 d g s GND nmos\n.ends\n",
            )
            self.assertTrue(si.check_pdk_has_no_bare_gnd_node(info))

    def test_a_gnd_mention_in_a_comment_is_not_an_offender(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            info = self._tree(
                Path(d),
                "* this cell ties its bulk to GND conceptually\n.subckt inv A Y\n.ends\n",
                "; GND is mentioned here too\n.model nfet nmos\n",
            )
            self.assertEqual(si.check_pdk_has_no_bare_gnd_node(info), [])

    def test_vgnd_is_not_mistaken_for_gnd(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            info = self._tree(
                Path(d),
                ".subckt inv A Y VPWR VGND\nM1 Y A VGND VGND nfet\n.ends\n",
                ".model nfet nmos\n",
            )
            self.assertEqual(si.check_pdk_has_no_bare_gnd_node(info), [])


class TestPackageAssumptionMatchesDR015(unittest.TestCase):
    """The runner's constants and DR-015's table are one fact stated twice."""

    def setUp(self) -> None:
        self.text = DR015.read_text()

    def _nh(self, pattern: str) -> float:
        m = re.search(pattern, self.text)
        self.assertIsNotNone(m, f"DR-015 no longer states {pattern!r}")
        return float(m.group(1))

    def test_dr015_exists_and_is_referenced_by_the_runner(self) -> None:
        self.assertTrue(DR015.is_file(), "DR-015 is missing; the values are unratified")
        self.assertIn("DR-015", (EXPERIMENT_DIR / "run_supply_impedance.py").read_text())
        self.assertIn("DR-015", (EXPERIMENT_DIR / "README.md").read_text())

    def test_bond_wire_inductance_row_matches_the_code(self) -> None:
        stated = self._nh(r"bond wire.*?`L = ([0-9.]+) nH`")
        self.assertAlmostEqual(stated, si.BOND_L_H * 1e9, places=2)

    def test_bond_wire_resistance_row_matches_the_code(self) -> None:
        m = re.search(r"bond wire.*?`R = ([0-9.]+) m", self.text)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(float(m.group(1)), si.BOND_R_OHM * 1e3, places=1)

    def test_per_terminal_total_row_matches_the_code(self) -> None:
        stated_l = self._nh(r"total, per terminal.*?`L = ([0-9.]+) nH")
        m = re.search(r"total, per terminal.*?R = ([0-9.]+) m", self.text)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(stated_l, si.PACKAGE_L_H * 1e9, places=2)
        self.assertAlmostEqual(float(m.group(1)), si.PACKAGE_R_OHM * 1e3, places=1)

    def test_total_is_the_wire_plus_the_stated_allowance(self) -> None:
        """The table is an addition; check it adds up rather than trusting it."""
        self.assertAlmostEqual(
            si.PACKAGE_L_H, si.BOND_L_H + si.LEAD_FRAME_L_NH * 1e-9, places=15
        )
        self.assertAlmostEqual(
            si.PACKAGE_R_OHM, si.BOND_R_OHM + si.LEAD_FRAME_R_MOHM * 1e-3, places=12
        )

    def test_substrate_stand_ins_match_the_code(self) -> None:
        m = re.search(r"`R_SUB = ([0-9.]+) ", self.text)
        self.assertIsNotNone(m)
        self.assertAlmostEqual(float(m.group(1)), si.R_SUB_OHM, places=3)
        self.assertIn("R_SUBX", self.text)

    def test_dr015_does_not_claim_to_be_a_package_selection(self) -> None:
        """CLAUDE.md's clean-room rule: these values may not be presented as a
        real package's parasitics, and the record must say so in its own text."""
        self.assertIn("not a package selection", self.text)


class TestBondWireArithmetic(unittest.TestCase):
    """The textbook expressions, recomputed independently of the runner."""

    def test_round_wire_self_inductance(self) -> None:
        length_m = si.BOND_WIRE_LENGTH_MM * 1e-3
        radius_m = 0.5 * si.BOND_WIRE_DIAMETER_UM * 1e-6
        expected = (
            (4.0e-7 * math.pi) * length_m / (2.0 * math.pi)
        ) * (math.log(2.0 * length_m / radius_m) - 0.75)
        self.assertAlmostEqual(si.BOND_L_H, expected, places=15)

    def test_wire_resistance_is_rho_l_over_area(self) -> None:
        radius_m = 0.5 * si.BOND_WIRE_DIAMETER_UM * 1e-6
        expected = (
            si.GOLD_RESISTIVITY_OHM_M * (si.BOND_WIRE_LENGTH_MM * 1e-3) / (math.pi * radius_m**2)
        )
        self.assertAlmostEqual(si.BOND_R_OHM, expected, places=15)

    def test_values_are_physically_plausible_for_a_short_fine_bond_wire(self) -> None:
        """A sanity band, not a spec: a ~1.5 mm 1-mil wire is order-1 nH and
        order-100 mOhm. A value outside this means a unit slipped."""
        self.assertTrue(0.5e-9 < si.BOND_L_H < 5e-9, si.BOND_L_H)
        self.assertTrue(10e-3 < si.BOND_R_OHM < 1.0, si.BOND_R_OHM)


class TestArms(unittest.TestCase):
    def test_control_arm_is_truly_zero_impedance(self) -> None:
        ideal = si.ARMS_BY_NAME[si.CONTROL_ARM]
        self.assertEqual(set(ideal.bonds), set(si.TERMINAL_ORDER))
        for terminal, bond in ideal.bonds.items():
            self.assertIsNone(bond, f"{terminal} carries an impedance in the control arm")

    def test_control_arm_leaves_the_committed_fragment_untouched(self) -> None:
        fragment = si.tb.FRAGMENT_PATH.read_text()
        self.assertEqual(
            si.patch_fragment_supplies(fragment, si.ARMS_BY_NAME[si.CONTROL_ARM]),
            fragment,
            "the control arm re-pointed a supply source it should have left alone",
        )

    def test_control_arm_emits_a_die_side_ground_source_and_no_series_element(self) -> None:
        cards = si.arm_network_lines(si.ARMS_BY_NAME[si.CONTROL_ARM])
        self.assertIn(f"VGNDA {si.GND_DIE} 0 DC 0", cards)
        self.assertEqual([c for c in cards if re.match(r"^L[A-Z]", c)], [])

    def test_package_and_package_r_only_differ_in_exactly_one_element(self) -> None:
        """The bond-inductance single-mechanism number depends on this."""
        full = si.ARMS_BY_NAME["package"]
        r_only = si.ARMS_BY_NAME["package-r-only"]
        self.assertEqual(set(full.bonds), set(r_only.bonds))
        self.assertEqual(full.substrate, r_only.substrate)
        for terminal in full.bonds:
            self.assertAlmostEqual(
                full.bonds[terminal].r_ohm, r_only.bonds[terminal].r_ohm, places=12
            )
            self.assertGreater(full.bonds[terminal].l_h, 0.0)
            self.assertEqual(r_only.bonds[terminal].l_h, 0.0)

    def test_substrate_arm_is_not_presented_as_an_ablation_of_package(self) -> None:
        """Its resistance is orders of magnitude larger, so a difference against
        `package` would confound two changes. The code must say so."""
        self.assertGreater(si.R_SUB_OHM, 10.0 * si.PACKAGE_R_OHM)
        self.assertIn("not an ablation", si.ARMS_BY_NAME["substrate"].summary.lower())

    def test_no_gnd_pad_arm_gives_gnd_no_bond_of_its_own(self) -> None:
        arm = si.ARMS_BY_NAME["no-gnd-pad"]
        self.assertNotIn("GND", arm.bonds)
        for terminal in ("VDD", "VPWR", "VGND"):
            self.assertIsNotNone(arm.bonds[terminal])
        cards = si.arm_network_lines(arm)
        self.assertEqual([c for c in cards if c.startswith("VGNDA ")], [])
        self.assertTrue(any(c.startswith(f"RSUBX {si.GND_DIE} VGND") for c in cards))

    def test_every_arm_carries_the_substrate_link_dr012_measured(self) -> None:
        for arm in si.ARMS:
            self.assertEqual(
                arm.substrate,
                (("RSUBX", si.GND_DIE, "VGND", si.R_SUBX_OHM),),
                f"arm {arm.name} does not carry the GND/VGND substrate link",
            )

    def test_a_resistance_only_bond_emits_a_resistor_not_a_zero_inductor(self) -> None:
        for name in ("package-r-only", "substrate"):
            cards = si.arm_network_lines(si.ARMS_BY_NAME[name])
            self.assertEqual([c for c in cards if re.match(r"^L[A-Z]", c)], [], name)
            self.assertTrue(any(re.match(r"^R(VDD|VGND|GND|VPWR)\b", c) for c in cards), name)

    def test_bonded_arms_repoint_only_the_fragment_cards_they_bond(self) -> None:
        fragment = si.tb.FRAGMENT_PATH.read_text()
        patched = si.patch_fragment_supplies(fragment, si.ARMS_BY_NAME["package"])
        for terminal in ("VDD", "VPWR", "VGND"):
            spec = si.TERMINALS[terminal]
            self.assertIn(f"{spec['source']} {spec['board']} 0 ", patched)
            self.assertNotIn(spec["card"], patched)
        # The reference sources are a different experiment and stay at the die.
        for card in ("VVREFP", "VVCM", "VVREFN"):
            if card in fragment:
                self.assertIn(card, patched)

    def test_source_instance_names_are_preserved_so_meas_cards_still_work(self) -> None:
        """The fragment's own `.meas tran i_vdd avg i(vvdd)` cards must keep
        measuring the current delivered from the board."""
        patched = si.patch_fragment_supplies(
            si.tb.FRAGMENT_PATH.read_text(), si.ARMS_BY_NAME["package"]
        )
        for source in ("VVDD", "VVPWR", "VVGND"):
            self.assertRegex(patched, rf"(?m)^{source}\s")

    def test_substrate_link_carries_no_current_in_the_control(self) -> None:
        """Both of its ends are ideal-source-held at 0 V in `ideal`, which is
        what makes the control a clean baseline rather than a fifth network."""
        ideal = si.ARMS_BY_NAME[si.CONTROL_ARM]
        self.assertIsNone(ideal.bonds["GND"])
        self.assertIsNone(ideal.bonds["VGND"])


class TestGroundPadAblation(unittest.TestCase):
    """`no-gnd-pad` vs `package` is the pair DR-012 actually decided between,
    and the record may only present it as an ablation if the two decks really
    do differ in exactly one element (issue #409, item 2)."""

    def _point(self, arm: str, cid: str, codes: list[int], gnd_pp: float) -> dict:
        return {
            "arm": arm,
            "corner_id": cid,
            "conversions": [
                {"conversion": i + 1, "fraction": f, "code": c}
                for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, codes))
            ],
            "extras": {"gnd_die_pp": gnd_pp},
        }

    def test_no_gnd_pad_and_package_differ_in_exactly_one_element(self) -> None:
        null_opt = si.ARMS_BY_NAME["no-gnd-pad"]
        as_built = si.ARMS_BY_NAME["package"]
        # The one element: GND's own bond, present in one arm and absent in the
        # other. Everything else -- the other three bonds and the substrate
        # link -- must be identical, or the difference confounds two changes.
        self.assertEqual(set(as_built.bonds) - set(null_opt.bonds), {"GND"})
        self.assertEqual(null_opt.substrate, as_built.substrate)
        for terminal in null_opt.bonds:
            self.assertAlmostEqual(
                null_opt.bonds[terminal].r_ohm, as_built.bonds[terminal].r_ohm, places=12
            )
            self.assertAlmostEqual(
                null_opt.bonds[terminal].l_h, as_built.bonds[terminal].l_h, places=15
            )

    def test_the_two_decks_differ_only_in_the_ground_terminal_s_cards(self) -> None:
        """The same claim one level down: on the cards themselves, not just on
        the dataclass."""
        null_cards = set(si.arm_network_lines(si.ARMS_BY_NAME["no-gnd-pad"]))
        built_cards = set(si.arm_network_lines(si.ARMS_BY_NAME["package"]))
        only_in_as_built = {c for c in built_cards - null_cards if not c.startswith("*")}
        self.assertTrue(
            all(re.match(r"^(VGNDA|LGND|RGND)\b", c) for c in only_in_as_built),
            f"the two arms differ in more than GND's own cards: {only_in_as_built}",
        )

    def test_the_ablation_is_reported_when_both_arms_ran(self) -> None:
        points = [
            self._point("package", "tt_27c_1.80v", [10, 20, 30, 40, 50], 37.0e-3),
            self._point("no-gnd-pad", "tt_27c_1.80v", [10, 20, 33, 40, 50], 74.0e-3),
        ]
        lines = si.gnd_pad_ablation_lines(points, ["package", "no-gnd-pad"], ["tt_27c_1.80v"])
        self.assertEqual(len(lines), 1)
        self.assertIn("3 LSB", lines[0])
        self.assertIn("74.000 mV vs 37.000 mV", lines[0])
        self.assertIn("2.0x", lines[0])

    def test_a_record_without_the_null_option_says_nothing_about_the_pad(self) -> None:
        """No noise in the records that omit the expensive arm: the omission
        section already explains it."""
        self.assertEqual(si.gnd_pad_ablation_lines([], ["ideal", "package"], ["tt_27c_1.80v"]), [])

    def test_the_null_option_without_its_as_built_twin_is_not_an_ablation(self) -> None:
        lines = si.gnd_pad_ablation_lines([], ["ideal", "no-gnd-pad"], ["tt_27c_1.80v"])
        self.assertEqual(len(lines), 1)
        self.assertIn("not available", lines[0])

    def test_the_bond_ablation_drops_its_uniqueness_claim_when_this_one_also_ran(self) -> None:
        """Records are append-only, so an unconditional "this is the only
        single-mechanism number" would be permanently false in any record that
        also carries the ground-pad ablation. It must be conditional."""
        points = [
            self._point("package", "tt_27c_1.80v", [10, 20, 30, 40, 50], 37.0e-3),
            self._point("package-r-only", "tt_27c_1.80v", [10, 20, 30, 40, 50], 0.059e-3),
            self._point("no-gnd-pad", "tt_27c_1.80v", [10, 20, 33, 40, 50], 74.0e-3),
        ]
        arms = ["ideal", "package-r-only", "package", "no-gnd-pad"]
        bond = si.ablation_lines(points, arms, ["tt_27c_1.80v"])
        self.assertEqual(len(bond), 1)
        self.assertNotIn("only single-mechanism number", bond[0])
        self.assertIn("two single-mechanism numbers in this record", bond[0])
        # and the sibling it now names is actually emitted into the same record
        self.assertTrue(si.gnd_pad_ablation_lines(points, arms, ["tt_27c_1.80v"]))

    def test_the_bond_ablation_keeps_its_uniqueness_claim_when_it_stands_alone(self) -> None:
        """The committed four-arm record really does carry exactly one
        single-mechanism number, and must keep saying so."""
        points = [
            self._point("package", "tt_27c_1.80v", [10, 20, 30, 40, 50], 37.0e-3),
            self._point("package-r-only", "tt_27c_1.80v", [10, 20, 30, 40, 50], 0.059e-3),
        ]
        arms = ["ideal", "package-r-only", "package", "substrate"]
        bond = si.ablation_lines(points, arms, ["tt_27c_1.80v"])
        self.assertEqual(len(bond), 1)
        self.assertIn("This is the only single-mechanism number in this record.", bond[0])
        self.assertEqual(si.gnd_pad_ablation_lines(points, arms, ["tt_27c_1.80v"]), [])

    def test_every_arm_has_a_standing_omission_reason(self) -> None:
        """A record that omits an arm must be able to say why -- an unexplained
        omission is not a valid record (`sim/README.md`)."""
        for arm in si.ARMS:
            if arm.name == si.CONTROL_ARM:
                continue  # the control can never be omitted (the CLI refuses)
            self.assertIn(arm.name, si.ARM_OMISSION_NOTES)
            self.assertTrue(si.ARM_OMISSION_NOTES[arm.name].strip())


class TestExtraMeasurements(unittest.TestCase):
    def test_rail_probes_watch_the_die_side_nodes(self) -> None:
        nodes = {node for _name, node, _label in si.RAIL_PROBES}
        self.assertEqual(nodes, {si.GND_DIE, "VGND", "VDD", "VPWR"})

    def test_ground_bond_current_is_measured_only_where_a_bond_exists(self) -> None:
        self.assertIn("i_gnda", si.extra_measure_names(si.ARMS_BY_NAME["package"]))
        self.assertNotIn("i_gnda", si.extra_measure_names(si.ARMS_BY_NAME["no-gnd-pad"]))

    def test_excursion_window_is_the_fragment_s_own_current_averaging_window(self) -> None:
        """One window for every number in the record, so a rail excursion and a
        supply current in the same row describe the same instant of time."""
        t0, t1 = si._idd_window_ns()
        self.assertLess(t0, t1)
        self.assertAlmostEqual(
            t0, si.tb.t_edge_ns(si.tb.PHASES_PER_CONVERSION * si.tb.IDD_CONVERSION), places=6
        )
        for line in si.extra_measure_lines(si.ARMS_BY_NAME["package"]):
            if line.startswith(".meas"):
                self.assertIn(f"from={t0:.4f}n", line)
                self.assertIn(f"to={t1:.4f}n", line)


class TestCodeComparison(unittest.TestCase):
    def _point(self, codes: list[int | None]) -> dict:
        return {
            "conversions": [
                {"conversion": i + 1, "fraction": f, "code": c}
                for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, codes))
            ]
        }

    def test_near_full_scale_inputs_are_excluded_from_the_delta(self) -> None:
        """They are already wrong by ~100 LSB at every corner (issue #267), so a
        change there cannot be attributed to supply impedance."""
        point = self._point([0] * len(si.tb.INPUT_FRACTIONS))
        kept = {cv["fraction"] for cv in si.mid_scale_conversions(point)}
        self.assertTrue(all(abs(f) <= 0.5 for f in kept))
        self.assertTrue(any(abs(f) > 0.5 for f in si.tb.INPUT_FRACTIONS))

    def test_worst_mid_scale_delta_ignores_the_excluded_columns(self) -> None:
        control = self._point([100 if abs(f) > 0.5 else 500 for f in si.tb.INPUT_FRACTIONS])
        point = self._point(
            [900 if abs(f) > 0.5 else 502 for f in si.tb.INPUT_FRACTIONS]
        )
        self.assertEqual(si.worst_mid_scale_delta(point, control), 2)

    def test_a_missing_code_is_reported_as_none_not_as_zero(self) -> None:
        control = self._point([500] * len(si.tb.INPUT_FRACTIONS))
        point = self._point([None] * len(si.tb.INPUT_FRACTIONS))
        self.assertIsNone(si.worst_mid_scale_delta(point, control))


class TestLogCache(unittest.TestCase):
    """`--log-cache` makes an interrupted campaign restartable. Its whole value
    rests on the identity gate: a cached log is reusable ONLY if it provably
    belongs to the same deck on the same toolchain, or the cache becomes a route
    by which a stale number reaches an append-only record."""

    class _FakePdk:
        variant = "sky130A"
        open_pdks_commit_expected = "b" * 40

        def __init__(self, tmp: Path) -> None:
            self.variant_dir = tmp

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name)
        self.deck = "* deck\n.end\n"
        self.pdk = self._FakePdk(self.cache)
        self._orig_commit = si.pdk.resolved_commit_verified
        self._orig_ngspice = si.toolchain._ngspice_version
        si.pdk.resolved_commit_verified = lambda _info: "commit-a"  # type: ignore[assignment]
        si.toolchain._ngspice_version = lambda: "ngspice-46"  # type: ignore[assignment]

    def tearDown(self) -> None:
        si.pdk.resolved_commit_verified = self._orig_commit  # type: ignore[assignment]
        si.toolchain._ngspice_version = self._orig_ngspice  # type: ignore[assignment]
        self._tmp.cleanup()

    def test_no_cache_directory_means_never_reuse(self) -> None:
        self.assertIsNone(si.load_cached_run(None, "ideal@c", self.deck, self.pdk))

    def test_a_stored_log_round_trips_with_its_wall_clock(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 12.5)
        self.assertEqual(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk), ("LOG", 12.5))

    def test_a_changed_deck_is_not_reused(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        self.assertIsNone(
            si.load_cached_run(self.cache, "ideal@c", self.deck + "* edited\n", self.pdk)
        )

    def test_a_different_open_pdks_commit_is_not_reused(self) -> None:
        """Records from different model libraries are not comparable
        (`sim/README.md`), so neither are their logs."""
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        si.pdk.resolved_commit_verified = lambda _info: "commit-b"  # type: ignore[assignment]
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))

    def test_a_different_ngspice_version_is_not_reused(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        si.toolchain._ngspice_version = lambda: "ngspice-47"  # type: ignore[assignment]
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))

    def test_a_corrupt_sidecar_is_not_reused(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        (self.cache / "ideal__c.json").write_text("{not json")
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))

    def test_a_log_without_its_sidecar_is_not_reused(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        (self.cache / "ideal__c.json").unlink()
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))

    def test_the_sidecar_records_every_identity_field_it_gates_on(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        meta = json.loads((self.cache / "ideal__c.json").read_text())
        for field in ("deck_sha256", "open_pdks_commit", "pdk_variant", "ngspice"):
            self.assertIn(field, meta)

    def test_arms_do_not_collide_in_the_cache(self) -> None:
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "A", 1.0)
        si.store_cached_run(self.cache, "package@c", self.deck, self.pdk, "B", 2.0)
        self.assertEqual(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk)[0], "A")
        self.assertEqual(si.load_cached_run(self.cache, "package@c", self.deck, self.pdk)[0], "B")

    def test_a_sidecar_without_a_usable_wall_clock_is_not_reused(self) -> None:
        """A missing `wall_s` is a malformed sidecar, not a run that took 0 s:
        defaulting it would land `0` and `0.00x` in the record's wall-clock
        table as if measured."""
        for bad in ({}, {"wall_s": None}, {"wall_s": "ages"}):
            with self.subTest(bad=bad):
                si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
                meta = json.loads((self.cache / "ideal__c.json").read_text())
                meta.pop("wall_s")
                meta.update(bad)
                (self.cache / "ideal__c.json").write_text(json.dumps(meta))
                self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))


class TestLogCacheRefusesUnverifiableProvenance(unittest.TestCase):
    """The identity gate must act on `pdk.resolved_commit_verified()`, never on
    `pdk.resolved_commit()`.

    `resolved_commit()` is a *display* string whose own docstring forbids
    treating it as proof of the install: for any non-volare install -- which
    `toolchain.check_env()` only *warns* about, so it reaches a real run -- it
    returns the same constant fallback whatever library is actually installed.
    A gate keyed on it would hand back library A's log for a run against
    library B, which is exactly the stale number `sim/README.md`'s append-only
    records must never absorb."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name)
        self.deck = "* deck\n.end\n"
        self.pdk = TestLogCache._FakePdk(self.cache)
        self._orig_verified = si.pdk.resolved_commit_verified
        self._orig_display = si.pdk.resolved_commit
        self._orig_ngspice = si.toolchain._ngspice_version
        si.toolchain._ngspice_version = lambda: "ngspice-46"  # type: ignore[assignment]

    def tearDown(self) -> None:
        si.pdk.resolved_commit_verified = self._orig_verified  # type: ignore[assignment]
        si.pdk.resolved_commit = self._orig_display  # type: ignore[assignment]
        si.toolchain._ngspice_version = self._orig_ngspice  # type: ignore[assignment]
        self._tmp.cleanup()

    def test_the_display_fallback_really_is_the_same_string_for_two_installs(self) -> None:
        """The premise, checked against the real `pdk` functions rather than a
        stub: two different non-volare installs are indistinguishable through
        `resolved_commit()` and both unverifiable through
        `resolved_commit_verified()`."""
        a = TestLogCache._FakePdk(self.cache / "install-a")
        b = TestLogCache._FakePdk(self.cache / "install-b")
        self.assertEqual(si.pdk.resolved_commit(a), si.pdk.resolved_commit(b))
        self.assertIn("unverified", si.pdk.resolved_commit(a))
        self.assertIsNone(si.pdk.resolved_commit_verified(a))
        self.assertIsNone(si.pdk.resolved_commit_verified(b))

    def test_an_unverifiable_pdk_provenance_has_no_cache_identity(self) -> None:
        si.pdk.resolved_commit_verified = lambda _info: None  # type: ignore[assignment]
        self.assertIsNone(si._cache_identity(self.deck, self.pdk))

    def test_an_unverifiable_pdk_provenance_is_never_reused(self) -> None:
        """Stored while provenance was verifiable, read back after the install
        became one this harness cannot vouch for: a miss, not a match."""
        si.pdk.resolved_commit_verified = lambda _info: "c" * 40  # type: ignore[assignment]
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        si.pdk.resolved_commit_verified = lambda _info: None  # type: ignore[assignment]
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))

    def test_two_different_unverifiable_installs_do_not_false_match(self) -> None:
        """The concrete failure the gate exists to prevent, written as the
        pre-fix cache would have written it: a sidecar carrying the display
        fallback string, read on a *different* non-volare install that produces
        that identical string. Gating on the display value would reuse library
        A's log for a run against library B."""
        display = si.pdk.resolved_commit(self.pdk)
        meta = {
            "deck_sha256": si.evidence.sha256_text(self.deck),
            "open_pdks_commit": display,  # what the display-string gate stored
            "pdk_variant": self.pdk.variant,
            "ngspice": "ngspice-46",
            "wall_s": 1.0,
            "point_id": "ideal@c",
        }
        (self.cache / "ideal__c.log").write_text("LOG FROM LIBRARY A")
        (self.cache / "ideal__c.json").write_text(json.dumps(meta))

        other = TestLogCache._FakePdk(self.cache / "some-other-hand-install")
        self.assertEqual(si.pdk.resolved_commit(other), display)  # indistinguishable
        si.pdk.resolved_commit_verified = lambda _info: None  # type: ignore[assignment]
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, other))

    def test_an_unverifiable_pdk_provenance_is_never_stored(self) -> None:
        """A log with no provable identity is not worth keeping: storing it
        could only ever be cashed in by weakening the gate later."""
        si.pdk.resolved_commit_verified = lambda _info: None  # type: ignore[assignment]
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        self.assertEqual(sorted(p.name for p in self.cache.iterdir()), [])

    def test_an_unreported_ngspice_version_is_neither_stored_nor_reused(self) -> None:
        """"unknown" == "unknown" is not a match; it is two hosts that both
        failed to answer."""
        si.pdk.resolved_commit_verified = lambda _info: "c" * 40  # type: ignore[assignment]
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 1.0)
        si.toolchain._ngspice_version = lambda: None  # type: ignore[assignment]
        self.assertIsNone(si._cache_identity(self.deck, self.pdk))
        self.assertIsNone(si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk))
        si.store_cached_run(self.cache, "package@c", self.deck, self.pdk, "LOG", 1.0)
        self.assertFalse((self.cache / "package__c.log").exists())

    def test_a_verified_install_still_round_trips(self) -> None:
        """The gate tightened, not broke: the ordinary volare-verified path is
        untouched."""
        si.pdk.resolved_commit_verified = lambda _info: "c" * 40  # type: ignore[assignment]
        si.store_cached_run(self.cache, "ideal@c", self.deck, self.pdk, "LOG", 7.5)
        self.assertEqual(
            si.load_cached_run(self.cache, "ideal@c", self.deck, self.pdk), ("LOG", 7.5)
        )
        meta = json.loads((self.cache / "ideal__c.json").read_text())
        self.assertEqual(meta["open_pdks_commit"], "c" * 40)
        self.assertNotIn("unverified", meta["open_pdks_commit"])


class TestInvocationFooter(unittest.TestCase):
    """`sim/check_spec_coverage.py` reads the footer to tie a record to its
    runner, and `sim/README.md` makes records non-rewritable -- so the footer
    must state the invocation that actually ran."""

    def test_default_arm_set_renders_the_canonical_command(self) -> None:
        line = si.invocation_line([arm.name for arm in si.ARMS], False, "")
        self.assertEqual(
            line, "sim/supply-impedance-sensitivity/run_supply_impedance.py --record"
        )

    def test_a_subset_run_names_its_arms(self) -> None:
        line = si.invocation_line(["ideal", "package"], False, "")
        self.assertIn("--arms ideal,package", line)

    def test_corners_and_supersedes_are_recorded(self) -> None:
        line = si.invocation_line([arm.name for arm in si.ARMS], True, "20260101-000000-abcdef0")
        self.assertIn("--corners", line)
        self.assertIn("--supersedes 20260101-000000-abcdef0", line)

    def test_the_footer_stays_inside_the_indexed_cold_start_command(self) -> None:
        """`check_spec_coverage.py` fails `cold-start-record-mismatch` if the
        footer carries any token the indexed bench's documented `cold_start`
        does not. That is why a scheduling-only flag (`--log-cache`, whose
        argument is one machine's scratch directory) must never reach the
        footer, and why a record minted with a different `--arms` list needs its
        own bench entry rather than a quietly softened footer -- a failure that
        would otherwise only surface after the hours-long run that minted it."""
        index = json.loads((REPO_ROOT / "sim" / "spec-coverage.json").read_text())
        runner = "sim/supply-impedance-sensitivity/run_supply_impedance.py"
        benches = [
            bench
            for row in index["rows"]
            for bench in row.get("benches", [])
            if bench.get("runner") == runner
        ]
        self.assertTrue(benches, f"{runner} is not indexed in sim/spec-coverage.json")
        for bench in benches:
            tokens = bench["cold_start"].split()
            cold_tokens = set(tokens)
            if "--null-sweep" in cold_tokens:
                # The null-option ladder mints through its own writer and its
                # own footer function; the same gate applies to it, and its one
                # axis flag must stay inside the indexed command.
                rsub = (
                    tuple(
                        float(v)
                        for v in tokens[tokens.index("--null-sweep-rsub") + 1].split(",")
                    )
                    if "--null-sweep-rsub" in tokens
                    else si.NULL_SWEEP_RSUBX_OHM
                )
                footer = si.null_sweep_invocation_line(rsub, "")
            elif "--sweep" in cold_tokens:
                # The sweep mints through its own writer and its own footer
                # function; the same gate applies to it, and it has its own
                # pair of axis flags that must stay inside the indexed command.
                l_mults = (
                    tuple(float(v) for v in tokens[tokens.index("--sweep-l-mult") + 1].split(","))
                    if "--sweep-l-mult" in tokens
                    else si.SWEEP_L_MULTIPLIERS
                )
                rsubx = (
                    tuple(float(v) for v in tokens[tokens.index("--sweep-rsubx") + 1].split(","))
                    if "--sweep-rsubx" in tokens
                    else si.SWEEP_RSUBX_OHM
                )
                footer = si.sweep_invocation_line(l_mults, rsubx, "")
            else:
                arm_names = (
                    tokens[tokens.index("--arms") + 1].split(",")
                    if "--arms" in tokens
                    else [arm.name for arm in si.ARMS]
                )
                # A corner subset is part of the record's identity, so it
                # reaches the footer and must be inside the indexed command
                # too -- the same gate the arm list is held to.
                corner_points = (
                    tokens[tokens.index("--corner-points") + 1].split(",")
                    if "--corner-points" in tokens
                    else []
                )
                footer = si.invocation_line(
                    arm_names, "--corners" in cold_tokens, "", corner_points
                )
            missing = [tok for tok in footer.split()[1:] if tok not in cold_tokens]
            self.assertEqual(
                missing, [], f"the footer would carry {missing}, absent from {bench['cold_start']}"
            )

    def test_the_documented_sweep_command_is_the_footer_the_sweep_would_write(self) -> None:
        """The half of the gate that CAN be checked before the run, is.

        `--sweep --record` is not in `sim/spec-coverage.json` yet, and cannot be:
        `check_spec_coverage.py` fails a bench entry that lists no evidence
        record (`bench-has-no-record`), so the entry lands with the record it
        names. That leaves `cold-start-undocumented` -- "the indexed command must
        appear verbatim in `documented_in`" -- checkable now against the README
        the entry will point at, which is the difference between discovering a
        drifted command before the hours and after them.
        """
        readme = (EXPERIMENT_DIR / "README.md").read_text()
        footer = si.sweep_invocation_line(si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM, "")
        self.assertIn(
            f"python3 {footer}",
            readme,
            "the README does not document the exact command the default sweep would "
            "record in its own footer -- indexing that record would fail "
            "cold-start-undocumented",
        )

    def test_the_documented_null_sweep_command_is_the_footer_it_would_write(self) -> None:
        """Same pre-run half of the gate as the sweep's, for the same reason:
        `cold-start-undocumented` ("the indexed command must appear verbatim in
        `documented_in`") is checkable against the README before the hours are
        spent, and is the difference between finding a drifted command before
        the run and after it."""
        readme = (EXPERIMENT_DIR / "README.md").read_text()
        footer = si.null_sweep_invocation_line(si.NULL_SWEEP_RSUBX_OHM, "")
        self.assertIn(
            f"python3 {footer}",
            readme,
            "the README does not document the exact command the default "
            "null-option ladder would record in its own footer -- indexing that "
            "record would fail cold-start-undocumented",
        )

    def test_a_corner_subset_reaches_the_footer(self) -> None:
        """`--corner-points` changes WHAT WAS SIMULATED, so it is part of the
        record's identity and is stated -- the same rule that puts `--arms` in
        the footer and keeps `--log-cache` out of it."""
        line = si.invocation_line(
            ["ideal", "package"], False, "", ["tt_27c_1.80v", "ss_27c_1.80v"]
        )
        self.assertIn("--corner-points tt_27c_1.80v,ss_27c_1.80v", line)
        self.assertNotIn("--corners ", line + " ")

    def test_a_full_grid_run_says_corners_not_a_nine_point_list(self) -> None:
        """The two flags are the same axis stated two ways; the footer names
        whichever one the run used, and never both."""
        line = si.invocation_line([arm.name for arm in si.ARMS], True, "")
        self.assertIn("--corners", line)
        self.assertNotIn("--corner-points", line)

    def test_the_documented_corner_slice_command_is_the_footer_it_would_write(self) -> None:
        """Same pre-run half of the `cold-start-undocumented` gate the sweep and
        the null-option ladder are held to. The corner axis is the one that will
        keep widening (issue #409 item 1), so every widening is a new documented
        command -- checked here against the README before the hours are spent,
        not after."""
        readme = (EXPERIMENT_DIR / "README.md").read_text()
        footer = si.invocation_line(
            ["ideal", "package"], False, "", ["tt_27c_1.80v", "ss_27c_1.80v"]
        )
        self.assertIn(
            f"python3 {footer}",
            readme,
            "the README does not document the exact command the committed corner "
            "slice recorded in its own footer -- indexing that record would fail "
            "cold-start-undocumented",
        )

    def test_the_runner_path_is_always_present(self) -> None:
        """The spec-coverage check matches the record's runner by this token."""
        for arms in (["ideal"], [arm.name for arm in si.ARMS]):
            self.assertIn(
                "sim/supply-impedance-sensitivity/run_supply_impedance.py",
                si.invocation_line(arms, False, ""),
            )


class TestCornerSubsetSelection(unittest.TestCase):
    """`--corner-points` exists so the ratified grid can be advanced in
    session-sized pieces (issue #409 item 1). The one property that makes that
    safe is that it can only ever NARROW the ratified set."""

    def test_no_selection_is_the_baseline_corner(self) -> None:
        self.assertEqual(si.resolve_grid(False, []), [si.BASELINE_CORNER])

    def test_corners_is_the_whole_ratified_grid(self) -> None:
        grid = si.resolve_grid(True, [])
        self.assertEqual(len(grid), 9)
        self.assertEqual(grid, si.full_ratified_grid())

    def test_a_named_subset_is_a_subset_of_the_ratified_grid(self) -> None:
        grid = si.resolve_grid(False, ["ss_27c_1.80v", "tt_27c_1.80v"])
        self.assertEqual(len(grid), 2)
        for point in grid:
            self.assertIn(point, si.full_ratified_grid())

    def test_the_subset_is_returned_in_ratified_grid_order(self) -> None:
        """Not the order the caller typed: the footer, the record's tables and
        the grid itself must agree on an ordering, and the ratified grid owns
        it."""
        typed_backwards = si.resolve_grid(False, ["ff_27c_1.80v", "tt_27c_1.80v"])
        ratified_order = [
            point
            for point in si.full_ratified_grid()
            if si.corners_mod.corner_id(*point) in {"ff_27c_1.80v", "tt_27c_1.80v"}
        ]
        self.assertEqual(typed_backwards, ratified_order)

    def test_a_point_outside_the_ratified_grid_is_refused(self) -> None:
        """The flag narrows the ratified corner set; it may not invent a corner
        the spec never ratified -- that would be a testbench choosing its own
        PVT points, which `sim/README.md` does not allow."""
        with self.assertRaises(ValueError) as caught:
            si.resolve_grid(False, ["tt_27c_1.80v", "tt_85c_1.80v"])
        self.assertIn("tt_85c_1.80v", str(caught.exception))

    def test_every_documented_subset_point_exists(self) -> None:
        """Guards the README's own corner-ids against a grid change."""
        ids = {si.corners_mod.corner_id(*point) for point in si.full_ratified_grid()}
        for cid in ("tt_27c_1.80v", "ss_27c_1.80v"):
            self.assertIn(cid, ids)


class TestDeckAssemblyUsesTheCommittedStimulus(unittest.TestCase):
    """The campaign's whole value is that it changes the supply network and
    nothing else, so the fragment's own cards must survive into the deck."""

    def test_arm_table_renders_a_row_per_arm(self) -> None:
        table = "\n".join(si.arm_table_lines(list(si.ARMS)))
        for arm in si.ARMS:
            self.assertIn(f"| `{arm.name}` |", table)

    def test_arm_table_states_no_bond_for_the_null_option(self) -> None:
        table = "\n".join(si.arm_table_lines([si.ARMS_BY_NAME["no-gnd-pad"]]))
        self.assertIn("no bond", table)

    def test_every_arm_is_reachable_from_the_cli_default(self) -> None:
        self.assertEqual(sorted(si.ARMS_BY_NAME), sorted(arm.name for arm in si.ARMS))
        self.assertIn(si.CONTROL_ARM, si.ARMS_BY_NAME)


class TestBoundedRLSweep(unittest.TestCase):
    """`--sweep` (issue #409 item 3; DR-015's own "No `R`/`L` sweep" open item).

    A sweep is only a sweep of *one* element per axis, and it is only a walk
    around the campaign's assumption point if its centre really is that point.
    Both are properties a later edit could break while every run still
    completed and still wrote a plausible record, so both are pinned here.
    """

    def test_the_anchor_point_is_the_committed_as_built_arm(self) -> None:
        """The `1x` / DR-015-`R_SUBX` grid point must be, card for card, the
        `package` arm the campaign already recorded -- otherwise the grid is a
        box around nothing in particular."""
        self.assertTrue(si.sweep_anchor_matches_base_arm())
        anchor = [
            c
            for c in si.arm_network_lines(si.sweep_arm(1.0, si.R_SUBX_OHM))
            if c and not c.startswith("*")
        ]
        base = [
            c
            for c in si.arm_network_lines(si.ARMS_BY_NAME[si.SWEEP_BASE_ARM])
            if c and not c.startswith("*")
        ]
        self.assertEqual(anchor, base)

    def test_the_zero_inductance_point_is_the_committed_r_only_arm(self) -> None:
        """The other tie to the existing record: the bottom of the `L` ladder
        is electrically `package-r-only`, the arm that record's bond-inductance
        ablation is taken against."""
        zero = [
            c
            for c in si.arm_network_lines(si.sweep_arm(0.0, si.R_SUBX_OHM))
            if c and not c.startswith("*")
        ]
        r_only = [
            c
            for c in si.arm_network_lines(si.ARMS_BY_NAME["package-r-only"])
            if c and not c.startswith("*")
        ]
        self.assertEqual(zero, r_only)

    def test_a_row_of_the_grid_moves_only_the_inductance(self) -> None:
        """DR-015 item 5: an effect may be attributed to an element only by a
        difference that moves that element and nothing else."""
        for rsubx in si.SWEEP_RSUBX_OHM:
            arms = [si.sweep_arm(m, rsubx) for m in si.SWEEP_L_MULTIPLIERS]
            for arm in arms[1:]:
                self.assertEqual(set(arm.bonds), set(arms[0].bonds))
                self.assertEqual(arm.substrate, arms[0].substrate)
                for terminal in arm.bonds:
                    self.assertAlmostEqual(
                        arm.bonds[terminal].r_ohm, arms[0].bonds[terminal].r_ohm, places=12
                    )
            inductances = [a.bonds["GND"].l_h for a in arms]
            self.assertEqual(inductances, sorted(inductances))
            self.assertEqual(len(set(inductances)), len(inductances))

    def test_a_column_of_the_grid_moves_only_the_substrate_link(self) -> None:
        for mult in si.SWEEP_L_MULTIPLIERS:
            arms = [si.sweep_arm(mult, r) for r in si.SWEEP_RSUBX_OHM]
            for arm in arms[1:]:
                self.assertEqual(arm.bonds, arms[0].bonds)
            values = [a.substrate[0][3] for a in arms]
            self.assertEqual(values, list(si.SWEEP_RSUBX_OHM))
            self.assertEqual([a.substrate[0][:3] for a in arms], [("RSUBX", si.GND_DIE, "VGND")] * 3)

    def test_the_default_box_brackets_dr015s_assumption_point(self) -> None:
        """A sweep whose box sits entirely to one side of the assumption point
        could not say whether that point is near a threshold."""
        self.assertIn(1.0, si.SWEEP_L_MULTIPLIERS)
        self.assertIn(si.R_SUBX_OHM, si.SWEEP_RSUBX_OHM)
        self.assertLess(min(si.SWEEP_RSUBX_OHM), si.R_SUBX_OHM)
        self.assertGreater(max(si.SWEEP_RSUBX_OHM), si.R_SUBX_OHM)
        self.assertGreater(max(si.SWEEP_L_MULTIPLIERS), 1.0)
        self.assertEqual(min(si.SWEEP_L_MULTIPLIERS), 0.0)

    def test_grid_point_names_are_unique_and_usable_as_filenames(self) -> None:
        """A grid point's name is also its log/deck filename and its log-cache
        key, so a collision would silently overwrite another point's evidence."""
        names = [a.name for a in si.sweep_arms(si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), len(si.SWEEP_L_MULTIPLIERS) * len(si.SWEEP_RSUBX_OHM))
        for name in names:
            self.assertRegex(name, r"^[A-Za-z0-9._-]+$")
            self.assertNotIn(name, si.ARMS_BY_NAME, "a grid point shadows a named arm")

    def test_the_cheap_points_run_first(self) -> None:
        """An inductance-free bond has nothing to ring and finishes quickly, so
        an interrupted sweep should leave the reusable points on disk."""
        arms = si.sweep_arms(si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)
        self.assertEqual(
            [a.bonds["GND"].l_h for a in arms],
            sorted(a.bonds["GND"].l_h for a in arms),
        )

    def test_unphysical_sweep_points_are_refused(self) -> None:
        for l_mult, rsubx in ((-1.0, 30.0), (1.0, 0.0), (1.0, -30.0)):
            with self.subTest(point=(l_mult, rsubx)):
                with self.assertRaises(RuntimeError):
                    si.sweep_arm(l_mult, rsubx)

    def test_a_base_arm_that_is_no_longer_fully_bonded_is_refused(self) -> None:
        """The sweep claims to move around the AS-BUILT network. If the arm it
        sweeps stopped being that, the run must fail rather than silently
        sweep a different topology."""
        original = si.ARMS_BY_NAME[si.SWEEP_BASE_ARM]
        broken = si.Arm(
            name=original.name,
            summary=original.summary,
            bonds={**original.bonds, "GND": si.IDEAL},
            substrate=original.substrate,
        )
        si.ARMS_BY_NAME[si.SWEEP_BASE_ARM] = broken
        try:
            with self.assertRaises(RuntimeError):
                si.sweep_arm(1.0, si.R_SUBX_OHM)
        finally:
            si.ARMS_BY_NAME[si.SWEEP_BASE_ARM] = original

    def test_sweep_footer_states_the_box_only_when_it_departs_from_the_default(self) -> None:
        self.assertEqual(
            si.sweep_invocation_line(si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM, ""),
            f"{si.RUNNER_REL} --sweep --record",
        )
        wider = si.sweep_invocation_line((0.0, 1.0, 3.0, 10.0), si.SWEEP_RSUBX_OHM, "")
        self.assertIn("--sweep-l-mult 0,1,3,10", wider)
        other_r = si.sweep_invocation_line(si.SWEEP_L_MULTIPLIERS, (10.0, 100.0), "")
        self.assertIn("--sweep-rsubx 10,100", other_r)
        self.assertIn(
            "--supersedes 20260101-000000-abcdef0",
            si.sweep_invocation_line(
                si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM, "20260101-000000-abcdef0"
            ),
        )


class TestBoundedNullOptionSubstrateLadder(unittest.TestCase):
    """`--null-sweep` (issue #409; the residual of DR-015's substrate item).

    DR-015 says in prose that the `no-gnd-pad` arm is "*entirely* a function of
    `R_SUB`: with a small `R_SUB` it looks harmless, with a large one it looks
    fatal". This ladder is what measures that, and it is only that measurement
    if two things hold: the swept element really is the analog ground's whole
    return (which is true only on a topology where `GND` has no bond), and the
    ladder's centre really is the point the campaign already recorded. Both are
    properties a later edit could break while every run still completed and
    still wrote a plausible record.
    """

    def test_the_anchor_point_is_the_committed_null_option_arm(self) -> None:
        self.assertTrue(si.null_sweep_anchor_matches_base_arm())
        anchor = [
            c
            for c in si.arm_network_lines(si.null_sweep_arm(si.R_SUBX_OHM))
            if c and not c.startswith("*")
        ]
        base = [
            c
            for c in si.arm_network_lines(si.ARMS_BY_NAME[si.NULL_SWEEP_BASE_ARM])
            if c and not c.startswith("*")
        ]
        self.assertEqual(anchor, base)

    def test_the_swept_element_is_the_analog_grounds_only_return(self) -> None:
        """What makes this ladder a different experiment from `--sweep` rather
        than a re-run of it: on the as-built topology `GND` is bonded and the
        swept resistor is a shunt; here `GND` has no bond at all, so that same
        resistor carries the entire analog-ground return current."""
        for r in si.NULL_SWEEP_RSUBX_OHM:
            arm = si.null_sweep_arm(r)
            self.assertNotIn("GND", arm.bonds, "the null option must leave `GND` unbonded")
            self.assertEqual(len(arm.substrate), 1)
            inst, node_a, node_b, ohm = arm.substrate[0]
            self.assertEqual((inst, node_a, node_b), ("RSUBX", si.GND_DIE, "VGND"))
            self.assertEqual(ohm, r)
        # ... whereas the 2-D sweep's points bond every terminal.
        self.assertEqual(
            set(si.sweep_arm(1.0, si.R_SUBX_OHM).bonds), set(si.TERMINAL_ORDER)
        )

    def test_the_ladder_moves_one_element_and_nothing_else(self) -> None:
        """DR-015 item 5: an effect may be attributed to an element only by a
        difference that moves that element and nothing else."""
        arms = si.null_sweep_arms(si.NULL_SWEEP_RSUBX_OHM)
        for arm in arms[1:]:
            self.assertEqual(arm.bonds, arms[0].bonds)
        values = [a.substrate[0][3] for a in arms]
        self.assertEqual(values, list(si.NULL_SWEEP_RSUBX_OHM))
        self.assertEqual(len(set(values)), len(values))

    def test_the_bonded_terminals_stay_at_dr015s_stated_values(self) -> None:
        """This is a one-axis ladder, not a second 2-D box: the three bonded
        terminals must be DR-015's R+L at every point, so a result here is a
        statement about the substrate return at DR-015's bond."""
        for r in si.NULL_SWEEP_RSUBX_OHM:
            for terminal, bond in si.null_sweep_arm(r).bonds.items():
                with self.subTest(r=r, terminal=terminal):
                    self.assertAlmostEqual(bond.r_ohm, si.PACKAGE_R_OHM, places=12)
                    self.assertAlmostEqual(bond.l_h, si.PACKAGE_L_H, places=15)

    def test_the_default_ladder_brackets_dr015s_assumption_point(self) -> None:
        """A ladder sitting entirely to one side of the assumption point could
        not say whether that point is near a threshold -- which is the whole
        question DR-015's 'harmless ... fatal' sentence poses."""
        self.assertIn(si.R_SUBX_OHM, si.NULL_SWEEP_RSUBX_OHM)
        self.assertLess(min(si.NULL_SWEEP_RSUBX_OHM), si.R_SUBX_OHM)
        self.assertGreater(max(si.NULL_SWEEP_RSUBX_OHM), si.R_SUBX_OHM)

    def test_ladder_point_names_are_unique_and_do_not_collide_with_the_2d_box(self) -> None:
        """A point's name is also its log/deck filename and its log-cache key,
        so a collision with a named arm or with a `--sweep` grid point would
        silently overwrite another run's evidence."""
        names = [a.name for a in si.null_sweep_arms(si.NULL_SWEEP_RSUBX_OHM)]
        self.assertEqual(len(names), len(set(names)))
        box = {a.name for a in si.sweep_arms(si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)}
        for name in names:
            self.assertRegex(name, r"^[A-Za-z0-9._-]+$")
            self.assertNotIn(name, si.ARMS_BY_NAME, "a ladder point shadows a named arm")
            self.assertNotIn(name, box, "a ladder point collides with a --sweep grid point")

    def test_unphysical_ladder_points_are_refused(self) -> None:
        for r in (0.0, -30.0):
            with self.subTest(r=r):
                with self.assertRaises(RuntimeError):
                    si.null_sweep_arm(r)

    def test_a_base_arm_that_regained_a_ground_bond_is_refused(self) -> None:
        """If the arm this ladder sweeps stopped being DR-012's rejected null
        option, the run must fail rather than silently sweep a shunt and report
        it as a return."""
        original = si.ARMS_BY_NAME[si.NULL_SWEEP_BASE_ARM]
        broken = si.Arm(
            name=original.name,
            summary=original.summary,
            bonds={**original.bonds, "GND": si.Bond(si.PACKAGE_R_OHM, si.PACKAGE_L_H)},
            substrate=original.substrate,
        )
        si.ARMS_BY_NAME[si.NULL_SWEEP_BASE_ARM] = broken
        try:
            with self.assertRaises(RuntimeError):
                si.null_sweep_arm(si.R_SUBX_OHM)
        finally:
            si.ARMS_BY_NAME[si.NULL_SWEEP_BASE_ARM] = original

    def test_footer_states_the_ladder_only_when_it_departs_from_the_default(self) -> None:
        self.assertEqual(
            si.null_sweep_invocation_line(si.NULL_SWEEP_RSUBX_OHM, ""),
            f"{si.RUNNER_REL} --null-sweep --record",
        )
        self.assertIn(
            "--null-sweep-rsub 1,10,100",
            si.null_sweep_invocation_line((1.0, 10.0, 100.0), ""),
        )
        self.assertIn(
            "--supersedes 20260101-000000-abcdef0",
            si.null_sweep_invocation_line(
                si.NULL_SWEEP_RSUBX_OHM, "20260101-000000-abcdef0"
            ),
        )


class TestNullOptionLadderFindings(unittest.TestCase):
    """The sentences the null-option record states about magnitudes. A ladder
    that reported "no code moved" while one had -- or that located a threshold
    at the wrong rung -- would be a wrong claim in an append-only record."""

    def _point(self, rsub: float, gnd_pp: float, codes: list[int]) -> dict:
        return {
            "arm": si.null_sweep_arm_name(rsub),
            "corner_id": "tt_27c_1.80v",
            "conversions": [
                {"conversion": i + 1, "fraction": f, "code": c}
                for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, codes))
            ],
            "extras": {"gnd_die_pp": gnd_pp},
            "missing": [],
        }

    def _ladder(self, mover: float | None) -> tuple[list[dict], dict]:
        base = [214, 383, 511, 641, 1023]
        control = self._point(0.0, 0.0, base)
        control["arm"] = si.CONTROL_ARM
        points = [control]
        for r in si.NULL_SWEEP_RSUBX_OHM:
            codes = list(base)
            if mover is not None and r >= mover:
                codes[2] += 3
            points.append(self._point(r, 0.001 * r, codes))
        return points, control

    def test_a_bounded_null_is_stated_as_bounded(self) -> None:
        points, control = self._ladder(None)
        text = "\n".join(
            si.null_sweep_findings_lines(points, control, si.NULL_SWEEP_RSUBX_OHM)
        )
        self.assertIn("bounded null result", text)
        self.assertIn("0 LSB", text)
        self.assertIn("outside** this ladder", text)
        # A null on the CODE row must not be reported as "the pad does not matter".
        self.assertIn("NOT a finding that the pad does not matter", text)

    def test_a_threshold_inside_the_ladder_is_located(self) -> None:
        points, control = self._ladder(300.0)
        text = "\n".join(
            si.null_sweep_findings_lines(points, control, si.NULL_SWEEP_RSUBX_OHM)
        )
        self.assertIn("moves inside this ladder", text)
        self.assertIn("**300 Ohm**", text)
        self.assertIn("3 LSB", text)
        self.assertIn("1 of 3 points", text)

    def test_the_sensitivity_dr015_asserted_is_reported_as_a_measured_ratio(self) -> None:
        """The one number this record exists to produce."""
        points, control = self._ladder(None)
        text = "\n".join(
            si.null_sweep_findings_lines(points, control, si.NULL_SWEEP_RSUBX_OHM)
        )
        self.assertIn("How sensitive the rejected option actually is", text)
        self.assertIn("100x change", text)  # 3 Ohm -> 300 Ohm
        self.assertIn("100.00x", text)  # the excursion ratio of this fixture
        self.assertIn("argument from one point", text)

    def test_the_ladder_is_anchored_to_the_committed_arm_record(self) -> None:
        points, control = self._ladder(None)
        lines = si.null_sweep_findings_lines(points, control, si.NULL_SWEEP_RSUBX_OHM)
        self.assertIn("anchored to the committed ground-pad ablation", lines[0])
        self.assertIn("card for card", lines[0])

    def test_the_worst_excursion_is_converted_to_lsb(self) -> None:
        points, control = self._ladder(None)
        text = "\n".join(
            si.null_sweep_findings_lines(points, control, si.NULL_SWEEP_RSUBX_OHM)
        )
        self.assertIn("Worst die-side analog-ground excursion on the ladder", text)
        self.assertIn("LSB at the nominal supply", text)
        self.assertIn("upper bound rather than a prediction", text)


class TestSweepFindings(unittest.TestCase):
    """The sentences the sweep record states about magnitudes. A sweep that
    reported "no code moved" while one had -- or a threshold at the wrong
    point -- would be a wrong claim in an append-only record."""

    def _point(self, l_mult: float, rsubx: float, gnd_pp: float, codes: list[int]) -> dict:
        return {
            "arm": si.sweep_arm_name(l_mult, rsubx),
            "corner_id": "tt_27c_1.80v",
            "conversions": [
                {"conversion": i + 1, "fraction": f, "code": c}
                for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, codes))
            ],
            "extras": {"gnd_die_pp": gnd_pp},
            "missing": [],
        }

    def _grid(self, mover: tuple[float, float] | None) -> tuple[list[dict], dict]:
        base = [214, 383, 511, 641, 1023]
        control = self._point(0.0, 0.0, 0.0, base)
        control["arm"] = si.CONTROL_ARM
        points = [control]
        for m in si.SWEEP_L_MULTIPLIERS:
            for r in si.SWEEP_RSUBX_OHM:
                codes = list(base)
                if mover is not None and (m, r) >= mover:
                    codes[2] += 4
                points.append(self._point(m, r, 0.001 + m * 0.037, codes))
        return points, control

    def test_a_bounded_null_is_stated_as_bounded(self) -> None:
        points, control = self._grid(None)
        text = "\n".join(
            si.sweep_findings_lines(points, control, si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)
        )
        self.assertIn("bounded null result", text)
        self.assertIn("0 LSB", text)
        self.assertIn("outside the box", text)

    def test_a_threshold_inside_the_box_is_located(self) -> None:
        points, control = self._grid((10.0, 30.0))
        text = "\n".join(
            si.sweep_findings_lines(points, control, si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)
        )
        self.assertIn("moves inside this box", text)
        self.assertIn("`L = 10x`, `R_SUBX = 30 Ohm`", text)
        self.assertIn("4 LSB", text)
        self.assertIn("2 of 9 grid points", text)

    def test_each_axis_is_read_one_element_at_a_time(self) -> None:
        points, control = self._grid(None)
        lines = si.sweep_findings_lines(
            points, control, si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM
        )
        rows = [ln for ln in lines if ln.startswith("- **Bond inductance at")]
        cols = [ln for ln in lines if ln.startswith("- **Substrate link at")]
        self.assertEqual(len(rows), len(si.SWEEP_RSUBX_OHM))
        self.assertEqual(len(cols), len(si.SWEEP_L_MULTIPLIERS))
        for line in rows + cols:
            self.assertIn("Only", line)

    def test_the_worst_excursion_is_converted_to_lsb(self) -> None:
        points, control = self._grid(None)
        text = "\n".join(
            si.sweep_findings_lines(points, control, si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)
        )
        self.assertIn("Worst die-side analog-ground excursion in the box", text)
        self.assertIn("LSB at the nominal supply", text)
        self.assertIn("upper bound rather than a prediction", text)


class TestSweepRecordIsNotTheCampaignsCurrentRecord(unittest.TestCase):
    """The sweep writes its own record and must NOT move `records/LATEST`.

    That pointer names the record the campaign's cited claim rests on -- the
    arm comparison DR-012 and `docs/chipalooza/challenge-4-proposal.md`'s Power
    row cite by record-id. The sweep supersedes none of it: it asks a different
    question about the same DUT. Moving the pointer would make a citation of
    the still-current arm-comparison record read as *stale* to this repo's
    citation gate while nothing had actually superseded it -- the same
    disposition, for the same reason, as `run_conversion.py`'s diagnostic
    record writers.
    """

    def _write(self) -> tuple[Path, Path]:
        import shutil
        import tempfile

        from harness import evidence

        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        real_dir, real_resolve = si.EXPERIMENT_DIR, evidence.resolve_provenance

        def fake_resolve(experiment_dir: Path, netlist_text: str):
            (experiment_dir / "netlist-snapshots").mkdir(parents=True, exist_ok=True)
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC",
                record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64,
                pdk_line="sky130A @ testing",
                ng_version="ngspice-46",
            )

        base = [214, 383, 511, 641, 1023]

        def point(arm: str, gnd_pp: float) -> dict:
            return {
                "arm": arm,
                "corner_id": "tt_27c_1.80v",
                "process_corner": "tt",
                "temp_c": 27.0,
                "supply_v": 1.8,
                "point_id": f"{arm}@tt_27c_1.80v",
                "conversions": [
                    {"conversion": i + 1, "fraction": f, "code": c}
                    for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, base))
                ],
                "currents": {"i_vdd": 1e-6, "i_vpwr": 2e-6},
                "power_w": 27.9e-6,
                "extras": {"gnd_die_pp": gnd_pp, "i_gnda": 2.2e-6},
                "missing": [],
                "log_text": "LOG\n",
                "deck_text": "* deck\n",
                "wall_s": 600.0,
                "reused": False,
            }

        points = [point(si.CONTROL_ARM, 0.0)] + [
            point(arm.name, 0.037)
            for arm in si.sweep_arms(si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM)
        ]
        try:
            si.EXPERIMENT_DIR = tmp_dir
            evidence.resolve_provenance = fake_resolve
            path = si.write_sweep_record(
                points, "* netlist\n", si.SWEEP_L_MULTIPLIERS, si.SWEEP_RSUBX_OHM
            )
        finally:
            si.EXPERIMENT_DIR = real_dir
            evidence.resolve_provenance = real_resolve
        return path, tmp_dir

    def test_the_latest_pointer_is_not_moved(self) -> None:
        _path, tmp_dir = self._write()
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())

    def test_the_record_says_it_supersedes_nothing_and_why(self) -> None:
        path, _tmp = self._write()
        text = path.read_text()
        self.assertIn("- **Supersedes**: (none)", text)
        self.assertIn("does not supersede the campaign's arm-comparison record", text)

    def test_the_record_carries_both_matrices_and_its_scope_caveats(self) -> None:
        path, _tmp = self._write()
        text = path.read_text()
        self.assertIn("## Die-side analog-ground excursion over the swept box", text)
        self.assertIn("## Worst mid-scale |delta code| vs the control, over the swept box", text)
        self.assertIn("## What this sweep does not cover", text)
        self.assertIn("## Subset-corner justification", text)
        # The two elements the sweep does NOT move must be named, not implied.
        self.assertIn("The substrate-only RETURN is not swept here", text)
        self.assertIn("`--null-sweep`", text)
        self.assertIn("No extracted substrate network", text)
        self.assertIn(
            "Written by `sim/supply-impedance-sensitivity/run_supply_impedance.py "
            "--sweep --record`",
            text,
        )

    def test_every_run_appears_with_its_raw_log_and_deck(self) -> None:
        _path, tmp_dir = self._write()
        dumped = sorted(p.name for p in (tmp_dir / "corners" / "REC").iterdir())
        expected = len(si.SWEEP_L_MULTIPLIERS) * len(si.SWEEP_RSUBX_OHM) + 1
        self.assertEqual(len(dumped), 2 * expected, dumped)

    def test_the_citation_gate_can_recognise_this_record_as_a_sweep_record(self) -> None:
        """The pointer this record must NOT move is why check 32 exists.

        `docs/chipalooza/challenge-4-proposal.md` §7 bounds DR-012's
        retirement on this box being unwalked, and check 32 of the citation
        gate is what re-derives that from the tree. Because this writer
        deliberately leaves `records/LATEST` alone, the ONLY thing that tells
        the gate a sweep record has arrived is this record's own `- **Grid**:`
        header line -- so the gate's parse of it is asserted here, against
        what this writer actually emits, rather than against a fixture in the
        gate's own test file. A writer that reworded that line would otherwise
        make check 32 silently unable to see the very event it grades.
        """
        sys.path.insert(0, str(REPO_ROOT / "docs" / "chipalooza"))
        import check_proposal_citations as gate  # noqa: PLC0415

        path, _tmp = self._write()
        grid = gate.SWEEP_RECORD_GRID_RE.search(path.read_text())
        self.assertIsNotNone(
            grid,
            "the citation gate cannot identify this record as a sweep record -- "
            "check 32 would not fire on the day the box is walked",
        )
        self.assertEqual(
            int(grid.group("points")),
            len(si.SWEEP_L_MULTIPLIERS) * len(si.SWEEP_RSUBX_OHM),
        )


class TestCornerSliceRecordDoesNotMoveThePointer(unittest.TestCase):
    """A corner-axis record mints and does not repoint (issue #409 item 1).

    `records/LATEST` names the record this campaign's cited claim rests on --
    the baseline-corner arm comparison DR-012 and
    `docs/chipalooza/challenge-4-proposal.md`'s Power row cite by id -- and
    moving it is exactly what makes a citing document stale to this repo's
    citation gate. A corner slice supersedes none of that: it asks whether the
    corner axis moves the answer, on a REDUCED arm set whose dropped arms are
    where the bond-inductance ablation and the substrate arm live. Same
    disposition as the sweep and the null-option ladder, and asserted here so
    a later edit cannot quietly restore the repoint.
    """

    def _write(self, corner_ids: list[str]) -> tuple[Path, Path]:
        import shutil
        import tempfile

        from harness import evidence

        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        real_dir, real_resolve = si.EXPERIMENT_DIR, evidence.resolve_provenance

        def fake_resolve(experiment_dir: Path, netlist_text: str):
            (experiment_dir / "netlist-snapshots").mkdir(parents=True, exist_ok=True)
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC",
                record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64,
                pdk_line="sky130A @ testing",
                ng_version="ngspice-46",
            )

        base = [214, 383, 511, 641, 1023]

        def point(arm: str, cid: str, gnd_pp: float) -> dict:
            process, temp, supply = next(
                p for p in si.full_ratified_grid() if si.corners_mod.corner_id(*p) == cid
            )
            return {
                "arm": arm,
                "corner_id": cid,
                "process_corner": process,
                "temp_c": temp,
                "supply_v": supply,
                "point_id": f"{arm}@{cid}",
                "conversions": [
                    {"conversion": i + 1, "fraction": f, "code": c}
                    for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, base))
                ],
                "currents": {"i_vdd": 1e-6, "i_vpwr": 2e-6},
                "power_w": 27.9e-6,
                "extras": {"gnd_die_pp": gnd_pp, "i_gnda": 2.2e-6},
                "missing": [],
                "log_text": "LOG\n",
                "deck_text": "* deck\n",
                "wall_s": 600.0,
                "reused": False,
            }

        points = [
            point(arm, cid, 0.0 if arm == si.CONTROL_ARM else 0.037)
            for arm in ("ideal", "package")
            for cid in corner_ids
        ]
        try:
            si.EXPERIMENT_DIR = tmp_dir
            evidence.resolve_provenance = fake_resolve
            path = si.write_record(
                points,
                "* netlist\n",
                False,
                ["ideal", "package"],
                "",
                corner_ids if corner_ids != ["tt_27c_1.80v"] else [],
            )
        finally:
            si.EXPERIMENT_DIR = real_dir
            evidence.resolve_provenance = real_resolve
        return path, tmp_dir

    def test_a_corner_slice_leaves_the_pointer_alone(self) -> None:
        _path, tmp_dir = self._write(["tt_27c_1.80v", "ss_27c_1.80v"])
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())

    def test_a_baseline_corner_record_still_moves_the_pointer(self) -> None:
        """The disposition is about the CORNER AXIS, not about arm subsets --
        the two committed baseline-corner records both ran an arm subset and
        both moved the pointer, and that behaviour is unchanged."""
        _path, tmp_dir = self._write(["tt_27c_1.80v"])
        self.assertEqual((tmp_dir / "records" / "LATEST").read_text().strip(), "REC.md")

    def test_the_slice_record_states_its_subset_justification(self) -> None:
        path, _tmp = self._write(["tt_27c_1.80v", "ss_27c_1.80v"])
        text = path.read_text()
        self.assertIn("## Subset-corner justification", text)
        self.assertIn("2 point(s) of the ratified corner set", text)
        self.assertIn("`tt_27c_1.80v`", text)
        self.assertIn("`ss_27c_1.80v`", text)
        self.assertIn(
            "Written by `sim/supply-impedance-sensitivity/run_supply_impedance.py "
            "--arms ideal,package --corner-points tt_27c_1.80v,ss_27c_1.80v --record`",
            text,
        )

    def test_the_retired_host_policy_reason_is_named_not_reused(self) -> None:
        """The reason this record does NOT give is load-bearing: the earlier
        wording ("this host may not run a multi-corner grid at all") was
        re-checked and retired, and a record that silently swapped its
        justification would be indistinguishable from one that never looked."""
        path, _tmp = self._write(["tt_27c_1.80v", "ss_27c_1.80v"])
        text = path.read_text()
        self.assertIn("What is NOT a constraint, and used to be stated as one", text)
        self.assertNotIn("operating rules forbid running a", text)
        self.assertIn("long-running-compute.md", text)


class TestNullOptionRecordIsNotTheCampaignsCurrentRecord(unittest.TestCase):
    """The null-option ladder writes its own record and must NOT move
    `records/LATEST`, for the same reason the 2-D sweep must not: that pointer
    names this flow's newest ARM-COMPARISON record, which is what the citation
    gate's arm census (check 31) reads. This record carries no arm census to
    offer -- it is one topology at three magnitudes -- and it supersedes
    nothing, so moving the pointer onto it would make a citation of a record
    nothing had superseded read as stale.

    It must also stay invisible to the *sweep* census (check 32), which counts
    grid points of the 2-D box: a ladder record that matched that parse would
    inflate a census of a box it is not a point of.
    """

    def _write(self) -> tuple[Path, Path]:
        import shutil
        import tempfile

        from harness import evidence

        tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        real_dir, real_resolve = si.EXPERIMENT_DIR, evidence.resolve_provenance

        def fake_resolve(experiment_dir: Path, netlist_text: str):
            (experiment_dir / "netlist-snapshots").mkdir(parents=True, exist_ok=True)
            (experiment_dir / "records").mkdir(parents=True, exist_ok=True)
            return evidence.ProvenanceInfo(
                record_id="REC",
                record_path=experiment_dir / "records" / "REC.md",
                netlist_sha="0" * 64,
                pdk_line="sky130A @ testing",
                ng_version="ngspice-46",
            )

        base = [214, 383, 511, 641, 1023]

        def point(arm: str, gnd_pp: float, bonded_gnd: bool) -> dict:
            return {
                "arm": arm,
                "corner_id": "tt_27c_1.80v",
                "process_corner": "tt",
                "temp_c": 27.0,
                "supply_v": 1.8,
                "point_id": f"{arm}@tt_27c_1.80v",
                "conversions": [
                    {"conversion": i + 1, "fraction": f, "code": c}
                    for i, (f, c) in enumerate(zip(si.tb.INPUT_FRACTIONS, base))
                ],
                "currents": {"i_vdd": 1e-6, "i_vpwr": 2e-6},
                "power_w": 27.3e-6,
                "extras": (
                    {"gnd_die_pp": gnd_pp, "vgnd_die_pp": 0.004, "i_gnda": 2.2e-6}
                    if bonded_gnd
                    else {"gnd_die_pp": gnd_pp, "vgnd_die_pp": 0.004}
                ),
                "missing": [],
                "log_text": "LOG\n",
                "deck_text": "* deck\n",
                "wall_s": 500.0,
                "reused": False,
            }

        points = [point(si.CONTROL_ARM, 0.0, True)] + [
            point(arm.name, 0.065, False) for arm in si.null_sweep_arms(si.NULL_SWEEP_RSUBX_OHM)
        ]
        try:
            si.EXPERIMENT_DIR = tmp_dir
            evidence.resolve_provenance = fake_resolve
            path = si.write_null_sweep_record(points, "* netlist\n", si.NULL_SWEEP_RSUBX_OHM)
        finally:
            si.EXPERIMENT_DIR = real_dir
            evidence.resolve_provenance = real_resolve
        return path, tmp_dir

    def test_the_latest_pointer_is_not_moved(self) -> None:
        _path, tmp_dir = self._write()
        self.assertFalse((tmp_dir / "records" / "LATEST").exists())

    def test_the_record_says_it_supersedes_nothing_and_why(self) -> None:
        path, _tmp = self._write()
        text = path.read_text()
        self.assertIn("- **Supersedes**: (none)", text)
        self.assertIn("It supersedes nothing, and is not a re-run of the 2-D sweep", text)

    def test_the_record_names_which_stand_in_it_moved(self) -> None:
        """The naming precision this record exists to keep: DR-015 calls the
        rejected arm a function of `R_SUB`, while the deck instance that plays
        that role in it is named `RSUBX`. A record that swept "the substrate
        resistance" without saying which element moved would be unreadable
        against the 2-D box, which moved an element of the same name in a
        topology where it does something else."""
        path, _tmp = self._write()
        text = path.read_text()
        self.assertIn("## Which stand-in this ladder moves, and what it is called", text)
        self.assertIn("one resistor", text)
        self.assertIn("`R_SUB`'s role", text)

    def test_the_record_carries_its_scope_caveats(self) -> None:
        path, _tmp = self._write()
        text = path.read_text()
        self.assertIn("## Die-side analog-ground excursion along the ladder", text)
        self.assertIn("## What this ladder does not cover", text)
        self.assertIn("## Subset-corner justification", text)
        self.assertIn("No extracted substrate network", text)
        self.assertIn("The bond inductance is not crossed with this axis", text)
        self.assertIn(
            "Written by `sim/supply-impedance-sensitivity/run_supply_impedance.py "
            "--null-sweep --record`",
            text,
        )

    def test_every_run_appears_with_its_raw_log_and_deck(self) -> None:
        _path, tmp_dir = self._write()
        dumped = sorted(p.name for p in (tmp_dir / "corners" / "REC").iterdir())
        self.assertEqual(len(dumped), 2 * (len(si.NULL_SWEEP_RSUBX_OHM) + 1), dumped)

    def test_the_citation_gates_two_censuses_do_not_see_this_record(self) -> None:
        """Neither the arm census (check 31) nor the sweep census (check 32)
        may count a ladder record: it is not an arm comparison and it is not a
        point of the 2-D box. Both are parsed off a header line this writer
        deliberately spells differently (`- **Ladder**:`), so the parse is
        asserted here against what the writer actually emits."""
        sys.path.insert(0, str(REPO_ROOT / "docs" / "chipalooza"))
        import check_proposal_citations as gate  # noqa: PLC0415

        path, _tmp = self._write()
        text = path.read_text()
        self.assertIsNone(gate.SWEEP_RECORD_GRID_RE.search(text))
        self.assertIsNone(gate.ARM_RECORD_RE.search(text))
        self.assertIn("- **Ladder**:", text)

    def test_the_citation_gates_ladder_census_does_see_this_record(self) -> None:
        """The POSITIVE half of the guard above -- the one check 34 needs.

        The two negatives above are what keep checks 31 and 32 from
        miscounting a ladder record, and that deliberate invisibility is
        precisely why check 34 exists: a ladder record is the union of every
        other check's blind spot, so its own `- **Ladder**:` header is the ONLY
        thing that tells the gate one has arrived. Asserting the negatives
        without the positive leaves the worst outcome reachable -- a writer
        that reworded that header would keep passing the three assertions above
        while silently making check 34 blind to the very event it grades, which
        is the state the gate was in for the four minutes between PR #445 and
        PR #446.

        So the gate's own regex is run against what this writer actually emits,
        rather than against a fixture in the gate's test file -- the same
        cross-file guard `TestSweepRecord` already carries for check 32.

        The RUNG COUNT is asserted too, not merely the match. The header states
        both the rungs and the transient total (`rungs + 1`, the `ideal`
        control), and a gate that read the total would overstate the ladder's
        coverage by exactly one on every record.
        """
        sys.path.insert(0, str(REPO_ROOT / "docs" / "chipalooza"))
        import check_proposal_citations as gate  # noqa: PLC0415

        path, _tmp = self._write()
        ladder = gate.NULL_SWEEP_RECORD_RE.search(path.read_text())
        self.assertIsNotNone(
            ladder,
            "the citation gate cannot identify this record as a ladder record -- "
            "check 34 would not fire on the day the ladder is walked or widened",
        )
        self.assertEqual(int(ladder.group("rungs")), len(si.NULL_SWEEP_RSUBX_OHM))


class TestCostProbe(unittest.TestCase):
    """`--cost-probe` (the price of the sweep box, before it is paid).

    A probe is a *truncated* run of the real deck, which makes it two things at
    once: the only cheap way to know what the box costs and whether its
    off-anchor points converge at all -- and, if anything ever let one reach a
    record, a run whose `.meas` cards never fired masquerading as evidence. So
    the tests below pin the truncation itself and the refusals that keep a
    probe's log out of both the record path and the restart cache.
    """

    def _deck(self, arm_name: str = "package") -> str:
        """A deck-shaped string with exactly the committed fragment's `.tran`."""
        return (
            f"* arm={arm_name}\n"
            ".include foo.spice\n"
            + si.tb.FRAGMENT_PATH.read_text()
            + ".end\n"
        )

    def test_the_truncated_deck_differs_only_in_the_tran_stop_time(self) -> None:
        deck = self._deck()
        sliced = si.truncate_tran(deck, 400.0)
        before = [ln for ln in deck.splitlines() if not ln.startswith(".tran ")]
        after = [ln for ln in sliced.splitlines() if not ln.startswith(".tran ")]
        self.assertEqual(before, after, "a cost probe changed something besides .tran")
        self.assertIn(".tran 0.5n 400n", sliced)

    def test_the_requested_timestep_is_preserved(self) -> None:
        """The probe measures solver work per simulated nanosecond, so changing
        the requested step would change the very thing being priced."""
        step = si.RE_TRAN_CARD.findall(self._deck())[0][0]
        self.assertEqual(si.RE_TRAN_CARD.findall(si.truncate_tran(self._deck(), 400.0))[0][0], step)

    def test_a_probe_must_be_shorter_than_the_run_it_prices(self) -> None:
        stop_ns = si.fragment_tran_stop_ns()
        self.assertIsNotNone(stop_ns)
        for slice_ns in (stop_ns, stop_ns + 1.0, 0.0, -1.0):
            with self.subTest(slice_ns=slice_ns):
                with self.assertRaises(RuntimeError):
                    si.truncate_tran(self._deck(), slice_ns)

    def test_an_ambiguous_deck_is_refused_rather_than_guessed(self) -> None:
        for deck in (self._deck() + ".tran 0.5n 100n\n", "* no tran here\n.end\n"):
            with self.subTest(deck=deck[:20]):
                with self.assertRaises(RuntimeError):
                    si.truncate_tran(deck, 400.0)

    def test_the_fragment_stop_time_is_read_from_the_fragment(self) -> None:
        """Not restated in the runner: a probe's bound must follow the stimulus
        it prices rather than a constant that can drift from it."""
        self.assertAlmostEqual(si.fragment_tran_stop_ns(), 6283.3333, places=3)
        self.assertIn(f"{si.fragment_tran_stop_ns():.4f}n", si.tb.FRAGMENT_PATH.read_text())

    def test_spice_time_values_parse_or_decline(self) -> None:
        self.assertAlmostEqual(si._spice_time_ns("6283.3333n"), 6283.3333, places=4)
        self.assertAlmostEqual(si._spice_time_ns("1u"), 1000.0)
        self.assertAlmostEqual(si._spice_time_ns("1ms"), 1e6)
        self.assertAlmostEqual(si._spice_time_ns("2e-9"), 2.0)
        for bad in ("", "abc", "6283x", "$(pwd)"):
            self.assertIsNone(si._spice_time_ns(bad), bad)

    def test_measurement_failures_are_not_reported_as_solver_trouble(self) -> None:
        """A truncated run misses every `.meas` by construction. Treating that
        as trouble would drown the one signal the probe exists to give."""
        log = (
            "Measurement d9_c1 FAILED\n"
            "MIF-ERROR: no such measurement\n"
            "Total analysis time (seconds) = 12\n"
        )
        self.assertEqual(si.solver_trouble_lines(log), [])

    def test_solver_trouble_is_reported(self) -> None:
        for line in (
            "Warning: Timestep too small; time = 1.2e-09",
            "doAnalyses: TRAN:  Timestep too small",
            "ERROR: singular matrix: check node vdd_board",
            "Fatal error: no convergence in dcop",
        ):
            with self.subTest(line=line):
                self.assertEqual(si.solver_trouble_lines(f"ok\n{line}\nok\n"), [line])

    def test_the_probe_table_ratios_against_the_anchor_point(self) -> None:
        anchor = si.sweep_arm_name(1.0, si.R_SUBX_OHM)
        rows = [
            {"arm": si.CONTROL_ARM, "wall_s": 50.0, "trouble": []},
            {"arm": anchor, "wall_s": 200.0, "trouble": []},
            {"arm": si.sweep_arm_name(10.0, si.R_SUBX_OHM), "wall_s": 100.0, "trouble": []},
        ]
        text = "\n".join(si.cost_probe_lines(rows, 400.0, anchor))
        self.assertIn("NOT A MEASUREMENT", text)
        self.assertIn("| 1.00x |", text)
        self.assertIn("| 0.50x |", text)
        self.assertIn("| 0.25x |", text)
        self.assertIn(f"The anchor point is `{anchor}`", text)

    def test_a_box_without_the_anchor_says_it_cannot_be_projected(self) -> None:
        anchor = si.sweep_arm_name(1.0, si.R_SUBX_OHM)
        rows = [{"arm": si.sweep_arm_name(10.0, 3.0), "wall_s": 100.0, "trouble": []}]
        text = "\n".join(si.cost_probe_lines(rows, 400.0, anchor))
        self.assertIn("does not contain the anchor point", text)
        self.assertIn("| n/a |", text)

    def test_a_troubled_point_is_called_out_separately(self) -> None:
        anchor = si.sweep_arm_name(1.0, si.R_SUBX_OHM)
        rows = [
            {"arm": anchor, "wall_s": 200.0, "trouble": []},
            {
                "arm": si.sweep_arm_name(10.0, 300.0),
                "wall_s": 9.0,
                "trouble": ["Timestep too small"],
            },
        ]
        text = "\n".join(si.cost_probe_lines(rows, 400.0, anchor))
        self.assertIn("The solver had trouble at:", text)
        self.assertIn("NOT known to be runnable over the full stimulus", text)

    def test_the_cli_refuses_every_way_a_probe_could_become_evidence(self) -> None:
        """A probe measures nothing, so `--record` must be impossible; and its
        log shares a point-id with the real run of the same point, so caching it
        would overwrite the log a restarted campaign reuses."""
        import subprocess

        for extra in (
            ["--record"],
            ["--log-cache", "/tmp/should-not-be-used"],
            ["--supersedes", "20260101-000000-abcdef0"],
        ):
            with self.subTest(extra=extra):
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(si.EXPERIMENT_DIR / "run_supply_impedance.py"),
                        "--sweep",
                        "--cost-probe",
                        "400",
                        *extra,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("refused", proc.stderr)

    def test_the_documented_probe_command_is_one_the_runner_accepts(self) -> None:
        """The README quotes a probe invocation and reports numbers from it, so a
        renamed flag must fail here rather than leave a documented command that
        no longer runs."""
        readme = (EXPERIMENT_DIR / "README.md").read_text()
        match = re.search(
            r"run_supply_impedance\.py --sweep --cost-probe (\d+(?:\.\d+)?)", readme
        )
        self.assertIsNotNone(match, "the README documents no --cost-probe invocation")
        slice_ns = float(match.group(1))
        self.assertGreater(slice_ns, 0.0)
        self.assertLess(slice_ns, si.fragment_tran_stop_ns())
        runner_src = (EXPERIMENT_DIR / "run_supply_impedance.py").read_text()
        for flag in ("--cost-probe", "--sweep"):
            self.assertIn(f'"{flag}"', runner_src)

    def test_the_cli_refuses_a_probe_without_a_box_to_price(self) -> None:
        import subprocess

        proc = subprocess.run(
            [
                sys.executable,
                str(si.EXPERIMENT_DIR / "run_supply_impedance.py"),
                "--cost-probe",
                "400",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("--sweep", proc.stderr)


class TestMidscaleBoundaryProbe(unittest.TestCase):
    """The probe that says what this campaign's mid-scale code comparison means
    (issue #455). Every failure mode here also simulates cleanly and writes a
    plausible record, which is why each is pinned:

    1. The perturbations must be supply-UNRELATED. If an input offset silently
       edited the PWL schedule's breakpoint times, or the timestep perturbation
       moved the stop time, the probe would be comparing two different
       experiments and its whole conclusion would be unsupported.
    2. The measurement cards must land before the deck's FINAL `.end`, not
       before the first `.ends` subcircuit terminator -- the failure this
       probe's own development actually hit.
    3. The control variant is mandatory: without it there is no reproduction
       row, and every perturbation row is a delta against nothing.
    """

    FRAGMENT = (
        FULL_CONVERSION_DIR / "testbench" / "full_conversion_tb_fragment.spice"
    )

    def _fake_deck(self) -> str:
        """A deck with the shape the probe's patches depend on: the fragment's
        own input/tran cards, a subcircuit terminator to be left alone, and a
        final `.end`."""
        return (
            "* header\n"
            ".subckt dummy a b\n"
            "R1 a b 1k\n"
            ".ends\n"
            "VINP VINP 0 PWL(0.0000n {vdd_val*0.11} 1950.0000n {vdd_val*0.11})\n"
            "VINN VINN 0 PWL(0.0000n {vdd_val*0.89} 1950.0000n {vdd_val*0.89})\n"
            ".tran 0.5n 6283.3333n\n"
            ".meas tran d9_c3 find v(dout9) at=4075.0000n\n"
            ".end\n"
        )

    def test_probe_cards_land_before_the_final_end_only(self) -> None:
        out = si.insert_before_end(self._fake_deck(), [".meas tran probe find v(x) at=1n"])
        lines = out.splitlines()
        self.assertEqual(lines[-1], ".end")
        self.assertEqual(lines[-2], ".meas tran probe find v(x) at=1n")
        # the subcircuit terminator is untouched, and there is exactly one copy
        # of the inserted card anywhere in the deck
        self.assertEqual(out.count(".ends"), 1)
        self.assertEqual(out.count(".meas tran probe find"), 1)

    def test_a_deck_without_a_final_end_is_refused(self) -> None:
        with self.assertRaises(RuntimeError):
            si.insert_before_end("* header\n.ends\n", [".meas tran x find v(y) at=1n"])

    def test_input_offset_is_differential_and_leaves_the_pwl_schedule_alone(self) -> None:
        deck = self._fake_deck()
        out = si.offset_vin(deck, +0.1, 1.8)
        # the PWL cards keep every breakpoint time and value; only the node they
        # drive is renamed, so the solver sees the same breakpoints
        for pin in ("VINP", "VINN"):
            before = next(l for l in deck.splitlines() if l.startswith(f"{pin} "))
            after = next(l for l in out.splitlines() if l.startswith(f"{pin} "))
            self.assertEqual(after, before.replace(f"{pin} {pin} 0", f"{pin} {pin}_OFS 0", 1))
        one_lsb = 2.0 * 1.8 / 1024
        vp = float(
            next(l for l in out.splitlines() if l.startswith("VOFS_VINP ")).split()[-1]
        )
        vn = float(
            next(l for l in out.splitlines() if l.startswith("VOFS_VINN ")).split()[-1]
        )
        # differential = +0.1 LSB, common mode unchanged
        self.assertAlmostEqual(vp - vn, 0.1 * one_lsb, places=12)
        self.assertAlmostEqual(vp + vn, 0.0, places=15)

    def test_a_zero_offset_is_the_identity(self) -> None:
        deck = self._fake_deck()
        self.assertEqual(si.offset_vin(deck, 0.0, 1.8), deck)

    def test_an_input_offset_refuses_a_deck_whose_source_cards_moved(self) -> None:
        with self.assertRaises(RuntimeError):
            si.offset_vin(self._fake_deck().replace("VINP VINP 0", "VIP VINP 0"), 0.1, 1.8)

    def test_the_timestep_perturbation_moves_the_step_and_nothing_else(self) -> None:
        out = si.retime_tran(self._fake_deck(), 0.25)
        self.assertIn(".tran 0.25n 6283.3333n", out)
        self.assertEqual(
            [l for l in out.splitlines() if not l.startswith(".tran")],
            [l for l in self._fake_deck().splitlines() if not l.startswith(".tran")],
        )

    def test_a_deck_without_a_tran_card_is_refused(self) -> None:
        with self.assertRaises(RuntimeError):
            si.retime_tran("* header\n.end\n", 0.25)

    def test_every_default_variant_names_a_real_arm_and_perturbation(self) -> None:
        for spec in si.MIDSCALE_PROBE_VARIANTS:
            arm, sep, pert = spec.partition(":")
            self.assertTrue(sep, f"{spec!r} is not `arm:perturbation`")
            self.assertIn(arm, si.ARMS_BY_NAME)
            self.assertIn(pert, si.PERTURBATIONS_BY_NAME)

    def test_the_default_variants_carry_the_control_and_the_anomaly_arm(self) -> None:
        self.assertIn(f"{si.CONTROL_ARM}:as-committed", si.MIDSCALE_PROBE_VARIANTS)
        self.assertIn(
            f"{si.MIDSCALE_PROBE_ARM}:as-committed", si.MIDSCALE_PROBE_VARIANTS
        )

    def test_as_committed_perturbs_nothing(self) -> None:
        self.assertTrue(si.AS_COMMITTED.is_as_committed)
        self.assertEqual(
            [p.name for p in si.PERTURBATIONS if p.is_as_committed], ["as-committed"]
        )

    def test_the_probe_traces_the_conversion_the_anomaly_is_on(self) -> None:
        self.assertIn(si.MIDSCALE_CONVERSION, si.MIDSCALE_PROBE_CONVERSIONS)
        self.assertEqual(si.tb.input_fraction(si.MIDSCALE_CONVERSION), 0.0)

    def test_the_probe_corner_is_the_corner_the_anomaly_was_recorded_at(self) -> None:
        self.assertEqual(
            si.corners_mod.corner_id(*si.MIDSCALE_PROBE_CORNER), "fs_27c_1.80v"
        )

    def test_the_reference_record_and_its_logs_are_in_the_repo(self) -> None:
        """The probe reproduces against committed logs, so those logs -- not
        just the record's Markdown tables -- have to be present."""
        rid = si.MIDSCALE_PROBE_REFERENCE_RECORD
        self.assertTrue((EXPERIMENT_DIR / "records" / f"{rid}.md").is_file())
        for arm in (si.CONTROL_ARM, si.MIDSCALE_PROBE_ARM):
            self.assertTrue(
                (EXPERIMENT_DIR / "corners" / rid / f"{arm}__fs_27c_1.80v.log").is_file(),
                f"{arm}@fs_27c_1.80v has no committed log in record {rid}",
            )

    def test_the_anomaly_the_probe_exists_for_is_still_in_that_record(self) -> None:
        """If a later record ever supersedes this one with a reproducible
        number, this test is the tripwire that says the probe's premise moved."""
        control = si.committed_reference_point(
            si.MIDSCALE_PROBE_REFERENCE_RECORD, si.CONTROL_ARM, "fs_27c_1.80v"
        )
        arm = si.committed_reference_point(
            si.MIDSCALE_PROBE_REFERENCE_RECORD, si.MIDSCALE_PROBE_ARM, "fs_27c_1.80v"
        )
        self.assertIsNotNone(control)
        self.assertIsNotNone(arm)
        self.assertEqual(si._conv_code(control, si.MIDSCALE_CONVERSION), 511)
        self.assertEqual(si._conv_code(arm, si.MIDSCALE_CONVERSION), 505)

    def test_the_closest_trial_is_the_one_a_perturbation_could_flip(self) -> None:
        trials = [
            {
                "conversion": si.MIDSCALE_CONVERSION,
                "trials": [
                    {"bit": 9, "missing": False, "v_in_mv": -0.001, "v_in_lsb": -0.0003,
                     "decision": 0, "dout": 0},
                    {"bit": 8, "missing": False, "v_in_mv": 894.2, "v_in_lsb": 254.4,
                     "decision": 1, "dout": 0},
                ],
            }
        ]
        worst = si.closest_trial(trials, si.MIDSCALE_CONVERSION)
        self.assertEqual(worst["bit"], 9)

    def test_dr018_exists_and_states_the_reading_rule(self) -> None:
        dr = REPO_ROOT / "spec" / "decision-records" / "DR-018-midscale-code-metastable-msb.md"
        self.assertTrue(dr.is_file(), "DR-018 is missing")
        text = dr.read_text()
        self.assertIn("#455", text)
        self.assertIn("+0.00", text)
        for other in ("DR-012", "DR-015", "DR-017", "DR-004"):
            self.assertIn(other, text, f"DR-018 does not relate itself to {other}")

    def test_the_sign_bit_really_gates_every_sel_pair(self) -> None:
        """DR-018's "a disturbed sign trial is not a 1-LSB event" argument reads
        the committed netlist, so the netlist is checked here rather than
        trusted: all nine SELn/SELp pairs must be gated by DOUT9/DOUT9N."""
        netlist = (REPO_ROOT / "design" / "sar_adc_top.spice").read_text()
        seln = re.findall(r"^xand_seln(\d) (\S+) (\S+) ", netlist, re.MULTILINE)
        selp = re.findall(r"^xand_selp(\d) (\S+) (\S+) ", netlist, re.MULTILINE)
        self.assertEqual(len(seln), 9)
        self.assertEqual(len(selp), 9)
        for _bit, a, b in seln:
            self.assertIn("DOUT9N", (a, b))
        for _bit, a, b in selp:
            self.assertIn("DOUT9", (a, b))
        # and the offset-binary recode is the same sign bit again
        self.assertEqual(
            len(re.findall(r"^xxor_code\d DOUT\d DOUT9N ", netlist, re.MULTILINE)), 9
        )


class TestDR012OpenItemIsRetired(unittest.TestCase):
    """The acceptance criterion this campaign exists to satisfy: DR-012's
    "the impedance argument is unmeasured" item is retired by citation rather
    than left to be remembered."""

    def test_dr012_cites_this_campaign(self) -> None:
        self.assertTrue(
            "sim/supply-impedance-sensitivity" in DR012.read_text(),
            "DR-012 does not cite sim/supply-impedance-sensitivity/ -- its "
            '"the impedance argument is unmeasured" open item is not retired',
        )

    def test_dr012_cites_a_record_of_this_campaign_by_id(self) -> None:
        """Retired *by citation* means by record-id, not by directory name: a
        reader must be able to open the evidence the item now rests on."""
        text = DR012.read_text()
        ids = {p.stem for p in (EXPERIMENT_DIR / "records").glob("*.md")}
        self.assertTrue(ids, "the campaign has minted no record yet")
        self.assertTrue(
            any(rid in text for rid in ids),
            f"DR-012 cites none of this campaign's records {sorted(ids)}",
        )

    def test_dr012_still_names_the_item_it_retired(self) -> None:
        """Append-only house style: the item is struck through and answered, not
        deleted, so a reader can see what was once open."""
        text = DR012.read_text()
        self.assertIn("The impedance argument is unmeasured", text)
        self.assertIn("#378", text)


if __name__ == "__main__":
    unittest.main()
