from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(slots=True)
class ScannerConfig:
    min_axis_length: int = 6
    max_axis_length: int = 32
    axis_lengths: List[int] = field(default_factory=lambda: [6, 8, 10, 12, 16, 20, 24, 32])
    table_shapes: List[List[int]] = field(default_factory=lambda: [[8, 8], [10, 10], [12, 16], [16, 16]])
    max_candidates_per_kind: int = 300
    axis_search_radius_bytes: int = 0x200
    element_sizes_bits: List[int] = field(default_factory=lambda: [8, 16])
    signed_modes: List[bool] = field(default_factory=lambda: [False, True])


@dataclass(slots=True)
class GhidraConfig:
    enabled: bool = False
    install_dir: str = ""
    project_dir: str = ".ghidra_projects"
    processor: str = ""
    compiler_spec: str = ""
    base_address: int = 0
    extra_import_args: List[str] = field(default_factory=list)
    postscript_name: str = "ExportFirmwareEvidence.py"
    decompile_referencing_functions: bool = True
    function_decompile_limit: int = 2


@dataclass(slots=True)
class LMStudioConfig:
    enabled: bool = False
    host: str = "http://127.0.0.1:1234/v1"
    model: str = "qwen/qwen3-4b"
    temperature: float = 0.1
    top_n_maps: int = 80
    top_n_scalars: int = 80
    timeout_seconds: int = 180


@dataclass(slots=True)
class ValidationConfig:
    accept_threshold: float = 0.62
    soft_review_threshold: float = 0.50


@dataclass(slots=True)
class ProjectConfig:
    architecture: str = "auto"
    endianness: str = "auto"
    base_address: int = 0
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    ghidra: GhidraConfig = field(default_factory=GhidraConfig)
    lmstudio: LMStudioConfig = field(default_factory=LMStudioConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)

    def require_ghidra(self) -> None:
        if not self.ghidra.enabled:
            raise ValueError("Ghidra is required. Set ghidra.enabled=true in your config.")
        install_dir = self.ghidra.install_dir.strip()
        if not install_dir:
            raise ValueError("Ghidra is required. Set ghidra.install_dir to your Ghidra installation directory.")
        executable = Path(install_dir) / "support" / ("analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless")
        if not executable.exists():
            raise ValueError(
                f"Ghidra is required. Expected analyzeHeadless at {executable}."
            )

    def require_lmstudio(self) -> None:
        if not self.lmstudio.enabled:
            raise ValueError("LM Studio adjudication is required. Set lmstudio.enabled=true in your config.")
        if not self.lmstudio.host.strip():
            raise ValueError("LM Studio adjudication is required. Set lmstudio.host in your config.")
        if not self.lmstudio.model.strip():
            raise ValueError("LM Studio adjudication is required. Set lmstudio.model in your config.")

    def require_supported_workflow(self) -> None:
        self.require_ghidra()
        self.require_lmstudio()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectConfig":
        scanner = ScannerConfig(**data.get("scanner", {}))
        ghidra = GhidraConfig(**data.get("ghidra", {}))
        lmstudio = LMStudioConfig(**data.get("lmstudio", data.get("ollama", {})))
        validation = ValidationConfig(**data.get("validation", {}))
        return cls(
            architecture=data.get("architecture", "auto"),
            endianness=data.get("endianness", "auto"),
            base_address=int(data.get("base_address", 0)),
            scanner=scanner,
            ghidra=ghidra,
            lmstudio=lmstudio,
            validation=validation,
        )


def load_config(path: str | Path | None) -> ProjectConfig:
    if not path:
        return ProjectConfig()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProjectConfig.from_dict(payload)
