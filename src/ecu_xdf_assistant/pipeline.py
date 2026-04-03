from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from .config import ProjectConfig
from .ghidra.runner import parse_ghidra_evidence, run_ghidra_headless
from .inference import apply_target_inference, filter_scan_result_by_endianness, infer_target
from .jsonio import dump_json, ensure_dir, load_json
from .llm.adjudicator import adjudicate_candidates
from .models import (
    AxisCandidate,
    EvidenceItem,
    GhidraCandidateEvidence,
    LLMJudgement,
    MapCandidate,
    ScalarCandidate,
    ScanResult,
    ValidatedCandidate,
    dataclass_to_dict,
)
from .scanner import BinaryImage, run_scan
from .validation.validator import validate_candidates
from .xdf.writer import write_xdf_bundle


def scan_stage(firmware_path: str | Path, config: ProjectConfig, out_dir: str | Path) -> ScanResult:
    config.require_supported_workflow()
    image = BinaryImage.from_file(firmware_path)
    result = run_scan(image, config)
    target = infer_target(image, result, config)
    apply_target_inference(config, target)
    result = filter_scan_result_by_endianness(result, config.endianness)
    scan_dir = ensure_dir(Path(out_dir) / "scan")
    dump_json(scan_dir / "axis_candidates.json", [dataclass_to_dict(item) for item in result.axes])
    dump_json(scan_dir / "map_candidates.json", [dataclass_to_dict(item) for item in result.maps])
    dump_json(scan_dir / "scalar_candidates.json", [dataclass_to_dict(item) for item in result.scalars])
    dump_json(
        scan_dir / "scan_summary.json",
        {
            "firmware_size": result.firmware_size,
            "axes": len(result.axes),
            "maps": len(result.maps),
            "scalars": len(result.scalars),
            "endianness": config.endianness,
            "architecture": config.architecture,
        },
    )
    dump_json(scan_dir / "target_inference.json", dataclass_to_dict(target))
    dump_json(scan_dir / "candidates_for_ghidra.json", _candidates_for_ghidra(result))
    return result


def ghidra_stage(
    firmware_path: str | Path,
    config: ProjectConfig,
    out_dir: str | Path,
) -> Dict[str, GhidraCandidateEvidence]:
    config.require_ghidra()
    scan_dir = Path(out_dir) / "scan"
    candidates_json = scan_dir / "candidates_for_ghidra.json"
    if not candidates_json.exists():
        raise FileNotFoundError("scan/candidates_for_ghidra.json not found. Run scan first.")
    ghidra_dir = ensure_dir(Path(out_dir) / "ghidra")
    payload = run_ghidra_headless(
        firmware_path=firmware_path,
        config=config,
        out_dir=ghidra_dir,
        candidates_json=candidates_json,
    )
    return parse_ghidra_evidence(payload)


def llm_stage(
    config: ProjectConfig,
    out_dir: str | Path,
    scan_result: ScanResult | None = None,
    ghidra_evidence: Dict[str, GhidraCandidateEvidence] | None = None,
) -> Dict[str, LLMJudgement]:
    config.require_lmstudio()
    if scan_result is None:
        scan_result = _load_scan_result(Path(out_dir) / "scan")
    ghidra_evidence = ghidra_evidence if ghidra_evidence is not None else _load_ghidra_result(Path(out_dir) / "ghidra")
    if not ghidra_evidence:
        raise RuntimeError("Ghidra evidence is required before LM Studio adjudication. Run ghidra-export with a valid Ghidra setup.")
    judgements = adjudicate_candidates(
        config=config,
        maps=scan_result.maps,
        axes=scan_result.axes,
        scalars=scan_result.scalars,
        ghidra_evidence=ghidra_evidence,
    )
    llm_dir = ensure_dir(Path(out_dir) / "llm")
    dump_json(llm_dir / "llm_judgements.json", {key: dataclass_to_dict(value) for key, value in judgements.items()})
    return judgements


def validation_stage(
    config: ProjectConfig,
    out_dir: str | Path,
    scan_result: ScanResult | None = None,
    ghidra_evidence: Dict[str, GhidraCandidateEvidence] | None = None,
    judgements: Dict[str, LLMJudgement] | None = None,
) -> Tuple[List[ValidatedCandidate], List[ValidatedCandidate]]:
    config.require_supported_workflow()
    if scan_result is None:
        scan_result = _load_scan_result(Path(out_dir) / "scan")
    ghidra_evidence = ghidra_evidence if ghidra_evidence is not None else _load_ghidra_result(Path(out_dir) / "ghidra")
    judgements = judgements if judgements is not None else _load_llm_result(Path(out_dir) / "llm")
    if not ghidra_evidence:
        raise RuntimeError("Validation requires Ghidra evidence. Run ghidra-export first.")
    if not judgements:
        raise RuntimeError("Validation requires LM Studio judgements. Run adjudicate first.")

    accepted, rejected = validate_candidates(
        config=config,
        maps=scan_result.maps,
        axes=scan_result.axes,
        scalars=scan_result.scalars,
        ghidra=ghidra_evidence,
        llm=judgements,
    )
    validated_dir = ensure_dir(Path(out_dir) / "validated")
    dump_json(validated_dir / "accepted_candidates.json", [dataclass_to_dict(item) for item in accepted])
    dump_json(validated_dir / "rejected_candidates.json", [dataclass_to_dict(item) for item in rejected])
    dump_json(
        validated_dir / "validation_summary.json",
        {
            "accepted": len(accepted),
            "rejected": len(rejected),
        },
    )
    return accepted, rejected


def xdf_stage(out_dir: str | Path, title: str = "Generated ECU XDF") -> tuple[Path, Path]:
    accepted = load_json(Path(out_dir) / "validated" / "accepted_candidates.json", default=[])
    if not accepted:
        raise RuntimeError("No accepted candidates found. Run validation first.")
    accepted_candidates = [ValidatedCandidate(**item) for item in accepted]
    return write_xdf_bundle(
        output_dir=Path(out_dir) / "xdf",
        accepted_candidates=accepted_candidates,
        title=title,
    )


def full_pipeline(firmware_path: str | Path, config: ProjectConfig, out_dir: str | Path) -> dict:
    config.require_supported_workflow()
    out_dir = ensure_dir(out_dir)
    scan_result = scan_stage(firmware_path=firmware_path, config=config, out_dir=out_dir)
    ghidra_evidence = ghidra_stage(firmware_path=firmware_path, config=config, out_dir=out_dir)
    judgements = llm_stage(config=config, out_dir=out_dir, scan_result=scan_result, ghidra_evidence=ghidra_evidence)
    accepted, rejected = validation_stage(
        config=config,
        out_dir=out_dir,
        scan_result=scan_result,
        ghidra_evidence=ghidra_evidence,
        judgements=judgements,
    )
    xdf_path, sidecar_path = xdf_stage(out_dir=out_dir)
    report_path = write_report(
        out_dir=out_dir,
        scan_result=scan_result,
        ghidra_evidence=ghidra_evidence,
        judgements=judgements,
        accepted=accepted,
        rejected=rejected,
        xdf_path=xdf_path,
        sidecar_path=sidecar_path,
    )
    return {
        "report_path": str(report_path),
        "xdf_path": str(xdf_path),
        "sidecar_path": str(sidecar_path),
    }


def write_report(
    out_dir: str | Path,
    scan_result: ScanResult,
    ghidra_evidence: Dict[str, GhidraCandidateEvidence],
    judgements: Dict[str, LLMJudgement],
    accepted: List[ValidatedCandidate],
    rejected: List[ValidatedCandidate],
    xdf_path: Path,
    sidecar_path: Path,
) -> Path:
    report_path = Path(out_dir) / "report.md"
    top = accepted[:20]
    lines = [
        "# ECU XDF Assistant report",
        "",
        "## Summary",
        f"- firmware size: {scan_result.firmware_size} bytes",
        f"- axis candidates: {len(scan_result.axes)}",
        f"- map candidates: {len(scan_result.maps)}",
        f"- scalar candidates: {len(scan_result.scalars)}",
        f"- ghidra evidence items: {len(ghidra_evidence)}",
        f"- llm judgements: {len(judgements)}",
        f"- accepted candidates: {len(accepted)}",
        f"- rejected candidates: {len(rejected)}",
        "",
        "## Top accepted candidates",
    ]
    for item in top:
        lines.append(
            f"- `{item.name}` at `0x{item.address:X}` | confidence={item.confidence:.3f} | "
            f"group={item.semantic_group} | scale={item.scale_expression}"
        )
    lines.extend(
        [
            "",
            "## Generated files",
            f"- XDF: `{xdf_path}`",
            f"- sidecar: `{sidecar_path}`",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _candidates_for_ghidra(result: ScanResult) -> dict:
    def axis_entry(item: AxisCandidate) -> dict:
        return {
            "id": item.id,
            "address": item.address,
            "length": item.length,
            "element_size_bits": item.element_size_bits,
            "size_bytes": item.length * (item.element_size_bits // 8),
            "stride_bytes": item.element_size_bits // 8,
        }

    def map_entry(item: MapCandidate) -> dict:
        return {
            "id": item.id,
            "address": item.address,
            "rows": item.rows,
            "cols": item.cols,
            "element_size_bits": item.element_size_bits,
            "size_bytes": item.rows * item.cols * (item.element_size_bits // 8),
            "stride_bytes": item.element_size_bits // 8,
        }

    def scalar_entry(item: ScalarCandidate) -> dict:
        return {
            "id": item.id,
            "address": item.address,
            "element_size_bits": item.element_size_bits,
            "size_bytes": item.element_size_bits // 8,
            "stride_bytes": item.element_size_bits // 8,
        }

    return {
        "maps": [map_entry(item) for item in result.maps],
        "axes": [axis_entry(item) for item in result.axes],
        "scalars": [scalar_entry(item) for item in result.scalars],
    }


def _convert_evidence(items: list[dict]) -> list[EvidenceItem]:
    out = []
    for item in items:
        out.append(
            EvidenceItem(
                source=str(item.get("source", "")),
                detail=str(item.get("detail", "")),
                weight=float(item.get("weight", 0.0)),
            )
        )
    return out


def _load_scan_result(scan_dir: Path) -> ScanResult:
    axis_payload = load_json(scan_dir / "axis_candidates.json", default=[])
    map_payload = load_json(scan_dir / "map_candidates.json", default=[])
    scalar_payload = load_json(scan_dir / "scalar_candidates.json", default=[])

    axes = []
    for item in axis_payload:
        item = dict(item)
        item["evidence"] = _convert_evidence(item.get("evidence", []))
        axes.append(AxisCandidate(**item))

    maps = []
    for item in map_payload:
        item = dict(item)
        item["evidence"] = _convert_evidence(item.get("evidence", []))
        maps.append(MapCandidate(**item))

    scalars = []
    for item in scalar_payload:
        item = dict(item)
        item["evidence"] = _convert_evidence(item.get("evidence", []))
        scalars.append(ScalarCandidate(**item))

    summary = load_json(scan_dir / "scan_summary.json", default={})
    return ScanResult(
        firmware_size=int(summary.get("firmware_size", 0)),
        axes=axes,
        maps=maps,
        scalars=scalars,
    )


def _load_ghidra_result(ghidra_dir: Path) -> Dict[str, GhidraCandidateEvidence]:
    payload = load_json(ghidra_dir / "ghidra_evidence.json", default={"candidates": []})
    if not payload:
        return {}
    if "candidates" not in payload:
        return {}
    return parse_ghidra_evidence(payload)


def _load_llm_result(llm_dir: Path) -> Dict[str, LLMJudgement]:
    payload = load_json(llm_dir / "llm_judgements.json", default={})
    out: Dict[str, LLMJudgement] = {}
    for key, value in payload.items():
        out[key] = LLMJudgement(**value)
    return out
