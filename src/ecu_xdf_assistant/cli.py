from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .pipeline import full_pipeline, ghidra_stage, llm_stage, scan_stage, validation_stage, xdf_stage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ECU XDF Assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    def common_arguments(cmd: argparse.ArgumentParser, firmware_required: bool = True) -> None:
        if firmware_required:
            cmd.add_argument("firmware", help="Path to the firmware BIN file")
        cmd.add_argument("--config", help="Path to settings JSON", default=None)
        cmd.add_argument("--out", help="Output directory", required=True)

    scan = sub.add_parser("scan", help="Run raw byte scanning")
    common_arguments(scan)

    ghidra = sub.add_parser("ghidra-export", help="Run Ghidra headless evidence export")
    common_arguments(ghidra)

    adjudicate = sub.add_parser("adjudicate", help="Run LLM adjudication")
    common_arguments(adjudicate, firmware_required=False)

    validate = sub.add_parser("validate", help="Run validation stage")
    common_arguments(validate, firmware_required=False)

    build_xdf = sub.add_parser("build-xdf", help="Generate XDF from accepted candidates")
    common_arguments(build_xdf, firmware_required=False)
    build_xdf.add_argument("--title", default="Generated ECU XDF", help="XDF title")

    pipeline = sub.add_parser("pipeline", help="Run the full pipeline")
    common_arguments(pipeline)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config(args.config)

        if args.command == "scan":
            result = scan_stage(args.firmware, config, args.out)
            print(f"scan complete: axes={len(result.axes)} maps={len(result.maps)} scalars={len(result.scalars)}")
            return

        if args.command == "ghidra-export":
            evidence = ghidra_stage(args.firmware, config, args.out)
            print(f"ghidra export complete: evidence_items={len(evidence)}")
            return

        if args.command == "adjudicate":
            judgements = llm_stage(config, args.out)
            print(f"llm adjudication complete: {len(judgements)} judgements")
            return

        if args.command == "validate":
            accepted, rejected = validation_stage(config, args.out)
            print(f"validation complete: accepted={len(accepted)} rejected={len(rejected)}")
            return

        if args.command == "build-xdf":
            xdf_path, sidecar_path = xdf_stage(args.out, title=args.title)
            print(f"xdf complete: {xdf_path} sidecar={sidecar_path}")
            return

        if args.command == "pipeline":
            result = full_pipeline(args.firmware, config, args.out)
            print(f"pipeline complete: {result['xdf_path']}")
            return

        parser.error(f"unknown command: {args.command}")
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
