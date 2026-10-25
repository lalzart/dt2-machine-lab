#!/bin/sh
GEN_BUILD=${GEN_BUILD:-$(( $(date +%s) & 0x1fffff ))}   # dt2gen.c: a new image starts from fresh DSP state (fix it to reproduce a build)
# build_gen.sh -- Capicola's DT2 generators: build/dt2gen.dxe (digikit's runner), build/gen_host
# (the host replay), build/dt2gen_l1.dxe (the release device build, firmware/build_cap.py
# --release) and build/dt2gen_l1_diag.dxe (the load-figures build, --diag); doscan.py on each.
# The SHARC toolchain (selache: selcc, selas, seld) is outside the repository: SELACHE,
# by default deps/selache (./build.sh's clone), else DT2_WORKSPACE/work/selache
# (DT2_WORKSPACE: the repository's parent folder).
# HOST_ONLY=1: gen_host alone, no SHARC toolchain needed (test/run_tests.py); GEN_OUT_DIR: where to.
set -e
cd "$(dirname "$0")"
WS=${DT2_WORKSPACE:-$(cd ../.. && pwd)}
[ -z "$SELACHE" ] && [ -d "${DT2_DEPS:-../deps}/selache" ] && SELACHE=$(cd "${DT2_DEPS:-../deps}/selache" && pwd)   # ./build.sh's clone
SELACHE=${SELACHE:-$WS/work/selache}; export SELACHE
S=$SELACHE/target/release
O=${GEN_OUT_DIR:-../build}
mkdir -p $O
CLEANFLAG=-DCC_CLEAN
[ -n "$NOCLEAN" ] && CLEANFLAG=   # NOCLEAN=1: the build before CAPI (keyframes only)
BLEND=${BLEND:-0.0}   # CAPI is an on/off switch (dt2entry.asm: off = the stock machines), on = the clean read
[ -n "$BLEND" ] && CLEANFLAG="$CLEANFLAG -DGEN_BLEND_FIXED=${BLEND}f"
[ "$BLEND" = "0.0" ] && CLEANFLAG="$CLEANFLAG -DGEN_BLEND_ZERO" && export BLEND_ZERO=1   # (render.asm cc_bfast: no blend to check; cold_split: only plan B's hot code in L1)
# SECTIONS=1: capload's per-section timing in the device build (about 0.6k cycles a call)
[ -z "$NOWSOLA" ] && CLEANFLAG="$CLEANFLAG -DGEN_WSOLA" && export WSOLA=1   # STRETCH at CAPI on without the analysis (plan B; NOWSOLA=1: plan A, Capicola's keyframes)
[ -n "$XFADE" ] && CLEANFLAG="$CLEANFLAG -DB_XFADE=${XFADE}.0f"   # XFADE=480: plan B's splice crossfade in input samples (default 640)
[ -n "$SLICE" ] && CLEANFLAG="$CLEANFLAG -DGEN_SLICE_MODE=$SLICE -DGEN_SLICE_BARS=${SLICEBARS:-0}"   # SLICE=1|2: a test image without the slots on the screen: GRID and SLICE always ours, REPITCH's (1) or STRETCH's (2) way, SLICE's sample at 2^SLICEBARS bars
C=../capicola_c99/sharc
host() {
  cc -std=c99 -O2 -ffp-contract=off -DCC_F32 -DCC_FASTPATH -DCC_ALIGN=8 -DCC_LINK $CLEANFLAG -DGEN_BUILD=$GEN_BUILD -DGEN_HOST "$@" $C/gen_host.c -lm -o $O/gen_host 2>&1 | grep -E "error" && exit 1 || true
}
if [ -n "$HOST_ONLY" ]; then
  host "$@"; [ -x $O/gen_host ] || exit 1; exit 0
fi
$S/selcc -proc ADSP-21569 -c -char-size-8 -I $SELACHE/libsel/include -I ../capicola_c99 -DCC_F32 -DCC_ASM -DCC_SOURCE_ONLY -DCC_ALIGN=8 -DCC_LINK $CLEANFLAG -DGEN_BUILD=$GEN_BUILD "$@" $C/dt2gen.c -o $O/dt2gen.doj
# selcc accepts a negative array size: dt2gen.c's layout checks (gen_voice_fits) through clang for a 32-bit target
clang --target=i386-none-elf -ffreestanding -fsyntax-only -DGEN_LAYOUT_CHECK -I $SELACHE/libsel/include -I ../capicola_c99 -DCC_F32 -DCC_ASM -DCC_SOURCE_ONLY -DCC_ALIGN=8 -DCC_LINK $CLEANFLAG -DGEN_BUILD=$GEN_BUILD "$@" $C/dt2gen.c
$S/selcc -proc ADSP-21569 -c -char-size-8 -I $SELACHE/libsel/include -DRT_NO_TANF -DRT_MEMSET_WORDS $C/rt.c -o $O/rt.doj
python3 labelcheck.py $C/render.asm $C/dt2entry.asm $C/feed.asm   # (selas accepts a label defined twice)
$S/selas -proc ADSP-21569 $CLEANFLAG ${SECTIONS:+-DGEN_SECTIONS} -o $O/render.doj $C/render.asm
$S/selas -proc ADSP-21569 $CLEANFLAG -o $O/dt2entry.doj $C/dt2entry.asm
$S/selas -proc ADSP-21569 $CLEANFLAG -o $O/feed.doj $C/feed.asm
$S/seld -proc ADSP-21569 -T $C/gen.ldf -o $O/dt2gen.dxe $O/dt2gen.doj $O/rt.doj $O/render.doj $O/dt2entry.doj $O/feed.doj
host
python3 doscan.py $O/dt2gen.dxe | grep -E 'EXITS|loop\(s\)'
# the diag build (build_cap.py --diag): load accounting for dt2probe.py capload
rm -f $O/dt2gen_l1.dxe
# rarely run functions to L2 (cold_split.py, l1l2.ldf)
$S/selcc -proc ADSP-21569 -S -char-size-8 -I $SELACHE/libsel/include -I ../capicola_c99 -DCC_F32 -DCC_ASM -DCC_SOURCE_ONLY -DCC_ALIGN=8 -DCC_LINK $CLEANFLAG -DGEN_BUILD=$GEN_BUILD -DGEN_DIAG ${SECTIONS:+-DGEN_SECTIONS} $C/dt2gen.c -o $O/dt2gen_diag.s
python3 cold_split.py $O/dt2gen_diag.s $O/dt2gen_diag_split.s
$S/selas -proc ADSP-21569 -o $O/dt2gen_diag.doj $O/dt2gen_diag_split.s
rm -f $O/dt2gen_l1_diag.dxe   # a failed link must not leave the previous build for build_cap.py
$S/seld -proc ADSP-21569 -T $C/l1l2.ldf -o $O/dt2gen_l1_diag.dxe $O/dt2gen_diag.doj $O/rt.doj $O/render.doj $O/dt2entry.doj $O/feed.doj
python3 doscan.py $O/dt2gen_l1_diag.dxe | grep -E 'EXITS|loop\(s\)'
# the release build (build_cap.py --release): no GEN_DIAG, and render.asm/dt2entry.asm
# with GEN_NO_DIAG (no load accounting, the stock generators called untimed)
$S/selcc -proc ADSP-21569 -S -char-size-8 -I $SELACHE/libsel/include -I ../capicola_c99 -DCC_F32 -DCC_ASM -DCC_SOURCE_ONLY -DCC_ALIGN=8 -DCC_LINK $CLEANFLAG -DGEN_BUILD=$GEN_BUILD $C/dt2gen.c -o $O/dt2gen_rel.s
python3 cold_split.py $O/dt2gen_rel.s $O/dt2gen_rel_split.s
$S/selas -proc ADSP-21569 -o $O/dt2gen_rel.doj $O/dt2gen_rel_split.s
$S/selas -proc ADSP-21569 $CLEANFLAG -DGEN_NO_DIAG -o $O/render_rel.doj $C/render.asm
$S/selas -proc ADSP-21569 $CLEANFLAG -DGEN_NO_DIAG -o $O/dt2entry_rel.doj $C/dt2entry.asm
$S/seld -proc ADSP-21569 -T $C/l1l2.ldf -o $O/dt2gen_l1.dxe $O/dt2gen_rel.doj $O/rt.doj $O/render_rel.doj $O/dt2entry_rel.doj $O/feed.doj
python3 doscan.py $O/dt2gen_l1.dxe | grep -E 'EXITS|loop\(s\)'
