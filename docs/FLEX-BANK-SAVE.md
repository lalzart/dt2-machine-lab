# Flex project RAM bank choice (OS 1.16)

The visible Flex save action now opens the stock filename editor, followed by
a project RAM bank page. LEFT/RIGHT selects A–H; YES saves; NO returns to the
Flex Save/Discard menu. The take's current bank is the default. The screen
shows the resulting slot, or FULL; a full bank requires another choice.

Keeping the current bank keeps the existing slot. A different bank uses its
first genuinely empty slot, checking both the project pool and loader's
identity/length. Reserved OFF slots are excluded. The bank page needs no
function-key shortcut.

Only the captured track changes its sample-slot number. Its playback machine
and all other controls remain intact, including STRETCH and SLICE. Changing
track/project or replacing the assignment cancels the pending bank page.
The filename editor's NO and the bank page's NO leave the take in RAM without
writing it. A full bank, invalid name, failed load or failed write preserves
the original track, project reference and source. A failed candidate loader
slot is unloaded only while its ownership can still be established.

## Reference preservation

The original slot remains as an alias when choosing a different bank. This
deliberately avoids rewriting numeric references held by inactive patterns,
sample locks, other tracks or undo/clipboard state. Both slots reference the
same saved +Drive file. This uses an additional project slot; the feature does
not claim to remove all old entries or provide project-wide relocation.

Persistence is staged: load the prospective slot, prepare the file without
promoting the take, revalidate ownership, publish the new slot and track
assignment, then promote exact aliases and run the existing managed-source
retirement. A project change during an operation prevents publication and
prevents clearing slots owned by the replacement project. IDs are not recycled.
If the file completes but a later revalidation fails, a saved file may remain;
the original take/assignment are retained and success is not reported.

The R4 missing-reference project-save repair stays enabled. This extension
does not alter the DSP, bootstrap or updater.

## Reproduce

Use the configured Python from `.local/config.json`, and fresh output paths:

```sh
./labctl doctor
python -B -m unittest discover -s tests -v
python -B scripts/build-cpu-extension.py out/runs/<package> \
  --elekloader-reference out/references/elekloader-upload-audit \
  --all-features --any-track --flex-save-screen
python -B scripts/check-flex-bank.py out/runs/<ui> \
  --package out/runs/<package> \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
python -B scripts/check-flex-bank-project.py out/runs/<project> \
  --package out/runs/<package> \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
```

The UI check uses original/emitted CPU code, modeled recorder/storage
peripherals and unedited guest framebuffer captures. The independent project
check uses the original project writer and stock decoder/loader, with Arp
uninitialized in its prepared direct-call fixture. Neither is a physical
recording, listening, timing or power-loss test.
