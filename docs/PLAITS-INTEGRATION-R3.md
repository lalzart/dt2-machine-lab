# Plaits R3 integration contract

Authorized 2026-10-06: close the duration, model-name, modulation and unsupported-track gaps observed in R2 hardware use. R2 remains reproducible; this is a separate integration family. No firmware transmission or hardware claim is authorized by this implementation.

- Six existing synthesis cores, parameters, gain ceiling, 12-sample rendering and two track-1 lanes remain unchanged. Source authority and core hashes remain those in `machines/plaits-controls/source-lock.json`.
- Track 1 only. Use the original machine permission mask to reject type 7 on tracks 2–16. Arbitrary track choice and simultaneous instances are deferred.
- Dedicated parameter 278 uses mirror 32, encoder F, raw 0..32512, default 2304. Display `(raw >> 8) + 1` times 100 milliseconds. Trigger-latched gate duration is `((raw >> 8)+1)*9600` internal 96-kHz age units, clamped to 9600..1228800. This extends the adapter gate, not an engine's internal drum decay. Existing five-millisecond fades remain.
- Models display V-ANALOG, 2-OP FM, BASSDRUM, WAVESHAP, HARMONIC, GRANULAR: abbreviated Virtual Analog, two-operator FM, Analog Bass Drum, Waveshaping, Harmonic, Granular Formant. MODEL remains trigger-latched.
- HARM/TIMB/MORP should be available in the LFO destination picker and receive the existing per-frame modulation without a retrigger. Preserve stock destination eligibility and parameter metadata. Duration may appear but is trigger-latched; no claim of continuous duration modulation.
- CPU overlay requires the exact audited R2 MAIN hash. Added code uses guarded, unused padding below the reset clear boundary and receives an independent ColdFire subset audit. Firmware and binary artifacts stay ignored.

Acceptance: original R2 reconstruction and old tests still pass; all 16 track permission results; actual string formatter output including invalid model fallback; four sparse rows and stock parameter parity; LFO eligibility across all stock IDs and types; actual panel selection and LFO-to-wire variation; compiled SHARC duration boundary/retrigger/finite PCM and baseline overlap; SINE regression. New hardware checks remain the user's separate step. If any gate fails, retain the failure and do not label a flashable artifact ready.
