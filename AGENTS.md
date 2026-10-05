# DTII machine development

Read README.md and docs/STATUS.md first. Use ordinary source changes, tests,
and short engineering notes. The former SYS-001/investigation workflow is
retired; do not introduce investigation IDs, claim ledgers, or coordinator roles.

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
- Preserve unrelated changes. Run python3 -m unittest discover -s tests -v
  for harness changes and ./labctl test sine --replay for DSP/adapter changes.
  The latter needs the private fixture and configured runtime.
