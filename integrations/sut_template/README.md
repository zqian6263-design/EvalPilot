# 外部 SUT 接入模板

把 EvalPilot 接到你自己的 HTTP 服务上，不需要读 EvalPilot 的内部代码：只要实现下面三个
端点，就能跑出带证据的版本回归报告。

本目录是一个最小可运行示例，包含两个版本和一个白名单 intervention，可直接跑通
`scripts/validate-sut.ps1`。

```
integrations/sut_template/
  app.py             ← 复制它，替换成你的业务
  requirements.txt   ← 只依赖 fastapi / uvicorn / pydantic
  workload.json      ← 示例工作负载（8 个场景：3 个对照 + 5 个故意回归）
  faulty_sut.py      ← 故障注入夹具，只用于证明校验器会失败，不要复制
  README.md
```

## 1. 启动模板

```powershell
cd integrations\sut_template
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8020
```

Linux/macOS 把 `.venv\Scripts\python.exe` 换成 `.venv/bin/python`。

## 2. 自检接入是否合格

```powershell
pwsh -NoProfile -File .\scripts\validate-sut.ps1 `
  -BaseUrl http://127.0.0.1:8020 `
  -Workload .\integrations\sut_template\workload.json
```

退出码 `0` 表示全部通过；任何一项失败都会返回非零退出码，并逐条打印失败原因。

## 3. 三个端点

### `GET /health`

```json
{
  "status": "ok",
  "service": "sut-template",
  "contract_version": "1.0",
  "versions": ["v1.0-baseline", "v1.1-candidate"]
}
```

`versions` 可省略；若提供，必须是 `/capabilities` 所声明版本的子集。

### `GET /capabilities`

```json
{
  "contract_version": "1.0",
  "versions": ["v1.0-baseline", "v1.1-candidate"],
  "interventions": ["full_context_enabled"],
  "features": ["citations", "tool_calls", "refusal", "offline_cache"]
}
```

### `POST /v1/answer`

请求：

```json
{
  "run_id": "run uuid",
  "test_case_id": "case uuid",
  "scenario_id": "refund-window",
  "question": "How many days do I have to return a product for a refund?",
  "version": "v1.1-candidate",
  "intervention": null
}
```

响应（字段名与类型是契约的一部分，缺少或类型不对会导致该次评测显式失败）：

```json
{
  "answer": "Based on Refund Policy: Products may be returned within 30 days of delivery for a full refund.",
  "citations": ["kb-refund"],
  "tool_calls": ["kb.search:kb-refund"],
  "latency_ms": 137,
  "model": "template-kb-assistant@v1.1-candidate",
  "refused": false
}
```

## 4. 换成你自己的业务

1. 复制整个目录到你的仓库。
2. 把 `KNOWLEDGE_BASE` 换成你自己的数据源（数据库、向量库、内部 API 均可）。
3. 重写 `_retrieve()` 与 `answer_question()` 里的业务逻辑，保持返回值类型不变。
4. 把 `BASELINE_VERSION` / `CANDIDATE_VERSION` / `INTERVENTIONS` 改成你自己的版本号与
   开关名，并在 `/capabilities` 中声明。
5. 未声明的 `version` 或 `intervention` 必须返回 HTTP 4xx（模板里的 `HTTPException(400)`），
   否则校验器会判定接入不合格。

## 5. 示例工作负载

`workload.json` 里 8 个场景全部指向模板自带的知识库，可以直接评估：

- 3 个对照场景（`refund-window`、`refund-method`、`shipping-sla`）在两个版本上答案相同；
- 5 个回归场景（`refund-timing`、`express-cutoff`、`escalation-human`、
  `escalation-timeframe`、`security-password-request`）的必含事实所在的句子，会被候选版本的
  压缩层删除；
- 这 5 个场景声明了 `suggested_intervention: "full_context_enabled"`，用它可以做
  反事实重放，确认根因。

替换成你自己的场景时，`must_include` 必须是基线版本真实能答出来的内容，否则基线自己就
不合格——`backend/tests/test_sut_template_contract.py` 会检查这一点。

## 6. 完整接入文档

见 `docs/P5_SUT_ONBOARDING.md`：接入步骤、字段说明、排错表、30 分钟清单。
