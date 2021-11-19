import unittest

import pyrt


class TestAllocator(unittest.TestCase):
    def test_free(self):
        a = pyrt.Allocator()
        a.free(0, 1)
        self.assertSetEqual(set(a.free_ranges), {(0, 1)})
        a.free(2, 3)
        self.assertSetEqual(set(a.free_ranges), {(0, 1), (2, 3)})
        a.free(1, 2)
        self.assertSetEqual(set(a.free_ranges), {(0, 3)})
        a.free(8, 10)
        self.assertSetEqual(set(a.free_ranges), {(0, 3), (8, 10)})
        a.free(7, 9)
        self.assertSetEqual(set(a.free_ranges), {(0, 3), (7, 10)})
        a.free(2, 11)
        self.assertSetEqual(set(a.free_ranges), {(0, 11)})

    def test_alloc_notail(self):
        a = pyrt.Allocator([(0, 20), (30, 90)])
        self.assertTupleEqual(a.alloc(10), (0, 10))
        self.assertSetEqual(set(a.free_ranges), {(10, 20), (30, 90)})
        self.assertTupleEqual(a.alloc(10, 16), (32, 42))
        self.assertSetEqual(set(a.free_ranges), {(10, 20), (30, 32), (42, 90)})
        self.assertRaises(pyrt.AllocatorOutOfFreeRanges, a.alloc, 50)
        self.assertRaises(pyrt.AllocatorOutOfFreeRanges, a.alloc, 49)
        self.assertTupleEqual(a.alloc(48), (42, 90))
        self.assertSetEqual(set(a.free_ranges), {(10, 20), (30, 32)})

    def test_alloc_withtail(self):
        a = pyrt.Allocator([(0, 20), (30, 90)], 100)
        self.assertTupleEqual(a.alloc(10), (0, 10))
        self.assertSetEqual(set(a.free_ranges), {(10, 20), (30, 90)})
        self.assertTupleEqual(a.alloc(10, 16), (32, 42))
        self.assertSetEqual(set(a.free_ranges), {(10, 20), (30, 32), (42, 90)})
        self.assertTupleEqual(a.alloc(50), (100, 150))
        self.assertEqual(a.tail_range_start, 150)
        self.assertTupleEqual(a.alloc(100, 16), (160, 260))
        self.assertEqual(a.tail_range_start, 260)
        self.assertSetEqual(set(a.free_ranges), {(10, 20), (30, 32), (42, 90), (150, 160)})
