from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_to_dict(item) for key, item in asdict(value).items()}
    return value


@dataclass(slots=True)
class EvidenceItem:
    source: str
    detail: str
    weight: float = 0.0


@dataclass(slots=True)
class AxisCandidate:
    id: str
    address: int
    length: int
    element_size_bits: int
    endian: str
    signed: bool
    values_preview: List[float]
    monotonicity_score: float
    step_consistency_score: float
    variance_score: float
    confidence: float
    units_hint: str = ""
    kind: str = "axis"
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class MapCandidate:
    id: str
    address: int
    rows: int
    cols: int
    element_size_bits: int
    endian: str
    signed: bool
    row_stride_bytes: int
    data_preview: List[List[float]]
    smoothness_score: float
    gradient_score: float
    entropy_score: float
    confidence: float
    x_axis_id: Optional[str] = None
    y_axis_id: Optional[str] = None
    semantic_guess: str = "unknown"
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class ScalarCandidate:
    id: str
    address: int
    element_size_bits: int
    endian: str
    signed: bool
    raw_value: int
    repeated_count: int
    neighborhood_score: float
    confidence: float
    semantic_guess: str = "unknown"
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class ScanResult:
    firmware_size: int
    axes: List[AxisCandidate]
    maps: List[MapCandidate]
    scalars: List[ScalarCandidate]


@dataclass(slots=True)
class GhidraReference:
    from_address: int
    to_address: int
    ref_type: str
    function_name: str = ""
    function_entry: Optional[int] = None


@dataclass(slots=True)
class GhidraFunctionSummary:
    entry: int
    name: str
    body_min: int
    body_max: int
    size: int
    callers: List[int] = field(default_factory=list)
    callees: List[int] = field(default_factory=list)
    decompiled: str = ""


@dataclass(slots=True)
class GhidraCandidateEvidence:
    candidate_id: str
    address: int
    references_to: List[GhidraReference] = field(default_factory=list)
    nearby_functions: List[GhidraFunctionSummary] = field(default_factory=list)
    lookup_keywords: List[str] = field(default_factory=list)

    @property
    def xref_count(self) -> int:
        return len(self.references_to)


@dataclass(slots=True)
class LLMJudgement:
    candidate_id: str
    verdict: str
    semantic_guess: str
    confidence: float
    x_axis_kind: str = ""
    y_axis_kind: str = ""
    units_hint: str = ""
    scale_candidates: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    evidence_summary: List[str] = field(default_factory=list)
    reject_reason: str = ""


@dataclass(slots=True)
class ValidatedCandidate:
    candidate_id: str
    candidate_type: str
    address: int
    name: str
    semantic_group: str
    confidence: float
    accepted: bool
    rows: Optional[int] = None
    cols: Optional[int] = None
    axis_x_address: Optional[int] = None
    axis_y_address: Optional[int] = None
    axis_x_length: Optional[int] = None
    axis_y_length: Optional[int] = None
    element_size_bits: int = 8
    endian: str = "little"
    signed: bool = False
    scale_expression: str = "X"
    units: str = ""
    source_scores: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineArtifacts:
    scan: ScanResult
    ghidra_evidence: Dict[str, GhidraCandidateEvidence] = field(default_factory=dict)
    llm_judgements: Dict[str, LLMJudgement] = field(default_factory=dict)
    validated: List[ValidatedCandidate] = field(default_factory=list)
