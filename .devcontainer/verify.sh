#!/usr/bin/env bash
# Acceptance check inside the Dev Container.
#
# Verifies the container toolchain, the backend install, and the external-SUT
# onboarding path end to end: it starts the template SUT as a real process,
# requires the onboarding validator to accept it, and requires the P5 tests to
# pass. Every step is reported, and the script exits non-zero if any failed.
set -uo pipefail

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace"

python_bin=".venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "FAIL: .venv is missing; run 'bash .devcontainer/post-create.sh' first" >&2
  exit 1
fi

failures=0

step() {
  local name="$1" code="$2" detail="${3:-}"
  if [[ "$code" -eq 0 ]]; then
    echo "  PASS  ${name}${detail:+ - $detail}"
  else
    echo "  FAIL  ${name}${detail:+ - $detail}" >&2
    failures=$((failures + 1))
  fi
}

run_step() {
  local name="$1"
  shift
  "$@"
  step "$name" "$?"
}

echo "== Dev Container acceptance =="

python_ok="$("$python_bin" -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')"
step "python is 3.11+" "$((1 - python_ok))" "$("$python_bin" -c 'import platform; print(platform.python_version())')"

node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
[[ "$node_major" =~ ^[0-9]+$ ]] || node_major=0
step "node is 22+" "$([[ "$node_major" -ge 22 ]] && echo 0 || echo 1)" "$(node --version 2>/dev/null || echo missing)"

run_step "backend dependencies import" \
  env PYTHONPATH="$workspace/backend" "$python_bin" -c 'import evalpilot, fastapi, httpx, jsonschema'

[[ -d frontend/node_modules ]]
step "frontend dependencies are installed" "$?" "frontend/node_modules"

port="${EVALPILOT_VERIFY_PORT:-8099}"
PYTHONPATH="$workspace/backend" "$python_bin" -m uvicorn app:app \
  --app-dir integrations/sut_template --host 127.0.0.1 --port "$port" --log-level warning \
  >"${TMPDIR:-/tmp}/evalpilot-verify-sut.log" 2>&1 &
sut_pid=$!
trap 'kill "$sut_pid" 2>/dev/null || true' EXIT

ready=1
for _ in $(seq 1 60); do
  if "$python_bin" -c "import socket; socket.create_connection(('127.0.0.1', $port), timeout=1).close()" 2>/dev/null; then
    ready=0
    break
  fi
  sleep 0.5
done
step "template SUT starts" "$ready" "http://127.0.0.1:$port (log: ${TMPDIR:-/tmp}/evalpilot-verify-sut.log)"

if [[ "$ready" -eq 0 ]]; then
  run_step "validate-sut accepts the template SUT" \
    env PYTHONPATH="$workspace/backend" "$python_bin" -m evalpilot.sut.validator \
      --base-url "http://127.0.0.1:$port" \
      --workload integrations/sut_template/workload.json
fi

kill "$sut_pid" 2>/dev/null || true
wait "$sut_pid" 2>/dev/null || true
trap - EXIT

run_step "P5 tests pass" \
  env PYTHONPATH="$workspace/backend" "$python_bin" -m pytest \
    backend/tests/test_sut_template_contract.py \
    backend/tests/test_workload_schema.py \
    backend/tests/test_sut_validator.py -q

if [[ "$failures" -ne 0 ]]; then
  echo "Dev Container acceptance FAILED ($failures failing step(s))" >&2
  exit 1
fi
echo "Dev Container acceptance passed."
