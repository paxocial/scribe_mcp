#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

echo "==> Checking Python environment"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: ${PYTHON_BIN} not found. Please install Python 3.11+."
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "==> Creating virtual environment at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

echo "==> Activating virtual environment"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

echo "==> Upgrading pip"
pip install --upgrade pip

echo "==> Installing project requirements"
pip install -r "${PROJECT_ROOT}/requirements.txt"

echo "==> Installation complete. Activate the environment with:"
echo "     source ${VENV_DIR}/bin/activate"
