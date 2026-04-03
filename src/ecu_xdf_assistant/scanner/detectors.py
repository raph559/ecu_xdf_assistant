from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from ..config import ProjectConfig
from ..models import AxisCandidate, EvidenceItem, MapCandidate, ScalarCandidate, ScanResult
from .binary_view import BinaryImage
from .metrics import (
    clamp01,
    entropy_like_score,
    gradient_structure_score,
    monotonicity_score,
    step_consistency_score,
    uniqueness_ratio,
    variance_score,
    matrix_smoothness_score,
)


def _endian_choices(config: ProjectConfig) -> List[str]:
    if config.endianness in {"little", "big"}:
        return [config.endianness]
    return ["little", "big"]


def detect_axes(image: BinaryImage, config: ProjectConfig) -> List[AxisCandidate]:
    found: List[AxisCandidate] = []
    seen_ranges: set[tuple[int, int, int, str, bool]] = set()
    counter = 0
    max_axis_length = max(config.scanner.axis_lengths or [config.scanner.max_axis_length])

    for element_size_bits in config.scanner.element_sizes_bits:
        size_bytes = element_size_bits // 8
        if size_bytes <= 0:
            continue
        offsets = range(0, max(0, image.size - size_bytes * config.scanner.min_axis_length + 1), size_bytes)
        for endian in _endian_choices(config):
            for signed in config.scanner.signed_modes:
                for offset in offsets:
                    for length in config.scanner.axis_lengths:
                        total_bytes = length * size_bytes
                        if not image.contains_range(offset, total_bytes):
                            continue
                        key = (offset, length, element_size_bits, endian, signed)
                        if key in seen_ranges:
                            continue
                        try:
                            values = image.read_series(offset, length, size_bytes, endian=endian, signed=signed)
                        except Exception:
                            continue

                        mono = monotonicity_score(values)
                        unique = uniqueness_ratio(values)
                        step_score = step_consistency_score(values)
                        var_score = variance_score(values)

                        if max(values) == min(values):
                            continue
                        if mono < 0.83:
                            continue
                        if unique < 0.5:
                            continue

                        confidence = clamp01(
                            0.45 * mono +
                            0.20 * unique +
                            0.20 * step_score +
                            0.15 * var_score
                        )

                        if confidence < 0.60:
                            continue

                        counter += 1
                        found.append(
                            AxisCandidate(
                                id=f"axis_{counter:05d}",
                                address=offset,
                                length=length,
                                element_size_bits=element_size_bits,
                                endian=endian,
                                signed=signed,
                                values_preview=values[: min(8, len(values))],
                                monotonicity_score=mono,
                                step_consistency_score=step_score,
                                variance_score=var_score,
                                confidence=confidence,
                                evidence=[
                                    EvidenceItem(source="scanner", detail=f"monotonicity={mono:.3f}", weight=mono),
                                    EvidenceItem(source="scanner", detail=f"unique={unique:.3f}", weight=unique),
                                    EvidenceItem(source="scanner", detail=f"step={step_score:.3f}", weight=step_score),
                                ],
                            )
                        )
                        seen_ranges.add(key)

    found.sort(key=lambda item: (-item.confidence, item.address, item.length))
    return _dedupe_axes(found, max_items=config.scanner.max_candidates_per_kind)


def _dedupe_axes(candidates: List[AxisCandidate], max_items: int) -> List[AxisCandidate]:
    accepted: List[AxisCandidate] = []
    occupied: List[tuple[int, int]] = []
    for candidate in candidates:
        start = candidate.address
        end = start + candidate.length * (candidate.element_size_bits // 8)
        overlapping = False
        for other_start, other_end in occupied:
            overlap_start = max(start, other_start)
            overlap_end = min(end, other_end)
            if overlap_start < overlap_end:
                overlapping = True
                break
        if overlapping:
            continue
        accepted.append(candidate)
        occupied.append((start, end))
        if len(accepted) >= max_items:
            break
    return accepted


def detect_maps(image: BinaryImage, config: ProjectConfig, axes: List[AxisCandidate]) -> List[MapCandidate]:
    found: List[MapCandidate] = []
    counter = 0
    axes_by_length: Dict[int, List[AxisCandidate]] = {}
    for axis in axes:
        axes_by_length.setdefault(axis.length, []).append(axis)

    for element_size_bits in config.scanner.element_sizes_bits:
        size_bytes = element_size_bits // 8
        if size_bytes <= 0:
            continue
        step = size_bytes
        for endian in _endian_choices(config):
            for signed in config.scanner.signed_modes:
                for rows, cols in config.scanner.table_shapes:
                    total_bytes = rows * cols * size_bytes
                    for offset in range(0, max(0, image.size - total_bytes + 1), step):
                        if not image.contains_range(offset, total_bytes):
                            continue
                        try:
                            matrix = image.read_matrix(offset, rows, cols, size_bytes, endian=endian, signed=signed)
                        except Exception:
                            continue
                        flattened = [value for row in matrix for value in row]
                        if max(flattened) == min(flattened):
                            continue

                        smooth = matrix_smoothness_score(matrix)
                        grad = gradient_structure_score(matrix)
                        entropy = entropy_like_score(flattened)

                        if smooth < 0.40 or grad < 0.55:
                            continue

                        confidence = clamp01(0.45 * smooth + 0.35 * grad + 0.20 * entropy)
                        if confidence < 0.58:
                            continue

                        x_axis, y_axis = _find_nearest_axes(offset, rows, cols, axes_by_length, config.scanner.axis_search_radius_bytes)
                        counter += 1
                        evidence = [
                            EvidenceItem(source="scanner", detail=f"smoothness={smooth:.3f}", weight=smooth),
                            EvidenceItem(source="scanner", detail=f"gradient={grad:.3f}", weight=grad),
                            EvidenceItem(source="scanner", detail=f"entropy={entropy:.3f}", weight=entropy),
                        ]
                        if x_axis:
                            evidence.append(EvidenceItem(source="scanner", detail=f"paired_x_axis={x_axis.id}", weight=x_axis.confidence))
                        if y_axis:
                            evidence.append(EvidenceItem(source="scanner", detail=f"paired_y_axis={y_axis.id}", weight=y_axis.confidence))

                        found.append(
                            MapCandidate(
                                id=f"map_{counter:05d}",
                                address=offset,
                                rows=rows,
                                cols=cols,
                                element_size_bits=element_size_bits,
                                endian=endian,
                                signed=signed,
                                row_stride_bytes=cols * size_bytes,
                                data_preview=[row[: min(8, len(row))] for row in matrix[: min(6, len(matrix))]],
                                smoothness_score=smooth,
                                gradient_score=grad,
                                entropy_score=entropy,
                                confidence=confidence,
                                x_axis_id=x_axis.id if x_axis else None,
                                y_axis_id=y_axis.id if y_axis else None,
                                evidence=evidence,
                            )
                        )

    found.sort(key=lambda item: (-item.confidence, item.address, item.rows * item.cols))
    return _dedupe_maps(found, max_items=config.scanner.max_candidates_per_kind)


def _find_nearest_axes(
    map_offset: int,
    rows: int,
    cols: int,
    axes_by_length: Dict[int, List[AxisCandidate]],
    radius: int,
) -> Tuple[AxisCandidate | None, AxisCandidate | None]:
    row_axes = axes_by_length.get(rows, [])
    col_axes = axes_by_length.get(cols, [])

    def pick(candidates: List[AxisCandidate]) -> AxisCandidate | None:
        best = None
        best_dist = None
        for candidate in candidates:
            dist = abs(candidate.address - map_offset)
            if dist > radius:
                continue
            if best is None or dist < best_dist:
                best = candidate
                best_dist = dist
        return best

    y_axis = pick(row_axes)
    x_axis = pick(col_axes)
    return x_axis, y_axis


def _dedupe_maps(candidates: List[MapCandidate], max_items: int) -> List[MapCandidate]:
    accepted: List[MapCandidate] = []
    occupied: List[tuple[int, int]] = []
    for candidate in candidates:
        size = candidate.rows * candidate.cols * (candidate.element_size_bits // 8)
        start = candidate.address
        end = start + size
        overlapping = False
        for other_start, other_end in occupied:
            overlap_start = max(start, other_start)
            overlap_end = min(end, other_end)
            overlap_size = max(0, overlap_end - overlap_start)
            if overlap_size >= size * 0.5:
                overlapping = True
                break
        if overlapping:
            continue
        accepted.append(candidate)
        occupied.append((start, end))
        if len(accepted) >= max_items:
            break
    return accepted


def detect_scalars(image: BinaryImage, config: ProjectConfig) -> List[ScalarCandidate]:
    found: List[ScalarCandidate] = []
    counter = 0
    for element_size_bits in config.scanner.element_sizes_bits:
        size_bytes = element_size_bits // 8
        if size_bytes <= 0:
            continue
        frequency: Dict[tuple[int, str, bool, int], int] = {}
        offsets = list(range(0, max(0, image.size - size_bytes + 1), size_bytes))
        for endian in _endian_choices(config):
            for signed in config.scanner.signed_modes:
                for offset in offsets:
                    value = image.read_int(offset, size_bytes, endian=endian, signed=signed)
                    key = (element_size_bits, endian, signed, value)
                    frequency[key] = frequency.get(key, 0) + 1

        for endian in _endian_choices(config):
            for signed in config.scanner.signed_modes:
                for offset in offsets:
                    value = image.read_int(offset, size_bytes, endian=endian, signed=signed)
                    repeated = frequency.get((element_size_bits, endian, signed, value), 0)
                    if repeated < 4:
                        continue
                    neighborhood = _scalar_neighborhood_score(image, offset, size_bytes, endian, signed)
                    confidence = clamp01(0.55 * min(repeated / 10.0, 1.0) + 0.45 * neighborhood)
                    if confidence < 0.58:
                        continue
                    counter += 1
                    found.append(
                        ScalarCandidate(
                            id=f"scalar_{counter:05d}",
                            address=offset,
                            element_size_bits=element_size_bits,
                            endian=endian,
                            signed=signed,
                            raw_value=value,
                            repeated_count=repeated,
                            neighborhood_score=neighborhood,
                            confidence=confidence,
                            evidence=[
                                EvidenceItem(source="scanner", detail=f"repeated_count={repeated}", weight=min(repeated / 10.0, 1.0)),
                                EvidenceItem(source="scanner", detail=f"neighborhood={neighborhood:.3f}", weight=neighborhood),
                            ],
                        )
                    )

    found.sort(key=lambda item: (-item.confidence, -item.repeated_count, item.address))
    return _dedupe_scalars(found, max_items=config.scanner.max_candidates_per_kind)


def _scalar_neighborhood_score(image: BinaryImage, offset: int, size_bytes: int, endian: str, signed: bool) -> float:
    values = []
    for delta in range(-4 * size_bytes, 5 * size_bytes, size_bytes):
        target = offset + delta
        if target < 0 or not image.contains_range(target, size_bytes):
            continue
        values.append(image.read_int(target, size_bytes, endian=endian, signed=signed))
    if not values:
        return 0.0
    return clamp01(0.5 * uniqueness_ratio(values) + 0.5 * variance_score(values))


def _dedupe_scalars(candidates: List[ScalarCandidate], max_items: int) -> List[ScalarCandidate]:
    accepted: List[ScalarCandidate] = []
    occupied_offsets: set[int] = set()
    for candidate in candidates:
        if candidate.address in occupied_offsets:
            continue
        accepted.append(candidate)
        occupied_offsets.add(candidate.address)
        if len(accepted) >= max_items:
            break
    return accepted


def run_scan(image: BinaryImage, config: ProjectConfig) -> ScanResult:
    axes = detect_axes(image, config)
    maps = detect_maps(image, config, axes)
    scalars = detect_scalars(image, config)
    return ScanResult(
        firmware_size=image.size,
        axes=axes,
        maps=maps,
        scalars=scalars,
    )
