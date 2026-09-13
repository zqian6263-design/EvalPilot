# EvalPilot 初赛提交包

Updated: 2026-09-13

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

- PPTX：9 页。
- PDF：9 页。
- 两个文件均包含产品定位、Agent 边界、8/26、52/0、4/4、BLOCK、CI 交付和商业边界。
- 所有截图只来自已在仓库验收的产品或公开证据。

## 提交顺序

1. 打开 `FORM_COPY.md`，复制表单字段。
2. 在线演示视频填写 B 站链接。
3. 作品详细描述使用 `FORM_COPY.md` 中的“作品详细描述”。
4. 如表单允许附件，上传 PDF；需要编辑时使用 PPTX。
5. 提交前再次确认产品站和视频均为公开可访问。