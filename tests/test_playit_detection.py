import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import find_embedded_dash_mp4


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def fragmented_dash_mp4() -> bytes:
    ftyp = box(b"ftyp", b"dash\x00\x00\x00\x00isommp41")
    moov = box(b"moov", box(b"mvex"))
    return ftyp + moov + box(b"sidx", b"\x00" * 8) + box(b"moof")


class EmbeddedDashDetectionTests(unittest.TestCase):
    def test_finds_appended_fragmented_dash_mp4(self):
        prefix = box(b"ftyp", b"isom\x00\x00\x00\x00isom") + box(b"moov") + b"preview"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.mp4"
            path.write_bytes(prefix + fragmented_dash_mp4())
            self.assertEqual(find_embedded_dash_mp4(path), len(prefix))

    def test_finds_marker_across_scan_chunk_boundary(self):
        prefix = b"x" * (1024 * 1024 - 5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boundary.mp4"
            path.write_bytes(prefix + fragmented_dash_mp4())
            self.assertEqual(find_embedded_dash_mp4(path), len(prefix))

    def test_ignores_regular_mp4(self):
        normal = box(b"ftyp", b"isom\x00\x00\x00\x00isom") + box(b"moov") + box(b"mdat", b"data")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "normal.mp4"
            path.write_bytes(normal)
            self.assertIsNone(find_embedded_dash_mp4(path))

    def test_ignores_dash_brand_without_fragmented_mp4_structure(self):
        false_positive = box(b"ftyp", b"dash\x00\x00\x00\x00isom") + box(b"moov", b"not-mvex") + box(b"mdat", b"data")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "not-fragmented.mp4"
            path.write_bytes(false_positive)
            self.assertIsNone(find_embedded_dash_mp4(path))


if __name__ == "__main__":
    unittest.main()
