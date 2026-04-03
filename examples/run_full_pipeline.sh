#!/usr/bin/env bash
set -euo pipefail

FIRMWARE_PATH="${1:-firmware.bin}"
CONFIG_PATH="${2:-settings.json}"
OUT_DIR="${3:-out}"

ecu-xdf-assistant pipeline "$FIRMWARE_PATH" --config "$CONFIG_PATH" --out "$OUT_DIR"

echo "Done."
echo "See:"
echo "  $OUT_DIR/report.md"
echo "  $OUT_DIR/xdf/generated.xdf"
