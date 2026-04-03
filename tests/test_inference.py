import tempfile
import unittest
from pathlib import Path

from ecu_xdf_assistant.config import ProjectConfig, ScannerConfig
from ecu_xdf_assistant.inference import filter_scan_result_by_endianness, infer_target
from ecu_xdf_assistant.scanner import BinaryImage, run_scan


class InferenceTests(unittest.TestCase):
    def test_infer_target_prefers_little_endian_and_arm_signatures(self):
        axis_x = [i * 500 for i in range(8)]
        axis_y = [i * 10 for i in range(8)]
        matrix = []
        for r in range(8):
            for c in range(8):
                matrix.append((r * 20) + (c * 5))

        blob = bytearray()
        blob += (b"\x2d\xe9\xf0\x41" + b"\x10\xb5" + b"\x70\x47") * 32
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
                architecture="auto",
                endianness="auto",
                scanner=ScannerConfig(
                    axis_lengths=[8],
                    table_shapes=[[8, 8]],
                    max_candidates_per_kind=20,
                    element_sizes_bits=[16],
                    signed_modes=[False],
                    axis_search_radius_bytes=256,
                ),
            )
            image = BinaryImage.from_file(path)
            result = run_scan(image, config)
            target = infer_target(image, result, config)
            filtered = filter_scan_result_by_endianness(result, target.endianness)

        self.assertEqual(target.endianness, "little")
        self.assertEqual(target.architecture, "arm")
        self.assertTrue(target.ghidra_processor_hint.startswith("ARM:LE"))
        self.assertGreaterEqual(len(filtered.maps), 1)


if __name__ == "__main__":
    unittest.main()
