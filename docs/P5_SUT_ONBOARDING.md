# P5 外部 SUT 快速接入

目标：一个外部团队在**不阅读 EvalPilot 内部代码**的前提下，30 分钟内把自己的 HTTP
服务接入 EvalPilot，并能跑出真实评测报告。

本页只描述 P5 中实际实现并验证过的能力，验证命令与结果见文末「验证记录」。

## 1. 30 分钟接入清单

| 时间盒 | 动作 | 完成判据 |
| --- | --- | --- |
| 0-5 分钟 | 复制 `integrations/sut_template/` 到你的仓库，`pip install -r requirements.txt` | `uvicorn app:app --port 8020` 能起来 |
| 5-10 分钟 | 用 `curl`/浏览器访问 `GET /health` 与 `GET /capabilities` | 两个端点都返回 JSON，`versions` / `interventions` 是你真实的版本与开关 |
| 10-20 分钟 | 把 `KNOWLEDGE_BASE` 与 `answer_question()` 换成你的业务逻辑 | `POST /v1/answer` 返回 `answer` / `citations` / `tool_calls` / `latency_ms` / `model` / `refused` 六个字段 |
| 20-25 分钟 | 写 `workload.json`（可用 `schemas/workload.schema.json` 对着填） | 每个场景的 `must_include` 都是基线版本真实能答出的内容 |
| 25-30 分钟 | 跑 `scripts/validate-sut.ps1` | 退出码 `0`，无 `[FAIL]` 行 |

## 2. HTTP 契约

EvalPilot 只通过 HTTP 与你通信，你不需要 import 任何 EvalPilot 代码，也不需要是 Python。

### `GET /health`

存活探针。`versions` 可选；若提供，必须是 `/capabilities` 声明版本的子集。

```json
{
  "status": "ok",
  "service": "sut-template",
  "contract_version": "1.0",
  "versions": ["v1.0-baseline", "v1.1-candidate"]
}
```

### `GET /capabilities`

在评测开始前声明能力。EvalPilot 会用这份声明拒绝未声明的版本或 intervention。

```json
{
  "contract_version": "1.0",
  "versions": ["v1.0-baseline", "v1.1-candidate"],
  "interventions": ["full_context_enabled"],
  "features": ["citations", "tool_calls", "refusal", "offline_cache"]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contract_version` | string | 否（默认 `1.0`） | 契约版本 |
| `versions` | string[] | 建议 | 可服务的版本标签，必须真实可服务 |
| `interventions` | string[] | 否 | 白名单开关名，必须真实可执行 |
| `features` | string[] | 否 | 能力声明，仅用于记录 |

未知字段会被拒绝：`SutCapabilities` 使用 `extra="forbid"`。

### `POST /v1/answer`

一次请求 = 一个测试用例。

请求：

```json
{
  "run_id": "8f0c...",
  "test_case_id": "3a91...",
  "scenario_id": "refund-window",
  "question": "How many days do I have to return a product for a refund?",
  "version": "v1.1-candidate",
  "intervention": null
}
```

响应：

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

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `answer` | string | 是 | 不能为空 |
| `citations` | string[] | 否（默认 `[]`） | 会被持久化为 citation 证据 |
| `tool_calls` | string[] | 否（默认 `[]`） | 会被持久化为 trace 证据 |
| `latency_ms` | int | 否（默认 `0`） | `>= 0` |
| `model` | string | 是 | 实际作答的模型/版本标识 |
| `refused` | bool | 否（默认 `false`） | 拒答时为 `true` |

硬约束（校验器与运行时都会强制）：

- 字段名与类型必须完全一致，**未知字段不忽略，直接判失败**；
- `answer` 不能是空字符串；
- 未在 `/capabilities` 中声明的 `version` 或 `intervention`，必须以 HTTP **4xx** 拒绝；
  静默按别的版本作答会让回归报告不可信。

## 3. 工作负载（`EVALPILOT_WORKLOAD_FILE`）

工作负载是 JSON，声明要测哪些场景、期望答案包含哪些事实。

```json
{
  "workload_id": "my-service-v2",
  "baseline_version": "v1.0-baseline",
  "candidate_version": "v1.1-candidate",
  "scenarios": [
    {
      "scenario_id": "refund-window",
      "question": "How many days do I have to return a product for a refund?",
      "category": "normal",
      "difficulty": 0.15,
      "expected_doc_ids": ["kb-refund"],
      "must_include": ["30 days"]
    }
  ]
}
```

| 字段 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `workload_id` | 顶层 | string | 是 | 工作负载标识 |
| `baseline_version` | 顶层 | string | 否 | 基线版本标签，须被 SUT 声明 |
| `candidate_version` | 顶层 | string | 否 | 候选版本标签，须被 SUT 声明 |
| `scenarios` | 顶层 | array | 是 | 至少 1 个场景 |
| `scenario_id` | 场景 | string | 是 | 跨版本匹配键，生成后不要改 |
| `question` | 场景 | string | 是 | 原样发送给 SUT 的问题 |
| `category` | 场景 | enum | 是 | `normal` / `boundary` / `adversarial` / `regression` |
| `difficulty` | 场景 | number | 是 | `0..1`，越大越难/越高风险 |
| `expected_doc_ids` | 场景 | string[] | 是 | 期望引用的文档 id，基线必须能引用到 |
| `must_include` | 场景 | string[] | 是 | 期望出现的事实；按关键词覆盖率计分 |
| `must_avoid` | 场景 | string[] | 否 | 不得出现的短语 |
| `expects_refusal` | 场景 | bool | 否 | 正确行为是拒答 |
| `candidate_drops` / `candidate_leaks` | 场景 | string[] | 否 | 声明的候选缺陷 |
| `hypothesis_domain` / `hypothesis_kind` / `hypothesis_title` | 场景 | string | 否 | 调查假设元数据 |
| `suggested_intervention` | 场景 | string | 否 | 反事实重放使用的开关，须被 SUT 声明 |
| `probe_action` / `recommendation` | 场景 | string | 否 | 探查动作说明 / 修复建议 |
| `browser_url` / `browser_actions` | 场景 | string / array | 否 | 浏览器形态场景 |

完整 schema：`schemas/workload.schema.json`（JSON Schema draft 2020-12）。用标准库校验：

```powershell
.venv\Scripts\python.exe -c "
import json, jsonschema
schema = json.load(open('schemas/workload.schema.json', encoding='utf-8'))
document = json.load(open('integrations/sut_template/workload.json', encoding='utf-8'))
jsonschema.Draft202012Validator(schema).validate(document)
print('workload OK')
"
```

说明：运行时的加载器（`backend/evalpilot/fixtures.py::_load_workload`）为了向后兼容比 schema
更宽松（允许裸数组、允许缺省字段），schema 是**编写与评审时的合同**，两者分工已由测试固定。

## 4. `scripts/validate-sut.ps1`

| 参数 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `-BaseUrl` | 是 | - | SUT 基地址，例如 `http://127.0.0.1:8020` |
| `-Workload` | 否 | - | 工作负载 JSON 路径 |
| `-TimeoutSeconds` | 否 | `20` | 单次请求超时 |
| `-Schema` | 否 | `schemas/workload.schema.json` | 覆盖 schema 路径 |
| `-JsonReport` | 否 | - | 输出机器可读报告 |

```powershell
pwsh -NoProfile -File .\scripts\validate-sut.ps1 `
  -BaseUrl http://127.0.0.1:8020 `
  -Workload .\integrations\sut_template\workload.json `
  -JsonReport .\.runtime\validate-sut.json
```

检查项：

| 检查名 | 内容 |
| --- | --- |
| `workload` / `workload-schema` | 工作负载可读取且满足 `schemas/workload.schema.json` |
| `health` / `health-contract` | `GET /health` 返回 200 且响应体是 JSON 对象 |
| `capabilities` / `capabilities-contract` | `GET /capabilities` 返回 200，声明可被 `SutCapabilities` 解析，版本与 intervention 非空且不重复 |
| `version-consistency` | `/health` 声明的版本是 `/capabilities` 版本的子集 |
| `undeclared-version-rejected` | 未声明的版本被 HTTP 4xx 拒绝 |
| `undeclared-intervention-rejected` | 未声明的 intervention 被 HTTP 4xx 拒绝 |
| `intervention:<name>` | 每个声明的 intervention 真实跑一次，返回 200 且响应符合契约 |
| `workload-capabilities` | 工作负载只引用 SUT 声明过的版本与 intervention |
| `scenario:<id>@<version>` | 每个场景 × 每个声明版本各发一次请求，检查状态码、字段类型、非空 answer |

退出码：`0` = 全部通过；`1` = 至少一项失败；`2` = 参数中的文件路径不存在。
**任何失败都会返回非零退出码，不存在「跳过即通过」。**

CI 用法：

```yaml
- name: Validate external SUT contract
  shell: pwsh
  run: |
    pwsh -NoProfile -File ./scripts/validate-sut.ps1 `
      -BaseUrl ${{ env.SUT_URL }} `
      -Workload ./workload.json `
      -JsonReport ./validate-sut.json
```

## 5. 用真实评测跑一次

接入通过后，沿用既有的外部 SUT 评测路径（P1-P4 已实现并验证，P5 未改动评测口径）：

```powershell
$env:EVALPILOT_SUT_URL = 'http://127.0.0.1:8020'
$env:EVALPILOT_SUT_DISCOVERY = 'true'
$env:EVALPILOT_WORKLOAD_FILE = (Resolve-Path .\integrations\sut_template\workload.json)
python scripts/deploy.py
```

然后在控制台 `http://127.0.0.1:5173/` 创建 `v1.0-baseline -> v1.1-candidate` 的运行。
契约细节见 `docs/EXTERNAL_SUT.md`。

## 6. Dev Container

`.devcontainer/` 提供 Python 3.11 + Node 22 的一次性环境，`postCreateCommand` 现场创建
`.venv` 并安装前后端依赖（不依赖宿主机 `.venv`）。验收：

```bash
bash .devcontainer/verify.sh
```

细节与验证边界见 `.devcontainer/README.md`。

## 7. 排错表

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `[FAIL] health: GET /health failed: ...` | 服务没起来或端口不对 | 先 `curl http://127.0.0.1:8020/health`，确认 BaseUrl 与监听地址 |
| `[FAIL] capabilities: ... HTTP 404` | 没实现 `/capabilities` | 按第 2 节补上；运行时虽然支持 404 回退，但接入验收要求显式声明能力 |
| `[FAIL] capabilities-contract: no versions advertised` | `versions` 为空 | 至少声明一个真实可服务的版本标签 |
| `[FAIL] undeclared-version-rejected: ... was answered with HTTP 200` | 未声明的版本被静默接受 | 对未声明版本返回 400/422，参考模板的 `HTTPException(400)` |
| `[FAIL] scenario:...@v1.1-candidate: ... violates the response contract at latency_ms` | 字段类型不对 | 对照第 2 节字段表逐项修正，注意不要多返回字段（`extra="forbid"`） |
| `[FAIL] scenario:...: ... returned an empty answer` | `answer` 为空字符串 | 保证任何分支都有非空答案，包括拒答分支 |
| `[FAIL] intervention:xxx: ... HTTP 500` | 声明了但没实现该 intervention | 实现它，或从 `/capabilities` 中移除 |
| `[FAIL] workload-schema: ... 'must_include' is a required property` | 工作负载字段缺失 | 按第 3 节字段表补齐 |
| `[FAIL] workload-capabilities: candidate_version=... is not advertised` | 工作负载版本与 `/capabilities` 不一致 | 统一版本标签 |
| `[FAIL] scenario:...@v1.0-baseline: ...` 但候选版本通过 | 基线版本本身答不出 `must_include` | 修正场景或知识库，基线必须能答对 |
| 评测报告显示 inconclusive | 真实差异太小或对照场景太少 | 这是统计结论，不是接入问题；增加对照场景或检查真实缺陷是否仍存在 |

## 8. 验证记录与边界

已在本仓库自动化环境（Windows，Python 3.11.15）验证：

- `integrations/sut_template` 可以真实启动（`scripts/p5-onboarding-check.ps1` 用 uvicorn
  启动真实进程）；
- `scripts/validate-sut.ps1` 对模板返回退出码 `0`；对 6 个故意破坏的 SUT 分别返回非零：
  `health`（503）、`capabilities`（404）、`version`（声明但不可服务）、
  `intervention`（声明但 500）、`silent`（静默接受未声明版本）、`response`（字段类型错误 +
  空 answer）；
- `schemas/workload.schema.json` 由 `jsonschema` 4.26 校验，并通过测试接受本仓库全部
  真实工作负载（`integrations/mcp_retro`、`integrations/mem0_retro`、模板示例）；
- 全量后端测试通过。

未解决边界：

- Docker 不可用，`.devcontainer` 的镜像构建与 `postCreateCommand` **未在真实容器中执行**；
  已用 JSON 解析器校验 `devcontainer.json`，脚本为纯 shell，首次使用请按
  `.devcontainer/README.md` 在本地构建一次。
- 上表「用真实评测跑一次」是既有能力（P1-P4 e2e 已覆盖同一契约），P5 未新增评测口径，
  也**没有**在本分支上重跑一次完整评测；如需端到端证据请运行
  `scripts/sut-e2e-check.ps1`。
