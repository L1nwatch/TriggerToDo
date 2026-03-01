#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

IMPORT_ONLY=0
SKIP_JSON_IMPORT=0
DATA_FILE="initialize_data.json"
PASS_ARGS=()

while [[ $# -gt 0 ]]; do
  arg="$1"
  case "${arg}" in
    --import-only)
      IMPORT_ONLY=1
      shift
      ;;
    --skip-json-import)
      SKIP_JSON_IMPORT=1
      shift
      ;;
    --data-file)
      DATA_FILE="${2:-}"
      if [[ -z "${DATA_FILE}" ]]; then
        echo "[initialize] ERROR: --data-file requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      PASS_ARGS+=("${arg}")
      shift
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[initialize] ERROR: Required command not found: $1" >&2
    exit 1
  fi
}

require_cmd uv
require_cmd npm

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  echo "[initialize] Created .env from .env.example. Review .env values, then rerun."
  exit 1
fi

if [[ "${IMPORT_ONLY}" -eq 0 ]]; then
  echo "[initialize] Installing backend dependencies with uv..."
  uv sync --extra dev

  echo "[initialize] Installing frontend dependencies with npm..."
  (
    cd frontend
    if [[ -f package-lock.json ]]; then
      npm ci
    else
      npm install
    fi
  )

  echo "[initialize] Building frontend..."
  (
    cd frontend
    npm run build
  )
else
  echo "[initialize] --import-only enabled: skipping dependency install and frontend build."
fi

if [[ "${SKIP_JSON_IMPORT}" -eq 1 ]]; then
  echo "[initialize] --skip-json-import enabled: skipping initialize_data.json import."
elif [[ -f "${DATA_FILE}" ]]; then
  echo "[initialize] Importing local bootstrap data from ${DATA_FILE}..."
  uv run python scripts/import_initialize_json.py --file "${DATA_FILE}" "${PASS_ARGS[@]}"
else
  echo "[initialize] No ${DATA_FILE} found. Skipping data import."
  echo "[initialize] You can later run: uv run python scripts/import_initialize_json.py --file ${DATA_FILE} --replace"
fi

echo "[initialize] Done."
