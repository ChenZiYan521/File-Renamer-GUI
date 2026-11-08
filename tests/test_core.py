# -*- coding: utf-8 -*-
"""rename_core 纯逻辑单元测试（不依赖 GUI）。"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import rename_core


def files_of(directory):
    result = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        st = os.stat(path)
        result.append({
            'name': name,
            'size': st.st_size,
            'mtime': st.st_mtime,
            'mtime_ns': st.st_mtime_ns,
            'type': os.path.splitext(name)[1],
        })
    return result


class CoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, mapping):
        for name, content in mapping.items():
            with open(os.path.join(self.dir, name), 'w', encoding='utf-8') as f:
                f.write(content)

    def _names(self):
        return sorted(os.listdir(self.dir))

    # ---------------- 映射生成 ----------------
    def test_build_mappings_integer_mode(self):
        files = [{'name': 'b.png'}, {'name': 'a.png'}]
        mappings = rename_core.build_mappings(files, '1', '1', 2, 'img', 'png')
        self.assertEqual(mappings, [('b.png', 'img_01.png'), ('a.png', 'img_02.png')])

    def test_build_mappings_decimal_and_spaces(self):
        files = [{'name': 'a.png'}, {'name': 'b.png'}]
        mappings = rename_core.build_mappings(files, '1.0', '0.05', 2, ' s ', 'png')
        self.assertEqual(mappings, [('a.png', 's_1.00.png'), ('b.png', 's_1.05.png')])

    # ---------------- 签名 ----------------
    def test_signature_detects_size_change(self):
        self._make({'a.png': 'x'})
        before = files_of(self.dir)
        sig1 = rename_core.compute_signature(before, ('p',))
        self._make({'a.png': 'yy'})
        after = files_of(self.dir)
        sig2 = rename_core.compute_signature(after, ('p',))
        self.assertNotEqual(sig1, sig2)

    # ---------------- 目录快照 / 差异 ----------------
    def test_snapshot_ignores_directories(self):
        self._make({'a.png': 'x'})
        os.makedirs(os.path.join(self.dir, 'sub'))
        snapshot = rename_core.snapshot_directory(self.dir)
        self.assertEqual(sorted(snapshot), ['a.png'])
        self.assertEqual(len(snapshot['a.png']), 2)

    def test_detect_no_change(self):
        self._make({'a.png': 'x'})
        baseline = rename_core.snapshot_directory(self.dir)
        result = rename_core.detect_directory_changes(self.dir, baseline)
        self.assertFalse(result['changed'])

    def test_detect_added_and_removed(self):
        self._make({'a.png': 'x', 'b.png': 'x'})
        baseline = rename_core.snapshot_directory(self.dir)
        os.remove(os.path.join(self.dir, 'b.png'))
        self._make({'c.png': 'x'})
        result = rename_core.detect_directory_changes(self.dir, baseline)
        self.assertTrue(result['changed'])
        self.assertEqual(result['added'], ['c.png'])
        self.assertEqual(result['removed'], ['b.png'])

    def test_detect_modified_by_mtime_and_size(self):
        self._make({'a.png': 'x'})
        baseline = rename_core.snapshot_directory(self.dir)
        st = os.stat(os.path.join(self.dir, 'a.png'))
        os.utime(os.path.join(self.dir, 'a.png'),
                 ns=(st.st_atime_ns, st.st_mtime_ns + 600_000_000))
        result = rename_core.detect_directory_changes(self.dir, baseline)
        self.assertEqual(result['modified'], ['a.png'])

    def test_detect_respects_filter(self):
        self._make({'a.png': 'x'})
        baseline = rename_core.snapshot_directory(self.dir)
        self._make({'note.txt': 'x'})
        result = rename_core.detect_directory_changes(self.dir, baseline, 'png')
        self.assertFalse(result['changed'])

    def test_detect_unreadable_directory(self):
        baseline = rename_core.snapshot_directory(self.dir)
        result = rename_core.detect_directory_changes(
            os.path.join(self.dir, 'missing'), baseline)
        self.assertTrue(result['changed'])
        self.assertIsNotNone(result['error'])

    # ---------------- 冲突检测 ----------------
    def test_duplicate_targets(self):
        self._make({'a.png': 'x', 'b.png': 'x'})
        conflicts = rename_core.detect_conflicts(
            [('a.png', '1.png'), ('b.png', '1.png')], self.dir)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['type'], 'duplicate')
        self.assertEqual(conflicts[0]['sources'], ['a.png', 'b.png'])

    def test_overwrite_existing_file(self):
        self._make({'a.png': 'x', 'keep.png': 'x'})
        conflicts = rename_core.detect_conflicts([('a.png', 'keep.png')], self.dir)
        self.assertEqual([c['type'] for c in conflicts], ['overwrite'])

    def test_swap_has_no_conflict(self):
        self._make({'a.png': 'x', 'b.png': 'x'})
        conflicts = rename_core.detect_conflicts(
            [('a.png', 'b.png'), ('b.png', 'a.png')], self.dir)
        self.assertEqual(conflicts, [])

    @unittest.skipUnless(os.name == 'nt', 'Windows 文件名大小写不敏感')
    def test_case_insensitive_overwrite(self):
        self._make({'a.png': 'x', 'b.png': 'x'})
        conflicts = rename_core.detect_conflicts([('a.png', 'B.PNG')], self.dir)
        self.assertEqual([c['type'] for c in conflicts], ['overwrite'])

    # ---------------- 扩展名统计 ----------------
    def test_count_extension_mismatches(self):
        mappings = [('a.jpg', 'x.png'), ('b.png', 'y.png'), ('noext', 'z.png')]
        self.assertEqual(rename_core.count_extension_mismatches(mappings, 'png'), 1)
        self.assertEqual(rename_core.count_extension_mismatches(mappings, '.PNG'), 1)


if __name__ == '__main__':
    unittest.main()