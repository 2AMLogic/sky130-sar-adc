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
        """The record's only single-mechanism number depends on this."""
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
        names = [arm.name for arm in si.ARMS]
        table = "\n".join(si.arm_table_lines(names))
        for name in names:
            self.assertIn(f"| `{name}` |", table)

    def test_arm_table_states_no_bond_for_the_null_option(self) -> None:
        table = "\n".join(si.arm_table_lines(["no-gnd-pad"]))
        self.assertIn("no bond", table)

    def test_every_arm_is_reachable_from_the_cli_default(self) -> None:
        self.assertEqual(sorted(si.ARMS_BY_NAME), sorted(arm.name for arm in si.ARMS))
        self.assertIn(si.CONTROL_ARM, si.ARMS_BY_NAME)


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
