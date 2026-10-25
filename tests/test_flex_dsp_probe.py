"""Negative lifecycle controls for a host oracle, never firmware claims."""

import unittest

from lab.flex_dsp_probe import DoubleBuffer


class DoubleBufferTests(unittest.TestCase):
    def ready(self, pool, index):
        token = pool.begin(index, 2)
        for page in range(2):
            pool.page(token, page)
        pool.commit(token)
        return token

    def test_incomplete_cannot_select_or_pin(self):
        pool = DoubleBuffer([8192])
        token = pool.begin(0, 2)
        pool.page(token, 0)
        for action in (pool.commit, pool.select, pool.pin):
            with self.assertRaises(ValueError):
                action(token)

    def test_swap_preserves_old_reader_and_generation(self):
        pool = DoubleBuffer([8192, 8192])
        old = self.ready(pool, 0)
        pool.select(old)
        pool.pin(old)
        new = self.ready(pool, 1)
        pool.select(new)
        with self.assertRaises(ValueError):
            pool.retire(old)
        with self.assertRaises(ValueError):
            pool.begin(0, 2)
        pool.unpin(old)
        pool.retire(old)
        self.assertNotEqual(pool.begin(0, 2), old)
        with self.assertRaises(ValueError):
            pool.pin(old)

    def test_project_change_keeps_readers_and_rejects_stale_requests(self):
        pool = DoubleBuffer([8192])
        token = self.ready(pool, 0)
        pool.select(token)
        pool.pin(token)
        pool.project_change()
        with self.assertRaises(ValueError):
            pool.select(token)
        with self.assertRaises(ValueError):
            pool.retire(token)
        pool.unpin(token)
        pool.retire(token)

    def test_exhaustion_and_selected_root(self):
        pool = DoubleBuffer([8192])
        with self.assertRaises(ValueError):
            pool.begin(0, 3)
        token = self.ready(pool, 0)
        pool.select(token)
        with self.assertRaises(ValueError):
            pool.retire(token)
