# ECU XDF Assistant

`ecu-xdf-assistant` is a local-first Python project that turns a raw ECU firmware BIN into:

- map / axis / scalar candidates
- Ghidra evidence
- LLM adjudications with structured JSON
- validated XDF hints
- a generated best-effort XDF file

This project is built for the workflow:

1. **scan firmware bytes**
2. **collect code/xref evidence with Ghidra**
3. **ask a local model to classify candidates**
4. **validate and score confidence**
5. **generate XDF + JSON sidecars**

It is intentionally designed so the model does **not** invent XML from scratch.
The LLM only judges structured evidence and returns JSON.  
The final XDF is emitted by deterministic Python code.

The supported workflow requires both:

- Ghidra headless evidence export
- LM Studio adjudication with a configured local model

Raw scanner output on its own is not treated as accurate enough for tuning work.

---

## Features

- raw BIN scanner for:
  - 1D axes
  - 2D table candidates
  - scalar candidates
  - nearby axis pairing
- mandatory Ghidra headless evidence export in the supported workflow
- mandatory LM Studio adjudication using JSON-schema constrained outputs
- validation and confidence scoring
- best-effort TunerPro-style XDF writer
- CLI with separate stages and full pipeline mode

---

## Project layout

```text
ecu_xdf_assistant/
├── docs/
├── examples/
├── src/ecu_xdf_assistant/
│   ├── scanner/
│   ├── ghidra/
│   ├── llm/
│   ├── validation/
│   ├── xdf/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   └── pipeline.py
└── tests/
```

---

## Installation

```bash
cd ecu_xdf_assistant
./scripts/install.sh
```

The installer bootstraps the local venv, installs the package, installs LM Studio when possible, starts the local API server, downloads and loads a small local model, installs JDK 21 when needed, downloads the current public Ghidra release into user space when needed, fixes executable permissions, and writes `settings.json`.
The default LM Studio model is `qwen/qwen3-4b`, which is a more realistic starting point for an RTX 4060 8 GB / 16 GB RAM machine than a 30B-class model.
On Linux, the fallback install path is `~/.local/jdk` and `~/.local/ghidra`, so the script does not rely on distro packages for Java or Ghidra.

Useful overrides:

```bash
LMSTUDIO_MODEL=qwen/qwen3-4b ./scripts/install.sh
GHIDRA_INSTALL_DIR=/opt/ghidra_11.0_PUBLIC ./scripts/install.sh
GHIDRA_DOWNLOAD_URL=https://.../ghidra.zip ./scripts/install.sh
JDK_DOWNLOAD_URL=https://.../OpenJDK21U-jdk_x64_linux_hotspot_....tar.gz ./scripts/install.sh
LMS_BIN=$HOME/.lmstudio/bin/lms ./scripts/install.sh
```

If you prefer manual setup, the minimum equivalent steps are:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Quick start

### 1) Create a config

Copy the example:

```bash
cp examples/settings.example.json settings.json
```

Then edit the fields you know:

- `architecture`
- `endianness`
- `base_address`
- `ghidra.install_dir`
- `lmstudio.model`

If you used `./scripts/install.sh`, `settings.json` is already created with Ghidra and LM Studio enabled. `architecture` and `endianness` can stay on `auto`; the scanner now writes a best-effort target inference report and uses the endianness guess to filter candidates before later stages. Endianness is usually inferable from candidate quality; architecture is only a heuristic for raw binaries and may still need manual confirmation. The CLI treats missing Ghidra or LM Studio configuration as a hard error.

### 2) Run the full pipeline

```bash
ecu-xdf-assistant pipeline firmware.bin \
  --config settings.json \
  --out out/
```

### 3) Or run stages manually

```bash
ecu-xdf-assistant scan firmware.bin --config settings.json --out out/
ecu-xdf-assistant ghidra-export firmware.bin --config settings.json --out out/
ecu-xdf-assistant adjudicate --config settings.json --out out/
ecu-xdf-assistant validate --config settings.json --out out/
ecu-xdf-assistant build-xdf --config settings.json --out out/
```

`scan` still writes the raw candidates needed by later stages, but it will not start unless both the Ghidra and LM Studio sides of the workflow are configured. This is intentional: the repository no longer supports a scan-only accuracy claim.

---

## Outputs

Typical output files:

```text
out/
├── scan/
│   ├── map_candidates.json
│   ├── axis_candidates.json
│   ├── scalar_candidates.json
│   └── scan_summary.json
├── ghidra/
│   ├── ghidra_evidence.json
│   └── ghidra_run.json
├── llm/
│   └── llm_judgements.json
├── validated/
│   ├── accepted_candidates.json
│   ├── rejected_candidates.json
│   └── validation_summary.json
├── xdf/
│   ├── generated.xdf
│   └── xdf_sidecar.json
└── report.md
```

---

## Config overview

Example `settings.json`:

```json
{
  "architecture": "auto",
  "endianness": "auto",
  "base_address": 0,
  "scanner": {
    "max_axis_length": 32,
    "table_shapes": [[8, 8], [10, 10], [12, 16], [16, 16]],
    "max_candidates_per_kind": 300
  },
  "ghidra": {
    "enabled": true,
    "install_dir": "/path/to/ghidra",
    "project_dir": ".ghidra_projects",
    "processor": "",
    "compiler_spec": "",
    "extra_import_args": []
  },
  "lmstudio": {
    "enabled": true,
    "host": "http://127.0.0.1:1234/v1",
    "model": "qwen/qwen3-4b",
    "temperature": 0.1,
    "top_n_maps": 80,
    "top_n_scalars": 80,
    "timeout_seconds": 180
  },
  "validation": {
    "accept_threshold": 0.62
  }
}
```

---

## Important notes

### 1) This is not an OEM source-code recovery tool
The goal is:
- find calibration objects
- gather evidence
- classify with confidence
- generate XDF assistance

### 2) Ghidra and LM Studio are required
This project no longer treats Ghidra evidence or model adjudication as optional.
Without both, the CLI will fail fast instead of pretending the result is trustworthy.

### 3) The generated XDF is best-effort
You should still inspect it in TunerPro and compare it against:
- known map patterns
- physical plausibility
- logged values
- family-specific expectations

### 4) Ghidra raw binary import often needs manual context
For unknown ECUs you may still need to tell Ghidra the right:
- processor
- compiler specification
- base address
- import flags

The wrapper in this project lets you pass extra arguments through `ghidra.extra_import_args`.

---

## Recommended workflow

### Unknown ECU / unknown file
1. run `scan`
2. inspect `scan/map_candidates.json`
3. configure Ghidra import settings
4. run `ghidra-export`
5. run `adjudicate`
6. run `build-xdf`

### Known family / repeated workflow
1. keep a family-specific config
2. run the full `pipeline`
3. inspect `validated/accepted_candidates.json`
4. open `xdf/generated.xdf` in TunerPro

---

## Extending the project

Good next steps:

- family-specific classifiers for:
  - Bosch EDC15
  - Bosch EDC16
  - Siemens SID80x
  - BMW MS43 / ME7-style layouts
- checksum plugin support
- auto-detection of likely lookup/interpolation helpers
- stronger scale-factor inference
- multi-pass consensus across two local models
- TunerPro import round-trip validation

---

## Running tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

---

## License

Use and modify freely for research, reverse-engineering study, and private motorsport projects.
