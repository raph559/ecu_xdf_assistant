from __future__ import annotations

from ..models import AxisCandidate, GhidraCandidateEvidence, LLMJudgement, MapCandidate, ScalarCandidate


def xref_score(ghidra: GhidraCandidateEvidence | None) -> float:
    if ghidra is None:
        return 0.0
    count = ghidra.xref_count
    if count <= 0:
        return 0.0
    return min(count / 5.0, 1.0)


def keyword_score(ghidra: GhidraCandidateEvidence | None) -> float:
    if ghidra is None:
        return 0.0
    if not ghidra.lookup_keywords:
        return 0.0
    return min(len(ghidra.lookup_keywords) / 4.0, 1.0)


def compute_final_confidence(
    candidate: MapCandidate | AxisCandidate | ScalarCandidate,
    ghidra: GhidraCandidateEvidence | None,
    llm: LLMJudgement | None,
) -> dict[str, float]:
    scanner = getattr(candidate, "confidence", 0.0)
    xrefs = xref_score(ghidra)
    keywords = keyword_score(ghidra)
    llm_score = llm.confidence if llm else 0.0

    weighted_sum = 0.0
    total_weight = 0.0

    weighted_sum += scanner * 0.55
    total_weight += 0.55

    if ghidra is not None:
        weighted_sum += xrefs * 0.25
        weighted_sum += keywords * 0.05
        total_weight += 0.30

    if llm is not None:
        weighted_sum += llm_score * 0.15
        total_weight += 0.15

    final_score = weighted_sum / total_weight if total_weight else 0.0

    return {
        "scanner": scanner,
        "xref": xrefs,
        "keyword": keywords,
        "llm": llm_score,
        "final": max(0.0, min(1.0, final_score)),
    }
