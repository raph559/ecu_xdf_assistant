# Architecture

## Why this project exists

For tuning, the useful output is not "recovered firmware C source".
The useful output is:

- map addresses
- dimensions
- likely axes
- scale hints
- evidence that code really references the object
- a best-effort XDF

## Pipeline

```text
BIN
 ├─> raw scanner
 │    ├─ axes
 │    ├─ maps
 │    └─ scalars
 ├─> Ghidra headless
 │    ├─ xrefs
 │    ├─ nearby functions
 │    └─ optional pseudocode
 ├─> local LLM via LM Studio
 │    ├─ classify candidate
 │    ├─ propose scale hints
 │    └─ state conflicts
 ├─> validator
 │    ├─ merge scanner + xrefs + LLM
 │    └─ compute final confidence
 └─> XDF writer
      ├─ generated.xdf
      └─ xdf_sidecar.json
```

## Design constraints

- The LLM is not trusted to invent XML.
- The XDF writer is deterministic.
- Ghidra evidence is required for supported runs.
- LM Studio adjudication is required for supported runs.
- Raw scanner output is an intermediate artifact, not a trustworthy end result.

## Extension ideas

- family-specific priors
- checksum plugins
- map transposition inference
- smarter scale guessing
- candidate clustering by function/xref neighborhood
