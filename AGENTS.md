# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/ecu_xdf_assistant/`. Keep new logic inside the existing domain packages: `scanner/` for raw BIN detection, `ghidra/` for evidence export, `llm/` for LM Studio adjudication, `validation/` for scoring/acceptance, and `xdf/` for deterministic XDF output. The CLI entrypoint is `src/ecu_xdf_assistant/cli.py`; shared models and config live in `models.py` and `config.py`. Put example configs in `examples/`, longer notes in `docs/`, and unit tests in `tests/`.

## Build, Test, and Development Commands
Create a local environment and install the package in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the CLI locally with either the console script or module:

```bash
ecu-xdf-assistant pipeline firmware.bin --config settings.json --out out/
python3 -m ecu_xdf_assistant scan firmware.bin --config settings.json --out out/

Treat `scan` as a low-level development aid only. For contributor validation, assume usable results require the full pipeline with Ghidra configured and LM Studio pointed at a local model; raw scan output alone is not considered accurate enough for real tuning work.
```

Run tests with the package installed, or by exposing `src/` directly:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Coding Style & Naming Conventions
Use Python 3.10+ and standard library patterns already present in the repo: dataclasses with `slots=True`, type hints, and small focused modules. Follow PEP 8 with 4-space indentation. Use `snake_case` for functions, variables, files, and CLI subcommands; use `PascalCase` for dataclasses and test classes. Prefer explicit, deterministic code paths over hidden side effects, especially in validation and XDF generation, but do not weaken the requirement for Ghidra evidence plus LM Studio model review in the main workflow.

## Testing Guidelines
This repository uses `unittest`. Name test files `test_*.py` and group related assertions in `unittest.TestCase` classes such as `ScannerTests`. Add coverage for each affected pipeline stage and include at least one end-to-end style fixture when changing candidate formats, scoring, or XDF emission. Keep tests self-contained with temporary directories and synthetic firmware blobs. If you touch pipeline behavior, test the enforced assumption that Ghidra and LM Studio-backed adjudication are required for trustworthy output.

## Commit & Pull Request Guidelines
Git history is not available in this workspace snapshot, so no local commit convention could be inferred. Use short imperative commit subjects, for example `scanner: tighten axis pairing heuristic`. In pull requests, describe the affected pipeline stage, note config or output format changes, link the issue if there is one, and include sample output paths or JSON/XDF snippets when behavior changes.

## Configuration & Safety Notes
Do not commit real firmware, generated `out/` artifacts, or machine-specific paths. Start from `examples/settings.example.json`, keep `ghidra.install_dir` and LM Studio model settings local, and document any new config keys in `README.md`. Contributors should treat missing Ghidra configuration or a missing local model as a blocker for production-like runs, not as a normal degraded mode.
