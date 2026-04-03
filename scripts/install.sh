#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
CONFIG_PATH="${CONFIG_PATH:-$ROOT_DIR/settings.json}"
LMSTUDIO_MODEL="${LMSTUDIO_MODEL:-qwen/qwen3-4b}"
LMSTUDIO_HOST="${LMSTUDIO_HOST:-http://127.0.0.1:1234/v1}"
LMSTUDIO_LOAD_TTL="${LMSTUDIO_LOAD_TTL:-3600}"
LMS_BIN="${LMS_BIN:-}"
JAVA_HOME="${JAVA_HOME:-}"
JDK_DOWNLOAD_URL="${JDK_DOWNLOAD_URL:-}"
JDK_INSTALL_DIR="${JDK_INSTALL_DIR:-$HOME/.local/jdk}"
GHIDRA_INSTALL_DIR="${GHIDRA_INSTALL_DIR:-}"
GHIDRA_DOWNLOAD_URL="${GHIDRA_DOWNLOAD_URL:-${GHIDRA_ZIP_URL:-}}"
GHIDRA_PARENT_DIR="${GHIDRA_PARENT_DIR:-$HOME/.local/ghidra}"
SKIP_LMSTUDIO_MODEL_SETUP="${SKIP_LMSTUDIO_MODEL_SETUP:-0}"

log() {
  printf '[install] %s\n' "$1"
}

fail() {
  printf '[install] error: %s\n' "$1" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

detect_os() {
  case "$(uname -s)" in
    Linux) echo "linux" ;;
    Darwin) echo "macos" ;;
    *) echo "unknown" ;;
  esac
}

download_file() {
  local url="$1"
  local destination="$2"
  curl -fL --retry 3 --retry-delay 2 "$url" -o "$destination"
}

extract_zip_archive() {
  local archive_path="$1"
  local destination="$2"
  mkdir -p "$destination"
  if command -v unzip >/dev/null 2>&1; then
    unzip -oq "$archive_path" -d "$destination"
    return 0
  fi

  "$PYTHON_BIN" - "$archive_path" "$destination" <<'PY'
import sys
import zipfile
from pathlib import Path

archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
with zipfile.ZipFile(archive) as zf:
    zf.extractall(destination)
PY
}

json_get() {
  local url="$1"
  local script="$2"
  curl -fsSL "$url" | "$PYTHON_BIN" -c "$script"
}

resolve_lms_bin() {
  local candidate
  for candidate in \
    "$LMS_BIN" \
    "$(command -v lms 2>/dev/null || true)" \
    "$HOME/.lmstudio/bin/lms" \
    "$HOME/.local/bin/lms"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      LMS_BIN="$candidate"
      return 0
    fi
  done
  return 1
}

install_python_env() {
  need_cmd "$PYTHON_BIN"
  log "creating virtualenv in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
  "$VENV_DIR/bin/pip" install -e "$ROOT_DIR"
}

install_lmstudio() {
  if resolve_lms_bin; then
    log "LM Studio CLI already available at $LMS_BIN"
    return 0
  fi

  need_cmd curl
  log "installing LM Studio with the official installer"
  curl -fsSL https://lmstudio.ai/install.sh | bash
  resolve_lms_bin || fail "LM Studio installed, but the lms CLI was not found. Set LMS_BIN manually and rerun."
}

ensure_lmstudio_server() {
  if curl -fsS "$LMSTUDIO_HOST/models" >/dev/null 2>&1; then
    log "LM Studio API already reachable at $LMSTUDIO_HOST"
    return 0
  fi

  resolve_lms_bin || fail "LM Studio CLI is not available"
  log "starting LM Studio daemon"
  "$LMS_BIN" daemon up >/tmp/ecu_xdf_assistant_lmstudio_daemon.log 2>&1 || true
  log "starting LM Studio API server"
  nohup "$LMS_BIN" server start >/tmp/ecu_xdf_assistant_lmstudio_server.log 2>&1 &

  for _ in $(seq 1 30); do
    if curl -fsS "$LMSTUDIO_HOST/models" >/dev/null 2>&1; then
      log "LM Studio server is ready"
      return 0
    fi
    sleep 1
  done

  fail "LM Studio server did not become ready; see /tmp/ecu_xdf_assistant_lmstudio_server.log"
}

resolve_loaded_model_id() {
  local requested_model response
  requested_model="$1"
  resolve_lms_bin || return 1
  response="$("$LMS_BIN" ps --json 2>/dev/null || true)"
  [[ -n "$response" ]] || return 1

  printf '%s' "$response" | "$PYTHON_BIN" -c '
import json
import sys

requested = sys.argv[1]
short_name = requested.split("/")[-1]
raw_payload = sys.stdin.read().strip()
if not raw_payload:
    raise SystemExit(1)

try:
    payload = json.loads(raw_payload)
except Exception:
    raise SystemExit(1)

if not isinstance(payload, list):
    raise SystemExit(1)

models = [item.get("identifier", "") for item in payload if isinstance(item, dict) and item.get("identifier")]
if requested in models:
    print(requested)
    raise SystemExit(0)

for model in models:
    model_short = model.split("/")[-1]
    if model_short == short_name or short_name in model:
        print(model)
        raise SystemExit(0)

raise SystemExit(1)
' "$requested_model"
}

resolve_loaded_model_id_from_log() {
  local log_path="$1"
  [[ -s "$log_path" ]] || return 1

  "$PYTHON_BIN" - "$log_path" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
match = re.search(r'identifier "([^"]+)"', text)
if not match:
    raise SystemExit(1)
print(match.group(1))
PY
}

download_and_load_model() {
  if [[ "$SKIP_LMSTUDIO_MODEL_SETUP" == "1" ]]; then
    log "skipping model setup because SKIP_LMSTUDIO_MODEL_SETUP=1"
    return 0
  fi

  local requested_model loaded_model_id
  requested_model="$LMSTUDIO_MODEL"
  resolve_lms_bin || fail "LM Studio CLI is not available"
  log "downloading LM Studio model $requested_model"
  "$LMS_BIN" get "$requested_model"

  if loaded_model_id="$(resolve_loaded_model_id "$requested_model")"; then
    LMSTUDIO_MODEL="$loaded_model_id"
    log "LM Studio model is already loaded as $LMSTUDIO_MODEL"
    return 0
  fi

  log "loading LM Studio model $requested_model"
  "$LMS_BIN" load "$requested_model" -y --ttl "$LMSTUDIO_LOAD_TTL" >/tmp/ecu_xdf_assistant_lmstudio_load.log 2>&1

  if loaded_model_id="$(resolve_loaded_model_id_from_log /tmp/ecu_xdf_assistant_lmstudio_load.log)"; then
    if LMSTUDIO_MODEL="$(resolve_loaded_model_id "$requested_model")"; then
      log "LM Studio model is available as $LMSTUDIO_MODEL"
      return 0
    fi
    LMSTUDIO_MODEL="$loaded_model_id"
    log "LM Studio model is available as $LMSTUDIO_MODEL"
    return 0
  fi

  for _ in $(seq 1 30); do
    if LMSTUDIO_MODEL="$(resolve_loaded_model_id "$requested_model")"; then
      log "LM Studio model is available as $LMSTUDIO_MODEL"
      return 0
    fi
    sleep 1
  done

  fail "LM Studio model did not appear in $LMSTUDIO_HOST/models; see /tmp/ecu_xdf_assistant_lmstudio_load.log"
}

java_major_version() {
  local java_bin="$1"
  "$java_bin" -version 2>&1 | "$PYTHON_BIN" -c '
import re
import sys

text = sys.stdin.read()
match = re.search(r"version \"(\d+)", text)
print(match.group(1) if match else "")
'
}

find_java_home() {
  local candidate major
  for candidate in \
    "$JAVA_HOME" \
    "$(dirname "$(dirname "$(command -v java 2>/dev/null || true)")")" \
    "$JDK_INSTALL_DIR"/* \
    /usr/lib/jvm/* \
    /Library/Java/JavaVirtualMachines/*/Contents/Home; do
    if [[ -n "$candidate" && -x "$candidate/bin/java" ]]; then
      major="$(java_major_version "$candidate/bin/java")"
      if [[ "$major" =~ ^[0-9]+$ ]] && (( major >= 21 )); then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

resolve_jdk_download_url() {
  if [[ -n "$JDK_DOWNLOAD_URL" ]]; then
    printf '%s\n' "$JDK_DOWNLOAD_URL"
    return 0
  fi

  local os_name arch_name
  os_name="$(detect_os)"
  case "$(uname -m)" in
    x86_64|amd64) arch_name="x64" ;;
    aarch64|arm64) arch_name="aarch64" ;;
    *) fail "unsupported architecture for automatic JDK install: $(uname -m)" ;;
  esac

  local api_url
  api_url="https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=${arch_name}&image_type=jdk&os=${os_name}&heap_size=normal&vendor=eclipse"
  json_get "$api_url" 'import json,sys; payload=json.load(sys.stdin); print(payload[0]["binary"]["package"]["link"])'
}

install_jdk() {
  local existing download_url archive_path extracted
  if existing="$(find_java_home)"; then
    JAVA_HOME="$existing"
    export JAVA_HOME
    export PATH="$JAVA_HOME/bin:$PATH"
    log "Java 21+ already available at $JAVA_HOME"
    return 0
  fi

  need_cmd tar
  mkdir -p "$JDK_INSTALL_DIR"
  archive_path="/tmp/ecu_xdf_assistant_jdk.tar.gz"
  download_url="$(resolve_jdk_download_url)"
  log "downloading JDK from $download_url"
  download_file "$download_url" "$archive_path"
  tar -xzf "$archive_path" -C "$JDK_INSTALL_DIR"
  extracted="$(find "$JDK_INSTALL_DIR" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
  [[ -n "$extracted" ]] || fail "JDK extraction failed"
  JAVA_HOME="$extracted"
  export JAVA_HOME
  export PATH="$JAVA_HOME/bin:$PATH"
  log "installed JDK at $JAVA_HOME"
}

find_ghidra_install_dir() {
  local candidate
  for candidate in \
    "$GHIDRA_INSTALL_DIR" \
    "$GHIDRA_PARENT_DIR"/* \
    /opt/ghidra* \
    "$HOME"/ghidra* \
    "$HOME"/Applications/ghidra* \
    /Applications/ghidra* \
    /Applications/Ghidra.app/Contents/Resources/ghidra*; do
    if [[ -n "$candidate" && -x "$candidate/support/analyzeHeadless" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

resolve_ghidra_download_url() {
  if [[ -n "$GHIDRA_DOWNLOAD_URL" ]]; then
    printf '%s\n' "$GHIDRA_DOWNLOAD_URL"
    return 0
  fi

  json_get \
    "https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest" \
    'import json,sys; payload=json.load(sys.stdin); assets=payload.get("assets", []); candidates=[a["browser_download_url"] for a in assets if a.get("browser_download_url","").endswith(".zip") and "PUBLIC" in a.get("name","")]; print(candidates[0] if candidates else "")'
}

normalize_ghidra_permissions() {
  local install_dir="$1"
  find "$install_dir/support" -type f -exec chmod u+x {} + 2>/dev/null || true
  find "$install_dir" -type f -name '*.sh' -exec chmod u+x {} + 2>/dev/null || true
  find "$install_dir" -type f -path '*/os/linux/*' -exec chmod u+x {} + 2>/dev/null || true
}

install_ghidra() {
  local existing archive_path download_url extracted
  if existing="$(find_ghidra_install_dir)"; then
    GHIDRA_INSTALL_DIR="$existing"
    log "Ghidra already available at $GHIDRA_INSTALL_DIR"
    return 0
  fi

  download_url="$(resolve_ghidra_download_url)"
  [[ -n "$download_url" ]] || fail "could not determine a Ghidra download URL; set GHIDRA_INSTALL_DIR or GHIDRA_DOWNLOAD_URL"
  archive_path="/tmp/ecu_xdf_assistant_ghidra.zip"
  mkdir -p "$GHIDRA_PARENT_DIR"
  log "downloading Ghidra from $download_url"
  download_file "$download_url" "$archive_path"
  extract_zip_archive "$archive_path" "$GHIDRA_PARENT_DIR"
  extracted="$(find_ghidra_install_dir || true)"
  [[ -n "$extracted" ]] || fail "Ghidra extraction did not produce an install with support/analyzeHeadless"
  GHIDRA_INSTALL_DIR="$extracted"
  normalize_ghidra_permissions "$GHIDRA_INSTALL_DIR"
  log "installed Ghidra at $GHIDRA_INSTALL_DIR"
}

write_settings() {
  log "writing $CONFIG_PATH"
  cp "$ROOT_DIR/examples/settings.example.json" "$CONFIG_PATH"
  "$PYTHON_BIN" - "$CONFIG_PATH" "$GHIDRA_INSTALL_DIR" "$LMSTUDIO_MODEL" "$LMSTUDIO_HOST" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
ghidra_install_dir = sys.argv[2]
lmstudio_model = sys.argv[3]
lmstudio_host = sys.argv[4]

data = json.loads(config_path.read_text(encoding="utf-8"))
data["architecture"] = "auto"
data["endianness"] = "auto"
data["ghidra"]["enabled"] = True
data["ghidra"]["install_dir"] = ghidra_install_dir
data["ghidra"]["postscript_name"] = "ExportFirmwareEvidence.py"
data["lmstudio"]["enabled"] = True
data["lmstudio"]["host"] = lmstudio_host
data["lmstudio"]["model"] = lmstudio_model
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

main() {
  need_cmd curl
  install_python_env
  install_lmstudio
  ensure_lmstudio_server
  download_and_load_model
  install_jdk
  install_ghidra
  write_settings

  log "installation complete"
  log "activate the environment with: source \"$VENV_DIR/bin/activate\""
  log "run the pipeline with: ecu-xdf-assistant pipeline firmware.bin --config \"$CONFIG_PATH\" --out out/"
}

main "$@"
