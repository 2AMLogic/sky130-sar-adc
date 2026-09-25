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
            if "--sweep" in cold_tokens:
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
                footer = si.invocation_line(arm_names, "--corners" in cold_tokens, "")
            missing = [tok for tok in footer.split()[1:] if tok not in cold_tokens]
            self.assertEqual(
                missing, [], f"the footer would carry {missing}, absent from {bench['cold_start']}"
            )

    def test_the_runner_path_is_always_present(self) -> None:
        """The spec-coverage check matches the record's runner by this token."""
        for arms in (["ideal"], [arm.name for arm in si.ARMS]):
            self.assertIn(
                "sim/supply-impedance-sensitivity/run_supply_impedance.py",
                si.invocation_line(arms, False, ""),
            )


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
        self.assertIn("`R_SUB`, the substrate-only RETURN, is not swept", text)
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
