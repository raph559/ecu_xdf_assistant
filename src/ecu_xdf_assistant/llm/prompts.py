from __future__ import annotations

import json
from typing import Any, Dict


SYSTEM_PROMPT = """You are an ECU firmware calibration classifier.
You never invent addresses, dimensions, or XML.
You only judge structured evidence and return valid JSON that matches the schema exactly.
Prefer conservative verdicts when evidence is weak or conflicting.
Use 'accept' only when the candidate is plausibly useful for tuning.
Use 'review' when the candidate is interesting but still ambiguous.
Use 'reject' when the candidate is probably not a tuning object."""


def build_candidate_prompt(candidate_payload: Dict[str, Any], schema: Dict[str, Any]) -> str:
    return (
        "Classify this ECU candidate for tuning usefulness.\n\n"
        "Rules:\n"
        "- Do not invent missing data.\n"
        "- Only use the evidence provided.\n"
        "- Confidence must be 0.0 to 1.0.\n"
        "- Keep notes short and concrete.\n"
        "- Scale candidates must be simple expressions like X, X*0.03125, X/10, (X-32768)*0.01.\n\n"
        "Expected JSON schema:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        "Candidate evidence:\n"
        f"{json.dumps(candidate_payload, indent=2)}\n"
    )
