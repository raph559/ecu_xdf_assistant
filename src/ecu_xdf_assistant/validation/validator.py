from __future__ import annotations

from typing import Dict, List, Tuple

from ..config import ProjectConfig
from ..models import (
    AxisCandidate,
    GhidraCandidateEvidence,
    LLMJudgement,
    MapCandidate,
    ScalarCandidate,
    ValidatedCandidate,
)
from .confidence import compute_final_confidence


def validate_candidates(
    config: ProjectConfig,
    maps: List[MapCandidate],
    axes: List[AxisCandidate],
    scalars: List[ScalarCandidate],
    ghidra: Dict[str, GhidraCandidateEvidence],
    llm: Dict[str, LLMJudgement],
) -> Tuple[List[ValidatedCandidate], List[ValidatedCandidate]]:
    if not ghidra:
        raise ValueError("Validation requires Ghidra evidence for candidate review.")
    if not llm:
        raise ValueError("Validation requires LM Studio judgements for candidate review.")

    axis_by_id = {axis.id: axis for axis in axes}
    accepted: List[ValidatedCandidate] = []
    rejected: List[ValidatedCandidate] = []

    for candidate in maps:
        llm_item = llm.get(candidate.id)
        ghidra_item = ghidra.get(candidate.id)
        scores = compute_final_confidence(candidate, ghidra_item, llm_item)
        conflicts = list(llm_item.conflicts) if llm_item else []
        verdict = llm_item.verdict if llm_item else "review"

        x_axis = axis_by_id.get(candidate.x_axis_id or "")
        y_axis = axis_by_id.get(candidate.y_axis_id or "")

        if x_axis and x_axis.length != candidate.cols:
            conflicts.append("x axis length does not match cols")
        if y_axis and y_axis.length != candidate.rows:
            conflicts.append("y axis length does not match rows")

        semantic_guess = llm_item.semantic_guess if llm_item and llm_item.semantic_guess else candidate.semantic_guess
        item = ValidatedCandidate(
            candidate_id=candidate.id,
            candidate_type="map",
            address=candidate.address,
            name=_build_name(semantic_guess, candidate.address),
            semantic_group=_semantic_group(semantic_guess),
            confidence=scores["final"],
            accepted=_is_accepted(config, scores["final"], verdict, conflicts),
            rows=candidate.rows,
            cols=candidate.cols,
            axis_x_address=x_axis.address if x_axis else None,
            axis_y_address=y_axis.address if y_axis else None,
            axis_x_length=x_axis.length if x_axis else None,
            axis_y_length=y_axis.length if y_axis else None,
            element_size_bits=candidate.element_size_bits,
            endian=candidate.endian,
            signed=candidate.signed,
            scale_expression=_pick_scale(llm_item.scale_candidates if llm_item else []),
            units=llm_item.units_hint if llm_item else "",
            source_scores=scores,
            notes=(llm_item.notes if llm_item else []),
            conflicts=conflicts,
        )
        (accepted if item.accepted else rejected).append(item)

    for candidate in scalars:
        llm_item = llm.get(candidate.id)
        ghidra_item = ghidra.get(candidate.id)
        scores = compute_final_confidence(candidate, ghidra_item, llm_item)
        verdict = llm_item.verdict if llm_item else "review"
        semantic_guess = llm_item.semantic_guess if llm_item and llm_item.semantic_guess else candidate.semantic_guess

        has_external_support = ghidra_item is not None or llm_item is not None
        scalar_accepted = (
            has_external_support and
            verdict != "reject" and
            scores["final"] >= config.validation.accept_threshold and
            not (candidate.raw_value == 0 and ghidra_item is None)
        )

        item = ValidatedCandidate(
            candidate_id=candidate.id,
            candidate_type="scalar",
            address=candidate.address,
            name=_build_name(semantic_guess or "scalar", candidate.address),
            semantic_group=_semantic_group(semantic_guess),
            confidence=scores["final"],
            accepted=scalar_accepted,
            element_size_bits=candidate.element_size_bits,
            endian=candidate.endian,
            signed=candidate.signed,
            scale_expression=_pick_scale(llm_item.scale_candidates if llm_item else []),
            units=llm_item.units_hint if llm_item else "",
            source_scores=scores,
            notes=llm_item.notes if llm_item else [],
            conflicts=llm_item.conflicts if llm_item else [],
        )
        (accepted if item.accepted else rejected).append(item)

    accepted.sort(key=lambda item: (-item.confidence, item.address))
    rejected.sort(key=lambda item: (-item.confidence, item.address))
    return accepted, rejected


def _pick_scale(candidates: List[str]) -> str:
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate:
            return candidate
    return "X"


def _build_name(semantic_guess: str, address: int) -> str:
    clean = (semantic_guess or "unknown").strip().replace(" ", "_").replace("/", "_")
    return f"{clean}_0x{address:X}"


def _semantic_group(semantic_guess: str) -> str:
    guess = (semantic_guess or "unknown").lower()
    if "boost" in guess or "turbo" in guess:
        return "boost"
    if "fuel" in guess or "rail" in guess or "lambda" in guess:
        return "fuel"
    if "torque" in guess or "driver" in guess or "limiter" in guess:
        return "torque"
    if "ign" in guess or "spark" in guess:
        return "ignition"
    if "dtc" in guess or "diag" in guess or "switch" in guess:
        return "diagnostics"
    return "generated"


def _is_accepted(config: ProjectConfig, score: float, verdict: str, conflicts: List[str]) -> bool:
    if verdict == "reject":
        return False
    if conflicts:
        return False
    if verdict == "accept" and score >= config.validation.soft_review_threshold:
        return True
    return score >= config.validation.accept_threshold
