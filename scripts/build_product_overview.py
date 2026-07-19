"""Build concise, local-only product-overview diagrams and report input.

The script uses Pillow for PNG generation and writes a canonical report
`artifact.json`. It does not call a model, a browser, an API, or the network.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_REGULAR = Path("C:/Windows/Fonts/msyh.ttc")
FONT_BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")

BG = "#F5F7FB"
PAPER = "#FFFFFF"
INK = "#172033"
MUTED = "#667085"
LINE = "#CBD5E1"
BLUE = "#2563EB"
BLUE_LIGHT = "#E9F0FF"
GOLD = "#B45309"
GOLD_LIGHT = "#FFF4D6"
OLIVE = "#4D7C0F"
OLIVE_LIGHT = "#EFF7DC"
PINK = "#BE185D"
PINK_LIGHT = "#FCE7F3"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines or [""]


def _centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str = INK,
    max_width: int | None = None,
    spacing: int = 8,
) -> None:
    x1, y1, x2, y2 = box
    width = max_width or (x2 - x1 - 24)
    lines = _wrap(draw, text, font, width)
    heights = [draw.textbbox((0, 0), line or " ", font=font)[3] for line in lines]
    total = sum(heights) + spacing * max(0, len(lines) - 1)
    y = y1 + (y2 - y1 - total) / 2
    for line, height in zip(lines, heights, strict=True):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = x1 + (x2 - x1 - (bbox[2] - bbox[0])) / 2
        draw.text((x, y), line, font=font, fill=fill)
        y += height + spacing


def _box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    text: str,
    fill: str = PAPER,
    outline: str = LINE,
    number: str | None = None,
    text_fill: str = INK,
    radius: int = 22,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=3)
    if number:
        x1, y1, _, _ = xy
        circle = (x1 + 14, y1 + 14, x1 + 66, y1 + 66)
        draw.ellipse(circle, fill=outline)
        number_size = 18 if len(number) == 1 else 14
        _centered_text(draw, circle, number, _font(number_size, True), PAPER, max_width=46, spacing=2)
    _centered_text(draw, xy, text, _font(23, True), text_fill, max_width=xy[2] - xy[0] - 42)


def _arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color: str = BLUE, width: int = 5) -> None:
    draw.line(points, fill=color, width=width, joint="curve")
    (x1, y1), (x2, y2) = points[-2], points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 15
    left = (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6))
    right = (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6))
    draw.polygon([(x2, y2), left, right], fill=color)


def _title(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((70, 40), title, font=_font(44, True), fill=INK)
    draw.text((72, 102), subtitle, font=_font(22), fill=MUTED)


def build_flow_diagram(path: Path) -> None:
    image = Image.new("RGB", (1800, 1280), BG)
    draw = ImageDraw.Draw(image)
    _title(draw, "企业从入驻到持续跟踪的完整流程", "核心原则：访谈产生主张，证据决定状态，人工决定接受与发布")

    draw.text((70, 150), "01  入驻与访谈", font=_font(22, True), fill=BLUE)
    row1 = [(70, 195, 390, 315), (500, 195, 820, 315), (930, 195, 1250, 315), (1360, 195, 1680, 315)]
    labels1 = ["创建企业案例", "授权与主体确认", "导入材料与公开预查", "生成提纲并完成\n30 分钟人工访谈"]
    for idx, (box, label) in enumerate(zip(row1, labels1, strict=True), 1):
        _box(draw, box, label, BLUE_LIGHT, BLUE, str(idx))
        if idx < len(row1):
            _arrow(draw, [(box[2] + 10, 255), (row1[idx][0] - 12, 255)])

    draw.text((70, 370), "02  主张、证据与补件闭环", font=_font(22, True), fill=GOLD)
    row2 = [(70, 415, 390, 535), (500, 415, 820, 535), (930, 415, 1250, 535)]
    labels2 = ["逐字稿与\n原子主张清单", "材料请求与\n白名单 Agent 任务", "证据采集与交叉验证"]
    for idx, (box, label) in enumerate(zip(row2, labels2, strict=True), 5):
        _box(draw, box, label, GOLD_LIGHT, GOLD, str(idx))
    _arrow(draw, [(1520, 325), (1520, 355), (230, 355), (230, 405)])
    _arrow(draw, [(400, 475), (488, 475)], GOLD)
    _arrow(draw, [(830, 475), (918, 475)], GOLD)

    diamond = [(1460, 395), (1695, 475), (1460, 555), (1225, 475)]
    draw.polygon(diamond, fill=PAPER, outline=GOLD)
    draw.line(diamond + [diamond[0]], fill=GOLD, width=4)
    _centered_text(draw, (1270, 425, 1650, 525), "最低证据\n是否满足？", _font(23, True), INK)
    _arrow(draw, [(1260, 475), (1220, 475)], GOLD)

    supplement = (1285, 585, 1635, 695)
    _box(draw, supplement, "企业补件、复访\n或保留未知", PINK_LIGHT, PINK, "8N")
    draw.text((1515, 570), "否", font=_font(20, True), fill=PINK)
    _arrow(draw, [(1510, 560), (1510, 595)], PINK)
    _arrow(draw, [(1280, 660), (1110, 660), (1110, 545)], PINK)

    draw.text((70, 735), "03  分析与基准", font=_font(22, True), fill=OLIVE)
    row3 = [(70, 780, 360, 900), (450, 780, 810, 900), (900, 780, 1260, 900)]
    labels3 = ["行业与阶段路由", "ESG｜影响｜ARL\n财务｜出海分析", "已验证结果与\n暂定判断分离"]
    for idx, (box, label) in enumerate(zip(row3, labels3, strict=True), 9):
        _box(draw, box, label, OLIVE_LIGHT, OLIVE, str(idx))
    draw.text((1630, 520), "是", font=_font(20, True), fill=OLIVE)
    _arrow(draw, [(1698, 475), (1730, 475), (1730, 750), (215, 750), (215, 770)], OLIVE)
    _arrow(draw, [(370, 840), (438, 840)], OLIVE)
    _arrow(draw, [(820, 840), (888, 840)], OLIVE)
    benchmark = (1360, 780, 1680, 900)
    _box(draw, benchmark, "同行业、同阶段\n基准比较", OLIVE_LIGHT, OLIVE, "12")
    _arrow(draw, [(1270, 840), (1348, 840)], OLIVE)

    draw.text((70, 935), "04  人工审核与输出", font=_font(22, True), fill=BLUE)
    review = (70, 1005, 360, 1125)
    report = (520, 980, 840, 1080)
    content = (520, 1110, 840, 1210)
    version = (1360, 1005, 1680, 1125)
    _box(draw, review, "人工审核", BLUE_LIGHT, BLUE, "13")
    _box(draw, report, "尽调报告与\n行动计划", PAPER, BLUE, "14A")
    _box(draw, content, "经授权的企业\nIP 内容包", PAPER, BLUE, "14B")
    _box(draw, version, "持续跟踪与\n版本更新", BLUE_LIGHT, BLUE, "15")
    _arrow(draw, [(1520, 910), (1520, 960), (215, 960), (215, 995)])
    _arrow(draw, [(370, 1050), (508, 1050)])
    _arrow(draw, [(370, 1090), (455, 1090), (455, 1160), (508, 1160)])
    _arrow(draw, [(850, 1030), (1280, 1030), (1280, 1050), (1348, 1050)])
    _arrow(draw, [(850, 1160), (1280, 1160), (1280, 1090), (1348, 1090)])

    draw.text((70, 1235), "补件闭环为下一阶段重点设计；其他流程节点已在本地工作台中形成可运行或可追踪的对象。", font=_font(20), fill=MUTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def build_architecture_diagram(path: Path) -> None:
    image = Image.new("RGB", (1800, 1060), BG)
    draw = ImageDraw.Draw(image)
    _title(draw, "技术架构：本地证据系统 + 受控智能", "模型负责理解与编排；规则、证据和人工保留最终权限")

    draw.rounded_rectangle((55, 145, 1330, 970), radius=28, fill=PAPER, outline=BLUE, width=4)
    draw.text((80, 165), "默认本地运行边界 / Local-first", font=_font(22, True), fill=BLUE)

    layers = [
        ((100, 230, 1285, 340), "输入层", "企业材料｜访谈录音与转写｜公开资料｜Agent 候选结果", BLUE_LIGHT, BLUE),
        ((100, 385, 1285, 495), "案例与证据层", "case.json｜权限｜管理层陈述｜原子主张｜证据记录｜版本与哈希", GOLD_LIGHT, GOLD),
        ((100, 540, 1285, 650), "控制层", "Schema 校验｜E0–E4｜主张状态｜五道闸门｜内容可见级别", PINK_LIGHT, PINK),
        ((100, 695, 1285, 805), "路由与专业引擎", "财务确定性内核（2 项已验证）｜ESG 框架｜ARL 脚手架｜出海框架", OLIVE_LIGHT, OLIVE),
        ((100, 850, 1285, 940), "输出层", "尽调底稿｜证据卡｜行动计划｜同行比较｜经授权的内容包", BLUE_LIGHT, BLUE),
    ]
    for idx, (xy, name, content, fill, outline) in enumerate(layers):
        draw.rounded_rectangle(xy, radius=20, fill=fill, outline=outline, width=3)
        draw.text((xy[0] + 28, xy[1] + 22), name, font=_font(24, True), fill=outline)
        draw.text((xy[0] + 250, xy[1] + 28), content, font=_font(21), fill=INK)
        if idx < len(layers) - 1:
            mid = (xy[0] + xy[2]) // 2
            _arrow(draw, [(mid, xy[3] + 8), (mid, layers[idx + 1][0][1] - 10)], outline)

    draw.rounded_rectangle((1390, 145, 1745, 970), radius=28, fill=PAPER, outline=LINE, width=3)
    draw.text((1420, 175), "权限模型", font=_font(26, True), fill=INK)
    authority = [
        ("模型 / Model", "拆分主张、生成追问、发现缺口\n不能自行确认事实", BLUE_LIGHT, BLUE),
        ("本地 Agent", "白名单取证与整理\n结果始终是候选证据", GOLD_LIGHT, GOLD),
        ("确定性内核", "已验证抽取、公式、规则版本\n不接受 Agent 覆盖信号", OLIVE_LIGHT, OLIVE),
        ("人工审核", "接受或拒绝证据\n确认不适用并批准发布", PINK_LIGHT, PINK),
    ]
    y = 245
    for name, body, fill, outline in authority:
        draw.rounded_rectangle((1420, y, 1715, y + 145), radius=18, fill=fill, outline=outline, width=3)
        draw.text((1445, y + 18), name, font=_font(22, True), fill=outline)
        _centered_text(draw, (1440, y + 48, 1695, y + 135), body, _font(18), INK)
        y += 170

    draw.text((80, 995), "可选 API / Agent 只进入输入层；任何外部结果必须经过来源、实体、期间、证据等级与人工审核。", font=_font(19), fill=MUTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def _data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_artifact(output: Path, flow_path: Path, architecture_path: Path) -> None:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    flow_uri = _data_uri(flow_path)
    architecture_uri = _data_uri(architecture_path)
    sources = [
        {"id": "repo_overview", "label": "CleanTech Finance README", "path": "README.md"},
        {"id": "workbench_guide", "label": "Local Company Evidence Workbench guide", "path": "docs/local-company-workbench.md"},
        {"id": "product_brief", "label": "Concise product overview and Mermaid source", "path": "docs/product-overview-brief.md"},
        {"id": "onboarding_source", "label": "Company onboarding implementation", "path": "src/cleantech_finance/onboarding.py"},
        {"id": "reporting_source", "label": "Local reporting implementation", "path": "src/cleantech_finance/onboarding_reporting.py"},
        {"id": "diagram_builder", "label": "Product diagram builder", "path": "scripts/build_product_overview.py"},
        {"id": "maturity_inventory_query", "label": "Product maturity inventory query", "path": "docs/product-maturity-inventory.sql"},
    ]
    maturity = [
        {"label": "财务｜端到端已验证", "count": 2, "domain": "Financial", "status": "validated", "definition": "抽取、计算、规则、证据卡与门禁均通过"},
        {"label": "财务｜仅输入蓝图", "count": 4, "domain": "Financial", "status": "authored", "definition": "只有字段与证据需求设计"},
        {"label": "ARL｜检索脚手架", "count": 17, "domain": "DOE ARL", "status": "retrieval scaffold", "definition": "仅组织候选证据检索"},
        {"label": "ARL｜端到端已验证", "count": 0, "domain": "DOE ARL", "status": "not validated", "definition": "当前没有自动 ARL 判断"},
    ]
    title = "CleanTech Evidence OS｜产品简介"
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "description": "简洁说明产品定位、完整业务流程、技术架构与真实能力边界。",
            "generatedAt": generated_at,
            "filters": [],
            "cards": [],
            "tables": [],
            "charts": [
                {
                    "id": "maturity_inventory",
                    "title": "专业维度成熟度计数",
                    "subtitle": "计数表示产品实现状态，不是企业评分",
                    "type": "bar",
                    "dataset": "maturity_inventory",
                    "sourceId": "maturity_inventory_query",
                    "valueFormat": "number",
                    "encodings": {
                        "x": {"field": "label", "type": "nominal", "label": "实现状态"},
                        "y": {"field": "count", "type": "quantitative", "label": "维度数量"},
                        "tooltip": [
                            {"field": "domain", "type": "nominal", "label": "领域"},
                            {"field": "status", "type": "nominal", "label": "状态"},
                            {"field": "definition", "type": "nominal", "label": "口径"},
                        ],
                    },
                }
            ],
            "sources": sources,
            "blocks": [
                {"id": "title", "type": "markdown", "body": f"# {title}"},
                {
                    "id": "executive_summary",
                    "type": "markdown",
                    "body": "## Executive Summary\n\n- **它是一套本地优先的企业证据与尽调操作系统。** 将企业材料、人工访谈、公开资料和受控 Agent 结果组织成主张—证据链。\n- **它解决的不是‘写一份更漂亮的 ESG 报告’，而是判断什么已经被证明、什么仍是假设、还缺什么材料。**\n- **最终形成两类成果：** 内部尽调报告与行动计划；在单独授权后，形成企业 IP 内容包。",
                },
                {
                    "id": "product_definition",
                    "type": "markdown",
                    "body": "## 一句话说明产品\n\n企业进入系统后，我们先确认主体和权限，再通过材料与 30 分钟人工访谈形成可验证主张；系统组织证据、发现缺口、生成补件和取证任务，并按行业与企业阶段路由到财务、ESG、清洁技术影响、ARL 和出海分析，最后由人工审核形成可追溯成果。",
                },
                {
                    "id": "flow_intro",
                    "type": "markdown",
                    "body": "## 主流程：从企业入驻到持续跟踪\n\n这张图是产品的业务主线。证据不足时不会强行给结论，而是回到补件、复访或保留未知；补件中心是下一阶段重点设计。",
                },
                {
                    "id": "flow_image",
                    "type": "html",
                    "body": f'<figure><img alt="企业从入驻到持续跟踪的完整流程" src="{flow_uri}" style="display:block;width:100%;height:auto;border-radius:16px"/><figcaption>访谈产生主张，证据决定状态，人工决定接受与发布。</figcaption></figure>',
                },
                {
                    "id": "technical_intro",
                    "type": "markdown",
                    "body": "## 技术设计：让模型更自由，但不让证据失去边界\n\n模型负责理解、拆分、追问和编排；本地对象、Schema、证据等级、闸门与规则负责可复现；Agent 只提交候选证据；人工保留接受证据、确认不适用和批准发布的最终权限。",
                },
                {
                    "id": "architecture_image",
                    "type": "html",
                    "body": f'<figure><img alt="本地证据系统与受控智能的技术架构" src="{architecture_uri}" style="display:block;width:100%;height:auto;border-radius:16px"/><figcaption>默认本地运行；可选 API 或 Agent 只从输入层进入，不能直接修改已验证事实或规则。</figcaption></figure>',
                },
                {
                    "id": "data_flow",
                    "type": "markdown",
                    "body": "## 程序中的信息只沿一条可追溯路径升级\n\n`原始记录 → 管理层陈述 → 原子主张 → 候选证据 → 已验证/部分验证/冲突/反驳/不适用 → 分析发现 → 批准发布`\n\n访谈只能证明‘说过什么’，不能直接证明为真；Agent 抓到的内容也必须经过实体、期间、来源和人工审核。",
                },
                {
                    "id": "maturity_intro",
                    "type": "markdown",
                    "sourceId": "repo_overview",
                    "body": "## 当前能力边界必须如实展示\n\n目前真正端到端验证的是 **盈利/单位经济性** 与 **现金流/资金缺口**。另外四个财务维度只有输入蓝图；17 个 ARL 维度仍是检索脚手架。完整 ESG、ARL 和出海分析先作为证据框架，不冒充自动认证或评分。",
                },
                {"id": "maturity_chart", "type": "chart", "chartId": "maturity_inventory"},
                {
                    "id": "truth_table",
                    "type": "markdown",
                    "body": "## 三个产品状态\n\n| 当前已经具备 | 下一阶段重点设计 | 明确不能宣称 |\n|---|---|---|\n| 本地企业案例、授权、访谈、材料、主张、证据和五道闸门 | 企业补件中心：提交、退回、接受、版本差异和局部重算 | 自动 ESG 认证、自动 ARL 分数或综合投资评级 |\n| 白名单 Agent 任务与候选证据边界 | 企业端提交界面、字段校验、敏感材料权限 | Agent 结果自动成为事实 |\n| 两项已验证财务证据分析 | 更多 ESG、财务、出海规则的真实企业验证 | 跨阶段强行比较或少样本百分位 |",
                },
                {
                    "id": "outputs",
                    "type": "markdown",
                    "body": "## 对客户交付什么\n\n1. **企业证据底稿：** 主张、证据、缺口、冲突和版本记录。\n2. **尽调报告与行动计划：** 已验证结论与暂定判断分开。\n3. **同行业、同阶段比较：** 只有样本和口径满足条件时才输出。\n4. **企业 IP 内容包：** 只使用已验证且已授权公开的内容。",
                },
                {
                    "id": "next_step",
                    "type": "markdown",
                    "body": "## 下一步\n\n先把企业补件中心的对象、字段、状态机、退回规则和权限原型设计清楚，再进入界面、持久化和 API 工程；之后继续用不同公司重复测试和更新规则库。",
                },
                {
                    "id": "caveats",
                    "type": "markdown",
                    "body": "## Caveats and Assumptions\n\n- 当前版本是本地工作快照，不是已发布的公共 SaaS。\n- 红/黄/绿只属于独立财务证据信号，不汇总为总分。\n- 产品提供研究与尽调支持，不替代投资、法律、会计、工程安全或正式 ESG 保证。",
                },
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {"maturity_inventory": maturity},
            "accessIssues": [],
        },
        "sources": sources,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="outputs/product-overview-v0.4")
    args = parser.parse_args()
    output = (ROOT / args.out).resolve()
    assets = output / "assets"
    flow_path = assets / "product-flow.png"
    architecture_path = assets / "technical-architecture.png"
    build_flow_diagram(flow_path)
    build_architecture_diagram(architecture_path)
    build_artifact(output, flow_path, architecture_path)
    print(json.dumps({"artifact": str(output / "artifact.json"), "images": [str(flow_path), str(architecture_path)]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
