"""Read-only decoder of the exact OS1.16 ColdFire buddy heap.

Native malloc/free are the oracle. This exposes occupied blocks and fragmentation;
it does not determine protected stock headroom or authorize firmware admission.
"""

import struct
from dataclasses import asdict, dataclass

PARAMS = 0x402B406C
EXPECTED_BASE = 0x44F39C40
EXPECTED_BITMAP = 0x44DC8654
EXPECTED_HEADS = 0x46F39C40
QUANTUM = 16
UNITS = 0x200000
MAX_ORDER = 21
MALLOC = 0x4011E674
MALLOC_RETURN = 0x4011E846
FREE = 0x4011E87A
FREE_RETURN = 0x4011E8EC


def block_bytes(request):
    if not 0 < request <= UNITS * QUANTUM:
        raise ValueError("Request outside guarded heap")
    return 1 << (max(QUANTUM, request) - 1).bit_length()


@dataclass(frozen=True)
class HeapSnapshot:
    free_bytes: int
    largest_block: int
    allocation_counter: int
    bucket_counts: tuple[int, ...]
    blocks: tuple[tuple[int, int], ...]

    def report(self):
        result = asdict(self)
        result.update(arena_bytes=UNITS * QUANTUM, base=hex(EXPECTED_BASE))
        return result


def inspect_heap(read):
    """Decode a paused guest; reject unknown parameters or malformed free lists."""
    params = struct.unpack(">7I", read(PARAMS, 28))
    if params[:6] != (
        1,
        EXPECTED_BASE,
        EXPECTED_BITMAP,
        EXPECTED_HEADS,
        MAX_ORDER,
        UNITS,
    ):
        raise ValueError("Unknown/uninitialized OS1.16 heap")
    heads = struct.unpack(">22i", read(EXPECTED_HEADS, 88))
    blocks, counts = [], []
    visited = set()
    for order, index in enumerate(heads):
        previous, count = -1, 0
        units = 1 << order
        while index != -1:
            if index < 0 or index + units > UNITS or index % units or index in visited:
                raise ValueError("Heap free block bounds/alignment/cycle")
            visited.add(index)
            checksum, before, after = struct.unpack(
                ">Iii", read(EXPECTED_BASE + index * QUANTUM, 12)
            )
            # Stock head removal advances the bucket without rewriting the new
            # head's previous field. Only non-head backlinks are authoritative.
            if (
                before < -1
                or before >= UNITS
                or (count and before != previous)
                or checksum != (~(before + after) & 0xFFFFFFFF)
            ):
                raise ValueError(
                    f"Heap free-list checksum/backlink: order={order} index={index} checksum={checksum:#x} prev={before} expected_prev={previous} next={after}"
                )
            blocks.append((index * QUANTUM, units * QUANTUM))
            previous, index = index, after
            count += 1
        counts.append(count)
    blocks.sort()
    end = 0
    for start, size in blocks:
        if start < end:
            raise ValueError("Overlapping heap free blocks")
        end = start + size
    free = sum(size for _, size in blocks)
    if free > UNITS * QUANTUM:
        raise ValueError("Heap accounting exceeds arena")
    return HeapSnapshot(
        free,
        max((size for _, size in blocks), default=0),
        params[6],
        tuple(counts),
        tuple(blocks),
    )


class HeapTrace:
    """Observe original allocator instructions; never replace malloc/free."""

    def __init__(self, fw):
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as r

        self.fw, self.phase = fw, "initial"
        self.initial = inspect_heap(fw.read)
        self.events, self.pending, self.known = [], [], {}
        self.minimum_free = self.initial.free_bytes
        self.hooks = []

        def observe(uc, pc, size, data):
            sp = uc.reg_read(r.UC_M68K_REG_A7)
            if pc in (MALLOC, FREE):
                self.pending.append(
                    (
                        pc,
                        sp,
                        fw.u32(sp + 4),
                        fw.u32(sp),
                        inspect_heap(fw.read),
                        self.phase,
                    )
                )
                return
            if not self.pending:
                raise ValueError("Unpaired heap return")
            entry, entered_sp, arg, caller, before, phase = self.pending.pop()
            if sp != entered_sp or (pc == MALLOC_RETURN) != (entry == MALLOC):
                raise ValueError("Heap call stack/return mismatch")
            after = inspect_heap(fw.read)
            event = dict(
                operation="malloc" if entry == MALLOC else "free",
                phase=phase,
                caller=hex(caller),
                free_before=before.free_bytes,
                free_after=after.free_bytes,
                largest_after=after.largest_block,
            )
            if entry == MALLOC:
                ptr = uc.reg_read(r.UC_M68K_REG_D0)
                expected = block_bytes(arg) if ptr else 0
                if before.free_bytes - after.free_bytes != expected:
                    raise ValueError("Observed malloc/free-list delta differs")
                if ptr:
                    if ptr in self.known:
                        raise ValueError("Live allocation reused")
                    self.known[ptr] = expected
                event.update(
                    requested=arg,
                    pointer=hex(ptr),
                    occupied=expected,
                    failed=not bool(ptr),
                )
            else:
                returned = after.free_bytes - before.free_bytes
                if arg in self.known and returned != self.known.pop(arg):
                    raise ValueError("Free released wrong block")
                if returned < 0 or (returned and returned & (returned - 1)):
                    raise ValueError("Unexpected free delta")
                event.update(pointer=hex(arg), released=returned)
            self.minimum_free = min(self.minimum_free, after.free_bytes)
            self.events.append(event)

        for pc in (MALLOC, FREE, MALLOC_RETURN, FREE_RETURN):
            self.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc))

    def report(self):
        final = inspect_heap(self.fw.read)
        return dict(
            initial=self.initial.report(),
            final=final.report(),
            minimum_free=self.minimum_free,
            pending_calls=len(self.pending),
            events=self.events,
        )
