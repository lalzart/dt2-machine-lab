# DTII machine development

Read README.md and docs/STATUS.md first. Use ordinary source changes, tests,
and short engineering notes. The former SYS-001/investigation workflow is
retired; do not introduce investigation IDs, claim ledgers, or coordinator roles.

The accepted Sketch/BUF checkpoint is `docs/SKETCH-BUF-CHECKPOINT.md` and
`profiles/sketch-buf-r8.json`. Read these before extending the active profile.
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
- Preserve unrelated changes. Use the scoped unit commands in docs/TESTING.md:
  ./labctl unit buf for BUF, ./labctl unit flex for existing Flex, and core
  plus affected suites for shared tooling changes. Add integration for shared
  builders/save/resource changes; use ./labctl unit all for broad cross-feature
  changes or an explicit full audit. Do not run Capicola/Arp suites for unrelated
  BUF work. Keep older BUF models in the separate buf-models group.
- `buf` covers the accepted Sketch workflow and shared recorder; `buf-full`
  additionally retains older Unicorn BUF/retirement fixtures. Retirement or
  shared lifecycle edits need their relevant explicit cases. The current host
  Unicorn first-map SIGILL is documented, not repaired or counted as passing.
- Run ./labctl test sine --replay for DSP/adapter behavior changes, alongside
  the relevant bounded compatibility/negative controls. This needs the private
  fixture and configured runtime; unit/docs organization alone needs no replay.
