# Quality profile implementation details

Approved scope: CAPICOLA-QUALITY-CORRECTION.md, user approval 2026-10-17:
"Okay, yeah, let's go ahead and try to fix this."

Preserve all existing Capicola C sources and their source-hash contracts.
Generate a source overlay for the quality runtime variant: copy C/H files with
relative includes intact; require the exact frozen stretch.c digest; replace
only the three reviewed anchors (splice admission, duration ceiling, phase
increment) and insert a policy header before cap_stretch_tick. Report all
original/modified hashes. Unknown/drifted sources fail before compilation.
This same generator feeds host and target checks. No extra state or allocation
is added to the render path; bank, lane and live-wrapper ABIs stay identical.

Quality policy, in source samples at 48 kHz, positive traversal coordinates:

- Normal splice admission remains absolute sparse-key distance > leash.
- Finite front rescue additionally admits a splice when actual > ideal,
  incoming has >=48 samples remaining and outgoing runway <=960+32*pitch.
  There is no moving writer; this is a selected-region guard, including reverse.
  Loops do not use that rescue rule.
- Normal duration is the exact original local keyframe span. Front rescue uses
  the separate fixed 960-sample budget. For finite playback limit duration to
  0.9*min(outgoing runway,incoming runway); for loops limit to one selected
  region length. Retain the upstream 48-source-sample minimum and safe-zero
  reads at an exhausted boundary. The minimum can exceed the last tiny runway;
  the safety contract is bounded reads/output, not original live-guard parity.
- Increment remains 1/duration; phase step remains increment*pitch, with a
  minimum step 2^-22 to ensure binary32 progress through phase 1. Normal
  interior comparisons never reach this numerical bound. A fade completes in
  at most 4194306 sample calls; test progress directly rather than waiting for
  millions of audio samples in every matrix case.
- Interpolation, reconstruction, gain, entry/exit/loop taper, Q24 transport,
  native callbacks, off behavior and ownership remain unchanged. No detector
  or stereo algorithm is introduced. These remain finite-file adaptations.

Interior acceptance: actual original Granule, matching source keys, no fixed
original guard, 55/220 Hz and three-tone chord, pitch .5/1/2, timing .425,
start96000, source576000, output144000. max1e-4/RMS1e-5. Compare old negative.
For target arithmetic use identical tolerances against a host quality core,
plus original Granule comparison for the primary interior test. Preserve all
failed runs; never loosen tolerances to fit the target.

A new --capicola-quality option on --all-features selects this DSP runtime.
MAIN must reproduce the existing all-feature MAIN exactly. The default DSP
must still reproduce cee93f5173313dabba145c9c0869f4133a700d1f09d8657305c1f3f593faf8d7.
Do not mark the quality image as hardware tested or claim audible superiority.
