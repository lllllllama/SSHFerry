#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "${ROOT_DIR}/.venv_compat/Scripts/python.exe" ]]; then
  exec "${ROOT_DIR}/.venv_compat/Scripts/python.exe" -m src.app.main
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  exec "${ROOT_DIR}/.venv/bin/python" -m src.app.main
fi

if [[ -x "${ROOT_DIR}/.venv_compat/bin/python" ]]; then
  exec "${ROOT_DIR}/.venv_compat/bin/python" -m src.app.main
fi

exec python3 -m src.app.main
