# EvalPilot 公开产品站设计

Date: 2026-09-13

Status: Approved direction, pending user review of this specification

## 1. Goal

为 EvalPilot 提供一个公开、快速、无需安装即可理解的产品入口。产品站的首要对象是竞赛评委、潜在用户和技术合作方；目标是让人在两分钟内回答：

1. EvalPilot 解决什么问题；
2. 它如何形成端到端闭环；
3. 哪些结果已经真实测量；
4. 如何查看代码、视频、Release 和完整证据。

产品站不是控制台替代品，也不承担交互式评测功能。它是公开说明、证据索引和演示入口。

## 2. Approach

采用独立静态站方案：

- 站点源码位于 `site/`，与现有 React/Vite 控制台解耦。
- 使用语义化 HTML 和单一样式表，不引入前端框架、包管理器或运行时 JavaScript。
- 由 GitHub Actions 构建并部署 GitHub Pages。
- 中文优先，桌面和移动端均可读。
- 视觉遵循“浅色专业版、极简企业评审工具”：白色与冷灰为主，单一蓝色强调色，无渐变光晕、粒子、机器人插画或装饰性动效。
- 首屏直接给出定位、关键动作和公开视频，不使用阻塞式加载动画。

默认公开地址规划为：

`https://zqian6263-design.github.io/EvalPilot/`

实现后同步更新 GitHub 仓库 Homepage 和 README 顶部入口。自定义域名不在本次范围。

## 3. Information Architecture

页面为单页结构，锚点导航包含：

- 产品
- 闭环
- 证据
- 架构
- 开始使用

首页内容顺序如下。

### 3.1 Hero

- 产品名：`EvalPilot`
- 定位：`AI 应用回归评测与自主发布质量官`
- 核心问题：版本更新后，AI 应用是否悄悄破坏了关键能力？
- 一句话价值：用匹配场景、统计置信和反事实重放，把“感觉变差”变成可验收的发布决策。
- 主按钮：`观看 3 分钟演示`
- 次按钮：`查看 GitHub`
- 次要入口：`v0.1.0-rc1 Release`
- Hero 右侧不放虚假的产品截图；使用纯 HTML/CSS 制作“版本对比 -> 回归确认 -> 根因重放 -> 发布门禁”四步闭环卡片。

### 3.2 Problem

以具体发布风险说明产品价值：

- 新版本可能更快、普通问答得分更高，同时破坏退款条款、权限隔离或安全护栏。
- 单次评测分数变化不能证明真实回归，测试集变难和采样噪声也会造成误判。
- 传统工具能报告失败，却不能稳定回答“哪个变更导致失败、是否足以阻断发布”。

不使用恐吓性语言，不使用客户 Logo 或未经授权的品牌背书。

### 3.3 Closed Loop

展示四个真实能力环节：

1. 匹配回归评测：baseline/candidate 使用同一组 26 个匹配场景。
2. 统计置信与功效：报告效应量、配对置信区间、控制组和 verdict。
3. 反事实根因重放：受约束模型规划候选实验，引擎执行白名单干预并实测恢复情况。
4. 发布质量门禁：输出 `BLOCK / REVIEW / ALLOW`、Markdown 报告、JUnit、SARIF、PR 回写和退出码。

每个环节必须说明模型与确定性引擎的边界：模型可以规划和解释，不能覆盖实测分数、证据、根因结论或发布决策。

### 3.4 Evidence

四张可点击证据卡片：

- `8 / 26`：公开 Haystack 场景中确认的回归数；链接 `docs/PUBLIC_OPEN_SOURCE_CASE.md`。
- `52 / 0`：Haystack 3.0.0 vs 3.1.1 的真实上游比较数 / 语义差异数；链接 `docs/UPSTREAM_VERSION_RESULT.json`。
- `4 / 4`：OOD 可执行反事实干预根因确认数；链接 `docs/OOD_REPLAY_RESULT.json`。
- `52 calls / $0.264697`：完整真实运行中的 Judge 调用数 / 峰值总成本下界；链接 `docs/MARKET_EVIDENCE_PACK.md`。

成本卡片必须标注“按 2026-09-12 已记录单价测算的完整运行下界”，并链接成本假设；不得表述为保证生产单价。若后续数据变化，站点只更新为有源文件支持的数值。

### 3.5 Architecture

用无外链依赖的 HTML/CSS 或内联 SVG 展示：

`产品需求 + 版本变更 -> 匹配场景规划 -> 外部 SUT 执行 -> 证据采集 -> 统计判定 -> 自主调查 -> 反事实重放 -> Release Gate / CI`

同时显示三个清晰边界：

- 外部 SUT 故障会显式失败，不会静默回退 mock。
- LLM Judge 可通过确定性实现替代，并受调用和 token 预算约束。
- 默认离线演示无需 API Key，Live 模式使用 OpenAI-compatible 模型。

### 3.6 Quick Start

提供两条互不混淆的路径：

- 公开产品验证：打开 GitHub Release，查看安装、测试、证据与演示说明。
- 本地一键运行：`python scripts/deploy.py`，然后访问控制台和 API 文档。

代码块必须可复制。页面本身不执行命令，也不请求本地 API。

### 3.7 Final CTA

集中放置：

- Bilibili 演示视频
- GitHub 仓库
- Release
- 许可证
- 安全策略
- 联系方式（仅使用仓库已有的公开联系方式；若没有，则不虚构）

### 3.8 Video

Hero 主按钮锚定到页面内的视频区。视频区使用 Bilibili 官方 iframe：

`https://player.bilibili.com/player.html?bvid=BV1mPYY6sE1k&page=1&high_quality=1&danmaku=0`

iframe 必须有明确标题、懒加载和固定宽高比。第三方播放器加载失败时，保留直接打开 Bilibili 的文本链接。不在站点自动播放视频。

## 4. Visual System

- 页面宽度：内容容器最大 `1120px`。
- 背景：`#f6f8fb`；卡片：`#ffffff`；正文：`#182230`；次要文字：`#475467`。
- 强调色：专业蓝 `#165dff`；成功：`#067647`；风险：`#b42318`。
- 字体：`system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif`。
- 正文基线：`16px`，行高不低于 `1.65`；移动端标题不做超大字号。
- 边框：`1px solid #dfe3e8`；阴影只用于区分层级，不使用发光效果。
- 圆角：`12px` 以内；按钮和卡片保持企业工具风格。
- 所有正文与背景对比度达到 WCAG AA。
- 动效仅允许输入控件和链接的短状态过渡；支持 `prefers-reduced-motion`。
- 图标仅在表达状态时有意义，优先使用文字和简单几何标记，不依赖图标字体。

## 5. Technical Design

### 5.1 Files

实现将新增：

- `site/index.html`
- `site/styles.css`
- `site/favicon.svg`
- `site/robots.txt`
- `site/sitemap.xml`
- `site/404.html`
- `.github/workflows/pages.yml`

可能更新：

- `README.md`：首页顶部增加产品站入口。
- GitHub 仓库 Homepage 设置：指向 Pages 地址。

不修改 `frontend/`、`backend/` 或运行时接口。

### 5.2 Static behavior

- 页面主体在禁用 JavaScript 时完整可用。
- 不加入分析脚本、Cookie、广告、追踪像素或第三方字体。
- 除 Bilibili iframe 外，不加载第三方运行时资源。
- 所有内部锚点使用稳定 `id`。
- 证据链接直接指向 GitHub 文件，避免复制证据正文而失去来源。
- 外链使用 `rel="noopener noreferrer"`。
- 页面不包含 API Key、Token、内网地址、个人手机号或未公开材料。

### 5.3 GitHub Pages deployment

新增 `.github/workflows/pages.yml`：

- 触发：推送到 `main`、手动触发。
- 权限：`contents: read`、`pages: write`、`id-token: write`。
- 并发：同一 ref 只保留最新部署，取消旧部署。
- 步骤：
  1. `actions/checkout@v7`
  2. `actions/configure-pages@v6`
  3. `actions/upload-pages-artifact@v4`，路径为 `site/`
  4. `actions/deploy-pages@v5`
- 部署环境：`github-pages`。
- 部署失败必须让 workflow 失败，不能显示为“已发布”。

实现前需核对 action 的主版本仍受 GitHub 官方支持；若仓库现行版本策略不同，以 GitHub 官方当前稳定主版本为准，并在计划中明确。

### 5.4 Search metadata

- `title`：`EvalPilot｜AI 应用回归评测与自主发布质量官`
- `description`：`用匹配回归评测、统计置信与反事实重放，为 AI 应用生成可验收的发布决策。`
- 设置 `lang="zh-CN"`、viewport、theme-color、canonical、Open Graph 和 Twitter Card 基础字段。
- 本次不生成独立 OG 图片，避免增加无证据的品牌资产；能否复用现有视频封面，推迟到后续独立任务。

## 6. Error Handling and Degradation

- CSS 加载失败时，HTML 仍保留正确的线性阅读顺序。
- Bilibili iframe 不可用时，用户仍可通过可见链接访问视频。
- GitHub Pages 404 页面提供返回首页、GitHub 和 Release 入口。
- 外链目标不存在不得通过占位 URL 掩盖；实现时逐一验证 HTTP 状态。
- sitemap 使用最终确定的生产地址；在首次成功部署前不添加不可验证的自定义域名。

## 7. Accessibility

- 页面只使用一个 `h1`，标题层级连续。
- 跳过导航链接可用。
- 所有可交互元素具有可见焦点样式和至少 `44px` 的移动端触控高度。
- iframe 提供 `title`。
- 装饰性图形使用 `aria-hidden="true"`；信息图提供等价文本。
- 颜色不是传递状态的唯一方式。
- 在 360px、768px、1440px 宽度下无横向滚动。
- 键盘可以访问全部导航和链接。

## 8. Testing and Acceptance

实现验收必须包含：

1. 在 `site/` 使用本地静态服务器启动，`GET /` 返回 `200`。
2. HTML 不引用缺失的内部文件。
3. 所有生产外链执行 HTTP 检查；允许 Bilibili/GitHub 对 HEAD 的限制时以 GET 复核。
4. 检查页面不包含常见密钥模式、`localhost`、`127.0.0.1` 或私网地址。
5. 桌面 `1440x900` 和移动 `390x844` 截图人工检查。
6. 键盘导航、跳过链接、焦点可见性和线性 DOM 顺序人工检查。
7. 无 JavaScript 环境可读、可导航。
8. GitHub Pages workflow 成功，线上 URL 返回 `200`。
9. 线上页面显示真实数值，且每个证据卡链接到对应源文件。
10. README 和 GitHub Homepage 指向线上站点。
11. 现有后台、前端和 E2E 测试不回归。

## 9. Evidence and Claim Rules

- 只使用 `PRODUCT.md`、`README.md` 和 `docs/` 中已经验证的事实。
- 不写“行业第一”“生产级零风险”“已被客户采用”等无法证明的声明。
- 不虚构客户、访谈、付费试点、市场份额或商业合同。
- 不把 roadmap 写成已实现能力。
- 数值必须可追溯到文件；若证据文件更新，产品站数值必须同步。
- `8 / 26` 只描述公开 Haystack 回归案例，不泛化为所有项目都能发现 8 个问题。
- `52 / 0` 只描述指定版本比较，不泛化为所有版本升级都无回归。
- `$0.264697` 是已记录场景和价格假设下的成本，不表述为普适定价。

## 10. Explicit Non-goals

本次不包含：

- 在线执行评测或调用本地 API；
- 用户登录、数据库、表单收集或邮件订阅；
- 控制台功能重做；
- 自定义域名、CDN、分析平台或增长埋点；
- 英文完整镜像；
- 自动生成或购买品牌插画、客户案例和推荐语；
- 修改评测引擎、工具白名单或 Release Gate 语义。

## 11. Success Criteria

产品站在公开环境上线后，应满足：

- 评委无需安装即可理解产品定位、闭环和证据；
- 从首屏到视频最多一次点击；
- 从任一证据卡到源文件最多一次点击；
- 360px 移动端可完整阅读；
- 页面无运行时错误且不产生额外服务成本；
- 所有公开声明与仓库证据一致；
- Pages 部署可重复、失败可见，并由 main 分支自动更新。