# Capicola integration R1 results

2026-10-07, Digitakt II OS 1.16. The twelve-second Capicola reader now shares the compiled voice hook with Plaits R3. This is a prepared-bank emulator integration; native sample loading and the CPU menu remain open. No installable OS was produced or sent to hardware.

## Changes

`machines/plaits-capicola/machine.c` dispatches provisional type 8 to Capicola on the two track-1 lanes. It preserves type-7 Plaits and stock fallback. A checked handoff binds the source identity, generation, bank layout and trigger-time controls. Invalid handoffs silence the reader. Both lanes share immutable keys with independent transport; the callback performs no analysis or allocation.

`lab/plaits.py` adds an optional `capicola` build family and guarded source fingerprints. The original integration family still reproduces the previous BLOB. The combined MAIN is byte-identical to the current twenty-second Flex / Plaits R3 / menu package, SHA-256 `32081f9ce0db5002e271cdda883feecb54f72c0a1111cb1fa6782f690fe4743a`.

## Evidence

The initial passing report is `out/runs/capicola-integration-02/report.json`; the final frozen-source rerun is `out/runs/capicola-integration-03/report.json`.

- Three pitch/advance combinations match host-reader audio, maximum output error 2.24e-8, including duration and terminal silence checks.
- One hundred calls through the actual stock voice-render entry and patched hook exactly match direct compiled adapter audio.
- All six Plaits models match the previous implementation on both lanes. Eight audible stock fallback blocks match exactly.
- Eleven invalid handoff cases silence safely; bank immutability, unsupported voice isolation, switching, retriggering and repeat builds pass.
- Twenty-three complete captured DSP frames tolerate injected type 8 with an unpublished bank: silence without interpreter faults. This does not prove audible native sample loading.

The combined test sample is 8192 mono frames. Twelve-second capacity was separately validated in [the capacity results](CAPICOLA-TWELVE-SECONDS-RESULTS.md); this integration run does not test a twelve-second native load. Worst observed emulator call count was 97,011 instructions; this is not physical cycle timing.

An initial hook comparison failed because the test caller stack overlapped the wrapper private stack. Separating the caller stack at 0x200dc000 from the wrapper stack at 0x200dff00 fixed the harness; the DSP core and tolerances were unchanged. The failed report is preserved.

Final regression: all 59 configured-runtime unit tests, Ruff and whitespace checks pass. SINE replay passes in `out/runs/20261007T133940Z-test-0bf2aa08/manifest.json`. After the frozen-source runs, only this documentation and the required Evidence ladder heading in the contract results were updated; executable source is unchanged.

## Reproduce

```sh
python3 scripts/check-capicola-integration.py out/runs/<unique-capicola-run>
./labctl test sine --replay
```

The integration runner uses the configured Python runtime and requires the existing private `flex-20sec-menu-package-02` baseline. All generated firmware, captures and banks remain in ignored run directories.

## Remaining work

Connect the CPU machine selector and controls, then implement native selected-sample analysis, memory ownership and serialized bank publication. The current 0x83000000 arena belongs only to the emulator test. The prior target analyzer arithmetic mismatch, end-of-sample quality, listening, final mixer output and hardware timing remain unresolved. Packaging must wait for a functional native loading path.
