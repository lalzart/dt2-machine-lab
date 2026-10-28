# DTII machine development

Read docs/README.md (the task/source/check map) and docs/STATUS.md first.
Use README.md for setup and dependency context. Use ordinary source changes, tests,
and short engineering notes. The former SYS-001/investigation workflow is
retired; do not introduce investigation IDs, claim ledgers, or coordinator roles.

The accepted Sketch/BUF checkpoint is `docs/SKETCH-BUF-CHECKPOINT.md` and
`profiles/sketch-buf-r8.json`. It is separate from the newer managed/combined
work in STATUS. Read the guide for the profile being changed.
Keep the accepted firmware behavior byte-exact during organizational cleanup.
The frozen BUF proposal remains hash-pinned; its older bare-trig wording is
superseded by the current checkpoint's all-sixteen-trig exit behavior.

For BUF, read BUF-WORKFLOW-CONTRACT.md. It is the canonical product direction;
historical one-bar/autoassignment experiments do not override its invariants.

- This repository owns machine source and test adapters. DigiKit and Selache
  are pinned dependencies under .deps/. Do not silently update or edit them.
- Run ./labctl doctor before firmware work. Use bounded, uniquely named runs.
  Refuse unknown firmware, stale fixtures and unexpected patch-site bytes.
- Keep firmware, derived binaries, native state and captures in ignored local
  directories. Preserve originals. Track hashes, source and reproduction notes.
- Keep exact-repeat tests, stock compatibility and explicit negative controls.
  Do not automatically rewrite expected results when a test fails.
- Report the observed layer: CPU selection, control transport, DSP execution,
  voice PCM, final output, emulator throughput and physical timing are distinct.
- The current native instruction clock is not physical DSP cycle timing.
- Elekloader is an optional integration reference; see docs/ECOSYSTEM.md.
- Do not flash hardware, publish, push, or commit unless the user asks. Creating
  this local repository does not authorize a remote publication or device test.
- Preserve unrelated changes. Start with the smallest feature suite in
  docs/README.md: buf-selector, buf-recording, buf-save or buf-managed. The
  default `unit buf` combines current behavior with shared recorder checks.
  Add `sketch-build` for emitter/placement/profile/packaging changes, `core`
  for shared tooling, and `integration` for cross-feature composition.
  Use `all` for an explicit broad audit, not routine iteration. Older BUF and
  Capicola experiments remain explicit; do not run unrelated feature suites.
- `buf-full` adds profile-build and older Unicorn/retirement fixtures. Retirement
  or lifecycle changes need their relevant explicit cases. The documented host
  Unicorn first-map SIGILL is not counted as passing or repaired by a suite change.
- Documentation/navigation changes need link/diff checks, not firmware rebuilds
  or audio replay. Test organization needs affected tests and catalogue checks.
  Once relevant checks pass, don't repeat or broaden them without a reason.
- Follow docs/README.md to existing results before starting an investigation.
  Search lab/scripts/tests for implementation; consult history only for a
  specific missing fact. Update the affected guide/STATUS, not parallel ledgers.
- Run ./labctl test sine --replay for DSP/adapter behavior changes, alongside
  the relevant bounded compatibility/negative controls. This needs the private
  fixture and configured runtime; unit/docs organization alone needs no replay.
