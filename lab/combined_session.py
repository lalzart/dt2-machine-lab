"""A published Flex take alongside the real GUI Arp project-save scenario.

Only recorder input and DSP sample transfers are peripheral peers. Native code
allocates, hashes, publishes, assigns, persists and reloads the sample.
"""

import hashlib
import struct
from contextlib import contextmanager

from lab.project import require


class FlexTake:
    def __init__(self, card, metadata):
        self.card, self.meta = card, metadata
        self.locations = metadata["flex"]["locations"]
        self.frames = 12000
        self.node = self.slot = self.track = self.original = self.durable = None

    @contextmanager
    def peers(self):
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as k

        card, hooks = self.card, []

        def peer(uc, pc, size, unused):
            if not card.direct:
                return
            sp = uc.reg_read(k.UC_M68K_REG_A7)

            def arg(i):
                return card.u32(sp + 4 + i * 4)

            if pc == 0x400124A0:
                command, mono, first, count = struct.unpack(
                    ">HHII", card.read(arg(1), 12)
                )
                require(command == 4 and mono == 0, "Stereo recorder request")
                pcm = b"".join(
                    struct.pack(">HH", i * 17 & 65535, (30000 - i * 29) & 65535)
                    for i in range(first, first + count)
                )
                require(len(pcm) <= 2048, "Recorder response overflow")
                card.write(0x4FE79340, pcm.ljust(2048, b"\xe7"))
            elif pc == card.check.FLEXBUS_PAGE:
                card.pages.append((arg(0), card.read(arg(1), 4096), arg(2)))
            else:
                card.events.append((arg(0), arg(1)))
            uc.reg_write(k.UC_M68K_REG_D0, 0)
            uc.reg_write(k.UC_M68K_REG_PC, card.u32(sp))
            uc.reg_write(k.UC_M68K_REG_A7, sp + 4)

        for pc in (0x400124A0, card.check.FLEXBUS_PAGE, card.check.LOADER_EVENT):
            hooks.append(card.uc.hook_add(UC_HOOK_CODE, peer, begin=pc, end=pc))
        try:
            yield
        finally:
            for hook in hooks:
                card.uc.hook_del(hook)

    def seed(self):
        card, loc = self.card, self.locations
        require(card.direct, "Seed only in a paused native transaction")
        pool = card.call(loc["save_pool"], [])
        require(pool != 0, "Missing native project pool")
        self.slot = next(
            i
            for i in range(1, 1024)
            if i % 128
            and card.u32(0x405BA768 + i * 4) == 0
            and card.u32(0x405B1368 + i * 16) == 0xFFFFFFFF
            and card.u32(pool + i * 16) == 0xFFFFFFFF
        )
        kit = card.u32(0x80004704)
        self.track = next(
            i for i in range(1, 16) if card.read(kit + i * 0x450 + 0xD6, 1) == b"\0"
        )
        with self.peers():
            self.node = card.call(
                loc["accept"],
                [loc["state"], 0, self.frames, 1, self.slot],
                limit=200_000_000,
            )
            require(self.node not in (0, 0xFFFFFFFF), "Native Flex publication failed")
            source, size = card.u32(self.node + 20), card.u32(self.node + 12)
            self.original = card.read(source, size)
            require(
                card.call(loc["assign"], [self.slot, self.track, kit]) == 0,
                "Native Flex assignment failed",
            )
        require(
            card.read(pool + self.slot * 16, 16) == card.read(self.node + 4, 16),
            "Published reference absent from active project",
        )
        return dict(
            track=self.track + 1,
            slot=self.slot,
            frames=self.frames,
            stereo=True,
            native_node=self.node,
            pcm_sha256=hashlib.sha256(self.original[80:]).hexdigest(),
        )

    def saved(self):
        card = self.card
        with card.transaction():
            pool = card.call(self.locations["save_pool"], [])
            self.durable = card.read(pool + self.slot * 16, 16)
            require(card.u32(self.node + 28) == 1, "Shared save did not persist Flex")
            require(
                self.durable == card.read(self.node + 32, 16),
                "Project lacks durable reference",
            )
            require(card.u32(self.node + 20) == 0, "Saved unpinned source not retired")
        return dict(durable_reference=self.durable.hex(), source_retired=True)

    def reloaded(self):
        from lab.flex_native import RESOURCE_SITES

        card = self.card
        with card.transaction(), self.peers():
            pool = card.call(self.locations["save_pool"], [])
            require(
                card.read(pool + self.slot * 16, 16) == self.durable,
                "Native project recall lost Flex reference",
            )
            kit = card.u32(0x80004704)
            slot = int.from_bytes(card.read(kit + self.track * 0x450 + 0x80, 2), "big")
            require(slot == self.slot, "Recalled track lost Flex assignment")
            # Validate the native backing independently of DSP transfer caching.
            ref = card.alloc(self.durable)
            handle = card.alloc(bytes(16))
            destination = card.alloc(bytes(len(self.original)))
            require(
                card.call(RESOURCE_SITES["open"][0], [ref, handle]) == 1,
                "Recalled stock resource did not open with exact success status",
            )
            try:
                count = card.call(
                    RESOURCE_SITES["read"][0],
                    [destination, len(self.original), handle],
                    limit=200_000_000,
                )
                require(
                    count == len(self.original)
                    and card.read(destination, count) == self.original,
                    "Recalled native backing differs",
                )
            finally:
                card.call(RESOURCE_SITES["close"][0], [handle])
            probe_slot = next(
                i
                for i in range(1, 1024)
                if i != self.slot and i % 128 and card.u32(card.check.LOADER_LEN + i * 4) == 0
            )
            loaded = card.check.check_load(card, self.durable, probe_slot)
            cached = loaded["data_pages"] == 0
            # A cache hit emits headers only. Release this fixture's matching
            # aliases through native teardown, then demand a fresh PCM upload.
            aliases = [
                i
                for i in range(1, 1024)
                if card.u32(card.check.LOADER_LEN + i * 4) > 0
                and card.read(card.check.LOADER_KEYS + i * 16 + 4, 8)
                == self.durable[4:12]
            ]
            require(aliases, "Recalled sample has no loaded alias")
            for alias in aliases:
                card.call(0x401540C6, [alias])
                card.call(0x40153BEA, [alias])
                require(
                    card.u32(card.check.LOADER_LEN + alias * 4) == 0,
                    "Native alias teardown failed",
                )
            fresh = card.check.check_load(card, self.durable, self.slot)
            require(
                fresh["data_pages"] > 0
                and all(card.check.sent_pcm_matches(fresh, self.original)),
                "Fresh recalled stock-backed PCM differs",
            )
        return dict(
            native_file_equal=True,
            loader_reused_cache=cached,
            released_fixture_aliases=aliases,
            fresh_transfer_pages=fresh["data_pages"],
            assignment_preserved=True,
            durable_reference_preserved=True,
            stock_backed_pcm_equal=True,
            compared_pcm_bytes=len(self.original) - 80,
        )
