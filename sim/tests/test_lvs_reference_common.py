"""PDK-free unit tests for `layout/bin/_lvs_reference_common.py`.

That module is the shared implementation behind the std-cell LVS references
and the schematic/composition parity gates. Its functions are pure text
transforms, so a silent regression (mis-sliced top body, dropped `m=`
scaling, wrong device class) would otherwise only surface in PDK-gated flows.

Pure stdlib -- no PDK, KLayout or `klt`; runs in `npm run test:unit`.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "_lvs_reference_common_under_test",
    REPO_ROOT / "layout" / "bin" / "_lvs_reference_common.py",
)
lrc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lrc)

SPICE = """\
* header
.subckt other a b
XU0 a b inner
.ends
**.subckt sar_adc_top vin vout
XA vin n1 foo
XB n1 vout bar
**.ends
.subckt foo x y
XNOPE x y baz
.ends
"""

VERILOG = """\
module blk (VPWR, VGND, A, Y);
  input A;
  output Y;
  sky130_fd_sc_hd__inv_1 u1 (.A(A), .Y(n1), .VPWR(VPWR));
  sky130_fd_sc_hd__buf_4 u2 (
    .A(n1),
    .X(Y),
    .NC()
  );
endmodule
"""

CDL = """\
* comment
.SUBCKT sky130_fd_sc_hd__inv_1 A VGND VNB VPB VPWR Y
* a comment line
M1000 Y A VGND VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15
+ mult=1
M1001 Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15
.ENDS
.SUBCKT sky130_fd_sc_hd__buf_4 A VGND VNB VPB VPWR X
M1000 mid A VGND VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15 m=4
.ENDS
"""

CELLS = ("sky130_fd_sc_hd__inv_1", "sky130_fd_sc_hd__buf_4")


class TopLevelSubcktBody(unittest.TestCase):
    def test_slices_only_top_region(self):
        body = lrc.top_level_subckt_body(SPICE)
        self.assertIn("XA vin n1 foo", body)
        self.assertIn("XB n1 vout bar", body)
        self.assertNotIn("XU0", body)
        self.assertNotIn("XNOPE", body)
        self.assertNotIn("**.ends", body)

    def test_missing_start_marker(self):
        with self.assertRaises(SystemExit) as cm:
            lrc.top_level_subckt_body(".subckt x\n.ends\n", prog="myprog")
        self.assertTrue(str(cm.exception).startswith("myprog:"))

    def test_missing_end_marker(self):
        with self.assertRaises(SystemExit) as cm:
            lrc.top_level_subckt_body("**.subckt sar_adc_top a\nXA a b c\n", prog="myprog")
        self.assertTrue(str(cm.exception).startswith("myprog:"))


class FileCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, name: str, text: str) -> str:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)


class ParseVerilog(FileCase):
    def test_module_and_instances(self):
        top, insts = lrc.parse_verilog_netlist(self.write("n.v", VERILOG), CELLS)
        self.assertEqual(top, "blk")
        self.assertEqual(
            insts,
            [
                ("u1", "sky130_fd_sc_hd__inv_1", {"A": "A", "Y": "n1", "VPWR": "VPWR"}),
                ("u2", "sky130_fd_sc_hd__buf_4", {"A": "n1", "X": "Y"}),
            ],
        )

    def test_no_module(self):
        with self.assertRaises(SystemExit):
            lrc.parse_verilog_netlist(self.write("n.v", "// nothing\n"), CELLS)


class ExtractCdl(unittest.TestCase):
    def test_ports_and_devices(self):
        pins, devs = lrc._extract_cdl_subckt(CDL, "sky130_fd_sc_hd__inv_1")
        self.assertEqual(pins, ["A", "VGND", "VNB", "VPB", "VPWR", "Y"])
        self.assertEqual(len(devs), 2)
        self.assertEqual(devs[0][:6], ("M1000", "Y", "A", "VGND", "VNB", "sky130_fd_pr__nfet_01v8"))
        self.assertEqual(str(devs[0][6]), "0.65")
        self.assertEqual(devs[0][7], "0.15")

    def test_m_scaling_exact(self):
        _, devs = lrc._extract_cdl_subckt(CDL, "sky130_fd_sc_hd__buf_4")
        self.assertEqual(str(devs[0][6]), "2.60")

    def test_unknown_cell(self):
        with self.assertRaises(SystemExit) as cm:
            lrc._extract_cdl_subckt(CDL, "sky130_fd_sc_hd__nope")
        self.assertIn("nope", str(cm.exception))
        self.assertIn("not found", str(cm.exception))

    def test_generalize_model(self):
        self.assertEqual(lrc._generalize_model("sky130_fd_pr__nfet_01v8"), "nfet")
        self.assertEqual(lrc._generalize_model("sky130_fd_pr__pfet_01v8_hvt"), "pfet")
        with self.assertRaises(SystemExit):
            lrc._generalize_model("resistor")


class EmitReference(FileCase):
    def run_emit(self, top_ports, netlist=VERILOG):
        pdk = self.tmp / "pdk"
        cdl = pdk / "libs.ref" / "sky130_fd_sc_hd" / "cdl" / "sky130_fd_sc_hd.cdl"
        cdl.parent.mkdir(parents=True)
        cdl.write_text(CDL, encoding="utf-8")
        net = self.write("n.v", netlist)
        out = str(self.tmp / "out" / "ref.spice")
        orig = lrc._resolve_pdk_root
        lrc._resolve_pdk_root = lambda: str(pdk)
        self.addCleanup(setattr, lrc, "_resolve_pdk_root", orig)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = lrc.emit_std_cell_lvs_reference(
                net, out, CELLS, top_ports, ["* hdr"], "run-flow.sh"
            )
        return rc, out

    def test_flat_subckt(self):
        ports = ["Y", "A", "VPWR", "VGND"]
        rc, out = self.run_emit(ports)
        self.assertEqual(rc, 0)
        lines = Path(out).read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[0], "* hdr")
        self.assertEqual(lines[1], ".SUBCKT blk Y A VPWR VGND")
        self.assertEqual(lines[-2], ".ENDS blk")
        mcards = [l for l in lines if l.startswith("M")]
        self.assertEqual(len(mcards), 3)
        # nfet/pfet generic classes, default power pin mapping
        self.assertEqual(mcards[0], "Mu1_M1000 n1 A VGND VGND nfet L=0.15U W=0.65U")
        self.assertEqual(mcards[1], "Mu1_M1001 n1 A VPWR VPWR pfet L=0.15U W=1U")
        # m=4 scaling: W = 0.65 * 4; internal node prefixed by instance
        self.assertEqual(mcards[2], "Mu2_M1000 u2_mid n1 VGND VGND nfet L=0.15U W=2.60U")

    def test_missing_netlist(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = lrc.emit_std_cell_lvs_reference(
                str(self.tmp / "none.v"), str(self.tmp / "o.spice"), CELLS, [], [], "rf.sh"
            )
        self.assertEqual(rc, 1)
        self.assertIn("rf.sh", err.getvalue())


if __name__ == "__main__":
    unittest.main()
