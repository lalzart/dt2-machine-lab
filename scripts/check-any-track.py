#!/usr/bin/env python3
"""Compare native Plaits PCM across tracks and independently interleaved lanes."""

# ruff: noqa: E402, I001
import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import require, settings, sha256, source_hashes, write_json

cfg = settings()
if Path(sys.executable).resolve() != cfg['python'].resolve():
    os.execv(str(cfg['python']), [str(cfg['python']), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
p.add_argument('--package', type=Path)
p.add_argument('--probe', type=Path)
a = p.parse_args()
out = a.output.resolve()
require(out.is_relative_to(ROOT / 'out/runs'), 'Use a fresh ignored run')
out.mkdir(parents=True, exist_ok=False)
os.environ['DT2_LAB_RUN_DIR'] = str(out.relative_to(ROOT / 'out/runs'))
from lab import runtime  # noqa: F401
from lab.dsp import Dsp
from lab.formats import read_frames
from lab.replay_io import load_pcm
from lab.dsp import header
import sharcldr
import plusdrive as pd
import sharc_lp0 as lp0
from lab.capicola_reddit import VOICE_BASE
from lab.capicola_layout import STATE_BASE
import sharc_trace as st

frozen = source_hashes()
if a.package:
    m = json.loads((a.package / 'manifest.json').read_text())
    require(m['status'] == 'target-build-complete' and m.get('any_tracks'), 'Wrong package')
    require(m['source_hashes'] == frozen, 'Stale package source')
    require(sha256(a.package / m['candidate']) == m['container']['sha256'], 'Changed package')
    blob = (a.package / m['dsp']['path']).read_bytes()
else:
    require(a.probe is not None, 'Package or development-only probe required')
    blob = (a.probe / 'firmware/PLAITS_BLOB.bin').read_bytes()
old_path = ROOT / 'out/runs/arp-stopped-package-20261019-02/firmware/PLAITS_BLOB.bin'
require(sha256(old_path) == 'fd6e504f6b19cc734acb905a1352cd65d8c1ec0e2f33e502c9ca15f320a82b90',
        'Reference R2 DSP changed')
old = old_path.read_bytes()
firmware = a.package / 'firmware' if a.package else a.probe / 'firmware'
def entry(folder):
    return int(re.search(r'(?m)^machine\.:\n\s+([0-9a-f]+)',
                         (folder/'listing.txt').read_text())[1], 16)
new_pc, old_pc = entry(firmware), entry(old_path.parent)
capture = ROOT / 'out/runs/capicola-panel-08/capicola.dtfr'
require(sha256(capture) == '3e6a3f0f319ca2c27087a77fb09d73f0b88922c2eabec0bb42651de8a1596290',
        'Reference control capture changed')
template = next(w for w in read_frames(capture)
                if int.from_bytes(w[0x94:0x96], 'big') == 8
                and int.from_bytes(w[0x22:0x24], 'big') & 1)


def put(w, at, value):
    w[at:at+2] = value.to_bytes(2, 'big')


def controls(entries):
    w = bytearray(template)
    for track in range(16):
        put(w, 0x94 + track*2, 0)
        put(w, 2 + track*2, 115*256)
        put(w, 0x34 + track*2, 100*256)
        at = 0xDA + track*0x60
        w[at:at+0x60] = template[0xDA:0x13A]
    for track, model, note in entries:
        put(w, 0x94 + track*2, 7)
        put(w, 2 + track*2, note*256)
        at = 0xDA + track*0x60
        for off, value in [(0, 0), (2, 17000), (4, model*256), (6, 23000),
                           (12, 9000), (14, 2304), (18, 25600)]:
            put(w, at+off, value)
    return w


def frame(e, packet, trigger=0):
    w = bytearray(packet)
    put(w, 0x22, trigger)
    e.frame(bytes(w), instruction_limit=24_000_000)


def raw(e, at, size):
    return bytes(e.core.peek(at+i, 1) for i in range(size))


def pcm(e, track):
    output = []
    for lane in (track*2, track*2+1):
        dest = e.core.peek(0x24EF2C + lane*4)
        require(0x80000000 <= dest < 0xA0000000, 'Invalid lane destination')
        output.append(raw(e, dest, 128))
    return b''.join(output)


def machine_pcm(e, track):
    # Voice work buffers retain the raw machine output after the native frame.
    # Destination buffers also include stock filter/mixer processing.
    return b''.join(raw(e, 0x2412CC+lane*0x1D8+4, 256)
                    for lane in (track*2, track*2+1))


def invoke(e, pc, track, model, block, lane=0, level=25600, typ=7):
    c = e.core
    voice_lane = track*2+lane
    regs = dict(M5=0, M6=1, M7=-1, M14=1, I6=STATE_BASE+0xFF00,
                I7=STATE_BASE+0xFEF8, R4=0x2412CC+voice_lane*0x1D8)
    regs.update({f'L{i}': 0 for i in range(16)})
    for k, v in regs.items():
        c.set_reg(st.UREG_CODES[k], st.Const(v))
    c.poke(STATE_BASE+0xFEFC, bytes(8), 1)
    c.poke(0x255970+track*2, struct.pack('<H', typ), 1)
    c.poke(0x24F0CC+voice_lane, bytes([block in (0, 8, 12)]), 1)
    c.poke(0x2558DE+track*2, struct.pack('<H', 115*256), 1)
    for at, value in [(0x2559B6, 0), (0x2559B8, 17000), (0x2559BA, model*256),
                      (0x2559BC, 23000), (0x2559C2, 9000), (0x2559C4, 2304),
                      (0x2559C8, level)]:
        c.poke(at+track*0x60, struct.pack('<H', value), 1)
    e.call(pc, 1_000_000)
    return raw(e, 0x2412CC+voice_lane*0x1D8+4, 256)


report = dict(status='running', source_hashes=frozen, candidate_dsp_sha256=hashlib.sha256(blob).hexdigest(),
              cases=[], hardware=False, scope='Raw native machine PCM before stock filters/mixer, T1 post-filter parity and lane-state isolation; no hardware timing claim')
try:
    for model in range(6):
        for track in (0, 1, 7, 15):
            reference, candidate = Dsp(old), Dsp(blob)
            got, want = bytearray(), bytearray()
            for block in range(24):
                for lane in range(2):
                    active_model = model if block < 12 else (model+1)%6
                    got += invoke(candidate, new_pc, track, active_model, block, lane)
                    want += invoke(reference, old_pc, 0, active_model, block, lane)
                require(raw(candidate, STATE_BASE+0x21000+704*track, 704) ==
                        raw(reference, STATE_BASE+0x21000, 704), 'Relocated state mismatch')
            require(got == want, f'Plaits PCM mismatch model={model} track={track+1}')
            samples = struct.unpack('<' + str(len(got)//4) + 'f', got)
            require(all(math.isfinite(x) for x in samples), 'Non-finite output')
            peak = max(map(abs, samples))
            require(peak > 1e-7, 'Vacuous Plaits comparison')
            name = f'model-{model}-track-{track+1}.f32'
            (out/name).write_bytes(got)
            report['cases'].append(dict(model=model, track=track+1, exact=True, peak=peak,
                                        pcm_sha256=hashlib.sha256(got).hexdigest(), path=name))
            print('exact', model, track+1, peak, flush=True)
    # Triggered model changes and exact mute/maximum level preserve reference quirks.
    for track in range(16):
        reference, candidate = Dsp(old), Dsp(blob)
        for model in range(6):
            for level in (0, 32512):
                for lane in range(2):
                    got = invoke(candidate, new_pc, track, model, 0, lane, level)
                    want = invoke(reference, old_pc, 0, model, 0, lane, level)
                    require(got == want, 'Model/level transition parity')
                    require(all(math.isfinite(x) for x in struct.unpack('<64f', got)), 'Invalid level output')
                    if level == 0:
                        require(all(x == 0 for x in struct.unpack('<64f', got)), 'Mute level not silent')
        before = raw(candidate, STATE_BASE+0x21000, 11264)
        for lane in range(2):
            invoke(candidate, new_pc, track, 0, 1, lane, typ=0)
        expected = bytearray(before)
        for lane in range(2):
            # active is at BankLane offset 336, after cursor/age/length.
            expected[(track*2+lane)*352+336:(track*2+lane)*352+340] = bytes(4)
        require(raw(candidate, STATE_BASE+0x21000, 11264) == expected, 'Machine exit changed another lane')
        print('transitions exact', track+1, flush=True)
    report['transitions'] = dict(tracks=16, models=6, levels=[0, 32512], exact=True, machine_exit=True)
    # Full-frame T1 preserves the original stock filter/mixer initialization.
    # Across different tracks those stock states differ in the captured snapshot,
    # so cross-track engine equivalence above taps before the stock filters.
    for model in range(6):
        reference, candidate = Dsp(old), Dsp(blob)
        packet = controls([(0, model, 115)])
        for block in range(24):
            for e in (reference, candidate):
                frame(e, packet, 1 if block in (2, 10) else 0)
            require(pcm(reference, 0) == pcm(candidate, 0), 'T1 full-frame parity')
    report['full_frame_T1_exact'] = dict(models=6, blocks=24)
    tracks = [(1, 0, 115), (7, 3, 119), (15, 5, 122)]
    samples = [int(10000*math.sin(i*.043)) for i in range(4096)]
    sample = pd.build_native_sample(struct.pack('>'+str(len(samples)*2)+'h',
                                    *[v for x in samples for v in (x, x)]), True)
    transfer = bytearray()
    for tag, block, swap in lp0.native_sample_transfers(sample, 1000, lp0.COLDFIRE_BLOCK_BASE+0x20000):
        transfer += struct.pack('<I', tag)
        width = 2 if swap else 4
        transfer += b''.join(block[i:i+width][::-1] for i in range(0, len(block), width))
    def mixed_engine():
        split = sharcldr.parse_blocks(blob)[-1]['offset']
        pool = bytes(4*1024*1024)
        image = blob[:split]+header(0x8422B9C8-1024, len(pool))+pool+blob[split:]
        e = Dsp(image)
        load_pcm(e, (ROOT/'out/runs/capicola-panel-05/flexbus.raw').read_bytes())
        load_pcm(e, bytes(transfer))
        return e
    def with_capi(w):
        put(w, 0x94, 2)
        put(w, 2, 60*256)
        for off, value in [(0, 16384), (2, 0), (4, 256), (6, 1000),
                           (12, 0), (14, 30720), (16, 0), (18, 25600)]:
            put(w, 0xDA+off, value)
        return w
    combined = mixed_engine()
    solos = {t: mixed_engine() for t, _, _ in tracks}
    capi_solo = mixed_engine()
    capi_pcm = bytearray()
    silence = raw(combined, STATE_BASE+0x21000, 352*2)
    wp = with_capi(controls(tracks))
    collected = {t: bytearray() for t, _, _ in tracks}
    for block in range(24):
        mask = (1+sum(1 << t for t, _, _ in tracks)) if block in (2, 10) else 0
        frame(combined, wp, mask)
        frame(capi_solo, with_capi(controls([])), 1 if block in (2, 10) else 0)
        require(raw(combined, VOICE_BASE, 2048) == raw(capi_solo, VOICE_BASE, 2048),
                'Plaits changed CAPI reader state')
        capi_pcm += pcm(combined, 0)
        for t, model, note in tracks:
            frame(solos[t], controls([(t, model, note)]), (1 << t) if block in (2, 10) else 0)
            require(machine_pcm(combined, t) == machine_pcm(solos[t], t), f'Cross-track PCM coupling {t+1}')
            state = STATE_BASE+0x21000+352*t*2
            require(raw(combined, state, 704) == raw(solos[t], state, 704), 'Cross-track state coupling')
            collected[t] += machine_pcm(combined, t)
    require(raw(combined, STATE_BASE+0x21000, 704) == silence, 'Untouched T1 Plaits state changed')
    require(all(combined.core.peek(VOICE_BASE+lane*0x400) != 0 for lane in (0, 1)),
            'CAPI readers were inactive in mixed scenario')
    for values in [capi_pcm, *collected.values()]:
        require(max(map(abs, struct.unpack('<'+str(len(values)//4)+'f', values))) > 1e-7, 'Vacuous mixed-track output')
    report['interleaving'] = dict(capi_track=1, capi_reader_state_exact=True, tracks=[t+1 for t, _, _ in tracks], exact=True, blocks=24,
                                  hashes={str(t+1):hashlib.sha256(v).hexdigest() for t, v in collected.items()})
    # Old T16 renderer cannot satisfy the new per-track claim.
    negative = Dsp(old)
    old_pcm = bytearray()
    for block in range(24):
        for lane in range(2):
            old_pcm += invoke(negative, old_pc, 15, 0, block, lane)
    require(old_pcm != (out/'model-0-track-16.f32').read_bytes(), 'Old-track negative did not falsify')
    require(source_hashes() == frozen, 'Source drift during PCM validation')
    report.update(status='passed', old_non_T1_negative=True)
except BaseException as exc:
    report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    raise
finally:
    write_json(out/'report.json', report)
