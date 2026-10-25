"""Emulator adapter for the native metadata-only command, not a device build.

BUF capture/commit is the existing host transaction. Registration, snapshot
identity/key/name resolution, aliasing, rollback and project guards execute as
ColdFire instructions. No PCM readback or gesture is supplied.
"""

import struct
from contextlib import contextmanager

from lab import recorder_freeze_code as n
from lab.coldfire import audit_code
from lab.project import require

# isort: off
from lab.recorder_normal import NormalBufferUI, RESERVED
import plusdrive_check as check
from unicorn import UC_HOOK_CODE, m68k_const as k
# isort: on


class NativeFreezeUI(NormalBufferUI):
    def __init__(self, *args, **kwargs):
        self.native_mode = False
        self.native_seen = 0
        self.resource_hle_calls = 0
        self.native_resource_calls = {}
        self.native_patches = []
        self.last_freeze_pages = []
        super().__init__(*args, **kwargs)

    def install(self, main):
        super().install(main)
        fw = self.fw
        require(RESERVED == n.RESERVED, "Native slot-reservation ABI mismatch")
        code, original = n.payload()
        for pc, expected in original.items():
            require(
                fw.read(pc, len(expected)) == expected, f"Resource entry drift {pc:#x}"
            )
        for page in range(n.BASE, n.BASE + 0x8000, 4096):
            fw.m.ensure(page)
            fw.write(page, bytes(4096))
        fw.write(n.STATE, struct.pack(">I", 1))
        fw.write(n.GEN_NAME, b"/TEMP/BUF-GEN\0".ljust(32, b"\0"))
        for buffer in range(4):
            for serial in range(8):
                fw.write(
                    n.NAMES + (buffer * 8 + serial) * 32,
                    f"/TEMP/B{buffer + 1}-{serial + 1:03d}".encode().ljust(32, b"\0"),
                )

        def patch(pc, expected, target, label):
            require(fw.read(pc, len(expected)) == expected, label + " drift")
            replacement = (
                b"\x4e\xf9"
                + struct.pack(">I", target)
                + b"\x4e\x71" * ((len(expected) - 6) // 2)
            )
            require(len(replacement) == len(expected), "Patch instruction extent")
            fw.write(pc, replacement)
            fw.uc.ctl_remove_cache(pc, pc + len(expected))
            self.native_patches.append(
                dict(
                    label=label,
                    address=pc,
                    before=expected.hex(),
                    after=replacement.hex(),
                )
            )

        for index, (op, (pc, _)) in enumerate(n.RESOURCE_SITES.items()):
            patch(pc, original[pc], n.HANDLERS + index * 512, op)
        for index, pc in enumerate((n.SAVE, n.LOAD_PROJECT)):
            expected = main[pc - 0x40000400 : pc - 0x40000400 + 8]
            tramp, guard = n.TRAMPOLINES + 0x700 + index * 32, n.GUARDS + index * 256
            code[tramp] = expected + b"\x4e\xf9" + struct.pack(">I", pc + 8)
            code[guard] = n.project_guard(guard, tramp)
            patch(pc, expected, guard, "volatile-project-guard")
        for index, pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
            expected = main[pc - 0x40000400 : pc - 0x40000400 + 8]
            tramp, guard = (
                n.TRAMPOLINES + 0x800 + index * 32,
                n.GUARDS + 0x400 + index * 512,
            )
            code[tramp] = expected + b"\x4e\xf9" + struct.pack(">I", pc + 8)
            code[guard] = n.slot_guard(guard, tramp, load=index == 0)
            patch(pc, expected, guard, "frozen-slot-guard")
        ranges = []
        for pc, block in sorted(code.items()):
            require(not ranges or pc >= ranges[-1][1], "Native code overlap")
            ranges.append((pc, pc + len(block)))
            fw.write(pc, block)
            # Exact authenticated stock prologues are classified separately;
            # every newly emitted instruction is independently audited.
            if not n.TRAMPOLINES <= pc < n.GUARDS:
                audit_code(block, pc)
        fw.uc.ctl_remove_cache(n.BASE, n.BASE + 0x8000)
        self.code_ranges = ranges
        # Replace only the seven old source HLEs. They remain available while
        # the older host BUF loader runs; native command mode executes thunks.
        require(
            len(fw.hooks) == 15 and len(fw.source_hooks) == 7,
            "Attached resource-hook layout drift",
        )
        for handle in fw.hooks[-7:]:
            fw.uc.hook_del(handle)
        del fw.hooks[-7:]
        callbacks = {
            check.RESOLVE_REF: fw.resolve,
            check.REF_KEY: fw.key,
            0x4015B2D0: fw.open_source,
            0x4015BA22: fw.size,
            0x4015832E: fw.read_source,
            check.PATH_OF_ID: fw.name,
            0x401585E4: fw.close_source,
        }
        for pc, callback in callbacks.items():

            def conditional(uc, _pc, _size, _data, fn=callback):
                if not fw.direct or self.native_mode:
                    return
                self.resource_hle_calls += 1
                sp = uc.reg_read(k.UC_M68K_REG_A7)
                result = fn(lambda index: fw.u32(sp + 4 + index * 4))
                uc.reg_write(k.UC_M68K_REG_D0, (result or 0) & 0xFFFFFFFF)
                uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
                uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

            fw.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, conditional, begin=pc, end=pc))
        for index, op in enumerate(n.RESOURCE_SITES):
            pc = n.HANDLERS + index * 512

            def observed(uc, _pc, _size, _data, operation=op):
                self.native_resource_calls[operation] = (
                    self.native_resource_calls.get(operation, 0) + 1
                )

            self.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, observed, begin=pc, end=pc))

    def extra_hook(self, uc, pc, *args):
        if pc in (n.SAVE, n.LOAD_PROJECT):
            return  # Patched native guards execute; do not use old host guards.
        super().extra_hook(uc, pc, *args)

    @contextmanager
    def native(self):
        self.native_mode = True
        before = self.resource_hle_calls
        try:
            with self.fw.transaction():
                yield
        finally:
            self.native_mode = False
            require(
                self.resource_hle_calls == before,
                "Native operation used host resource HLE",
            )

    def process(self):
        super().process()
        if self.current and self.current.get("generation", 0) > self.native_seen:
            current = self.current
            generation = self.buffers.current[self.destination - 1]
            require(generation is not None, "Committed buffer generation missing")
            with self.native():
                result = self.fw.call(
                    n.REGISTER,
                    [
                        self.destination,
                        current["slot"],
                        generation.slot,
                        self.buffers.epoch,
                    ],
                )
                require(result == 0, "Native generation registration rejected")
            self.native_seen = current["generation"]

    @property
    def snapshots(self):
        fw = self.fw
        if fw is None:
            return []
        snapshots = []
        for index in range(min(8, fw.u32(n.STATE + 4))):
            address = n.SNAP + index * 64
            if fw.u32(address) != 1:
                continue
            slot = fw.u32(address + 36)
            allocation = fw.slot(slot)
            snapshots.append(
                dict(
                    identity=fw.u32(address + 4),
                    epoch=fw.u32(address + 8),
                    slot=slot,
                    name=fw.read(0x405B6368 + slot * 16, 16).split(b"\0")[0].decode(),
                    generation=fw.u32(address + 56),
                    allocation=allocation,
                )
            )
        return snapshots

    def freeze(self, destination, *, expected_epoch=None):
        fw = self.fw
        with self.native():
            fw.pages.clear()
            result = fw.call(
                n.FREEZE,
                [
                    destination,
                    self.buffers.epoch if expected_epoch is None else expected_epoch,
                    fw.u32(0x80004704),
                ],
            )
            self.last_freeze_pages = list(fw.pages)
            self.pages.extend(fw.pages)
        signed = result - 0x100000000 if result & 0x80000000 else result
        if signed < 0:
            raise ValueError(f"Native FREEZE rejected ({signed})")
        require(
            all(tag == 0xFFFFFFFF for tag, _, _ in self.last_freeze_pages),
            "FREEZE published PCM",
        )
        return next(
            snapshot for snapshot in self.snapshots if snapshot["slot"] == result
        )
