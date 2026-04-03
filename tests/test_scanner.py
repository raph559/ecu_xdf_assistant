import tempfile
import unittest
from pathlib import Path

from ecu_xdf_assistant.config import ProjectConfig, ScannerConfig
from ecu_xdf_assistant.scanner import BinaryImage, run_scan


class ScannerTests(unittest.TestCase):
    def test_scan_finds_axis_and_map(self):
        axis_x = [i * 500 for i in range(8)]
        axis_y = [i * 10 for i in range(8)]
        matrix = []
        for r in range(8):
            for c in range(8):
                matrix.append((r * 20) + (c * 5))

        blob = bytearray()
        for value in axis_x:
            blob += int(value).to_bytes(2, "little", signed=False)
        for value in axis_y:
            blob += int(value).to_bytes(2, "little", signed=False)
        for value in matrix:
            blob += int(value).to_bytes(2, "little", signed=False)
        blob += b"\x00" * 128

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware.bin"
            path.write_bytes(bytes(blob))

            config = ProjectConfig(
                endianness="little",
                scanner=ScannerConfig(
                    axis_lengths=[8],
                    table_shapes=[[8, 8]],
                    max_candidates_per_kind=20,
                    element_sizes_bits=[16],
                    signed_modes=[False],
                    axis_search_radius_bytes=256,
                ),
            )
            result = run_scan(BinaryImage.from_file(path), config)

        self.assertGreaterEqual(len(result.axes), 1)
        self.assertGreaterEqual(len(result.maps), 1)


if __name__ == "__main__":
    unittest.main()
