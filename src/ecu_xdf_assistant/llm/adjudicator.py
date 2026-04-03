from __future__ import annotations

from typing import Dict, Iterable, List

from ..config import ProjectConfig
from ..models import AxisCandidate, GhidraCandidateEvidence, LLMJudgement, MapCandidate, ScalarCandidate
from .lmstudio_client import LMStudioClient
from .prompts import SYSTEM_PROMPT, build_candidate_prompt
from .schema import judgement_schema


def _candidate_to_payload(
    candidate: MapCandidate | AxisCandidate | ScalarCandidate,
    ghidra: GhidraCandidateEvidence | None,
) -> dict:
    payload = {
        "candidate": {
            "id": getattr(candidate, "id"),
            "address": getattr(candidate, "address"),
            "confidence": getattr(candidate, "confidence"),
            "type": candidate.__class__.__name__,
        },
        "scanner_evidence": {
            "evidence": [
                {
                    "source": item.source,
                    "detail": item.detail,
                    "weight": item.weight,
                }
                for item in getattr(candidate, "evidence", [])
            ]
        },
        "ghidra_evidence": {
            "xref_count": ghidra.xref_count if ghidra else 0,
            "lookup_keywords": ghidra.lookup_keywords if ghidra else [],
            "references_to": [
                {
                    "from_address": item.from_address,
                    "to_address": item.to_address,
                    "ref_type": item.ref_type,
                    "function_name": item.function_name,
                    "function_entry": item.function_entry,
                }
                for item in (ghidra.references_to if ghidra else [])
            ],
            "nearby_functions": [
                {
                    "entry": item.entry,
                    "name": item.name,
                    "size": item.size,
                    "decompiled": item.decompiled,
                }
                for item in (ghidra.nearby_functions if ghidra else [])
            ],
        },
    }
    if isinstance(candidate, MapCandidate):
        payload["candidate"].update(
            {
                "rows": candidate.rows,
                "cols": candidate.cols,
                "element_size_bits": candidate.element_size_bits,
                "endian": candidate.endian,
                "signed": candidate.signed,
                "x_axis_id": candidate.x_axis_id,
                "y_axis_id": candidate.y_axis_id,
                "data_preview": candidate.data_preview,
                "smoothness_score": candidate.smoothness_score,
                "gradient_score": candidate.gradient_score,
                "entropy_score": candidate.entropy_score,
            }
        )
    elif isinstance(candidate, AxisCandidate):
        payload["candidate"].update(
            {
                "length": candidate.length,
                "element_size_bits": candidate.element_size_bits,
                "endian": candidate.endian,
                "signed": candidate.signed,
                "values_preview": candidate.values_preview,
                "monotonicity_score": candidate.monotonicity_score,
                "step_consistency_score": candidate.step_consistency_score,
                "variance_score": candidate.variance_score,
            }
        )
    else:
        payload["candidate"].update(
            {
                "element_size_bits": candidate.element_size_bits,
                "endian": candidate.endian,
                "signed": candidate.signed,
                "raw_value": candidate.raw_value,
                "repeated_count": candidate.repeated_count,
                "neighborhood_score": candidate.neighborhood_score,
            }
        )
    return payload


def adjudicate_candidates(
    config: ProjectConfig,
    maps: List[MapCandidate],
    axes: List[AxisCandidate],
    scalars: List[ScalarCandidate],
    ghidra_evidence: Dict[str, GhidraCandidateEvidence],
) -> Dict[str, LLMJudgement]:
    config.require_lmstudio()
    if not ghidra_evidence:
        raise ValueError("Ghidra evidence is required before running LM Studio adjudication.")

    client = LMStudioClient(
        host=config.lmstudio.host,
        timeout_seconds=config.lmstudio.timeout_seconds,
    )
    schema = judgement_schema()
    judgements: Dict[str, LLMJudgement] = {}

    selected = []
    selected.extend(maps[: config.lmstudio.top_n_maps])
    selected.extend(axes[: config.lmstudio.top_n_maps])
    selected.extend(scalars[: config.lmstudio.top_n_scalars])

    for candidate in selected:
        prompt = build_candidate_prompt(
            candidate_payload=_candidate_to_payload(candidate, ghidra_evidence.get(candidate.id)),
            schema=schema,
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = client.chat_structured(
            model=config.lmstudio.model,
            messages=messages,
            schema=schema,
            temperature=config.lmstudio.temperature,
        )
        judgement = LLMJudgement(
            candidate_id=str(response.get("candidate_id", candidate.id)),
            verdict=str(response.get("verdict", "review")),
            semantic_guess=str(response.get("semantic_guess", "unknown")),
            confidence=float(response.get("confidence", 0.0)),
            x_axis_kind=str(response.get("x_axis_kind", "")),
            y_axis_kind=str(response.get("y_axis_kind", "")),
            units_hint=str(response.get("units_hint", "")),
            scale_candidates=[str(item) for item in response.get("scale_candidates", [])],
            notes=[str(item) for item in response.get("notes", [])],
            conflicts=[str(item) for item in response.get("conflicts", [])],
            evidence_summary=[str(item) for item in response.get("evidence_summary", [])],
            reject_reason=str(response.get("reject_reason", "")),
        )
        judgements[judgement.candidate_id] = judgement

    return judgements
