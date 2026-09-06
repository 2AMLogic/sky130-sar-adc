#!/usr/bin/env python3
"""Render layout/seln-inverters/reports/<record-id>/record.md from the JSON
envelopes run-flow.sh already wrote into that directory -- mirrors
layout/bin/render-record.py's own "stamp provenance, print verdicts, never
re-derive from exit codes" discipline, simplified for this sub-block's own
(currently: DRC-clean, LVS-blocked-on-a-filed-tool-gap) status.

Prints record.md to stdout; does not itself decide pass/fail -- run-flow.sh
treats a failed place-and-route as the only hard failure (see that script).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _record_common import build_argparser, render_pnr_drc_lvs_record  # noqa: E402


def main() -> int:
    args = build_argparser().parse_args()
    print(render_pnr_drc_lvs_record("SELn inverter bank layout record", args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
