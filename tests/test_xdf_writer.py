import tempfile
import unittest
from pathlib import Path

from ecu_xdf_assistant.models import ValidatedCandidate
from ecu_xdf_assistant.xdf.writer import write_xdf_bundle


class XdfWriterTests(unittest.TestCase):
    def test_xdf_writer_creates_files(self):
        accepted = [
            ValidatedCandidate(
                candidate_id="map_00001",
                candidate_type="map",
                address=0x100,
                name="fuel_main_0x100",
                semantic_group="fuel",
                confidence=0.91,
                accepted=True,
                rows=8,
                cols=8,
                axis_x_address=0x00,
                axis_y_address=0x10,
                axis_x_length=8,
                axis_y_length=8,
                element_size_bits=16,
                endian="little",
                signed=False,
                scale_expression="X*0.01",
                units="mg/stk",
                source_scores={"final": 0.91},
                notes=["synthetic test"],
                conflicts=[],
            ),
            ValidatedCandidate(
                candidate_id="scalar_00001",
                candidate_type="scalar",
                address=0x500,
                name="rev_limit_0x500",
                semantic_group="torque",
                confidence=0.88,
                accepted=True,
                element_size_bits=16,
                endian="little",
                signed=False,
                scale_expression="X",
                units="rpm",
                source_scores={"final": 0.88},
                notes=["synthetic scalar"],
                conflicts=[],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            xdf_path, sidecar_path = write_xdf_bundle(tmp, accepted)
            self.assertTrue(Path(xdf_path).exists())
            self.assertTrue(Path(sidecar_path).exists())
            text = Path(xdf_path).read_text(encoding="utf-8")
            self.assertIn("XDFTABLE", text)
            self.assertIn("XDFCONSTANT", text)


if __name__ == "__main__":
    unittest.main()
