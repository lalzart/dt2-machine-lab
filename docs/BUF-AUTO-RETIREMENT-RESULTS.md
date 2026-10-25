# Automatic cleanup in the BUF experiment

Digitakt II OS 1.16, 2026-10-22. Implementation of the
[bounded lifecycle plan](BUF-AUTO-RETIREMENT-PLAN.md). This is a separate,
opt-in BUF emulator adapter. Existing packaged Flex R5, its Save/Discard and
bank-saving workflow, normal firmware builders and all DSP code are preserved.
No firmware package or hardware transfer is part of this increment.

## What changed

`lab/buf_auto_retirement.py` selects obsolete generations inside the native
GUI loop. Its bounded eight-seat scan skips current logical buffers, frozen
versions, stale epochs, invalid identities and quarantined entries. A rotating
cursor and token-tagged per-seat cooldown let other eligible versions progress
when one still has readers. Time only limits retries; the existing native
CPU/DSP ownership transaction still decides whether storage can be released.
All reader pointers remain under the original playback code's control.

The original native recorder singleton/state getter excludes armed, recording,
intermediate and trim states. An automatic request is cancelled when capture
starts or explicit FREEZE arrives. FREEZE's existing request remains unconsumed
until the automatic lease is released. Other stock mutations and unsupported
machine contexts block admission. Every final release still passes the existing
worker revalidation, DSP descriptor seal, native ISR reply matching and original
stock unload. This policy never clears a reader or triggers a pad.

`lab/buf_auto_retirement_ui.py` installs this native code in explicit emulator
scratch and observes the native queue caller. It refuses manual/host retirement
serials. The host models the recorder input and transport as before; it does not
choose retirement tokens, supply certificates, match completions or free memory.

## Validation record

Twelve focused ColdFire policy tests pass. They cover current/frozen/stale/
quarantine filtering, eight-entry scan bounds, busy and recorder-state refusal,
rotating candidate selection, failure backoff, tick wrap, new tokens in reused
seats, queue refusal, cancellation, deferred FREEZE, single completion and
register/stack preservation. A focused native-state replay is byte-identical.
The tests execute the original state getter with a prepared native singleton
and a native queue stub; they are separate from the coupled panel scenario.

Full suite: 406 tests pass, including the existing 24 transaction controls and
all twelve new policy controls. Log: `out/buf-auto-unit-20261022-01.log`.

SINE replay passes on the frozen implementation:
`out/runs/20261022T064751Z-test-9d10343a/manifest.json`.
Log: `out/buf-auto-sine-20261022-01.log`.

The single four-record native panel scenario passes:
`out/runs/buf-auto-retirement-20261022-01/report.json`.
Read-only aggregate checks:
`out/runs/buf-auto-retirement-audit-20261022-01/verification.json`.

| Scenario/check | Observed result |
| --- | --- |
| Record A, FREEZE A | Current and frozen roots remain protected |
| Play B, replace with C | Native policy selects obsolete B without a host command |
| B still retained by playback | Native timeout; no release; DSP seal refusal code 2 |
| Ordinary C pad presses | Retry selects B automatically and releases it |
| Record and play D | Policy automatically selects and releases obsolete C |
| Native attempts | Three submissions, two releases, one timeout, zero queue denials |
| Retirement command serial | Zero throughout; native policy derives candidate tokens |
| Stock execution comparator | All 32 raw voice buffers exact across 7,493 blocks |
| Independent stock-file playback | Current D and late frozen A exact, finite and nonzero over 48 blocks each |
| Final recording storage | 32 KiB for current D + frozen A; unrelated 8 KiB stock allocation preserved |
| CPU sources | Four transient PCM source frees; two linked metadata entries remain |

Original worker unloads run below IPL 7 with unload authority limited to their
call interval. The existing native completion matcher and GUI wakeup perform
the commits; the driver supplies no completed tuple or allocator instruction.
The coupled run uses modeled recorder input and LP0/SEC/cadence, with actual
native CPU/SHARC execution. It is distinct from the prepared focused fixtures.

The executable source set stayed frozen. The rebuilt DSP SHA-256 is unchanged:
`db737142a31e6e393de5c802dc0a94396d2e0a9e2a3fd625a0fb242efb943ff7`.
All 843 inherited files captured before this increment are preserved except
the intentional README and status-document pointers. Existing Flex R5 package
SHA-256 still matches `668b5fa644427dffbe7d1bde757ac31ac1824fd8b28e5a8e647dd240f911b3b1`.
Scoped Ruff and diff checks pass. The panel scenario completed on its first run;
no long stress run was started.

## Reproduction

Use the configured Python 3.12 and an unused ignored output directory:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
"$LAB_PYTHON" -m unittest discover -s tests -p test_buf_auto_retirement.py -v
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-buf-auto-retirement.py out/runs/YOUR-UNIQUE-BUF-AUTO-RUN
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
```

The four-record scenario uses deterministic stereo input, native record/trim/
USE and queued FREEZE. Ordinary pad events replace retained old playback
pointers; the scheduler never does so. Reports retain source hashes, candidate
PCM, native page history, CPU/DSP streams, worker/ISR traces and original stock
voice comparisons. This increment does not run the earlier 100-cycle stress
qualification.

## Remaining boundary

Stopped sequencer and all-ONESHOT kit are the declared experiment context.
Sequencer-running scheduling, arbitrary project roots and transitions,
readback/SAVE of DSP-resident BUF audio, production memory placement and merger
with existing Flex R5 remain separate work. Frozen BUF versions are volatile;
they are not proven durable project samples. Capture, LP0 delivery, cadence
and SEC initialization remain modeled. Voice PCM is distinct from final DAC
output, listening and physical timing. Retained readers may continue to prevent
cleanup and eventually fill the finite seats; no indefinite recording guarantee.
