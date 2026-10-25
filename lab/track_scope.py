"""Optional all-track Plaits CPU routing over the exact reviewed CPU base."""

import hashlib
import struct

from lab.dt2_116 import BASE
from lab.emit import Code
from lab.project import require

MIRROR_STRIDE = 142
TYPE_STRIDE = 154
TYPE_BASE = 0x80003CD0
SOURCE = 0x80003396
DESTINATION = 0x80005BA6
PERMISSION = 0x40311980
FILTER_RETURN = 0x400D9346
REPACK = 0x4002E978


def transport(address):
    """Preserve full-width Plaits controls after stock filtering on all tracks."""
    c = Code()
    c.emit('4fefffe8 48d7070e')  # D1-D3/A0-A2, 24 bytes.
    c.imm('41f9', SOURCE)
    c.imm('43f9', DESTINATION)
    c.imm('45f9', TYPE_BASE)
    c.emit('7210')
    c.label('track')
    c.emit('7000 1012')
    c.imm('0c80', 7)
    c.branch(6, 'next')
    c.emit('2290 336800040004 3368000a000a 3368000c000c')
    c.label('next')
    c.emit('41e8008e 43e9008e 45ea009a 5381')
    c.branch(6, 'track')
    c.emit('4cd7070e 4fef0018')
    c.imm('203c', 0x80005B50)
    c.imm('4ef9', FILTER_RETURN + 6)
    return c.finish(address)


def repack(address):
    """D6 is the stock track index; preserve stock repacking for other types."""
    c = Code()
    c.emit('4feffff8 48d70102 2006')  # Preserve D1/A0.
    c.imm('223c', TYPE_STRIDE)
    c.emit('4c010800')
    c.imm('41f9', TYPE_BASE)
    c.emit('d1c0 7000 1010')
    c.imm('0c80', 7)
    c.branch(7, 'plaits')
    c.emit('4cd70102 508f 716c005a0c8000000400')
    c.imm('4ef9', 0x4002E982)
    c.label('plaits')
    c.emit('4cd70102 508f')
    c.imm('4ef9', 0x4002E994)
    return c.finish(address)


def payload(allocator):
    locations = {}
    data = []
    for name, fn in [('transport', transport), ('repack', repack)]:
        code = fn(0)
        at = allocator.allocate('tracks/' + name, len(code))
        locations[name] = at
        data.append(dict(address=at, before=bytes(len(code)).hex(),
                         after=fn(at).hex(), label='tracks/' + name,
                         kind='code', payload=True))
    return locations, data


def overlay_base(stock, image, metadata, locations):
    """Compose intentional overrides after exact old-base validation."""
    from lab.all_features_base import BASE_SHA
    from lab.capicola_toggle import ARENA, SOURCE_ARENA

    require(hashlib.sha256(image).hexdigest() == BASE_SHA, 'Track overlay base drift')
    data = bytearray(image)
    original_filter = bytes.fromhex('4ef940311d04')
    old_repack = data[REPACK - BASE:REPACK - BASE + 10]
    require(old_repack[:2] == b'\x4e\xf9', 'Missing reviewed repack hook')
    edits = [
        (PERMISSION, b'\x00\x01', b'\xff\xff', 'Plaits permissions on all tracks'),
        (FILTER_RETURN, original_filter,
         b'\x4e\xf9' + struct.pack('>I', locations['transport']), 'All-track raw transport'),
        (REPACK, old_repack,
         b'\x4e\xf9' + struct.pack('>I', locations['repack']) + bytes.fromhex('4e714e71'),
         'All-track Plaits repack bypass'),
    ]
    for at, before, after, label in edits:
        require(len(before) == len(after) and data[at-BASE:at-BASE+len(before)] == before,
                'Track scope guard: ' + label)
        data[at-BASE:at-BASE+len(after)] = after
    # Re-describe final stock-to-base bytes, so intentional stage overrides do
    # not appear as conflicting concurrent owners in the composition checker.
    padded = stock + bytes(len(data) - len(stock))
    writes, cursor = [], 0
    while cursor < len(data):
        if data[cursor] == padded[cursor]:
            cursor += 1
            continue
        end = cursor + 1
        while end < len(data) and data[end] != padded[end]:
            end += 1
        at = BASE + cursor
        w = dict(address=at, before=padded[cursor:end].hex(), after=data[cursor:end].hex(),
                 label='plaits-capi/any-track-base', kind='validated-base', payload=False)
        if at >= SOURCE_ARENA:
            w['runtime_address'] = ARENA + at - SOURCE_ARENA
        writes.append(w)
        cursor = end
    return bytes(data), dict(metadata, baseline_sha256=BASE_SHA,
                             sha256=hashlib.sha256(data).hexdigest(), writes=writes,
                             any_track=True, track_scope_edits=[
                                 dict(address=a, before=b.hex(), after=c.hex(), label=n)
                                 for a, b, c, n in edits])
