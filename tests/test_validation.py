import unittest

from ecu_xdf_assistant.config import ProjectConfig
from ecu_xdf_assistant.models import (
    AxisCandidate,
    EvidenceItem,
    GhidraCandidateEvidence,
    GhidraReference,
    LLMJudgement,
    MapCandidate,
)
from ecu_xdf_assistant.validation.validator import validate_candidates


class ValidationTests(unittest.TestCase):
    def test_validate_requires_external_evidence(self):
        axis_x, axis_y, map_candidate = self._build_candidates()

        with self.assertRaisesRegex(ValueError, "Ghidra evidence"):
            validate_candidates(
                config=ProjectConfig(),
                maps=[map_candidate],
                axes=[axis_x, axis_y],
                scalars=[],
                ghidra={},
                llm={},
            )

    def test_validate_accepts_supported_candidate(self):
        axis_x, axis_y, map_candidate = self._build_candidates()
        ghidra = {
            "map_1": GhidraCandidateEvidence(
                candidate_id="map_1",
                address=0x100,
                references_to=[
                    GhidraReference(
                        from_address=0x2000,
                        to_address=0x100,
                        ref_type="DATA",
                        function_name="lookup_main",
                    )
                ],
                lookup_keywords=["fuel", "driver_wish"],
            )
        }
        llm = {
            "map_1": LLMJudgement(
                candidate_id="map_1",
                verdict="accept",
                semantic_guess="fuel_main",
                confidence=0.94,
                units_hint="mg/stk",
                scale_candidates=["X*0.01"],
                evidence_summary=["xref and keyword support"],
            )
        }

        accepted, rejected = validate_candidates(
            config=ProjectConfig(),
            maps=[map_candidate],
            axes=[axis_x, axis_y],
            scalars=[],
            ghidra=ghidra,
            llm=llm,
        )
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 0)

    @staticmethod
    def _build_candidates():
        axis_x = AxisCandidate(
            id="axis_x",
            address=0x10,
            length=8,
            element_size_bits=16,
            endian="little",
            signed=False,
            values_preview=[0, 1, 2, 3],
            monotonicity_score=1.0,
            step_consistency_score=1.0,
            variance_score=1.0,
            confidence=0.9,
            evidence=[EvidenceItem(source="scanner", detail="ok", weight=1.0)],
        )
        axis_y = AxisCandidate(
            id="axis_y",
            address=0x20,
            length=8,
            element_size_bits=16,
            endian="little",
            signed=False,
            values_preview=[0, 1, 2, 3],
            monotonicity_score=1.0,
            step_consistency_score=1.0,
            variance_score=1.0,
            confidence=0.9,
            evidence=[EvidenceItem(source="scanner", detail="ok", weight=1.0)],
        )
        map_candidate = MapCandidate(
            id="map_1",
            address=0x100,
            rows=8,
            cols=8,
            element_size_bits=16,
            endian="little",
            signed=False,
            row_stride_bytes=16,
            data_preview=[[1, 2], [3, 4]],
            smoothness_score=0.9,
            gradient_score=0.9,
            entropy_score=0.7,
            confidence=0.95,
            x_axis_id="axis_x",
            y_axis_id="axis_y",
            evidence=[EvidenceItem(source="scanner", detail="ok", weight=1.0)],
        )
        return axis_x, axis_y, map_candidate


if __name__ == "__main__":
    unittest.main()
