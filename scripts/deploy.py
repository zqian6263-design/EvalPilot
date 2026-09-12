"""Cross-platform EvalPilot launcher.

This is the product's portable one-command path: create the Python environment,
install dependencies, start both services, and optionally stop or inspect them.

Examples:
    python scripts/deploy.py
    python scripts/deploy.py --frontend-port 5473
    python scripts/deploy.py --status
    python scripts/deploy.py --stop
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv'
VENV_PYTHON = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
RUNTIME = ROOT / '.runtime'
STATE = RUNTIME / 'deploy-pids.json'
NPM = shutil.which('npm.cmd') or shutil.which('npm') or 'npm'


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def wait_http(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if http_ok(url):
            return True
        time.sleep(0.5)
    return False


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def install_dependencies() -> None:
    if not VENV_PYTHON.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(VENV)], check=True)
    subprocess.run(
        [str(VENV_PYTHON), '-m', 'pip', 'install', '--quiet', '-r', str(ROOT / 'backend/requirements.txt')],
        check=True,
    )
    frontend = ROOT / 'frontend'
    if not (frontend / 'node_modules').exists():
        subprocess.run([NPM, 'install'], cwd=frontend, check=True)


def launch(command: list[str], cwd: Path, log_name: str, env: dict[str, str]):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    handle = open(RUNTIME / log_name, 'a', encoding='utf-8')
    kwargs = {'cwd': cwd, 'env': env, 'stdout': handle, 'stderr': handle}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs['start_new_session'] = True
    process = subprocess.Popen(command, **kwargs)
    handle.close()
    return process.pid


def stop_process(pid: int) -> None:
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def start(args: argparse.Namespace) -> int:
    backend_url = f'http://127.0.0.1:{args.backend_port}'
    frontend_url = f'http://127.0.0.1:{args.frontend_port}'
    install_dependencies()

    state = {'backend': None, 'frontend': None}
    if not http_ok(f'{backend_url}/api/health'):
        env = os.environ.copy()
        env['PYTHONPATH'] = str(ROOT / 'backend')
        backend_pid = launch(
            [str(VENV_PYTHON), '-m', 'uvicorn', 'evalpilot.app:create_app', '--factory', '--host', '127.0.0.1', '--port', str(args.backend_port)],
            ROOT / 'backend',
            'deploy-backend.log',
            env,
        )
        state['backend'] = {'pid': backend_pid, 'owned': True}
        if not wait_http(f'{backend_url}/api/health', args.timeout):
            stop_process(backend_pid)
            raise SystemExit(f'backend did not become healthy at {backend_url}')
    else:
        state['backend'] = {'pid': None, 'owned': False}

    if not http_ok(f'{frontend_url}/'):
        env = os.environ.copy()
        env['EVALPILOT_API_PROXY_TARGET'] = backend_url
        frontend_pid = launch(
            [NPM, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(args.frontend_port), '--strictPort'],
            ROOT / 'frontend',
            'deploy-frontend.log',
            env,
        )
        state['frontend'] = {'pid': frontend_pid, 'owned': True}
        if not wait_http(f'{frontend_url}/', args.timeout):
            stop_process(frontend_pid)
            raise SystemExit(f'frontend did not become healthy at {frontend_url}')
    else:
        state['frontend'] = {'pid': None, 'owned': False}

    save_state(state)
    print(f'EvalPilot is up: {frontend_url}/')
    print(f'API: {backend_url}/api')
    return 0


def stop() -> int:
    state = load_state()
    for name in ('frontend', 'backend'):
        entry = state.get(name)
        if entry and entry.get('owned') and entry.get('pid'):
            stop_process(int(entry['pid']))
            print(f'stopped {name} pid={entry["pid"]}')
    if STATE.exists():
        STATE.unlink()
    return 0


def status(args: argparse.Namespace) -> int:
    backend_url = f'http://127.0.0.1:{args.backend_port}'
    frontend_url = f'http://127.0.0.1:{args.frontend_port}'
    print(f'backend  {backend_url}  {"healthy" if http_ok(f"{backend_url}/api/health") else "unreachable"}')
    print(f'frontend {frontend_url}  {"healthy" if http_ok(f"{frontend_url}/") else "unreachable"}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    if args.stop:
        return stop()
    if args.status:
        return status(args)
    return start(args)


if __name__ == '__main__':
    raise SystemExit(main())
