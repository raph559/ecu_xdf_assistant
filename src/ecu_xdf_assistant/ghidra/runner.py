from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List

from ..config import ProjectConfig
from ..jsonio import ensure_dir, dump_json, load_json
from ..models import GhidraCandidateEvidence, GhidraFunctionSummary, GhidraReference


def build_analyze_headless_command(
    firmware_path: str | Path,
    config: ProjectConfig,
    project_root: str | Path,
    script_dir: str | Path,
    output_json: str | Path,
    candidates_json: str | Path,
) -> List[str]:
    ghidra_install_dir = Path(config.ghidra.install_dir)
    executable = ghidra_install_dir / "support" / ("analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless")
    project_name = "ecu_xdf_assistant_project"

    cmd = [
        str(executable),
        str(Path(project_root).resolve()),
        project_name,
        "-import",
        str(Path(firmware_path).resolve()),
        "-overwrite",
        "-scriptPath",
        str(Path(script_dir).resolve()),
        "-postScript",
        config.ghidra.postscript_name,
        str(Path(output_json).resolve()),
        str(Path(candidates_json).resolve()),
        str(int(config.ghidra.function_decompile_limit)),
    ]

    if config.ghidra.processor:
        cmd.extend(["-processor", config.ghidra.processor])
    if config.ghidra.compiler_spec:
        cmd.extend(["-cspec", config.ghidra.compiler_spec])
    if config.ghidra.extra_import_args:
        cmd.extend(config.ghidra.extra_import_args)

    return cmd


def run_ghidra_headless(
    firmware_path: str | Path,
    config: ProjectConfig,
    out_dir: str | Path,
    candidates_json: str | Path,
) -> Dict[str, object]:
    out_dir = ensure_dir(out_dir)
    output_json = out_dir / "ghidra_evidence.json"
    run_json = out_dir / "ghidra_run.json"
    script_dir = Path(__file__).resolve().parent / "scripts"
    project_root = ensure_dir(Path(config.ghidra.project_dir).expanduser())

    command = build_analyze_headless_command(
        firmware_path=firmware_path,
        config=config,
        project_root=project_root,
        script_dir=script_dir,
        output_json=output_json,
        candidates_json=candidates_json,
    )

    completed = subprocess.run(
        command,
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    run_payload = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_json": str(output_json),
    }
    dump_json(run_json, run_payload)

    if completed.returncode != 0:
        raise RuntimeError(
            "Ghidra headless analysis failed. See ghidra_run.json for stdout/stderr."
        )

    payload = load_json(output_json, default={})
    if not isinstance(payload, dict):
        raise RuntimeError("Ghidra output JSON is missing or invalid.")
    return payload


def parse_ghidra_evidence(payload: Dict[str, object]) -> Dict[str, GhidraCandidateEvidence]:
    evidence_by_id: Dict[str, GhidraCandidateEvidence] = {}
    for entry in payload.get("candidates", []):
        references = []
        for ref in entry.get("references_to", []):
            references.append(
                GhidraReference(
                    from_address=int(ref.get("from_address", 0)),
                    to_address=int(ref.get("to_address", 0)),
                    ref_type=str(ref.get("ref_type", "")),
                    function_name=str(ref.get("function_name", "")),
                    function_entry=int(ref.get("function_entry")) if ref.get("function_entry") is not None else None,
                )
            )
        nearby = []
        for func in entry.get("nearby_functions", []):
            nearby.append(
                GhidraFunctionSummary(
                    entry=int(func.get("entry", 0)),
                    name=str(func.get("name", "")),
                    body_min=int(func.get("body_min", 0)),
                    body_max=int(func.get("body_max", 0)),
                    size=int(func.get("size", 0)),
                    callers=[int(value) for value in func.get("callers", [])],
                    callees=[int(value) for value in func.get("callees", [])],
                    decompiled=str(func.get("decompiled", "")),
                )
            )
        item = GhidraCandidateEvidence(
            candidate_id=str(entry.get("candidate_id", "")),
            address=int(entry.get("address", 0)),
            references_to=references,
            nearby_functions=nearby,
            lookup_keywords=[str(value) for value in entry.get("lookup_keywords", [])],
        )
        evidence_by_id[item.candidate_id] = item
    return evidence_by_id
