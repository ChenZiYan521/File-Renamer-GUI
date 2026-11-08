# -*- coding: utf-8 -*-
"""helpers 纯函数单元测试（不依赖 GUI）。"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import helpers as H


class TestNameLength(unittest.TestCase):
    def test_ascii_boundary_all_platforms(self):
        # 255 个字符单元通过，256 个被拒（Linux 按字节计，ASCII 与码元等价）
        self.assertTrue(H.validate_output_name('a' * 251 + '.png')[0])
        self.assertFalse(H.validate_output_name('a' * 252 + '.png')[0])

    @unittest.skipUnless(os.name == 'nt' or sys.platform == 'darwin',
                         '仅 Windows/macOS 按 UTF-16 码元计长')
    def test_chinese_name_not_limited_by_utf8_bytes(self):
        ok, err = H.validate_output_name('测' * 128 + '.png')
        self.assertTrue(ok, err)
        self.assertFalse(H.validate_output_name('测' * 252 + '.png')[0])

    def test_units_follow_platform(self):
        name = '测' * 4 + '.png'
        expected = 8 if (os.name == 'nt' or sys.platform == 'darwin') else 16
        self.assertEqual(H.name_length_units(name), expected)


class TestBuildName(unittest.TestCase):
    def test_prefix_spaces_are_stripped(self):
        self.assertEqual(H.build_new_filename('1', ' photo ', 'png'), 'photo_1.png')
        self.assertEqual(H.build_new_filename('1', '  ', 'png'), '1.png')
        self.assertEqual(H.build_new_filename('1', 'a b', 'png'), 'a b_1.png')

    def test_extension_dot_is_normalized(self):
        self.assertEqual(H.build_new_filename('7', 'x', '.png'), 'x_7.png')
        self.assertEqual(H.build_new_filename('7', 'x', 'png'), 'x_7.png')


class TestSerial(unittest.TestCase):
    def test_integer_serial_zero_padded(self):
        self.assertEqual(H.build_serial(0, '1', '1', 3), '001')
        self.assertEqual(H.build_serial(41, '1', '1', 2), '42')

    def test_decimal_serial_fixed_digits(self):
        self.assertEqual(H.build_serial(2, '1.0', '0.05', 2), '1.10')

    def test_decimal_mode_detection(self):
        self.assertTrue(H.is_decimal_mode('1.0', '1'))
        self.assertTrue(H.is_decimal_mode('1', '0.1'))
        self.assertFalse(H.is_decimal_mode('1', '2'))

    def test_min_decimal_digits(self):
        self.assertEqual(H.find_min_decimal_digits('1.0', '0.01', 100), 2)
        self.assertIsNone(H.find_min_decimal_digits('1', '1', 100))


class TestValidation(unittest.TestCase):
    def test_invalid_chars_and_control_chars(self):
        self.assertFalse(H.validate_component('a?b')[0])
        self.assertFalse(H.validate_component('a\x01b')[0])
        self.assertTrue(H.validate_component('正常前缀')[0])

    def test_extension_single_dot(self):
        self.assertTrue(H.validate_extension('.png')[0])
        self.assertFalse(H.validate_extension('a.b')[0])

    def test_serial_inputs(self):
        self.assertTrue(H.validate_serial_inputs('1', '1', '2')[0])
        self.assertFalse(H.validate_serial_inputs('-1', '1', '2')[0])
        self.assertFalse(H.validate_serial_inputs('1', '0', '2')[0])
        self.assertFalse(H.validate_serial_inputs('1', '1', '0')[0])
        self.assertFalse(H.validate_serial_inputs('abc', '1', '2')[0])

    def test_reserved_and_trailing_dot(self):
        self.assertFalse(H.validate_output_name('CON.png')[0])
        self.assertFalse(H.validate_output_name('a.png.')[0])
        self.assertFalse(H.validate_output_name('')[0])
        self.assertTrue(H.validate_output_name('a.png')[0])


class TestFilter(unittest.TestCase):
    def test_parse_filter(self):
        self.assertEqual(H.parse_filter('PNG, jpg;.txt'), {'.png', '.jpg', '.txt'})
        self.assertIsNone(H.parse_filter('   '))

    def test_matches_filter(self):
        self.assertTrue(H.matches_filter('A.PNG', 'png'))
        self.assertFalse(H.matches_filter('a.txt', 'png'))
        self.assertTrue(H.matches_filter('a.txt', ''))

    def test_natural_sort(self):
        names = ['file10.png', 'file2.png', 'file1.png']
        self.assertEqual(sorted(names, key=H.natural_sort_key),
                         ['file1.png', 'file2.png', 'file10.png'])


class TestFormat(unittest.TestCase):
    def test_file_size(self):
        self.assertEqual(H.format_file_size(0), '0 B')
        self.assertEqual(H.format_file_size(1536), '1.5 KB')

    def test_time_format(self):
        self.assertRegex(H.format_time(1700000000),
                         r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')


class TestLogRotation(unittest.TestCase):
    def setUp(self):
        self._old_path = H.LOG_PATH
        self._dir = tempfile.mkdtemp()
        H.LOG_PATH = os.path.join(self._dir, 'rename_debug.log')

    def tearDown(self):
        H.LOG_PATH = self._old_path
        for name in os.listdir(self._dir):
            os.remove(os.path.join(self._dir, name))
        os.rmdir(self._dir)

    def test_rotates_when_exceeding_limit(self):
        with open(H.LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('x' * (H.MAX_LOG_BYTES + 1))
        H.log('after rotation')
        self.assertTrue(os.path.exists(H.LOG_PATH + '.1'))
        self.assertLess(os.path.getsize(H.LOG_PATH), 1024)

    def test_does_not_rotate_small_log(self):
        H.log('small')
        self.assertFalse(os.path.exists(H.LOG_PATH + '.1'))
        with open(H.LOG_PATH, encoding='utf-8') as f:
            self.assertIn('small', f.read())


if __name__ == '__main__':
    unittest.main()