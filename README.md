# EvalPilot

[![CI](https://github.com/zqian6263-design/EvalPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/zqian6263-design/EvalPilot/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![产品站](https://img.shields.io/badge/在线产品站-GitHub_Pages-165dff)](https://zqian6263-design.github.io/EvalPilot/)

**AI 应用回归评测数字员工**。输入产品需求和版本变更，自动规划测试、调用工具执行、采集证据，并用匹配样本和统计置信区间判断是否存在真实能力回归。

公开产品站：<https://zqian6263-design.github.io/EvalPilot/>

初赛提交包：`submission/README.md`（表单文案、9 页 PPTX/PDF、证据索引和模拟评审）

## 当前状态

- 赛道：AI+超级智能体（高校组）
- 初赛截止：2026-09-19
- 演示场景：企业知识库问答 / 智能客服
- 状态：可运行 MVP，前端、后端、评测引擎和端到端验收已打通

## 演示视频

- B站：<https://www.bilibili.com/video/BV1mPYY6sE1k>
- 直链备用：<https://n.uguu.se/AFnrdUSF.mp4>
- 本地成片：`release/EvalPilot-competition-demo-v2.mp4`

## 核心能力

- 自动生成正常、边界和对抗测试用例。
- 通过 API、浏览器、文件和可选沙箱工具执行任务。
- `browser_run` 支持白名单导航、选择、点击、输入、断言、文本提取、截图和完整动作轨迹。
- 保存文本、引用、日志、指标和执行轨迹作为证据。
- 使用确定性检查和可注入 LLM Judge 评分。
- 对 baseline / candidate 做匹配比较，报告 effect size、置信区间和 verdict。
- 区分“统计上确认的整体回归”和“局部真实回归”，不会把噪声说成结论。
- 确认回归后自动启动发布调查：生成风险假设、召回历史事故、追加探查并输出结构化时间线。
- 通过真实反事实重放确认根因：禁用压缩层恢复条款丢失，恢复安全护栏消除凭证泄露。
- Live LLM 可规划受约束的反事实实验；实验选择经过白名单校验后由引擎真实执行和测量，不能篡改分数或结论。
- OpenAI-compatible 运行时已验证 DeepSeek V4 Pro 与 GLM-4.7；切换仅需环境变量。
- 输出 BLOCK / REVIEW / ALLOW 发布决策和可下载的 Markdown 证据报告。
- 导出 JUnit、SARIF 和 GitHub PR 摘要，直接接入 CI/CD。
- GitHub Webhook 支持 HMAC 校验和 PR 发布门禁回写。
- 支持 Judge 调用/token 预算和配对样本功效诊断。
- 外部 SUT 通过能力发现声明支持的版本、干预和证据能力。
- 外部团队接入模板：`integrations/sut_template/` 是一个可直接运行的 FastAPI SUT（两个版本 + 一个白名单干预），`scripts/validate-sut.ps1` 逐项校验健康检查、能力声明、每个声明版本与每个工作负载场景的响应契约，并用 `schemas/workload.schema.json` 校验工作负载。接入步骤见 `docs/P5_SUT_ONBOARDING.md`。
- 支持 `EVALPILOT_WORKLOAD_FILE` 外部工作负载：不修改内置 fixture 即可评测公开应用的历史版本回归。
- 第三方 MCP SDK 回顾性诊断：隔离运行公开 mcp==1.30.0 与 mcp==2.2.0，识别协议错误通道、错误码和数据丢失，并用 v2 错误路径反事实恢复。
- 可校验源码发行包：生成 SHA-256、内部文件清单，并在全新解压目录中启动前后端完成安装验收。

## 快速开始

跨平台一键启动：

```bash
python scripts/deploy.py
```

Windows 也可以使用：

```powershell
.\scripts\start-all.ps1
```

停止服务：

```bash
python scripts/deploy.py --stop
```

启动后访问：

- 控制台：`http://127.0.0.1:5173/`
- API 文档：`http://127.0.0.1:8000/docs`

停止服务：

```powershell
.\scripts\start-all.ps1 -Stop
```

## 接入你自己的服务（P5）

```powershell
# 1. 启动示例外部 SUT
.venv\Scripts\python.exe -m uvicorn app:app --app-dir integrations\sut_template --host 127.0.0.1 --port 8020

# 2. 校验它是否符合接入契约（失败返回非零退出码）
pwsh -NoProfile -File .\scripts\validate-sut.ps1 `
  -BaseUrl http://127.0.0.1:8020 `
  -Workload .\integrations\sut_template\workload.json
```

30 分钟接入清单、请求/响应示例、字段表和排错表见 `docs/P5_SUT_ONBOARDING.md`；
模板说明见 `integrations/sut_template/README.md`；一次性开发环境见 `.devcontainer/README.md`。

## 验证

```powershell
.\scripts\test-backend.ps1
.\scripts\test-frontend.ps1
.\scripts\e2e-check.ps1
.\scripts\v2-e2e-check.ps1
.\scripts\sut-e2e-check.ps1
.\scripts\p1-mem0-retro-check.ps1
.\scripts\p3-browser-check.ps1
.\scripts\p4-mcp-retro-check.ps1
.\scripts\p5-onboarding-check.ps1
.\scripts\validate-sut.ps1 -BaseUrl http://127.0.0.1:8020 -Workload .\integrations\sut_template\workload.json
.\scripts\build-release.ps1 -Version evalpilot-p4-20260914
.\scripts\install-check.ps1
.venv\Scripts\python.exe backend\scripts\planning_quality_check.py
.venv\Scripts\python.exe backend\scripts\planning_ood_check.py
.venv\Scripts\python.exe backend\scripts\ood_replay_check.py
.venv\Scripts\python.exe backend\scripts\upstream_version_check.py --baseline-python <python3.0-env> --candidate-python .venv\Scripts\python.exe
.venv\Scripts\python.exe backend\scripts\judge_calibration.py <human_scores.csv>
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\public_workload_check.py
.\scripts\measure-live-cost.ps1 -RunId <run-id>
```

`e2e-check.ps1` 会真实启动双服务，创建、执行并轮询一次完整 run，验证报告指标、证据链接、前端代理和截图，然后只停止它自己启动的进程。

## 仓库结构

```text
backend/   FastAPI、运行状态机、SQLite、工具层和统计评测引擎
frontend/  React + TypeScript + Vite 演示控制台
docs/      产品、接口、路演、验收和协作约定
scripts/   一键启动与端到端验收
```

详细说明见 `backend/README.md`、`frontend/README.md`、`docs/COMPETITION_PITCH.md` 和 `docs/E2E.md`。
