"""Host tests for the source patch and boundary filter in ad_patch.c.

Most tests run anywhere with a C compiler. The four exact-player tests need the captured
player source, which is Google's code and is not distributed here. Point
AD_GUARD_PLAYER_SOURCE at your own capture (SHA-256 in ../source-pin.json) to run them;
otherwise they are skipped and reported as such.
"""
import ctypes
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'source-pin.json').read_text())
_TMP = tempfile.TemporaryDirectory()
_LIB = pathlib.Path(_TMP.name) / 'host-patch.so'
subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', '-O2', str(ROOT / 'ad_patch.c'), '-o', str(_LIB)], check=True)
LIB = ctypes.CDLL(str(_LIB))
LIB.guard_sha256.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
LIB.guard_patch.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
LIB.guard_patch.restype = ctypes.c_int
LIB.guard_boundary.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
LIB.guard_boundary.restype = ctypes.c_int

LENGTH = PIN['source_length']
OFFSET = PIN['memory_patch']['offset']
ORIGINAL = PIN['memory_patch']['original'].encode()
REPLACEMENT = PIN['memory_patch']['replacement'].encode()


def apply(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return LIB.guard_patch(buf, len(data)), buf.raw[:len(data)]


def load_player():
    path = os.environ.get('AD_GUARD_PLAYER_SOURCE')
    if not path:
        return None
    data = pathlib.Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != PIN['original_sha256']:
        raise AssertionError(f'{path} is not the pinned player source (SHA-256 mismatch)')
    return data


PLAYER = load_player()


class ShaTests(unittest.TestCase):
    def test_matches_standard_vectors_and_padding_boundaries(self):
        for data in [b'', b'abc', b'a' * 55, b'a' * 56, b'a' * 63, b'a' * 64, b'a' * 65, b'a' * 128, b'a' * 1000000]:
            with self.subTest(length=len(data)):
                result = ctypes.create_string_buffer(32)
                LIB.guard_sha256(data, len(data), result)
                self.assertEqual(result.raw, hashlib.sha256(data).digest())


class ConfigTests(unittest.TestCase):
    def test_patch_config_header_matches_source_pin(self):
        header = (ROOT / 'patch_config.h').read_text()
        def array(name):
            return bytes(int(x) for x in re.search(name + r'\[\]=\{([0-9,]+)\}', header).group(1).split(','))
        self.assertEqual(array('guard_expected_hash').hex(), PIN['original_sha256'])
        self.assertEqual(array('guard_original'), ORIGINAL)
        self.assertEqual(array('guard_replacement'), REPLACEMENT)
        self.assertEqual(len(ORIGINAL), len(REPLACEMENT))
        self.assertIn(f'GUARD_SOURCE_LENGTH {LENGTH}u', header)
        self.assertIn(f'GUARD_PATCH_OFFSET {OFFSET}u', header)
        lo, hi = PIN['loader_range']
        self.assertTrue(lo <= OFFSET and OFFSET + len(ORIGINAL) <= hi)


class SyntheticPatchTests(unittest.TestCase):
    def test_right_length_and_statement_but_wrong_digest_is_untouched(self):
        data = bytearray(b' ' * LENGTH)
        data[OFFSET:OFFSET + len(ORIGINAL)] = ORIGINAL
        self.assertEqual(apply(bytes(data)), (0, bytes(data)))

    def test_empty_and_short_inputs_are_untouched(self):
        for data in [b'', ORIGINAL, b' ' * (LENGTH - 1)]:
            self.assertEqual(apply(data), (0, data))


@unittest.skipIf(PLAYER is None, 'set AD_GUARD_PLAYER_SOURCE to the captured player source to run')
class PinnedPlayerTests(unittest.TestCase):
    def expected(self):
        return PLAYER[:OFFSET] + REPLACEMENT + PLAYER[OFFSET + len(ORIGINAL):]

    def test_exact_player_changes_only_the_reviewed_statement(self):
        result, actual = apply(PLAYER)
        self.assertEqual(result, 1)
        self.assertEqual(actual, self.expected())
        self.assertEqual(hashlib.sha256(actual).hexdigest(), PIN['same_length_sha256'])

    def test_unknown_source_with_matching_loader_is_untouched(self):
        changed = bytearray(PLAYER)
        changed[100] ^= 1
        self.assertEqual(apply(bytes(changed)), (0, bytes(changed)))

    def test_truncated_sources_are_untouched(self):
        for data in [PLAYER[:-1], PLAYER[:100]]:
            self.assertEqual(apply(data), (0, data))

    def test_already_patched_source_is_untouched(self):
        patched = self.expected()
        self.assertEqual(apply(patched), (0, patched))


class BoundaryTests(unittest.TestCase):
    def test_only_the_observed_engine_copy_boundary_can_patch(self):
        base = 0xbc100000
        self.assertEqual(LIB.guard_boundary(base + 0x814a6c, base, LENGTH), 1)
        self.assertEqual(LIB.guard_boundary(base + 0x814a6d, base, LENGTH), 1)
        for ret, b, n in [(base + 0x814a68, base, LENGTH), (base + 0x814a6c, base, LENGTH - 1), (base - 1, base, LENGTH), (0, base, LENGTH)]:
            self.assertEqual(LIB.guard_boundary(ret, b, n), 0)


if __name__ == '__main__':
    unittest.main()
