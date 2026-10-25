"""Move rarely run functions of a selcc -S listing into section seg_cold (linked
into L2 by capicola_c99/sharc/l1l2.ldf); the rest stays in seg_swco (L1).

  python3 cold_split.py IN.s OUT.s

L2 code runs at about half L1's speed (dt2capicola_memtest: 171 against 85
cycles), so only code run per trig or more rarely belongs here."""
import os
import re
import sys

COLD = {
    # initialisation and setters (the first call, a trig)
    "cc_dline8_init", "cc_sparse_init", "cc_analyzer_init", "cc_granule_init",
    "cc_granule_set_fade", "cc_granule_set_leash", "rec_apply_params", "rec_reset_reader",
    "cc_recorder_init", "cc_recorder_set_leash", "cc_recorder_set_fade",
    # a trig, a spawn, a re-anchor, a rebase's shift
    "cc_recorder_source", "gr_spawn", "gr_reanchor_master", "gr_reanchor_grid", "gr_shift",
    # a splice's start (aligned) and render.asm's rare-event fallback
    "gr_aligned_start", "cc_granule_read",
    # once a block or call, and the C fallback's read (render.asm reads itself)
    "rec_fast_count", "ph_sample",
}
OPTIONAL = set()
# plan B (WSOLA=1 build_gen.sh): its event code to L2, and the analysis chain it
# leaves unused at CAPI on
# plan B (WSOLA=1 build_gen.sh) at blend 0 (GEN_BLEND_ZERO, the default): everything to L2
# but what an ordinary block or the C fallback runs (render.asm cc_bfast serves most
# blocks; gen_wsola the rest); Capicola's keyframe chain never runs
HOT_WSOLA = {"gen_run", "gen_wsola", "b_count", "gen_declick", "gen_phase_out", "gen_zero",
             "cc_recorder_set_blend", "b_floor", "cc_dt2_stretch", "cc_dt2_repitch",
             "diag_account", "diag_frame", "cc_diag_acc", "gen_mark", "gen_fed",
             # a splice's start (its search: the worst frame) and end
             "b_align", "b_step", "b_x", "b_shift", "smooth_step", "cc_bloop"}
WSOLA_HOT_ONLY = bool(os.environ.get("WSOLA")) and bool(os.environ.get("BLEND_ZERO"))
if os.environ.get("WSOLA"):
    WSOLA_COLD = {"b_align", "b_step", "b_begin", "b_x", "b_floor",
                  "cc_recorder_process", "src_process", "src_feed", "src_feed_run", "src_head_max",
                  "rec_rebase", "cc_granule_begin_block", "gr_update_master", "rec_fast_count"}
    COLD |= WSOLA_COLD

src, dst = sys.argv[1], sys.argv[2]
lines = open(src).read().split("\n")
starts = []
for i, l in enumerate(lines):
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\.:$", l)
    if m:
        k = i
        if k > 0 and lines[k - 1].startswith(".GLOBAL ") and lines[k - 1].strip() == f".GLOBAL {m.group(1)}.;":
            k -= 1
        starts.append((k, m.group(1)))
if not starts:
    raise SystemExit("no functions found")
found = {n for _, n in starts}
if "cc_granule_read_inner" in found:   # GEN_DIAG: the timing wrapper stays in L1, the body goes to L2
    COLD = (COLD - {"cc_granule_read"}) | {"cc_granule_read_inner"}
missing = COLD - found - OPTIONAL
if missing:
    raise SystemExit(f"cold functions not in the listing: {sorted(missing)}")
if WSOLA_HOT_ONLY:
    COLD = found - HOT_WSOLA
out = lines[:starts[0][0]]
moved = 0
for j, (k, name) in enumerate(starts):
    end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
    body = lines[k:end]
    if not (body[0].startswith(".GLOBAL ")):   # statics too: the runner's profile needs their names
        body = [f".GLOBAL {name}.;"] + body
    if name in COLD:
        out += [".SECTION/SW seg_cold;"] + body + [".SECTION/SW seg_swco;"]
        moved += len(body)
    else:
        out += body
open(dst, "w").write("\n".join(out))
print(f"cold_split: {len(COLD)} functions, {moved} of {len(lines)} lines into seg_cold")
