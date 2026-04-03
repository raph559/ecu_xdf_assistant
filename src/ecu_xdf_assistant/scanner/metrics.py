from __future__ import annotations

import math
from typing import Iterable, List


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def monotonicity_score(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    non_decreasing = sum(1 for left, right in zip(values, values[1:]) if right >= left)
    return non_decreasing / (len(values) - 1)


def uniqueness_ratio(values: List[float]) -> float:
    if not values:
        return 0.0
    return len(set(values)) / len(values)


def step_consistency_score(values: List[float]) -> float:
    if len(values) < 3:
        return 0.0
    steps = [b - a for a, b in zip(values, values[1:])]
    mean = sum(steps) / len(steps)
    variance = sum((step - mean) ** 2 for step in steps) / len(steps)
    if math.isclose(mean, 0.0) and math.isclose(variance, 0.0):
        return 0.0
    normalized = 1.0 / (1.0 + variance / (abs(mean) + 1.0))
    return clamp01(normalized)


def variance_score(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return clamp01(1.0 - math.exp(-variance / (abs(mean) + 1.0)))


def matrix_smoothness_score(matrix: List[List[float]]) -> float:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if rows < 2 or cols < 2:
        return 0.0
    penalty = 0.0
    comparisons = 0
    for r in range(rows):
        for c in range(cols):
            if r + 1 < rows:
                penalty += abs(matrix[r][c] - matrix[r + 1][c])
                comparisons += 1
            if c + 1 < cols:
                penalty += abs(matrix[r][c] - matrix[r][c + 1])
                comparisons += 1
    mean_value = sum(abs(v) for row in matrix for v in row) / max(1, rows * cols)
    normalized_penalty = penalty / max(1, comparisons) / (mean_value + 1.0)
    return clamp01(1.0 / (1.0 + normalized_penalty))


def gradient_structure_score(matrix: List[List[float]]) -> float:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if rows < 2 or cols < 2:
        return 0.0

    row_monotonic = []
    for row in matrix:
        row_monotonic.append(monotonicity_score(row))

    col_monotonic = []
    for c in range(cols):
        col = [matrix[r][c] for r in range(rows)]
        col_monotonic.append(monotonicity_score(col))

    return clamp01((sum(row_monotonic) / len(row_monotonic) + sum(col_monotonic) / len(col_monotonic)) / 2.0)


def entropy_like_score(values: Iterable[float]) -> float:
    bucket_counts = {}
    total = 0
    for value in values:
        bucket = int(value) // 4
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        total += 1
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in bucket_counts.values():
        p = count / total
        entropy -= p * math.log(p, 2)
    max_entropy = math.log(max(2, len(bucket_counts)), 2)
    if math.isclose(max_entropy, 0.0):
        return 0.0
    return clamp01(entropy / max_entropy)
