#!/usr/bin/env bash
# Dev Container bootstrap for EvalPilot.
#
# Runs after the container is created. It builds every dependency from scratch
# inside the container and never reuses a .venv from the host: a host virtualenv
# contains host-absolute paths and host-specific wheels, so bind-mounting it
# into a Linux container breaks imports in ways that are hard to diagnose.
set -euo pipefail

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace"

echo "== EvalPilot dev container setup =="
python3 --version
node --version
npm --version

echo "-- creating the backend virtualenv (.venv)"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip

echo "-- installing backend dependencies"
.venv/bin/python -m pip install -r backend/requirements.txt

echo "-- installing frontend dependencies"
npm --prefix frontend ci

echo "-- verifying the checkout"
PYTHONPATH="$workspace/backend" .venv/bin/python -c "import evalpilot, fastapi, httpx, jsonschema; print('backend import OK')"
npm --prefix frontend run typecheck

cat <<'EOF'

Setup complete.

Start both services:
  .venv/bin/python scripts/deploy.py

Then open:
  console : http://127.0.0.1:5173/
  API docs: http://127.0.0.1:8000/docs

Run the checks:
  PYTHONPATH="$PWD/backend" .venv/bin/python -m pytest backend/tests -q
  bash .devcontainer/verify.sh
EOF
