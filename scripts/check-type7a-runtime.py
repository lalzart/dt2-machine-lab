#!/usr/bin/env python3
# ruff: noqa: E402
"""Execute focused cases natively; baseline is an explicit failed control."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lab.project import ROOT, doctor, require, sha256, write_json

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--baseline", action="store_true")
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored output")
out.mkdir(exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
provenance = doctor()
# lab.runtime installs the tooling path before these imports.
# isort: off
from lab import type7a_cases as cases
from lab.dsp import Dsp
from lab.runtime import LIB, STOCK_BLOB
import sharc_trace as st
import sharc_transpile_run as native
from sharc_disasm import Instruction
# isort: on

rows = []
core = native.NativeCore(native.pack_image(None), str(LIB))
for case in cases.cases():
    template = cases.state(case, st)
    insn = Instruction(0, 6, "7a", case["fields"], kind="confident")
    py = st._execute(cases.state(case, st), insn)[0]
    native.to_native(core, template)
    ok = core.exec_insn(native.pack_insn("7a", 6, "confident", insn.fields))
    result = native.to_python(core, template)
    if a.baseline and insn.fields["cond[4:0]"] not in (31, 23):
        require(not ok and "unsupported Type7a predicate" in core.halt_reason, "Baseline healed")
    else:
        cases.check(case, py, st)
        result.stopped = core.halt_reason if not ok else None
        # The pinned generator reduces dynamic diagnostic strings (formatted
        # wrap/compute errors) to a generic stop, retaining the exact callsite.
        dynamic_reason = case["name"] in ("circular-oversize", "invalid-compute-true")
        cases.check(case, result, st, reason=not dynamic_reason)
        require(ok == (case["stop"] is None), "Unexpected native completion")
        if not ok:
            site = ("sharc_core.compute._compute:339:" if case["name"] == "invalid-compute-true"
                    else "sharc_core.forms_dag._type_7a:")
            require(site in core.halt_reason,
                    f"Wrong native stop {case['name']}: {core.halt_reason}")
    rows.append(dict(name=case["name"], ok=ok, pc=core.pc(), reason=core.halt_reason))

# Actual original firmware bytes, decoded by the native runtime. No fabricated
# instruction blob, instruction replacement, Python fallback or opcode skip.
stock = []
for az in (0, 1):
    dsp = Dsp()
    for name, value in dict(MODE1=0, ASTATX=az, I4=0x84230000, M4=4, L4=0).items():
        dsp.core.set_reg(st.UREG_CODES[name], st.Const(value))
    dsp.core.set_option(native.OPT_STOP_PC, 0x1CBC96)
    dsp.core.fresh_call(0x1CBC93)
    count = dsp.core.run(4)
    pointer = dsp.core.get_reg(st.UREG_CODES["I4"]).value
    require(pointer == 0x84230000 + (16 if az and not a.baseline else 0), "Stock I4")
    require(dsp.core.pc() == (0x1CBC93 if a.baseline else 0x1CBC96), "Stock PC")
    require(count == (0 if a.baseline else 1), "Stock instruction count")
    stock.append(dict(az=az, pointer=pointer, instructions=count, pc=dsp.core.pc(),
                      reason=dsp.core.halt_reason))
write_json(out / "report.json", dict(status="passed", baseline=a.baseline,
           provenance=provenance, library_sha256=sha256(LIB), native_info=core.info(),
           stock_blob_sha256=sha256(STOCK_BLOB), cases=rows, actual_stock_opcode=stock,
           python_fallback=False))
print("PASS", len(rows), "cases and actual stock opcode", flush=True)
