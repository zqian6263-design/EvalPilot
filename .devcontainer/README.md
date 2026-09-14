# Dev Container（Python 3.11 + Node 22）

一次性的、可复现的开发/验收环境。容器内的 `.venv` 由 `postCreateCommand` 现场创建，
**不使用宿主机的 `.venv`**：宿主的虚拟环境里是宿主绝对路径和宿主平台的 wheel，
挂进 Linux 容器后会出现难以定位的导入错误。

## 本地运行

1. 安装 Docker Desktop（Windows/macOS）或 Docker Engine + Dev Containers CLI（Linux）。
2. 在 VS Code 中执行 **Dev Containers: Reopen in Container**，或使用 CLI：

   ```bash
   devcontainer up --workspace-folder .
   ```

3. `postCreateCommand` 会自动执行 `.devcontainer/post-create.sh`：
   - `python3 -m venv .venv` 新建后端虚拟环境；
   - `pip install -r backend/requirements.txt` 安装后端依赖；
   - `npm --prefix frontend ci` 安装前端依赖；
   - 校验 `import evalpilot` 与前端 `typecheck`。

4. 启动服务：

   ```bash
   .venv/bin/python scripts/deploy.py
   ```

   - 控制台：<http://127.0.0.1:5173/>
   - API 文档：<http://127.0.0.1:8000/docs>

## 验收

```bash
bash .devcontainer/verify.sh
```

该脚本会检查 Python/Node 版本、后端依赖导入、前端依赖是否安装，真实启动
`integrations/sut_template` 的外部 SUT，要求 `evalpilot.sut.validator`（即
`scripts/validate-sut.ps1` 的核心逻辑）接受它，最后运行 P5 测试。任一步失败都会返回
非零退出码。

也可以单独运行：

```bash
PYTHONPATH="$PWD/backend" .venv/bin/python -m pytest backend/tests -q
```

## 环境内容

| 组件 | 版本 | 来源 |
| --- | --- | --- |
| Python | 3.11 | `mcr.microsoft.com/devcontainers/python:3.11-bookworm` |
| Node.js | 22 | `ghcr.io/devcontainers/features/node:1` |
| GitHub CLI | 最新 | `ghcr.io/devcontainers/features/github-cli:1` |

`containerEnv.PYTHONPATH` 指向 `${containerWorkspaceFolder}/backend`，因此容器内的
`python -m pytest backend/tests` 与 `python -m evalpilot.sut.validator` 无需手动设置
`PYTHONPATH`。

## 验证边界

- `devcontainer.json` 已用标准 JSON 解析器校验，`postCreateCommand` 指向的脚本已随仓库提交。
- 本仓库的自动化环境没有 Docker，因此**容器镜像构建与 `postCreateCommand` 未在真实容器内执行**；
  请在本地 Docker 中按上面的步骤首次构建一次。
