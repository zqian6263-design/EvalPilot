# EvalPilot 初赛提交包

Updated: 2026-09-14 ｜ 对应提交：`f9b30e8`（main）

## 可直接提交

- `EvalPilot-Initial-Submission.pdf`：9 页评审版，用于表单附件或人工审阅。
- `EvalPilot-Initial-Submission.pptx`：可编辑版本，含演讲备注。
- `FORM_COPY.md`：队伍描述、作品名称、视频链接、公开产品站和详细描述。
- `EVALUATOR_GUIDE.md`：30 秒、3 分钟和 5 分钟审阅路径。
- `EVIDENCE_INDEX.csv`：五个评分维度逐项对应证据、复现方式和边界。
- `SIMULATED_JUDGE_REVIEW.md`：独立盲审、扣分原因和评委追问。
- `assets/`：演示文稿使用的产品与证据截图。

## 公开入口

- 产品站：https://zqian6263-design.github.io/EvalPilot/
- 视频：https://www.bilibili.com/video/BV1mPYY6sE1k
- 仓库：https://github.com/zqian6263-design/EvalPilot
- Release：https://github.com/zqian6263-design/EvalPilot/releases/tag/evalpilot-v0.1.0-rc1

## 当前实测数据（全部可在仓库内复现）

| 案例 | 实测结果 | 证据文件 | 验收命令 |
| --- | --- | --- | --- |
| 公开 Haystack HTTP SUT | 26 匹配场景 / 18 控制；8 个阻断回归；mean delta `-0.173`；95% CI `[-0.288, -0.077]`；8 次 HTTP 重放 | `docs/PUBLIC_OPEN_SOURCE_CASE.md` | `.\scripts\sut-e2e-check.ps1` |
| 公开 mem0 浏览器任务 | 3 次浏览器反事实重放，两臂真实执行；18 截图 / 18 trace；`0.50`、`0.67` → `1.00`；CI `[-0.3611, -0.0556]` | `docs/P3_BROWSER_RESULT.json` | `.\scripts\p3-browser-check.ps1` |
| 第三方 MCP Python SDK | 3 协议回归 + 3 控制；3 次实测 HTTP 重放；mean `-0.25`；CI `[-0.4167, -0.0833]` | `docs/P4_MCP_RESULT.json` | `.\scripts\p4-mcp-retro-check.ps1` |
| 外部 SUT 接入模板 | 8 匹配场景、5 回归、3 对照、5 次实测重放、16 条 SUT trace、`BLOCK / CRITICAL`；接入校验 28 项 | `docs/P5_E2E_RESULT.json` | `.\scripts\p5-sut-e2e-check.ps1` |
| 可校验发行包 | SHA-256 + MANIFEST.sha256 + 全新解压安装后前后端健康 | `docs/P4_INSTALL_RESULT.json` | `.\scripts\build-release.ps1` → `.\scripts\install-check.ps1` |
| 完整 Live Run 成本 | 52 Judge calls、78,695 tokens、峰值下界 `$0.264697` | `docs/MARKET_EVIDENCE_PACK.md` | `.\scripts\measure-live-cost.ps1` |

后端测试：`464` 项收集（`463 passed / 1 skipped`），全量 exit code `0`（`$env:PYTHONPATH=(Resolve-Path backend); .venv\Scripts\python.exe -m pytest backend\tests -q`）。

## 重新生成

使用 Codex 工作区依赖中的 Python：

```powershell
& "C:\Users\win\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" submission\generate_deck.py
```

验证生成结果：

```powershell
& "C:\Users\win\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" submission\verify_package.py
```

生成结果必须满足：

- PPTX：9 页，每页含演讲备注。
- PDF：9 页。
- 两个文件均包含产品定位、Agent 边界、8/26、52/0、4/4、四个真实适配器、可校验发行包、BLOCK、CI 交付和商业边界。
- 所有截图只来自已在仓库验收的产品或公开证据。

## 提交顺序

1. 打开 `FORM_COPY.md`，复制表单字段。
2. 在线演示视频填写 B 站链接。
3. 作品详细描述使用 `FORM_COPY.md` 中的“作品详细描述”。
4. 如表单允许附件，上传 PDF；需要编辑时使用 PPTX。
5. 提交前再次确认产品站和视频均为公开可访问。

## 包内事实边界

- 不包含任何客户名称、付费收入或市场份额声明。
- `$0.264697` 是已记录场景与价格假设下的运行下界。
- Haystack 的 8 个回归来自受控 candidate patch，不代表上游项目本身存在缺陷。
- 浏览器验收需要本机 Chrome/Edge；缺少浏览器时验收会明确失败，不会退化为预测结论。
