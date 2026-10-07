"""External recorder-peer model and observation for native Flex UI checks.

No temporary-sample, USE, allocation, assignment or filesystem callbacks.
The new firmware instructions and original OS tasks execute those operations.
"""

import struct

from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab.flex_native_build import BASE, patch_cpu
from lab.flex_recorder import RecorderInput
from lab.project import require

RESPONSE = 0x4FE79340


class Memory:
    def __init__(self, machine):
        self.m, self.uc = machine, machine.uc

    def read(self, address, size):
        return bytes(self.uc.mem_read(address, size))

    def write(self, address, data):
        self.uc.mem_write(address, bytes(data))

    def u32(self, address):
        return int.from_bytes(self.read(address, 4), "big")

    def close(self):
        pass


class NativeFlexInput:
    def __init__(self, gui, clock_state, source, card, main, *, enabled=True):
        require(enabled, "Native check requires the native overlay")
        self.input = RecorderInput(source)
        self.phase, self.error = "ready", None
        self.current = self.target = self.controller = self.view = None
        self.pages, self.events, self.hooks = [], [], []
        self.lock_depth = 0
        self.fw = None
        image, self.metadata = patch_cpu(main)
        self.image = image
        original_build = gui.build

        def build(*args, **kwargs):
            result = original_build(*args, **kwargs)
            self.fw = Memory(result[0])
            self.install()
            return result

        gui.build = build

    def install(self):
        fw = self.fw
        for patch in self.metadata["writes"]:
            before = bytes.fromhex(patch["before"])
            require(
                fw.read(patch["address"], len(before)) == before,
                "Native GUI patch byte guard: " + patch["label"],
            )
            fw.write(patch["address"], bytes.fromhex(patch["after"]))
        fw.uc.ctl_remove_cache(BASE, BASE + len(self.image))
        sites = (
            0x40015FDA,
            0x400161FE,
            0x40015FF8,
            0x400CD6CE,
            0x400124A0,
            0x40001608,
            0x4000172A,
            0x400CD638,
        )
        for address in sites:
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.observe, begin=address, end=address)
            )
        # Observe the successful finish epilogue, without changing its state.
        start = self.metadata["locations"]["use_finish"]
        finish = next(w for w in self.metadata["writes"] if w["label"] == "use_finish")
        offset = bytes.fromhex(finish["after"]).index(
            bytes.fromhex("4cd70c044fef000c4e75")
        )
        self.finish_pc = start + offset
        self.hooks.append(
            fw.uc.hook_add(
                UC_HOOK_CODE, self.observe, begin=self.finish_pc, end=self.finish_pc
            )
        )

    def tick(self):
        return self.fw.u32(0x40966500)

    def observe(self, uc, pc, _size, _data):
        fw = self.fw
        sp = uc.reg_read(k.UC_M68K_REG_A7)

        def arg(i):
            return fw.u32(sp + 4 + i * 4)

        def peer_return(value=0):
            uc.reg_write(k.UC_M68K_REG_D0, value)
            uc.reg_write(k.UC_M68K_REG_PC, fw.u32(sp))
            uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

        if pc == 0x40015FDA:
            self.controller = arg(0)
            self.view = uc.reg_read(k.UC_M68K_REG_A2)
            self.input.begin(self.tick())
            self.phase = "recording"
            self.events.append(dict(event="record", tick=self.tick()))
        elif pc == 0x400161FE:
            self.input.finish(self.tick())
            self.phase = "trim"
            self.events.append(dict(event="stop", frames=self.input.captured))
        elif pc == 0x40015FF8:
            self.input.discard()
            self.phase = "ready"
            self.events.append(dict(event="discard"))
        elif pc == 0x400CD6CE:
            peer_return(self.input.count(self.tick()))
        elif pc in (0x40001608, 0x4000172A) and arg(0) == 0x40965B74:
            self.lock_depth += 1 if pc == 0x40001608 else -1
            require(self.lock_depth >= 0, "Recorder lock observation underflow")
            if not self.lock_depth:
                fw.write(RESPONSE, b"\xa5" * 2048)
        elif pc == 0x400CD638:
            self.pages.append((arg(0), fw.read(arg(1), 4096), arg(2)))
        elif pc == self.finish_pc:
            state = self.metadata["locations"]["state"]
            self.target = fw.u32(state + 16)
            self.current = dict(
                track=self.target,
                slot=fw.u32(state + 36),
                frames=fw.u32(state + 28),
                stereo=bool(fw.u32(state + 32)),
            )
            self.phase = "assigned"
            self.events.append(dict(event="native-use", **self.current))
        elif pc == 0x400124A0:
            length, pointer, response = arg(0), arg(1), arg(2)
            require(
                length in (2, 4, 12) and response <= 0xB40,
                "Recorder peer request bounds",
            )
            descriptor = fw.read(pointer, length)
            command = int.from_bytes(descriptor[:2], "big")
            payload = bytes(response)
            if command == 3:
                _, _selector, start, end = struct.unpack(">HHII", descriptor)
                payload = self.input.extrema(start, end)
                require(response == 16, "Waveform extent")
            elif command == 4:
                _, mono, start, count = struct.unpack(">HHII", descriptor)
                require(
                    self.lock_depth == 2 and response == 2048,
                    "Native recorder worker lost outer lock",
                )
                payload = self.input.chunk(start, count, mono).ljust(response, b"\0")
            else:
                require(command in (0, 1, 2, 5), "Unknown recorder peer command")
            fw.write(RESPONSE, payload)
            peer_return()
