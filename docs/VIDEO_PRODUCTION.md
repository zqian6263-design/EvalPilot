# EvalPilot Competition Video Production

Status: v2 rendered at `release/EvalPilot-competition-demo-v2.mp4` (2:28.97, 1920x1080, 30fps); v1 remains at `release/EvalPilot-competition-demo.mp4`.

The v2 cut inserts `release/EvalPilot-model-plan-slide.png` from 1:10 to 1:25. It shows the actual DeepSeek V4 Pro replay plan, the 8/8 comparison with deterministic planning, token cost, and the validation boundary. Public mirrors: https://n.uguu.se/AFnrdUSF.mp4 (direct MP4, temporary) and https://gofile.io/d/TPBMWhtR (public download page, backup). Replace with Bilibili/YouTube after login for a permanent submission link.

Target duration: 2 minutes 30 seconds  
Language: Chinese  
Format: 1920x1080, 30 fps, H.264 MP4  
Evidence rule: every number shown comes from a running or recorded live run.

## Story

A candidate release is faster and ordinary answers still work, so the team wants
to ship it. EvalPilot proves that two independent regressions remain, replays
the failures to identify their causes, and blocks the release with evidence.

## Shot list

### 0:00-0:15 — Problem

Visual: title slide and a simple release flow.

Narration:

> AI 应用每次修改模型、Prompt、检索或工具，都可能让正常回答看起来更好，却悄悄破坏安全、合规和服务流程。真正危险的不是分数变化，而是团队无法证明这次变化是否造成了回归。

### 0:15-0:45 — Confirm the regression

Visual: console at `#console&demo`.

Show:

- candidate is faster;
- 26 matched scenarios;
- 18 controls;
- 8 regressions;
- mean delta `-0.173`, 95% CI `-0.288 to -0.077`;
- verdict `已确认回归`.

Narration:

> 候选版本把响应时间缩短了约 75 毫秒，普通问题仍然通过。但 EvalPilot 用同一组 26 个场景分别运行两个版本，结果有 8 个场景发生了稳定回归，18 个对照组完全不变。配对置信区间整体落在回归阈值以下，因此这不是采样噪声。

### 0:45-1:10 — Show the failures and evidence

Visual: Findings page and one evidence drawer.

Show:

- prompt-injection-password;
- escalation-path;
- urgent-safety;
- evidence ids and recommendations.

Narration:

> 失败集中在两类高风险行为：压缩层丢失了升级、安全和时限条款；安全护栏失效导致提示注入场景泄露了凭据。每个结论都能追溯到具体场景、输入输出和证据 ID。

### 1:10-1:50 — Investigate the root cause

Visual: Investigation page after a real live run.

Show:

- live model badge;
- risk hypotheses;
- historical incident recall;
- probe actions;
- the model-guided replay plan;
- counterfactual replays;
- compression restores seven scenarios;
- security guard restores one scenario.

Narration:

> 确认回归后，EvalPilot 不是直接给出建议，而是启动自主调查。它会生成风险假设、召回历史事故、追加探查，再分别禁用可疑变更进行反事实重放。结果显示，关闭压缩层后 7 个场景恢复通过，恢复安全护栏后凭证泄露消失。模型负责规划和解释，但不能覆盖实测结果。

### 1:50-2:15 — Release decision and report

Visual: decision panel and downloaded report.

Show:

- `BLOCK`;
- risk `CRITICAL`;
- blocking findings;
- report download;
- model rationale section.

Narration:

> 最终输出不是一张分数表，而是一份可验收的发布决策：阻断、严重风险、根因、修复建议和完整证据报告。发布经理可以直接依据这份报告停止上线，并把修复项交给工程团队。

### 2:15-2:30 — Value and closing

Visual: three-step value summary.

Text:

```text
更快发现真实回归
定位导致回归的变更
用可审计证据阻止不安全发布
```

Narration:

> EvalPilot 把 AI 发布从经验判断变成可复现的证据决策。它不是另一个问答机器人，而是一名能够接管发布质量检查、定位根因并交付结论的 AI 数字员工。

## Reproducible deep links

- Existing run: `#console&run=<run-id>`
- Existing live investigation: `#investigation&run=<run-id>&inv=<investigation-id>`

These links open recorded service data and do not create a new run.

## Recording rules

- Prefer a pre-warmed completed run for the main console sequence.
- Use a real live investigation artifact; cut waiting time rather than faking it.
- Keep the live model badge visible in at least one shot.
- Do not show private chain-of-thought.
- Show structured actions, tool calls, evidence, and artifacts only.
- Recheck every visible number against the current run before rendering.
- If live mode fails, use deterministic mode for continuity and clearly label it.
