# EvalPilot

**AI 应用回归评测数字员工**。输入产品需求和版本变更，自动规划测试、调用工具执行、采集证据，并用匹配样本和统计置信区间判断是否存在真实能力回归。

## 当前状态

- 赛道：AI+超级智能体（高校组）
- 初赛截止：2026-09-19
- 演示场景：企业知识库问答 / 智能客服
- 状态：可运行 MVP，前端、后端、评测引擎和端到端验收已打通

## 核心能力

- 自动生成正常、边界和对抗测试用例。
- 通过 API、浏览器、文件和可选沙箱工具执行任务。
- 保存文本、引用、日志、指标和执行轨迹作为证据。
- 使用确定性检查和可注入 LLM Judge 评分。
- 对 baseline / candidate 做匹配比较，报告 effect size、置信区间和 verdict。
- 区分“统计上确认的整体回归”和“局部真实回归”，不会把噪声说成结论。

## 快速开始

```powershell
.\scripts\start-all.ps1
```

启动后访问：

- 控制台：`http://127.0.0.1:5173/`
- API 文档：`http://127.0.0.1:8000/docs`

停止服务：

```powershell
.\scripts\start-all.ps1 -Stop
```

## 验证

```powershell
.\scripts\test-backend.ps1
.\scripts\test-frontend.ps1
.\scripts\e2e-check.ps1
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
