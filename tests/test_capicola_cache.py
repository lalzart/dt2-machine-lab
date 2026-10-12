"""Multi-source cache lifetimes, bounded storage and independent PCM oracles."""

import ctypes as ct
import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from capicola_stretch_reference import Reader  # noqa: E402

SHIM = r"""
#include <stdlib.h>
#include <string.h>
#include "stretch.c"
#include "prepare.c"
#include "cache.c"
static CapCache cache; static CapPrepare worker; static CapStretch reader;
void setup(void *arena,unsigned bytes) {cap_cache_init(&cache,&worker,arena,bytes);}
void cycle(void) {cap_cache_cycle(&cache);}
void reference(unsigned token,int frames) {cap_cache_reference(&cache,token,frames);}
int select_sample(const short *input,int frames,unsigned token) {return cap_cache_select(&cache,input,frames,token);}
void step(void) {cap_cache_step(&cache,32);}
int ready(int i) {return cap_cache_ready(&cache,i);}
int state(int i) {return cache.entries[i].state;}
int find(unsigned token,int frames) {return cap_cache_find(&cache,token,frames);}
unsigned used(void) {unsigned n=0;for(int i=0;i<16;i++) n+=cache.entries[i].bytes;return n;}
CapBank *bank(int i) {return &cache.entries[i].bank;}
void invalidate_entry(int i,int blocked) {cap_cache_invalidate(&cache,i,blocked);}
void pin(int i) {cap_cache_pin(&cache,&cache.entries[i].bank,cache.entries[i].bank.generation);}
int start_reader(int i) {return cap_stretch_start(&reader,&cache.entries[i].bank,0,cache.entries[i].frames,0,1,1,1,128);}
void render(float *out,int frames) {cap_stretch_process(&reader,out,frames);}
int independent(int i) {
 CapCacheEntry *e=&cache.entries[i];CapBank b;CapPrepare p;cap_bank_init(&b);cap_prepare_init(&p,&b);
 cap_prepare_begin(&p,e->input,e->frames,1,e->token);
 while(p.phase==CAP_PREP_COUNT) cap_prepare_step(&p,e->token,256);
 int n=p.needed;void *storage=malloc(n*12);if(!storage) return 0;
 cap_prepare_storage(&p,storage,(int *)((char *)storage+n*4),(unsigned *)((char *)storage+n*8),n);
 while(p.phase==CAP_PREP_WRITE) cap_prepare_step(&p,e->token,256);
 int ok=b.count==e->bank.count && !memcmp(b.value,e->bank.value,n*4) && !memcmp(b.whole,e->bank.whole,n*4) && !memcmp(b.fraction,e->bank.fraction,n*4);
 free(storage);return ok;
}
void render_case(int i,int reverse,float pitch,float advance,float *out,int frames) {
 CapStretch s;cap_stretch_init(&s);
 cap_stretch_start(&s,&cache.entries[i].bank,0,cache.entries[i].frames,reverse,1,pitch,advance,128);
 cap_stretch_process(&s,out,frames);
}
"""


class Bank(ct.Structure):
    _fields_ = [
        ("values", ct.POINTER(ct.c_float)),
        ("whole", ct.POINTER(ct.c_int)),
        ("fraction", ct.POINTER(ct.c_uint)),
        ("capacity", ct.c_int),
        ("count", ct.c_int),
        ("frames", ct.c_int),
        ("error", ct.c_int),
        ("generation", ct.c_uint),
    ]


class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        source = Path(cls.temp.name) / "shim.c"
        source.write_text(SHIM)
        lib = Path(cls.temp.name) / "cache.dylib"
        subprocess.run(
            [
                "cc",
                "-std=c99",
                "-O2",
                "-shared",
                "-fPIC",
                "-I",
                str(ROOT / "machines/capicola"),
                str(source),
                "-o",
                str(lib),
            ],
            check=True,
        )
        cls.lib = ct.CDLL(str(lib))
        cls.lib.setup.argtypes = [ct.c_void_p, ct.c_uint]
        cls.lib.select_sample.argtypes = [ct.POINTER(ct.c_short), ct.c_int, ct.c_uint]
        cls.lib.bank.restype = ct.POINTER(Bank)
        cls.lib.render_case.argtypes = [
            ct.c_int,
            ct.c_int,
            ct.c_float,
            ct.c_float,
            ct.POINTER(ct.c_float),
            ct.c_int,
        ]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.inputs = {}
        self.init(65536)

    def init(self, bytes):
        self.arena = (ct.c_ubyte * (bytes + 32))(*([0xA5] * (bytes + 32)))
        self.lib.setup(ct.byref(self.arena, 16), bytes)
        self.budget = bytes

    def sample(self, token, kind="tone", frames=512):
        rng = random.Random(token)
        data = [
            rng.randrange(-16000, 16001)
            if kind == "noise"
            else 0
            if kind == "silence"
            else int(12000 * math.sin(i * (token + 1) * 0.08))
            for i in range(frames)
        ]
        self.inputs[token] = (ct.c_short * frames)(*data)
        return token

    def select(self, *tokens, pins=()):
        self.lib.cycle()
        for i in pins:
            self.lib.pin(i)
        for token in tokens:
            self.lib.reference(token, len(self.inputs[token]))
        return [
            self.lib.select_sample(self.inputs[t], len(self.inputs[t]), t)
            for t in tokens
        ]

    def prepare(self, *tokens, pins=(), blocks=4000):
        for _ in range(blocks):
            indices = self.select(*tokens, pins=pins)
            self.lib.step()
            if all(i >= 0 and self.lib.ready(i) for i in indices):
                return indices
        self.fail("Cache failed to prepare selected sources")

    def guards(self):
        self.assertEqual(bytes(self.arena[:16]), b"\xa5" * 16)
        self.assertEqual(bytes(self.arena[-16:]), b"\xa5" * 16)
        self.assertLessEqual(self.lib.used(), self.budget)

    def test_sixteen_distinct_banks_match_independent_analysis_and_pcm(self):
        tokens = [self.sample(i + 1) for i in range(16)]
        indices = self.prepare(*tokens)
        self.assertEqual(len(set(indices)), 16)
        for track, i in enumerate(indices):
            self.assertEqual(self.lib.independent(i), 1)
            b = self.lib.bank(i).contents
            times = [b.whole[j] + b.fraction[j] / 2**24 for j in range(b.count)]
            pitch = (0.5, 1, 2)[track % 3]
            advance = (0.1, 1, 4)[track % 3]
            ref = Reader(
                list(b.values[: b.count]),
                times,
                b.frames,
                0,
                b.frames,
                track % 2,
                1,
                pitch,
                advance,
            )
            output = (ct.c_float * 1024)()
            self.lib.render_case(i, track % 2, pitch, advance, output, 1024)
            errors = [
                abs(a - b) for a, b in zip(output, ref.process(1024), strict=True)
            ]
            self.assertLessEqual(max(errors), 1e-4)
            self.assertLessEqual(math.sqrt(sum(e * e for e in errors) / 1024), 1e-5)
        self.guards()

    def test_aliases_share_one_bank(self):
        t = self.sample(1)
        a = self.prepare(t)[0]
        used = self.lib.used()
        self.assertEqual(self.select(*([t] * 16)), [a] * 16)
        self.assertEqual(self.lib.used(), used)
        self.guards()

    def test_rejects_invalid_source_without_reading_input(self):
        token = self.sample(1)
        data = self.inputs[token]
        for frames, identity in ((140, 1), (576001, 1), (512, 0)):
            self.assertEqual(self.lib.select_sample(data, frames, identity), -1)
        self.assertEqual(self.lib.select_sample(None, 512, 1), -1)
        self.assertEqual(self.lib.used(), 0)
        self.guards()

    def test_interrupted_count_and_write_never_publish_mixed_input(self):
        token = self.sample(1, "noise")
        for phase in (1, 3):
            self.init(65536)
            index = self.select(token)[0]
            for _ in range(40):
                self.select(token)
                self.lib.step()
                if self.lib.state(index) == phase:
                    break
            self.assertEqual(self.lib.state(index), phase)
            self.lib.invalidate_entry(index, 1)
            for i in range(512):
                self.inputs[token][i] = -self.inputs[token][i]
            for _ in range(40):
                self.select(token)
                self.lib.step()
                self.assertFalse(self.lib.ready(index))
            self.lib.invalidate_entry(index, 0)
            index = self.prepare(token)[0]
            self.assertEqual(self.lib.independent(index), 1)
            self.guards()

    def test_large_pressure_job_does_not_starve_small_source(self):
        self.init(96)
        large = self.sample(1, "noise")
        small = self.sample(2, "silence")
        for _ in range(100):
            i, j = self.select(large, small)
            self.lib.step()
        self.assertEqual(self.lib.state(i), 7)
        self.assertFalse(self.lib.ready(i))
        self.assertTrue(self.lib.ready(j))
        self.assertEqual(self.lib.independent(j), 1)
        self.guards()

    def test_pinned_bank_survives_pressure_then_releases_for_retry(self):
        a = self.sample(1, "noise", 256)
        b = self.sample(2, "noise", 256)
        ia = self.prepare(a)[0]
        ba = self.lib.used()
        self.prepare(b)
        bb = self.lib.used() - ba
        self.init(max(ba, bb) + 24)
        ia = self.prepare(a)[0]
        self.assertEqual(self.lib.start_reader(ia), 0)
        for _ in range(80):
            ib = self.select(b, pins=(ia,))[0]
            self.lib.step()
        self.assertTrue(self.lib.ready(ia))
        self.assertEqual(self.lib.state(ib), 7)
        ib = self.prepare(b)[0]
        self.assertTrue(self.lib.ready(ib))
        out = (ct.c_float * 32)()
        self.lib.render(out, 32)
        self.assertEqual(list(out), [0.0] * 32)
        self.guards()

    def test_reload_invalidates_only_one_bank_and_requires_unblock(self):
        a, b = self.sample(1), self.sample(2)
        ia, ib = self.prepare(a, b)
        other = self.lib.bank(ib).contents.generation
        self.lib.invalidate_entry(ia, 1)
        for _ in range(100):
            self.select(a, b)
            self.lib.step()
        self.assertFalse(self.lib.ready(ia))
        self.assertTrue(self.lib.ready(ib))
        self.assertEqual(self.lib.bank(ib).contents.generation, other)
        self.lib.invalidate_entry(ia, 0)
        self.prepare(a, b)
        self.guards()

    def test_admission_preserves_pinned_entries_and_selected_later_tracks(self):
        tokens = [self.sample(i + 1) for i in range(16)]
        indices = self.prepare(*tokens)
        new = self.sample(17)
        self.assertEqual(self.select(new, pins=tuple(indices)), [-1])
        selected = self.select(new, *tokens[1:])
        self.assertGreaterEqual(selected[0], 0)
        self.assertEqual(selected[1:], indices[1:])
        self.prepare(new, *tokens[1:])
        self.guards()

    def test_fragmented_arena_reclaims_only_inactive_unselected_storage(self):
        tokens = [self.sample(i + 1, "noise", 256) for i in range(4)]
        self.prepare(*tokens)
        used = self.lib.used()
        self.init(used + 24)
        self.prepare(*tokens)
        large = self.sample(8, "noise", 512)
        # Enough total free bytes can still be split into unusable holes.
        # No compaction is permitted while selected banks are retained.
        for _ in range(100):
            il, _, _ = self.select(large, tokens[1], tokens[3])
            self.lib.step()
        self.assertEqual(self.lib.state(il), 7)
        self.assertTrue(self.lib.ready(self.lib.find(tokens[1], 256)))
        self.assertTrue(self.lib.ready(self.lib.find(tokens[3], 256)))
        self.prepare(large, tokens[3])
        self.guards()
