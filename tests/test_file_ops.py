# -*- coding: utf-8 -*-
"""file_ops 两阶段重命名与回滚的单元测试。"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import file_ops


class FileOpsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, *names):
        for name in names:
            with open(os.path.join(self.dir, name), 'w', encoding='utf-8') as f:
                f.write(name)

    def _names(self):
        return sorted(os.listdir(self.dir))

    def test_swapping_names(self):
        self._make('a.png', 'b.png')
        result = file_ops.two_phase_rename(
            self.dir, [('a.png', 'b.png'), ('b.png', 'a.png')])
        self.assertTrue(result['success'])
        self.assertEqual(self._names(), ['a.png', 'b.png'])

    def test_duplicate_target_rolls_back(self):
        self._make('x.png', 'y.png')
        result = file_ops.two_phase_rename(
            self.dir, [('x.png', '1.png'), ('y.png', '1.png')])
        self.assertFalse(result['success'])
        self.assertEqual(self._names(), ['x.png', 'y.png'])

    def test_existing_target_is_not_overwritten(self):
        self._make('x.png', 'keep.png')
        result = file_ops.two_phase_rename(self.dir, [('x.png', 'keep.png')])
        self.assertFalse(result['success'])
        with open(os.path.join(self.dir, 'keep.png'), encoding='utf-8') as f:
            self.assertEqual(f.read(), 'keep.png')

    def test_missing_source_rolls_back(self):
        self._make('x.png')
        result = file_ops.two_phase_rename(
            self.dir, [('nope.png', '1.png'), ('x.png', '2.png')])
        self.assertFalse(result['success'])
        self.assertEqual(self._names(), ['x.png'])

    def test_cancel_rolls_back_all(self):
        self._make('a.png', 'b.png', 'c.png')
        state = {'n': 0}

        def cancel():
            state['n'] += 1
            return state['n'] > 2

        result = file_ops.two_phase_rename(
            self.dir,
            [('a.png', '1.png'), ('b.png', '2.png'), ('c.png', '3.png')],
            cancel_check=cancel)
        self.assertFalse(result['success'])
        self.assertTrue(result['cancelled'])
        self.assertEqual(self._names(), ['a.png', 'b.png', 'c.png'])

    def test_renamed_pairs_and_progress(self):
        self._make('1.png', '2.png')
        events = []
        result = file_ops.two_phase_rename(
            self.dir,
            [('1.png', 'p_01.png'), ('2.png', 'p_02.png')],
            progress_callback=lambda *a: events.append(a))
        self.assertTrue(result['success'])
        self.assertEqual(result['renamed_pairs'],
                         [('1.png', 'p_01.png'), ('2.png', 'p_02.png')])
        self.assertEqual([e[0] for e in events], [1, 1, 2, 2])
        self.assertTrue(all('__rn_tmp' not in str(e[4]) for e in events))
        self.assertEqual(self._names(), ['p_01.png', 'p_02.png'])

    def test_identity_mapping_is_skipped(self):
        self._make('a.png', 'b.png')
        result = file_ops.two_phase_rename(
            self.dir, [('a.png', 'a.png'), ('b.png', '2.png')])
        self.assertTrue(result['success'])
        self.assertEqual(result['renamed'], 1)
        self.assertEqual(self._names(), ['2.png', 'a.png'])

    def test_case_only_rename(self):
        self._make('photo.png')
        result = file_ops.two_phase_rename(self.dir, [('photo.png', 'PHOTO.PNG')])
        self.assertTrue(result['success'])
        self.assertEqual(self._names(), ['PHOTO.PNG'])

    def test_no_mapping_returns_zero(self):
        self._make('a.png')
        result = file_ops.two_phase_rename(self.dir, [('a.png', 'a.png')])
        self.assertTrue(result['success'])
        self.assertEqual(result['renamed'], 0)
        self.assertEqual(result['renamed_pairs'], [])


if __name__ == '__main__':
    unittest.main()