from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from .config import ProjectConfig
from .models import AxisCandidate, MapCandidate, ScalarCandidate, ScanResult
from .scanner.binary_view import BinaryImage


@dataclass(slots=True)
class TargetInference:
    endianness: str = "unknown"
    architecture: str = "unknown"
    ghidra_processor_hint: str = ""
    endianness_scores: Dict[str, float] = field(default_factory=dict)
    architecture_scores: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def infer_target(image: BinaryImage, scan_result: ScanResult, config: ProjectConfig) -> TargetInference:
    endianness_scores = _score_endianness(scan_result)
    endianness = _pick_best(endianness_scores, minimum=0.1, margin_ratio=1.10)
    notes: List[str] = []
    if endianness == "unknown":
        notes.append("No clear endianness winner from scanner candidates; keep manual review.")
    else:
        notes.append(f"Scanner candidates favor {endianness}-endian decoding.")

    architecture_scores = _score_architecture(image, endianness)
    architecture = _pick_best(architecture_scores, minimum=3.0, margin_ratio=1.35)
    if architecture == "unknown":
        notes.append("Architecture heuristic is weak for raw binaries; confirm the Ghidra processor manually.")
    else:
        notes.append(f"Signature probe suggests {architecture}.")

    return TargetInference(
        endianness=endianness,
        architecture=architecture,
        ghidra_processor_hint=_ghidra_processor_hint(architecture, endianness),
        endianness_scores=endianness_scores,
        architecture_scores=architecture_scores,
        notes=notes,
    )


def apply_target_inference(config: ProjectConfig, target: TargetInference) -> None:
    if config.endianness in {"", "auto", "unknown"} and target.endianness != "unknown":
        config.endianness = target.endianness
    if config.architecture in {"", "auto", "unknown"} and target.architecture != "unknown":
        config.architecture = target.architecture
    if not config.ghidra.processor and target.ghidra_processor_hint:
        config.ghidra.processor = target.ghidra_processor_hint


def filter_scan_result_by_endianness(scan_result: ScanResult, endianness: str) -> ScanResult:
    if endianness not in {"little", "big"}:
        return scan_result
    return ScanResult(
        firmware_size=scan_result.firmware_size,
        axes=[item for item in scan_result.axes if item.endian == endianness],
        maps=[item for item in scan_result.maps if item.endian == endianness],
        scalars=[item for item in scan_result.scalars if item.endian == endianness],
    )


def _score_endianness(scan_result: ScanResult) -> Dict[str, float]:
    scores = {"little": 0.0, "big": 0.0}
    _accumulate(scores, scan_result.axes, weight=2.0)
    _accumulate(scores, scan_result.maps, weight=5.0)
    _accumulate(scores, scan_result.scalars, weight=1.0)
    return scores


def _accumulate(
    scores: Dict[str, float],
    candidates: Iterable[AxisCandidate | MapCandidate | ScalarCandidate],
    weight: float,
) -> None:
    for candidate in candidates:
        if candidate.endian in scores:
            scores[candidate.endian] += weight * float(candidate.confidence)


def _score_architecture(image: BinaryImage, endianness: str) -> Dict[str, float]:
    data = image.data
    signatures = {
        "arm": [
            (b"\x2d\xe9", 1.4),
            (b"\xf0\xb5", 1.2),
            (b"\x10\xb5", 1.0),
            (b"\xbd\xe8", 1.2),
            (b"\x70\x47", 0.8),
        ],
        "mips": [
            (b"\x27\xbd", 1.3),
            (b"\xaf\xbf", 1.0),
            (b"\x03\xe0\x00\x08", 1.4),
            (b"\x8f\xbf", 0.8),
        ],
        "ppc": [
            (b"\x94\x21", 1.3),
            (b"\x7c\x08\x02\xa6", 1.6),
            (b"\x4e\x80\x00\x20", 1.3),
            (b"\x38\x60", 0.7),
        ],
    }

    if endianness == "little":
        signatures["arm"] = [
            (b"\x2d\xe9", 1.4),
            (b"\xf0\xb5", 1.2),
            (b"\x10\xb5", 1.0),
            (b"\xbd\xe8", 1.2),
            (b"\x70\x47", 0.8),
        ]
        signatures["mips"] = [
            (b"\xbd\x27", 1.3),
            (b"\xbf\xaf", 1.0),
            (b"\x08\x00\xe0\x03", 1.4),
            (b"\xbf\x8f", 0.8),
        ]
        signatures["ppc"] = [
            (b"\x21\x94", 1.3),
            (b"\xa6\x02\x08\x7c", 1.6),
            (b"\x20\x00\x80\x4e", 1.3),
            (b"\x60\x38", 0.7),
        ]

    return {
        architecture: sum(data.count(signature) * weight for signature, weight in items)
        for architecture, items in signatures.items()
    }


def _pick_best(scores: Dict[str, float], minimum: float, margin_ratio: float) -> str:
    if not scores:
        return "unknown"
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_name, best_score = ordered[0]
    runner_up = ordered[1][1] if len(ordered) > 1 else 0.0
    if best_score < minimum:
        return "unknown"
    if runner_up > 0 and best_score < runner_up * margin_ratio:
        return "unknown"
    return best_name


def _ghidra_processor_hint(architecture: str, endianness: str) -> str:
    mapping = {
        ("arm", "little"): "ARM:LE:32:v7",
        ("arm", "big"): "ARM:BE:32:v7",
        ("mips", "little"): "MIPS:LE:32:default",
        ("mips", "big"): "MIPS:BE:32:default",
        ("ppc", "little"): "PowerPC:LE:32:default",
        ("ppc", "big"): "PowerPC:BE:32:default",
    }
    return mapping.get((architecture, endianness), "")
