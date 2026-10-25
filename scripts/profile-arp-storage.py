"""Bounded old/full-copy versus incremental private overlay benchmark."""
import argparse
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.arp_storage import OverlaySync
from lab.project import require, source_hashes, write_json


class Card:
    def __init__(self): self.overlay = {}
    def read(self, sector, n): return self.overlay.get(sector, bytes(n))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
out = args.output.resolve()
require(out.is_relative_to(ROOT / 'out/runs'), 'Use a fresh out/runs directory')
out.mkdir(parents=True, exist_ok=False)
fingerprint = source_hashes()
sectors, repetitions = 1024, 10
initial = {offset: offset & 255 for offset in range(sectors * 512)}
legacy, model = SimpleNamespace(overlay=dict(initial)), SimpleNamespace(overlay=dict(initial))
old_card, card = Card(), Card()
sync = OverlaySync(model, card)
sync.after(sync.before())
start = time.perf_counter()
for _ in range(repetitions):
    for sector in {offset // 512 for offset in legacy.overlay}:
        data = bytearray(old_card.read(sector, 512))
        for i in range(512):
            value = legacy.overlay.get(sector * 512 + i)
            if value is not None: data[i] = value
        old_card.overlay[sector] = bytes(data)
    for sector, data in old_card.overlay.items():
        legacy.overlay.update((sector * 512 + i, value) for i, value in enumerate(data))
legacy_seconds = time.perf_counter() - start
counts = sync.imported, sync.published
start = time.perf_counter()
for _ in range(repetitions): sync.after(sync.before())
seconds = time.perf_counter() - start
require(model.overlay == legacy.overlay and card.overlay == old_card.overlay, 'Overlay parity failed')
require((sync.imported, sync.published) == counts, 'No-op synchronized sectors')
require(source_hashes() == fingerprint, 'Source drift')
write_json(out / 'profile.json', {'status':'passed', 'source_sha256':fingerprint,
    'scope':'Host overlay synchronization; no device CPU or physical storage timing claim',
    'bytes':sectors * 512, 'transactions':repetitions,
    'legacy_imported_sectors':sectors * repetitions, 'legacy_published_sectors':sectors * repetitions,
    'incremental_imported_sectors':0, 'incremental_published_sectors':0,
    'legacy_seconds':legacy_seconds, 'incremental_seconds':seconds,
    'exact_overlay_parity':True})
print('PASS exact overlay parity; no-op seconds:', legacy_seconds, '->', seconds)
