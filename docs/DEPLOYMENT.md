# Deployment

## Portable one-command start

EvalPilot includes a cross-platform Python launcher:

```bash
python scripts/deploy.py
```

It creates or reuses `.venv`, installs Python dependencies, installs frontend
dependencies when needed, starts both services, and waits for HTTP health.

```bash
python scripts/deploy.py --status
python scripts/deploy.py --stop
```

The frontend proxy target follows `--backend-port`, so alternate ports work:

```bash
python scripts/deploy.py --backend-port 8300 --frontend-port 5473
```

## Windows convenience scripts

The existing PowerShell path remains available:

```powershell
.\scripts\start-all-live.ps1
.\scripts\start-all.ps1 -Status
.\scripts\start-all.ps1 -Stop
```

## CI release gate

```powershell
.\scripts\ci-gate.ps1 -RunId <run-id>
```

Exit codes: `0 allow`, `1 review`, `2 block`.

## Live cost measurement

```powershell
.\scripts\measure-live-cost.ps1 -RunId <run-id>
```

The script reads persisted token usage, run/investigation wall time, and logical
storage size, then computes model, compute, storage, and total costs. Rates are
parameters so they can be replaced with a provider's published prices.
