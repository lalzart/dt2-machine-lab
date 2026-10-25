"""Public-resource lifecycle controls for the host buffer prototype."""

import unittest

from lab.flex_buffer_core import Buffers, Generation


class BufferTests(unittest.TestCase):
    def commit(self, pool, destination, number):
        candidate = pool.begin(destination, 4, 0x1234)
        generation = Generation(pool.epoch, number, 1000 - number, 8192, 2000)
        pool.commit(candidate, generation, complete=True)
        return generation

    def test_four_buffers_are_independent_and_shared_reference_is_stable(self):
        pool = Buffers()
        first = self.commit(pool, 1, 1)
        references = {0: 1, 4: 1, 9: 2}
        self.commit(pool, 2, 2)
        self.commit(pool, 1, 3)
        self.commit(pool, 3, 4)
        self.commit(pool, 4, 5)
        self.assertEqual(references, {0: 1, 4: 1, 9: 2})
        self.assertEqual(pool.current[0].number, 3)
        self.assertEqual(pool.current[1].number, 2)
        self.assertEqual([g.number for g in pool.current], [3, 2, 4, 5])
        self.assertIs(pool.generations[0], first)  # An old reader keeps this.

    def test_cancel_preserves_committed_audio(self):
        pool = Buffers()
        old = self.commit(pool, 1, 1)
        pool.begin(1, 0, 0x1234)
        self.assertEqual(pool.status(1), "RECORDING")
        pool.cancel()
        self.assertIs(pool.current[0], old)
        self.assertEqual(pool.status(1), "READY")

    def test_cancelled_candidate_cannot_commit_after_another_recording(self):
        pool = Buffers()
        stale = pool.begin(1, 0, 1)
        pool.cancel()
        fresh = pool.begin(1, 0, 1)
        self.assertNotEqual(stale, fresh)
        with self.assertRaises(ValueError):
            pool.commit(stale, Generation(1, 1, 1000, 8192, 2000), complete=True)

    def test_incomplete_commit_preserves_old_generation(self):
        pool = Buffers()
        old = self.commit(pool, 1, 1)
        candidate = pool.begin(1, 4, 0x1234)
        with self.assertRaises(ValueError):
            pool.commit(candidate, Generation(1, 2, 999, 8192, 2000), complete=False)
        self.assertIs(pool.current[0], old)
        self.assertEqual(len(pool.generations), 1)

    def test_project_epoch_rejects_stale_and_quarantines_old_readers(self):
        pool = Buffers()
        old = self.commit(pool, 1, 1)
        candidate = pool.begin(2, 0, 0x1234)
        pool.project_change()
        self.assertEqual(pool.current, [None] * 4)
        self.assertIs(pool.generations[0], old)
        with self.assertRaises(ValueError):
            pool.commit(candidate, Generation(1, 2, 999, 8192, 2000), complete=True)

    def test_memory_and_generation_failure_retain_committed_audio(self):
        for options in (dict(max_bytes=8192), dict(max_generations=1)):
            pool = Buffers(**options)
            old = self.commit(pool, 1, 1)
            candidate = pool.begin(1, 0, 0x1234)
            with self.assertRaises(ValueError):
                pool.admit(candidate, 8192)
            self.assertIs(pool.current[0], old)

    def test_ids_cannot_be_reissued_and_empty_state_is_explicit(self):
        pool = Buffers()
        self.assertEqual(pool.status(4), "EMPTY")
        self.commit(pool, 1, 1)
        candidate = pool.begin(2, 0, 0x1234)
        with self.assertRaises(ValueError):
            pool.commit(candidate, Generation(1, 1, 999, 8192, 2000), complete=True)

    def test_project_writer_refuses_volatile_references(self):
        pool = Buffers()
        self.assertTrue(pool.save_allowed([1, 2, 3], [100, 101, 102, 103]))
        with self.assertRaisesRegex(ValueError, "PROJECT NOT SAVED"):
            pool.save_allowed([1, 100], [100, 101, 102, 103])
