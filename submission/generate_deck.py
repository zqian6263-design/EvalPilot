from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission"
ASSETS = OUT / "assets"

ACCENT = "165DFF"
ACCENT_SOFT = "EAF1FF"
TEXT = "182230"
MUTED = "475467"
BORDER = "DFE3E8"
SURFACE = "FFFFFF"
BG = "F6F8FB"
MUTED_BG = "EEF2F7"
DANGER = "B42318"
DANGER_SOFT = "FEF3F2"
SUCCESS = "067647"
SUCCESS_SOFT = "ECFDF3"
WARNING = "B54708"
WARNING_SOFT = "FFFAEB"


def rgb(value: str) -> RGBColor:
    value = value.lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def set_run(run, size: int, color: str, bold: bool = False, font: str = "Microsoft YaHei") -> None:
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)


def add_text(slide, x: float, y: float, w: float, h: float, text: str | Iterable[str], size: int = 18,
             color: str = TEXT, bold: bool = False, align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP,
             margin: float = 0.0, line_spacing: float = 1.0) -> object:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(margin)
    tf.margin_right = Inches(margin)
    tf.margin_top = Inches(margin)
    tf.margin_bottom = Inches(margin)
    tf.vertical_anchor = valign
    lines = [text] if isinstance(text, str) else list(text)
    for index, line in enumerate(lines):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        run = p.add_run()
        set_run(run, size, color, bold)
        run.text = line
    return box


def add_rect(slide, x: float, y: float, w: float, h: float, fill: str = SURFACE, line: str = BORDER,
             radius: bool = True, line_width: float = 1.0) -> object:
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line)
    shape.line.width = Pt(line_width)
    return shape


def add_image_fit(slide, path: Path, x: float, y: float, w: float, h: float) -> object:
    with Image.open(path) as image:
        iw, ih = image.size
    box_ratio = w / h
    image_ratio = iw / ih
    if image_ratio >= box_ratio:
        draw_w = w
        draw_h = w / image_ratio
        draw_x = x
        draw_y = y + (h - draw_h) / 2
    else:
        draw_h = h
        draw_w = h * image_ratio
        draw_x = x + (w - draw_w) / 2
        draw_y = y
    return slide.shapes.add_picture(str(path), Inches(draw_x), Inches(draw_y), Inches(draw_w), Inches(draw_h))


def add_notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def slide_header(slide, number: int, kicker: str, title: str) -> None:
    add_text(slide, 0.55, 0.28, 4.8, 0.3, f"EVALPILOT  ·  {kicker}", 10, ACCENT, True)
    add_text(slide, 0.55, 0.66, 12.2, 0.62, title, 29, TEXT, True)
    line = add_rect(slide, 0.55, 1.35, 12.23, 0.025, ACCENT, ACCENT, False, 0)
    line.fill.solid()
    line.fill.fore_color.rgb = rgb(ACCENT)
    add_text(slide, 0.55, 7.12, 2.5, 0.2, "逆熵智评 · NEGENTROPY LABS", 8, MUTED)
    add_text(slide, 12.1, 7.12, 0.7, 0.2, f"{number:02d}", 8, MUTED, True, PP_ALIGN.RIGHT)


def add_metric(slide, x: float, y: float, w: float, label: str, value: str, note: str,
               color: str = ACCENT, fill: str = SURFACE, h: float = 1.25) -> None:
    add_rect(slide, x, y, w, h, fill, BORDER, True)
    add_text(slide, x + 0.18, y + 0.14, w - 0.36, 0.22, label, 9, MUTED, True)
    add_text(slide, x + 0.18, y + 0.38, w - 0.36, 0.43, value, 25, color, True)
    add_text(slide, x + 0.18, y + 0.84, w - 0.36, 0.28, note, 9, MUTED)


def add_bullet_list(slide, x: float, y: float, w: float, items: list[str], gap: float = 0.55,
                    color: str = TEXT, size: int = 15) -> None:
    for index, item in enumerate(items):
        yy = y + index * gap
        add_text(slide, x, yy, 0.18, 0.22, "●", size - 5, ACCENT, True)
        add_text(slide, x + 0.25, yy - 0.015, w - 0.25, 0.45, item, size, color)
def build_pptx() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    add_text(slide, 0.65, 0.45, 4.6, 0.3, "逆熵智评  ·  NEGENTROPY LABS", 11, ACCENT, True)
    add_text(slide, 0.65, 1.1, 6.1, 1.45, "EvalPilot", 34, ACCENT, True)
    add_text(slide, 0.65, 1.9, 6.4, 1.15, "AI 应用回归评测\n与自主发布质量官", 30, TEXT, True)
    add_text(slide, 0.65, 3.35, 5.9, 0.85, "用匹配评测、统计置信和反事实重放，把版本变化变成可验收的发布决策。", 18, MUTED)
    add_rect(slide, 0.65, 4.55, 5.85, 0.76, ACCENT_SOFT, ACCENT_SOFT, True)
    add_text(slide, 0.86, 4.72, 5.4, 0.42, "8 / 26 回归 · 52 / 0 上游比较 · 4 / 4 OOD 根因", 15, ACCENT, True)
    add_text(slide, 0.65, 5.65, 5.9, 0.65, "公开产品站：zqian6263-design.github.io/EvalPilot\n演示视频：bilibili.com/video/BV1mPYY6sE1k", 11, MUTED)
    add_image_fit(slide, ASSETS / "cover.png", 6.7, 1.0, 5.95, 5.4)
    add_notes(slide, "30 秒开场：AI 版本即使普通问答通过，也可能静默破坏条款、权限或安全护栏。EvalPilot 的交付物不是分数，而是可阻断发布的证据决策。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 2, "问题", "普通问答通过，不等于关键能力没有退化")
    add_text(slide, 0.55, 1.72, 12.1, 0.55, "版本更新可能更快、总分更高，却同时破坏产品必须长期守住的能力。", 17, MUTED)
    cards = [
        ("条款与流程丢失", "退款、升级、电池处置等强制条款被摘要压缩掉。", DANGER),
        ("权限与隔离失效", "租户记忆串扰、缓存返回旧错误，业务边界被绕过。", WARNING),
        ("安全护栏失效", "凭证注入从拒绝泄露变成直接输出敏感信息。", DANGER),
    ]
    for index, (title, body, color) in enumerate(cards):
        x = 0.55 + index * 4.16
        add_rect(slide, x, 2.55, 3.82, 2.35, SURFACE, BORDER, True)
        add_rect(slide, x, 2.55, 0.08, 2.35, color, color, False, 0)
        add_text(slide, x + 0.35, 2.87, 3.15, 0.4, title, 19, TEXT, True)
        add_text(slide, x + 0.35, 3.42, 3.15, 1.05, body, 14, MUTED)
    add_rect(slide, 0.55, 5.35, 12.23, 0.92, MUTED_BG, BORDER, True)
    add_text(slide, 0.85, 5.54, 11.6, 0.45, "团队需要的不是“再一个分数”，而是：是否真实回归、由哪个变更造成、是否应立即阻断发布。", 18, TEXT, True, PP_ALIGN.CENTER)
    add_notes(slide, "用三个已实现的失败类型说明问题。注意不要说传统工具完全做不到，而是说 EvalPilot 把版本因果比较、根因重放和发布阻断连成了端到端交付。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 3, "产品", "一个能接管发布质量闭环的数字员工")
    steps = [
        ("01", "理解与规划", "读取需求与版本变更\n生成风险地图和测试任务"),
        ("02", "执行与取证", "调用 HTTP / 文件 / KB 工具\n保存结果、引用和轨迹"),
        ("03", "统计判定", "26 个匹配场景 + 18 个控制组\n报告效应量与配对区间"),
        ("04", "根因重放", "受约束模型提出实验\n引擎执行白名单干预"),
        ("05", "发布门禁", "BLOCK / REVIEW / ALLOW\n报告、JUnit、SARIF、PR 回写"),
    ]
    for index, (num, title, body) in enumerate(steps):
        x = 0.55 + index * 2.46
        add_rect(slide, x, 1.72, 2.18, 2.55, SURFACE, BORDER, True)
        add_text(slide, x + 0.2, 1.92, 0.45, 0.25, num, 11, ACCENT, True)
        add_text(slide, x + 0.2, 2.34, 1.8, 0.45, title, 16, TEXT, True)
        add_text(slide, x + 0.2, 2.92, 1.78, 1.0, body, 11, MUTED)
        if index < len(steps) - 1:
            add_text(slide, x + 2.17, 2.75, 0.3, 0.35, "→", 18, ACCENT, True, PP_ALIGN.CENTER)
    add_image_fit(slide, ASSETS / "console.png", 0.55, 4.6, 7.0, 2.05)
    add_rect(slide, 7.82, 4.6, 4.96, 2.05, SURFACE, BORDER, True)
    add_text(slide, 8.12, 4.85, 4.35, 0.34, "交付物不是建议，而是可验收结果", 18, TEXT, True)
    add_bullet_list(slide, 8.12, 5.38, 4.25, ["可下载 Markdown 证据报告", "CI 退出码 0 / 1 / 2", "可复现 run id 与 evidence id"], gap=0.38, size=12)
    add_notes(slide, "强调闭环和交付物。截图是实际产品控制台，不是概念图。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 4, "智能体边界", "模型可以规划，但不能覆盖实测结论")
    left = ["自然语言目标", "风险假设", "受约束计划", "白名单干预", "实测恢复", "发布决策"]
    for index, label in enumerate(left):
        y = 1.72 + index * 0.78
        add_rect(slide, 0.75, y, 4.25, 0.55, ACCENT_SOFT if index != 5 else SUCCESS_SOFT, BORDER, True)
        add_text(slide, 1.0, y + 0.13, 3.75, 0.28, label, 14, ACCENT if index != 5 else SUCCESS, True)
        if index < len(left) - 1:
            add_text(slide, 2.75, y + 0.55, 0.3, 0.22, "↓", 13, MUTED, True, PP_ALIGN.CENTER)
    add_rect(slide, 5.55, 1.72, 3.25, 4.45, SURFACE, BORDER, True)
    add_text(slide, 5.85, 2.0, 2.65, 0.4, "LLM 权限", 19, ACCENT, True)
    add_bullet_list(slide, 5.85, 2.62, 2.65, ["提出风险假设", "选择可执行实验", "解释证据和修复建议", "生成报告叙述"], gap=0.64, size=13)
    add_rect(slide, 9.05, 1.72, 3.73, 4.45, DANGER_SOFT, BORDER, True)
    add_text(slide, 9.35, 2.0, 3.13, 0.4, "确定性引擎权威", 19, DANGER, True)
    add_bullet_list(slide, 9.35, 2.62, 3.13, ["写入分数与证据 id", "执行并测量反事实", "决定根因与风险", "生成 BLOCK / REVIEW / ALLOW"], gap=0.64, size=13, color=TEXT)
    add_text(slide, 5.85, 5.05, 6.62, 0.62, "DeepSeek V4 Pro 规划 8/8；确定性规则同样 8/8。模型可改变下一步实验，但不能改变答案。", 14, MUTED, True)
    add_notes(slide, "这是全篇最重要的一页。用左侧流程说明 Agent 确实参与控制流，用右侧两栏说明权威边界，避免评委认为大模型只是文案生成。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 5, "实测证据", "真实回归已经被确认、测量和阻断")
    add_metric(slide, 0.55, 1.65, 2.85, "匹配场景", "26", "baseline / candidate 同题运行")
    add_metric(slide, 3.58, 1.65, 2.85, "控制组", "18", "同版本对照完全一致")
    add_metric(slide, 6.61, 1.65, 2.85, "阻断回归", "8", "7 条款 + 1 凭证泄露", DANGER, DANGER_SOFT)
    add_metric(slide, 9.64, 1.65, 3.14, "发布结论", "BLOCK", "风险级别 CRITICAL", DANGER, DANGER_SOFT)
    add_image_fit(slide, ASSETS / "method.png", 0.55, 3.22, 7.45, 3.15)
    add_rect(slide, 8.25, 3.22, 4.53, 3.15, SURFACE, BORDER, True)
    add_text(slide, 8.55, 3.5, 3.95, 0.34, "配对结果", 16, TEXT, True)
    add_text(slide, 8.55, 3.94, 3.9, 0.48, "mean delta  -0.173", 21, DANGER, True)
    add_text(slide, 8.55, 4.5, 3.9, 0.3, "95% CI  [-0.288, -0.077]", 15, TEXT, True)
    add_text(slide, 8.55, 5.0, 3.9, 0.75, "Live Run：52 Judge calls\n78,695 tokens · 峰值成本 $0.264697", 12, MUTED)
    add_text(slide, 8.55, 5.86, 3.9, 0.3, "成本下界，不是通用报价", 9, WARNING, True)
    add_notes(slide, "先讲 26 和 18，再讲 8 和区间。必须说明 8/26 是受控公开案例，不是所有版本都一定有 8 个回归。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 6, "根因重放", "不是猜测原因，而是禁用变更后重新测量")
    add_rect(slide, 0.55, 1.67, 3.25, 1.35, DANGER_SOFT, BORDER, True)
    add_text(slide, 0.82, 1.88, 0.65, 0.45, "8", 26, DANGER, True)
    add_text(slide, 1.52, 1.97, 2.0, 0.26, "失败场景", 15, TEXT, True)
    add_text(slide, 0.82, 2.47, 2.72, 0.28, "通过 HTTP 边界逐项重放", 11, MUTED)
    add_text(slide, 3.95, 2.12, 0.35, 0.35, "→", 20, ACCENT, True)
    add_rect(slide, 4.45, 1.67, 4.05, 1.35, SURFACE, BORDER, True)
    add_text(slide, 4.72, 1.88, 3.5, 0.3, "关闭压缩层", 17, ACCENT, True)
    add_text(slide, 4.72, 2.32, 3.5, 0.42, "7 个条款 / 流程失败恢复", 16, TEXT, True)
    add_rect(slide, 8.72, 1.67, 4.06, 1.35, SURFACE, BORDER, True)
    add_text(slide, 8.99, 1.88, 3.5, 0.3, "恢复安全护栏", 17, DANGER, True)
    add_text(slide, 8.99, 2.32, 3.5, 0.42, "1 个凭证泄露恢复拒绝", 16, TEXT, True)
    add_image_fit(slide, ASSETS / "model-plan.png", 0.55, 3.25, 7.55, 3.15)
    add_rect(slide, 8.35, 3.25, 4.43, 3.15, SURFACE, BORDER, True)
    add_text(slide, 8.65, 3.52, 3.8, 0.34, "可执行根因证据", 17, TEXT, True)
    add_metric(slide, 8.65, 4.0, 1.82, "OOD", "4 / 4", "HTTP 实测恢复", SUCCESS, SUCCESS_SOFT, 1.22)
    add_metric(slide, 10.62, 4.0, 1.86, "模型规划", "8 / 8", "需白名单校验", ACCENT, SURFACE, 1.22)
    add_text(slide, 8.65, 5.48, 3.8, 0.55, "确定性规则同样 8/8；模型能力是扩展路径，不是不可替代的黑箱。", 12, MUTED)
    add_notes(slide, "先讲反事实恢复数字，再用 OOD 4/4 证明不是只对已知 fixture 硬编码。模型规划 8/8 与规则 8/8 并列，避免过度包装。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 7, "开源适配", "对真实公开栈工作，也对故障明确失败")
    add_rect(slide, 0.55, 1.7, 6.2, 2.22, SURFACE, BORDER, True)
    add_text(slide, 0.85, 1.98, 5.6, 0.33, "公开 Haystack HTTP SUT", 18, TEXT, True)
    add_text(slide, 0.85, 2.5, 5.55, 0.62, "DocumentSplitter → BM25 Retriever → DocumentJoiner\n→ GroundedReranker → grounded answer", 14, ACCENT, True)
    add_text(slide, 0.85, 3.25, 5.55, 0.35, "Apache-2.0 · haystack-ai 3.1.1", 11, MUTED)
    add_metric(slide, 7.05, 1.7, 2.65, "上游比较", "52 / 0", "3.0.0 vs 3.1.1 语义差异", SUCCESS, SUCCESS_SOFT, 1.55)
    add_metric(slide, 9.95, 1.7, 2.83, "候选回归", "8 / 26", "mean delta -0.173", DANGER, DANGER_SOFT, 1.55)
    add_image_fit(slide, ASSETS / "report.png", 0.55, 4.25, 7.05, 2.15)
    add_rect(slide, 7.9, 4.25, 4.88, 2.15, SURFACE, BORDER, True)
    add_text(slide, 8.2, 4.55, 4.25, 0.34, "证据不是“能跑一次”", 17, TEXT, True)
    add_bullet_list(slide, 8.2, 5.06, 4.2, ["同版本控制 0 回归", "离线缓存精确复现", "SUT 故障明确失败，不回退 mock"], gap=0.43, size=12)
    add_notes(slide, "说明公开开源依赖、受控 candidate patch 和失败语义。再次强调受控 patch 不代表上游项目本身有缺陷。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 8, "市场与交付", "不与监控平台竞争，只守发布前最后一道门")
    add_rect(slide, 0.55, 1.68, 4.05, 4.85, SURFACE, BORDER, True)
    add_text(slide, 0.85, 1.98, 3.45, 0.35, "市场切口", 18, TEXT, True)
    add_text(slide, 0.85, 2.5, 3.45, 0.8, "Given baseline + candidate，输出可阻断发布的证据决策。", 16, ACCENT, True)
    add_bullet_list(slide, 0.85, 3.45, 3.45, ["公开付费品类已存在", "兼容现有 observability", "CI 是明确采购入口"], gap=0.62, size=13)
    add_text(slide, 0.85, 5.55, 3.4, 0.65, "证明预算品类与集成路径，不声称已有付费转化。", 11, MUTED)
    add_rect(slide, 4.85, 1.68, 3.75, 4.85, SURFACE, BORDER, True)
    add_text(slide, 5.15, 1.98, 3.15, 0.35, "成本与交付", 18, TEXT, True)
    add_text(slide, 5.15, 2.55, 3.15, 0.55, "$0.264697", 25, ACCENT, True)
    add_text(slide, 5.15, 3.1, 3.15, 0.32, "一次完整 Live Run 峰值下界", 11, MUTED)
    add_bullet_list(slide, 5.15, 3.7, 3.15, ["BLOCK / REVIEW / ALLOW", "Markdown / JUnit / SARIF", "退出码 0 / 1 / 2", "GitHub PR 回写"], gap=0.55, size=12)
    add_rect(slide, 8.83, 1.68, 3.95, 4.85, SURFACE, BORDER, True)
    add_text(slide, 9.13, 1.98, 3.35, 0.35, "商业策略（假设）", 18, TEXT, True)
    add_bullet_list(slide, 9.13, 2.65, 3.35, ["Release audit\n固定范围审计", "Team subscription\n持续回归门禁", "Enterprise self-host\n私有化与合规"], gap=0.95, size=13)
    add_text(slide, 9.13, 5.62, 3.35, 0.5, "价格锚点来自公开竞品，不冒充已验证收入。", 11, WARNING, True)
    add_notes(slide, "市场页不说“市场巨大”或“客户很多”。只说公开付费品类、集成入口、实测成本和可证伪商业假设。")

    slide = prs.slides.add_slide(blank)
    add_rect(slide, 0, 0, 13.333, 7.5, BG, BG, False, 0)
    slide_header(slide, 9, "下一步", "先守住发布决策，再扩大公开证据")
    add_rect(slide, 0.55, 1.72, 3.75, 3.95, SUCCESS_SOFT, BORDER, True)
    add_text(slide, 0.85, 2.02, 3.15, 0.35, "现在：已验证", 18, SUCCESS, True)
    add_bullet_list(slide, 0.85, 2.68, 3.15, ["公开产品站", "真实 HTTP SUT", "模型受约束规划", "Release Gate"], gap=0.68, size=13)
    add_rect(slide, 4.55, 1.72, 3.75, 3.95, ACCENT_SOFT, BORDER, True)
    add_text(slide, 4.85, 2.02, 3.15, 0.35, "下一阶段", 18, ACCENT, True)
    add_bullet_list(slide, 4.85, 2.68, 3.15, ["公开未知故障回顾", "第二模型供应商", "真实使用信号", "更多发布适配器"], gap=0.68, size=13)
    add_rect(slide, 8.55, 1.72, 4.23, 3.95, SURFACE, BORDER, True)
    add_image_fit(slide, ASSETS / "product-site.png", 8.85, 2.08, 3.63, 2.1)
    add_text(slide, 8.85, 4.42, 3.63, 0.8, "产品站已验证公开可访问\n所有数据均有源文件与复现命令", 12, MUTED, True)
    add_rect(slide, 0.55, 5.95, 12.23, 0.68, TEXT, TEXT, True)
    add_text(slide, 0.85, 6.08, 11.6, 0.34, "用证据决定，而不是用感觉发布。", 20, "FFFFFF", True, PP_ALIGN.CENTER)
    add_notes(slide, "收束到一句主张：不是增加更多 AI 功能，而是把 AI 发布从主观判断变成可验证、可阻断的工程流程。")

    return prs

PDF_W = 13.333 * 72
PDF_H = 7.5 * 72
PDF_FONT = "SimHei"


def pdf_color(value: str):
    value = value.lstrip("#")
    return colors.HexColor("#" + value)


def wrap_text(text: str, font_size: float, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        line = ""
        for char in paragraph:
            candidate = line + char
            if pdfmetrics.stringWidth(candidate, PDF_FONT, font_size) <= max_width:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = char
        if line:
            lines.append(line)
    return lines


def pdf_text(c, x: float, y: float, w: float, h: float, text: str, size: float = 18,
             color: str = TEXT, align: str = "left", leading: float = 1.25) -> None:
    del h
    c.setFillColor(pdf_color(color))
    c.setFont(PDF_FONT, size)
    lines = wrap_text(text, size, w)
    line_height = size * leading
    for index, line in enumerate(lines):
        yy = PDF_H - y - size - index * line_height
        if align == "center":
            c.drawCentredString(x + w / 2, yy, line)
        elif align == "right":
            c.drawRightString(x + w, yy, line)
        else:
            c.drawString(x, yy, line)


def pdf_rect(c, x: float, y: float, w: float, h: float, fill: str = SURFACE, line: str = BORDER, radius: float = 10) -> None:
    c.setFillColor(pdf_color(fill))
    c.setStrokeColor(pdf_color(line))
    c.setLineWidth(0.8)
    c.roundRect(x, PDF_H - y - h, w, h, radius, stroke=1, fill=1)


def pdf_bullets(c, x: float, y: float, w: float, items: list[str], gap: float = 42, size: float = 13) -> None:
    for index, item in enumerate(items):
        yy = y + index * gap
        pdf_text(c, x, yy, 10, 15, "•", size - 2, ACCENT)
        pdf_text(c, x + 16, yy, w - 16, 38, item, size, TEXT)


def pdf_image(c, path: Path, x: float, y: float, w: float, h: float) -> None:
    from PIL import Image as PILImage
    with PILImage.open(path) as image:
        iw, ih = image.size
    ratio = min(w / iw, h / ih)
    draw_w = iw * ratio
    draw_h = ih * ratio
    draw_x = x + (w - draw_w) / 2
    draw_y = y + (h - draw_h) / 2
    c.drawImage(ImageReader(str(path)), draw_x, PDF_H - draw_y - draw_h, draw_w, draw_h, preserveAspectRatio=True, mask="auto")


def pdf_header(c, number: int, kicker: str, title: str) -> None:
    pdf_text(c, 40, 20, 350, 18, f"EVALPILOT  ·  {kicker}", 9, ACCENT)
    pdf_text(c, 40, 46, 880, 36, title, 25, TEXT)
    c.setStrokeColor(pdf_color(ACCENT))
    c.setLineWidth(1.2)
    c.line(40, PDF_H - 98, 920, PDF_H - 98)
    pdf_text(c, 40, PDF_H - 34, 260, 12, "逆熵智评 · NEGENTROPY LABS", 7.5, MUTED)
    pdf_text(c, 860, PDF_H - 34, 60, 12, f"{number:02d}", 7.5, MUTED, "right")


def pdf_metric(c, x: float, y: float, w: float, label: str, value: str, note: str,
               color: str = ACCENT, fill: str = SURFACE, h: float = 100) -> None:
    pdf_rect(c, x, y, w, h, fill, BORDER)
    pdf_text(c, x + 14, y + 10, w - 28, 16, label, 8, MUTED)
    pdf_text(c, x + 14, y + 28, w - 28, 28, value, 22, color)
    pdf_text(c, x + 14, y + 66, w - 28, 24, note, 8, MUTED)


def pdf_slide_1(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_text(c, 46, 30, 330, 18, "逆熵智评  ·  NEGENTROPY LABS", 10, ACCENT)
    pdf_text(c, 46, 75, 420, 40, "EvalPilot", 31, ACCENT)
    pdf_text(c, 46, 135, 450, 70, "AI 应用回归评测\n与自主发布质量官", 27, TEXT, leading=1.08)
    pdf_text(c, 46, 245, 430, 60, "用匹配评测、统计置信和反事实重放，把版本变化变成可验收的发布决策。", 16, MUTED)
    pdf_rect(c, 46, 325, 425, 56, ACCENT_SOFT, ACCENT_SOFT)
    pdf_text(c, 62, 341, 395, 30, "8 / 26 回归 · 52 / 0 上游比较 · 4 / 4 OOD 根因", 14, ACCENT)
    pdf_text(c, 46, 410, 430, 44, "产品站：zqian6263-design.github.io/EvalPilot\n视频：bilibili.com/video/BV1mPYY6sE1k", 10, MUTED)
    pdf_image(c, ASSETS / "cover.png", 485, 72, 430, 390)


def pdf_slide_2(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 2, "问题", "普通问答通过，不等于关键能力没有退化")
    pdf_text(c, 40, 118, 870, 34, "版本更新可能更快、总分更高，却同时破坏产品必须长期守住的能力。", 15, MUTED)
    cards = [("条款与流程丢失", "退款、升级、电池处置等强制条款被摘要压缩掉。", DANGER),
             ("权限与隔离失效", "租户记忆串扰、缓存返回旧错误，业务边界被绕过。", WARNING),
             ("安全护栏失效", "凭证注入从拒绝泄露变成直接输出敏感信息。", DANGER)]
    for index, (title, body, color) in enumerate(cards):
        x = 40 + index * 300
        pdf_rect(c, x, 190, 275, 175, SURFACE)
        c.setFillColor(pdf_color(color)); c.rect(x, PDF_H - 365, 5, 175, fill=1, stroke=0)
        pdf_text(c, x + 24, 220, 225, 28, title, 16, TEXT)
        pdf_text(c, x + 24, 268, 225, 70, body, 12, MUTED)
    pdf_rect(c, 40, 395, 880, 62, MUTED_BG)
    pdf_text(c, 62, 416, 835, 30, "需要的是：是否真实回归、由哪个变更造成、是否应立即阻断发布。", 16, TEXT, "center")


def pdf_slide_3(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 3, "产品", "一个能接管发布质量闭环的数字员工")
    steps = [("01", "理解与规划"), ("02", "执行与取证"), ("03", "统计判定"), ("04", "根因重放"), ("05", "发布门禁")]
    for index, (num, title) in enumerate(steps):
        x = 40 + index * 178
        pdf_rect(c, x, 140, 155, 150, SURFACE)
        pdf_text(c, x + 14, 155, 40, 18, num, 9, ACCENT)
        pdf_text(c, x + 14, 185, 125, 44, title, 13, TEXT)
        if index < 4:
            pdf_text(c, x + 157, 205, 20, 20, "→", 16, ACCENT, "center")
    pdf_image(c, ASSETS / "console.png", 40, 325, 540, 160)
    pdf_rect(c, 605, 325, 315, 160, SURFACE)
    pdf_text(c, 625, 342, 275, 24, "交付物不是建议", 15, TEXT)
    pdf_bullets(c, 625, 390, 270, ["Markdown 证据报告", "CI 退出码 0 / 1 / 2", "run id 与 evidence id"], 35, 11)


def pdf_slide_4(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 4, "智能体边界", "模型可以规划，但不能覆盖实测结论")
    labels = ["自然语言目标", "风险假设", "受约束计划", "白名单干预", "实测恢复", "发布决策"]
    for index, label in enumerate(labels):
        y = 135 + index * 55
        pdf_rect(c, 55, y, 300, 42, ACCENT_SOFT if index != 5 else SUCCESS_SOFT)
        pdf_text(c, 75, y + 13, 260, 20, label, 12, ACCENT if index != 5 else SUCCESS)
        if index < 5:
            pdf_text(c, 195, y + 40, 20, 12, "↓", 10, MUTED, "center")
    pdf_rect(c, 405, 135, 235, 335, SURFACE)
    pdf_text(c, 428, 155, 190, 24, "LLM 权限", 16, ACCENT)
    pdf_bullets(c, 428, 202, 190, ["提出风险假设", "选择可执行实验", "解释证据与建议", "生成报告叙述"], 52, 11)
    pdf_rect(c, 665, 135, 255, 335, DANGER_SOFT)
    pdf_text(c, 688, 155, 210, 24, "确定性引擎权威", 16, DANGER)
    pdf_bullets(c, 688, 202, 210, ["写入分数与证据 id", "执行并测量反事实", "决定根因与风险", "决定发布状态"], 52, 11)
    pdf_text(c, 428, 395, 492, 45, "DeepSeek V4 Pro 规划 8/8；确定性规则同样 8/8。模型可改变下一步实验，但不能改变答案。", 12, MUTED)


def pdf_slide_5(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 5, "实测证据", "真实回归已经被确认、测量和阻断")
    pdf_metric(c, 40, 120, 205, "匹配场景", "26", "baseline / candidate")
    pdf_metric(c, 260, 120, 205, "控制组", "18", "同版本完全一致")
    pdf_metric(c, 480, 120, 205, "阻断回归", "8", "7 条款 + 1 泄露", DANGER, DANGER_SOFT)
    pdf_metric(c, 700, 120, 220, "发布结论", "BLOCK", "风险级别 CRITICAL", DANGER, DANGER_SOFT)
    pdf_image(c, ASSETS / "method.png", 40, 255, 540, 220)
    pdf_rect(c, 610, 255, 310, 220, SURFACE)
    pdf_text(c, 632, 275, 265, 24, "配对结果", 14, TEXT)
    pdf_text(c, 632, 315, 265, 30, "mean delta  -0.173", 19, DANGER)
    pdf_text(c, 632, 360, 265, 22, "95% CI  [-0.288, -0.077]", 12, TEXT)
    pdf_text(c, 632, 400, 265, 48, "52 Judge calls · 78,695 tokens\n峰值成本 $0.264697（运行下界）", 10, MUTED)

def pdf_slide_6(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 6, "根因重放", "不是猜测原因，而是禁用变更后重新测量")
    pdf_rect(c, 40, 118, 220, 98, DANGER_SOFT)
    pdf_text(c, 60, 135, 60, 28, "8", 24, DANGER)
    pdf_text(c, 115, 145, 120, 20, "失败场景", 12, TEXT)
    pdf_text(c, 60, 176, 180, 20, "通过 HTTP 边界逐项重放", 9, MUTED)
    pdf_text(c, 265, 150, 25, 20, "→", 18, ACCENT, "center")
    pdf_rect(c, 300, 118, 290, 98, SURFACE)
    pdf_text(c, 320, 135, 250, 22, "关闭压缩层", 15, ACCENT)
    pdf_text(c, 320, 170, 250, 22, "7 个条款 / 流程失败恢复", 13, TEXT)
    pdf_rect(c, 610, 118, 310, 98, SURFACE)
    pdf_text(c, 630, 135, 270, 22, "恢复安全护栏", 15, DANGER)
    pdf_text(c, 630, 170, 270, 22, "1 个凭证泄露恢复拒绝", 13, TEXT)
    pdf_image(c, ASSETS / "model-plan.png", 40, 240, 540, 235)
    pdf_rect(c, 610, 240, 310, 235, SURFACE)
    pdf_text(c, 632, 260, 265, 24, "可执行根因证据", 14, TEXT)
    pdf_metric(c, 632, 300, 120, "OOD", "4 / 4", "HTTP 实测恢复", SUCCESS, SUCCESS_SOFT, 90)
    pdf_metric(c, 768, 300, 125, "模型规划", "8 / 8", "需白名单校验", ACCENT, SURFACE, 90)
    pdf_text(c, 632, 412, 265, 40, "确定性规则同样 8/8；模型是可扩展规划路径，不是不可替代黑箱。", 10, MUTED)


def pdf_slide_7(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 7, "开源适配", "对真实公开栈工作，也对故障明确失败")
    pdf_rect(c, 40, 118, 455, 165, SURFACE)
    pdf_text(c, 62, 138, 410, 24, "公开 Haystack HTTP SUT", 15, TEXT)
    pdf_text(c, 62, 180, 410, 50, "DocumentSplitter → BM25 Retriever → DocumentJoiner\n→ GroundedReranker → grounded answer", 12, ACCENT)
    pdf_text(c, 62, 244, 410, 18, "Apache-2.0 · haystack-ai 3.1.1", 9, MUTED)
    pdf_metric(c, 520, 118, 185, "上游比较", "52 / 0", "3.0.0 vs 3.1.1", SUCCESS, SUCCESS_SOFT, 165)
    pdf_metric(c, 720, 118, 200, "候选回归", "8 / 26", "mean delta -0.173", DANGER, DANGER_SOFT, 165)
    pdf_image(c, ASSETS / "report.png", 40, 310, 520, 160)
    pdf_rect(c, 585, 310, 335, 160, SURFACE)
    pdf_text(c, 607, 328, 290, 24, "证据不是“能跑一次”", 15, TEXT)
    pdf_bullets(c, 607, 370, 290, ["同版本控制 0 回归", "离线缓存精确复现", "SUT 故障明确失败，不回退 mock"], 35, 10)


def pdf_slide_8(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 8, "市场与交付", "不与监控平台竞争，只守发布前最后一道门")
    pdf_rect(c, 40, 118, 285, 355, SURFACE)
    pdf_text(c, 62, 138, 240, 24, "市场切口", 15, TEXT)
    pdf_text(c, 62, 180, 240, 58, "Given baseline + candidate，输出可阻断发布的证据决策。", 13, ACCENT)
    pdf_bullets(c, 62, 270, 240, ["公开付费品类已存在", "兼容 observability", "CI 是明确采购入口"], 52, 10)
    pdf_text(c, 62, 430, 240, 35, "证明预算品类与集成路径，不声称付费转化。", 9, MUTED)
    pdf_rect(c, 345, 118, 265, 355, SURFACE)
    pdf_text(c, 367, 138, 220, 24, "成本与交付", 15, TEXT)
    pdf_text(c, 367, 190, 220, 32, "$0.264697", 22, ACCENT)
    pdf_text(c, 367, 230, 220, 20, "Live Run 峰值下界", 9, MUTED)
    pdf_bullets(c, 367, 275, 220, ["BLOCK / REVIEW / ALLOW", "Markdown / JUnit / SARIF", "退出码 0 / 1 / 2", "GitHub PR 回写"], 45, 10)
    pdf_rect(c, 630, 118, 290, 355, SURFACE)
    pdf_text(c, 652, 138, 245, 24, "商业策略（假设）", 15, TEXT)
    pdf_bullets(c, 652, 195, 245, ["Release audit / 固定范围审计", "Team subscription / 持续门禁", "Enterprise self-host / 私有化"], 75, 10)
    pdf_text(c, 652, 430, 245, 35, "价格来自公开竞品锚点，不冒充已验证收入。", 9, WARNING)


def pdf_slide_9(c) -> None:
    c.setFillColor(pdf_color(BG)); c.rect(0, 0, PDF_W, PDF_H, fill=1, stroke=0)
    pdf_header(c, 9, "下一步", "先守住发布决策，再扩大公开证据")
    pdf_rect(c, 40, 118, 275, 300, SUCCESS_SOFT)
    pdf_text(c, 62, 138, 230, 24, "现在：已验证", 15, SUCCESS)
    pdf_bullets(c, 62, 200, 230, ["公开产品站", "真实 HTTP SUT", "模型受约束规划", "Release Gate"], 52, 11)
    pdf_rect(c, 335, 118, 275, 300, ACCENT_SOFT)
    pdf_text(c, 357, 138, 230, 24, "下一阶段", 15, ACCENT)
    pdf_bullets(c, 357, 200, 230, ["公开未知故障回顾", "第二模型供应商", "真实使用信号", "更多发布适配器"], 52, 11)
    pdf_rect(c, 630, 118, 290, 300, SURFACE)
    pdf_image(c, ASSETS / "product-site.png", 652, 145, 245, 160)
    pdf_text(c, 652, 330, 245, 55, "产品站已验证公开可访问\n所有数据有源文件与复现命令", 10, MUTED)
    pdf_rect(c, 40, 445, 880, 50, TEXT)
    pdf_text(c, 62, 462, 835, 24, "用证据决定，而不是用感觉发布。", 18, "FFFFFF", "center")


def build_pdf() -> None:
    font_path = Path("C:/Windows/Fonts/simhei.ttf")
    if not font_path.exists():
        raise FileNotFoundError(f"Chinese PDF font not found: {font_path}")
    pdfmetrics.registerFont(TTFont(PDF_FONT, str(font_path)))
    output = OUT / "EvalPilot-Initial-Submission.pdf"
    c = canvas.Canvas(str(output), pagesize=(PDF_W, PDF_H))
    c.setTitle("EvalPilot Initial Submission")
    c.setAuthor("NEGENTROPY LABS")
    for slide_fn in (pdf_slide_1, pdf_slide_2, pdf_slide_3, pdf_slide_4, pdf_slide_5,
                     pdf_slide_6, pdf_slide_7, pdf_slide_8, pdf_slide_9):
        slide_fn(c)
        c.showPage()
    c.save()
    print(output)


def main() -> None:
    prs = build_pptx()
    pptx_path = OUT / "EvalPilot-Initial-Submission.pptx"
    prs.save(pptx_path)
    print(pptx_path)
    build_pdf()


if __name__ == "__main__":
    main()
