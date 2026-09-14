# EvalPilot 评委审阅指南

Updated: 2026-09-14

## 30 秒判断

EvalPilot 不是聊天机器人，也不是另一个只看总分的评测看板。它回答一个具体发布问题：

> 这次 AI 版本变更是否造成了真实回归；如果是，哪个变更导致失败，是否应立即阻断发布？

## 3 分钟阅读路径

1. 打开产品站：https://zqian6263-design.github.io/EvalPilot/
2. 阅读首屏定位与四步闭环。
3. 查看“公开证据”中的 `8 / 26`、`52 / 0`、`4 / 4`、`12 / 12`（浏览器任务）和 `6 / 6`（第三方 MCP）。
4. 进入“架构”，确认模型可规划但不能覆盖实测结果。
5. 观看 B 站演示：https://www.bilibili.com/video/BV1mPYY6sE1k

## 5 分钟复核路径

### 技术可行性

- 阅读：`docs/P0_VERIFICATION.md`、`docs/P5_SUT_ONBOARDING.md`
- 查看：`docs/P2_PLUS_VERIFICATION.md`、`docs/P4_INSTALL_RESULT.json`
- 复核：公开 Haystack HTTP SUT、离线缓存一致性、SUT 故障显式失败、四个真实适配器、可校验发行包。
- 命令：`.\scripts\sut-e2e-check.ps1`、`.\scripts\p5-sut-e2e-check.ps1`、`.\scripts\install-check.ps1`

### 市场可行性

- 阅读：`docs/MARKET_EVIDENCE_PACK.md`
- 查看：公开竞品价格、公开采用信号、单位成本、CI 门禁与商业模式假设。
- 边界：这些证据证明预算品类和集成路径存在，不冒充真实客户或付费试点。

### 综合创新性

- 阅读：`docs/DIFFERENTIATION_BENCHMARK.md`
- 查看：Naive pass-rate delta 与 EvalPilot 匹配控制结论的差异。
- 关键：配对控制、不确定性和反事实重放共同构成发布结论，而不是叠加一个 AI 文案。
- 诚实性检查：每条反事实必须带真实重放 trace 与引擎生成的 rationale；预测结果不会被标记为实测（`backend/tests/test_acceptance_evidence.py` 强制）。

### AI 大模型结合

- 阅读：`docs/V3_LLM_INTERFACES.md`
- 查看：DeepSeek V4 Pro 规划 8/8、确定性规则 8/8、真实模型调用持久化。
- 关键边界：模型提出下一步实验，白名单校验执行，测量结果决定根因与发布。

### 赛道维度

- 阅读：`docs/V2_INTERFACES.md`、`docs/SUBMISSION_COPY.md`、`docs/P5_SUT_ONBOARDING.md`
- 查看：自然语言目标、规划、工具调用、证据、报告、CI 退出码、回归记忆，以及外部团队接入模板。
- 交付物：BLOCK / REVIEW / ALLOW、Markdown 报告、JUnit、SARIF、PR 回写、可校验发行包。

## 三个可直接复核的实测案例

| 案例 | 关键证据 | 命令 |
| --- | --- | --- |
| 浏览器任务形态（公开 mem0） | 3 次浏览器反事实重放，两臂真实执行：18 截图 / 18 trace，`0.50`、`0.67` → `1.00` | `.\scripts\p3-browser-check.ps1` |
| 第三方 MCP SDK 回顾 | 3 个协议回归 + 3 个控制；3 次实测 HTTP 重放 | `.\scripts\p4-mcp-retro-check.ps1` |
| 外部 SUT 接入模板 | 8 匹配场景、5 回归、3 对照、5 次实测重放、16 trace、`BLOCK / CRITICAL` | `.\scripts\p5-sut-e2e-check.ps1` |

结果文件：`docs/P3_BROWSER_RESULT.json`、`docs/P4_MCP_RESULT.json`、`docs/P5_E2E_RESULT.json`。

## 本地复现

```powershell
git clone https://github.com/zqian6263-design/EvalPilot.git
cd EvalPilot
python scripts/deploy.py
```

确定性演示不需要 API Key。若只审阅产品，不需要安装；公开产品站与视频已覆盖完整流程。

## 证据可信规则

- 实测分数、证据 id、反事实恢复和发布结论由确定性引擎掌握。
- 模型不可写入或覆盖上述结果。
- 外部 SUT 不可用且缓存缺失时明确失败，不静默回退 mock。
- 反事实重放必须真实执行：每条 counterfactual 都要有真实重放 trace 与引擎 rationale；只有预测时不得标记为实测。
- 公开页面中的成本是已记录场景和价格假设下的运行下界。
- 所有商业数字均标注为价格锚点、测算或商业假设，不作为已验证收入。
