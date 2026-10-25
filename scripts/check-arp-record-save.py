"""Independently reload recorded notes and modes using original OS 1.16 calls."""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, source_hashes, write_json

config = settings()
if Path(sys.executable).resolve() != config['python'].resolve():
    os.execv(str(config['python']), [str(config['python']), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('capture', type=Path)
p.add_argument('output', type=Path)
args = p.parse_args()
doctor()
capture, out = args.capture.resolve(), args.output.resolve()
require(out.is_relative_to(ROOT / 'out/runs'), 'Use a fresh out/runs directory')
out.mkdir(parents=True, exist_ok=False)
os.environ['DT2_LAB_RUN_DIR'] = str(out.relative_to(ROOT / 'out/runs'))
from lab.runtime import REPO
from lab.arp_persistence import ModeJournal, NativeFiles
import plusdrive_check as check
import tools.plusdrive as pd

inputs = json.loads((ROOT / '.local/cpu-inputs.json').read_text())
os.environ.update(DT2_SYX=inputs['syx'], DT2_SECTIONS=inputs['sections'], DT2_MAIN_IMG=inputs['main'])
meta = json.loads((capture / 'arp.json').read_text())
require(meta['status'] == 'passed' and meta.get('record_replay_passed'), 'Recording capture did not pass')
require(sha256(capture / 'control.dtfr') == meta['capture_sha256'], 'Control capture changed')
require(sha256(inputs['main']) == '344bf871f4e25f0d3c349099223ed17ef44da47eddde167fc14e5fe493f44830', 'Unknown CPU fixture')
for key in ('main', 'snapshot', 'card', 'syx'):
    require(sha256(inputs[key]) == meta['input_sha256'][key], f'Input changed: {key}')
raw = (capture / 'card-overlay.bin').read_bytes()
require(raw[:4] == b'ASOV' and len(raw) >= 8, 'Invalid private card overlay')
count = struct.unpack_from('>I', raw, 4)[0]
require(count <= 100_000 and len(raw) == 8 + count * 516, 'Invalid card overlay extent')
overlay = {struct.unpack_from('>I', raw, 8+n*516)[0]: raw[12+n*516:524+n*516] for n in range(count)}
require(len(overlay) == count and all(k < 8_388_608 for k in overlay), 'Invalid overlay sectors')
fingerprint = source_hashes()
report = {'status': 'running', 'condition': meta['condition'], 'source_sha256': fingerprint,
          'capture_sha256': sha256(capture / 'arp.json'), 'overlay_sha256': hashlib.sha256(raw).hexdigest(),
          'boundary': 'Independent prepared firmware instance; native saved-slot reader and project decoder; original card read-only'}
f = check.Firmware(inputs['card'], inputs['snapshot'], inputs['main'])
try:
    f.card.overlay = overlay
    require(f.call(check.MOUNT, [0], limit=200_000_000) == 0, 'Native mount failed')
    # Read the saved slot afresh. The snapshot's project cache and boot COKi
    # record may contain an older project; neither is a reload oracle.
    files = NativeFiles(f)
    buf = files.alloc(bytes(pd.PROJECT_CONTAINER_SIZE))
    slot = meta.get('saved_slot', 128)
    require(0 <= slot <= 128, 'Unknown saved slot')
    manager = f.call(0x4019D8FE, [])
    require(f.call(0x4012F1D8, [manager, buf, slot], limit=300_000_000) == 0,
            'Native saved-slot reader did not return a current-format record')
    project = f.read(buf, pd.PROJECT_CONTAINER_SIZE)
    require(project[:8] == bytes.fromhex('beefbace00000005'), 'Unknown saved project format')
    project_hash = hashlib.sha256(project).hexdigest()
    require(meta['saved_modes']['path'].startswith(f'/ARP{slot:03d}-{project_hash[:16]}'), 'Saved project identity differs')
    active = f.call(check.PROJECT_GET, [])
    data = f.call(f.u32(f.u32(active)+0x28), [active])
    require(f.call(0x40043F74, [active, buf, 0], limit=800_000_000) & 255 == 1, 'Native project loader failed')
    pattern_id = meta.get('saved_pattern', 0)
    require(0 <= pattern_id < 128, 'Unknown recorded pattern')
    pattern = active + 0x43D0 + pattern_id * 0x954
    storage = f.call(f.u32(f.u32(pattern)+0x28), [pattern])
    saved = f.read(storage, 0x1DB8C)
    expected = (capture / 'pattern-recorded.bin').read_bytes()
    (out / 'loaded-pattern.bin').write_bytes(saved)
    differences = [i for i, (a, b) in enumerate(zip(expected, saved)) if a != b]
    require(len(expected) == len(saved) and not differences,
            f'Native reloaded pattern differs at {differences[:8]}')
    modes = ModeJournal(files).load(slot, project)
    require(modes == meta['pattern_modes'], 'Reloaded mode settings differ')
    require(source_hashes() == fingerprint, 'Source changed during reload')
    report.update(status='passed', slot=slot, pattern=pattern_id, overlay_sectors=count,
                  serialized_project_sha256=project_hash, pattern_sha256=hashlib.sha256(saved).hexdigest(),
                  recalled_modes=modes, exact_pattern_bytes=len(saved),
                  scope='Exact native decoded pattern, including notes and duration bytes; mode companion. GUI load gesture and subsequent audio playback are separate checks.')
except BaseException as error:
    report.update(status='failed', error=str(error))
    raise
finally:
    f.close()
    write_json(out / 'storage.json', report)
print('PASS exact native recorded pattern and mode reload:', meta['condition'])
