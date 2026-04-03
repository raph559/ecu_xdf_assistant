from __future__ import annotations


def judgement_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["accept", "review", "reject"]},
            "semantic_guess": {"type": "string"},
            "confidence": {"type": "number"},
            "x_axis_kind": {"type": "string"},
            "y_axis_kind": {"type": "string"},
            "units_hint": {"type": "string"},
            "scale_candidates": {
                "type": "array",
                "items": {"type": "string"},
            },
            "notes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "conflicts": {
                "type": "array",
                "items": {"type": "string"},
            },
            "evidence_summary": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reject_reason": {"type": "string"},
        },
        "required": [
            "candidate_id",
            "verdict",
            "semantic_guess",
            "confidence",
            "x_axis_kind",
            "y_axis_kind",
            "units_hint",
            "scale_candidates",
            "notes",
            "conflicts",
            "evidence_summary",
            "reject_reason",
        ],
        "additionalProperties": False,
    }
