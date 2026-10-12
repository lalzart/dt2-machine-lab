# Flex capacity continuation — 2026-10-08

Status: allocator tracing and optional native streaming Save As implemented;
see [results, exact build and remaining limits](FLEX-CAPACITY-RESULTS.md).

Authority: the user's "Okay, let's continue then" resumes the approved bounded
memory implementation. This continues FLEX-MEMORY-IMPLEMENTATION.md and its final
source manifest. Preserve the opt-in path, all inherited changes and legacy bytes.

Working artifact/evidence level: read-only OS1.16 CPU heap decoder and actual
allocator/resource lifetime traces. Native admission/recycling changes follow only
from measured invariants. No DSP algorithm edits, guessed reservation, ID-range
increase, current-track GC, flash, commits or dependency edits.

Experiment: exact stock MAIN/snapshot; decode all free bucket lists with structural
checks; compare the measured free-byte delta against real malloc/free at sizes
16,64,362,2130,1,920,080 and 3,840,080 bytes; deliberately fragment free space and
check a request fails despite sufficient total free bytes; restore every experiment
allocation and require initial free lists/accounting to return. Corrupt a list in a
separate snapshot and require decoder rejection rather than invented free capacity.
Then trace the optional Flex 20-second mono/stereo handover and bounded sequential
reuse. Trace source allocation sizes and late handle identity, preserving old takes.

Acceptance: all buckets in bounds, checksum/backlinks valid, blocks aligned to class,
no overlap/cycle, total within arena, exact observed block deltas. Negative controls
must falsify total-free-only admission and unvalidated heap snapshots. A physical
headroom claim still requires stock workload coverage and a separate device gate.

Deliverables: lab-owned decoder/tracer, meaningful source tests, reproducible unique
ignored native runs, results with exact hashes and a decision for the next native
admission step. Unknown project roots/handle generations remain pinned; no unsafe
identity reuse is authorized by uncertainty.


Selected native implementation after measured heap gate: streaming Save As for
retired sources. Allocate one 32 KiB CPU scratch block, validate/read a small prefix
before any destination mutation, then read/write 32 KiB chunks through the existing
exclusive writer. Validate exact cached identity on every chunk and final hash/length;
close/delete partial destination on error, preserve descriptor/backing and references.
Resident RAM saves retain their existing pin behavior and writer path. Negative:
fragmented heap with no 4 MiB block must still allow backed Save As, full PCM/hash
must match stock reload; stale/missing reference must still cause zero file writes.
No new admission budget, ID recycling or new global memory reservation.
