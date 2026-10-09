"""Run the unchanged resource contract against the optional compact router."""

import struct

import test_flex_native as original

from lab.flex_resources import OPERATIONS, dispatch, entry, parts


class CompactResourceTests(original.NativeResourceTests):
    def setUp(self):
        super().setUp()
        dispatcher, table = original.CODE + 0x2000, original.CODE + 0x2800
        self.cpu.mem_write(dispatcher, dispatch(dispatcher, original.CODE, table))
        self.cpu.mem_write(table, struct.pack(">7I", *([original.CODE + 0x100] * 7)))
        for operation, address in self.entries.items():
            self.cpu.mem_write(address, entry(address, operation, dispatcher))

    def test_every_stock_operation_selects_its_own_fallback(self):
        table = original.CODE + 0x2800
        addresses = []
        for i in range(7):
            address = original.CODE + 0x2900 + i * 16
            self.cpu.mem_write(address, bytes((0x70, 40 + i, 0x4E, 0x75)))
            addresses.append(address)
        self.cpu.mem_write(table, struct.pack(">7I", *addresses))
        self.cpu.mem_write(0x300200, struct.pack(">4I", 5, 0, 0, 0))
        for i, operation in enumerate(OPERATIONS):
            args = {
                "resolve": (0x300200, 0x300300),
                "open": (0x300200, 0x300300),
                "close": (0x300200,),
                "read": (0x304000, 1, 0x300200),
                "key": (5, 0x300300),
                "size": (5,),
                "name": (5, 0, 0x304000),
            }[operation]
            with self.subTest(operation=operation):
                self.assertEqual(self.call(operation, *args), 40 + i)


class PartitionedResourceTests(CompactResourceTests):
    def setUp(self):
        super().setUp()
        addresses = [original.CODE + 0x2000, original.CODE + 0x2600]
        for address, code in zip(
            addresses,
            parts(addresses, original.CODE, original.CODE + 0x2800),
            strict=True,
        ):
            self.cpu.mem_write(address, code)
