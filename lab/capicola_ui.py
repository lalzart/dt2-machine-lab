"""Reuse the stock OS1.16 AMP RSET switch renderer for CAPI's SRC field."""

import copy
import hashlib
import struct

from lab.dt2_116 import BASE
from lab.project import require

# The global UI initializer clones a std::function into row 204's drawing
# callback. Select row 74's stock template instead of the Crossfade knob's.
# These are UI callback templates, not the parameter/range/MIDI metadata.
SITE = 0x401C267A
BEFORE = bytes.fromhex("48794293b36448794293f6844e94")
AFTER = bytes.fromhex("48794293b02448794293f6844e94")
CALLBACK = 0x4293C040 + 204 * 68 + 28
KNOB_CALLBACK = struct.pack(">II", 0x400C3586, 0x400C6470)
SWITCH_CALLBACK = struct.pack(">II", 0x400C462E, 0x400C1DE4)


def apply_switch(image, metadata):
    """Patch only the callback template operand; retain the original allocation.

    Prepared fixtures already ran the global initializer. Their equivalent
    initializer changes its manager/invoker, retaining the existing one-byte
    stateless function object and its allocation. Both stock managers allocate
    one byte; neither draws from its contents. Never alias another function's
    heap data.
    """
    require(metadata["features"] == "all", "CAPI switch requires all features")
    require(
        hashlib.sha256(image).hexdigest() == metadata["sha256"],
        "CAPI switch input identity changed",
    )
    offset = SITE - BASE
    require(image[offset : offset + len(BEFORE)] == BEFORE, "CAPI UI byte guard")
    result = bytearray(image)
    result[offset : offset + len(AFTER)] = AFTER
    meta = copy.deepcopy(metadata)
    meta["writes"].append(
        dict(
            address=SITE + 2,
            before=BEFORE[2:6].hex(),
            after=AFTER[2:6].hex(),
            kind="data-operand",
            payload=False,
            label="capi-ui/stock-binary-switch",
        )
    )
    meta["base"]["runtime_initializers"].append(
        dict(
            address=CALLBACK,
            after=SWITCH_CALLBACK.hex(),
            mutable=False,
            label="capi-ui/prepared-drawing-callback",
        )
    )
    meta["capi_switch"] = dict(
        stock_control="AMP RSET (parameter 74)",
        parameter=204,
        template=0x4293B024,
        initializer=SITE,
        callback=CALLBACK,
        manager=0x400C462E,
        draw=0x400C1DE4,
        prepared_before=KNOB_CALLBACK.hex(),
        prepared_after=SWITCH_CALLBACK.hex(),
        added_code_bytes=0,
        added_runtime_bytes=0,
    )
    meta["sha256"] = hashlib.sha256(result).hexdigest()
    return bytes(result), meta
