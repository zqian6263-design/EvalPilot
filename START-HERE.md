# EvalPilot 快速安装

## 环境要求

- Python 3.11+
- Node.js 22+
- Windows PowerShell 7，或可运行 Python 的 macOS / Linux 环境

## 启动

在解压后的目录执行：

```powershell
python scripts/deploy.py
```

服务地址：

- 控制台：http://127.0.0.1:5173/
- API：http://127.0.0.1:8000/api
- API 文档：http://127.0.0.1:8000/docs

停止：

```powershell
python scripts/deploy.py --stop
```

## 验收公开 MCP 回归

```powershell
pwsh -NoProfile -File .\scripts\p4-mcp-retro-check.ps1
```

该命令使用公开的 `mcp==1.30.0` 和 `mcp==2.2.0`，分别安装到隔离环境，并生成回归、控制组和反事实证据。
