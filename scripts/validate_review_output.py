#!/usr/bin/env python3
"""Validate the user-facing nine-step A-share review contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


EXPECTED_SECTIONS = [
    "## 一、市场环境",
    "## 二、今天赚钱效应在哪里",
    "## 三、市场地位 × 生命周期",
    "## 四、每条重点方向谁最强、为什么强",
    "## 五、我的持仓在板块里属于强还是弱",
    "## 六、今天自己的交易哪里做对 / 做错",
    "## 七、明日核心池",
    "## 八、超预期 / 符合预期 / 低于预期怎么处理",
    "## 九、MA + RSI9 + BIAS20具体买卖位置",
]

TECHNICAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])MA(?:5|10|20|60)?(?![A-Za-z0-9])|RSI\s*9|BIAS\s*20",
    re.IGNORECASE,
)
TOOL_LOG_PATTERN = re.compile(
    r"tool_call_id|custom_tool_call|functions\.(?:exec|wait)|exec_command|search_query\s*[:=]",
    re.IGNORECASE,
)
B_FORBIDDEN_ACTION_PATTERN = re.compile(
    r"新增买入|补仓|加仓|摊低成本|重新(?:升级|进入).{0,8}核心池",
    re.IGNORECASE,
)


def _read_text(input_path: str) -> str:
    if input_path == "-":
        return sys.stdin.read()
    return Path(input_path).read_text(encoding="utf-8")


def _parse_inline_list(
    text: str, key: str, errors: list[str], *, required: bool = True
) -> list[str]:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(\[[^\n]*\])\s*$", text)
    if not match:
        if required:
            errors.append(f"frontmatter缺少可解析的{key}列表")
        return []
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        errors.append(f"frontmatter的{key}不是合法的行内列表")
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"frontmatter的{key}必须是字符串列表")
        return []
    return value


def _frontmatter_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*[\"']?([^\"'\n]+)[\"']?\s*$", text)
    return match.group(1).strip() if match else None


def _section_blocks(text: str, errors: list[str]) -> list[str]:
    positions: list[int] = []
    for heading in EXPECTED_SECTIONS:
        matches = [m.start() for m in re.finditer(rf"(?m)^{re.escape(heading)}\s*$", text)]
        if len(matches) != 1:
            errors.append(f"固定标题应出现且只出现一次：{heading}")
            positions.append(-1)
        else:
            positions.append(matches[0])

    valid_positions = [position for position in positions if position >= 0]
    if len(valid_positions) == len(EXPECTED_SECTIONS) and valid_positions != sorted(valid_positions):
        errors.append("九步标题顺序不符合复盘流程")

    if any(position < 0 for position in positions):
        return [""] * len(EXPECTED_SECTIONS)

    blocks: list[str] = []
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(text)
        block = text[start:end]
        blocks.append(block)
        body = block.split("\n", 1)[1].strip() if "\n" in block else ""
        if not body:
            errors.append(f"步骤{index + 1}只有标题，没有正文")
    return blocks


def _subsections(block: str) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", block))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(block)
        result.append((match.group(1).strip(), block[match.end() : end]))
    return result


def _nested_subsections(block: str) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^####\s+(.+?)\s*$", block))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(block)
        result.append((match.group(1).strip(), block[match.end() : end]))
    return result


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _identifier_matches(item: str, text: str) -> bool:
    item_norm = _normalize_identifier(item)
    text_norm = _normalize_identifier(text)
    return bool(item_norm and text_norm and item_norm == text_norm)


def _find_subsection(block: str, prefix: str) -> tuple[str, str] | None:
    for title, body in _subsections(block):
        if title.startswith(prefix):
            return title, body
    return None


def _table_rows(body: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if cells[0] in {"股票", "方向"}:
            continue
        if any(cells):
            rows.append(cells)
    return rows


def _validate_stock_subsections(
    block: str,
    core_pool: list[str],
    errors: list[str],
    *,
    step_name: str,
    required_labels: tuple[str, ...] = (),
) -> None:
    sections = _subsections(block)
    if not core_pool:
        if sections:
            errors.append(f"核心池为0时，{step_name}不应出现股票小节")
        return

    if len(sections) != len(core_pool):
        errors.append(
            f"{step_name}有{len(sections)}个股票小节，但核心池有{len(core_pool)}只；必须逐只且只能覆盖核心池"
        )

    for item in core_pool:
        matches = [(title, body) for title, body in sections if _identifier_matches(item, title)]
        if len(matches) != 1:
            errors.append(f"{step_name}对核心池‘{item}’的覆盖次数为{len(matches)}，应为1")
            continue
        title, body = matches[0]
        missing = [label for label in required_labels if label not in body]
        if missing:
            errors.append(f"{step_name}‘{title}’缺少：{'、'.join(missing)}")

    for title, _ in sections:
        if not any(_identifier_matches(item, title) for item in core_pool):
            errors.append(f"{step_name}出现非核心池股票小节：{title}")


def _validate_named_sections(
    sections: list[tuple[str, str]],
    expected_items: list[str],
    errors: list[str],
    *,
    section_name: str,
    required_labels: tuple[str, ...] = (),
) -> dict[str, str]:
    matched_bodies: dict[str, str] = {}
    if len(sections) != len(expected_items):
        errors.append(
            f"{section_name}有{len(sections)}个股票小节，但应有{len(expected_items)}个；身份必须完全一致"
        )

    for item in expected_items:
        matches = [(title, body) for title, body in sections if _identifier_matches(item, title)]
        if len(matches) != 1:
            errors.append(f"{section_name}对‘{item}’的覆盖次数为{len(matches)}，应为1")
            continue
        title, body = matches[0]
        matched_bodies[item] = body
        missing = [label for label in required_labels if label not in body]
        if missing:
            errors.append(f"{section_name}‘{title}’缺少：{'、'.join(missing)}")

    for title, _ in sections:
        if not any(_identifier_matches(item, title) for item in expected_items):
            errors.append(f"{section_name}出现身份范围外的股票小节：{title}")
    return matched_bodies


def validate(text: str) -> list[str]:
    errors: list[str] = []

    if not re.search(r"(?m)^## 先说结论\s*$", text):
        errors.append("缺少顶部‘## 先说结论’")

    blocks = _section_blocks(text, errors)
    core_pool = _parse_inline_list(text, "core_pool", errors)
    watch_pool = _parse_inline_list(text, "watch_pool", errors, required=False)
    core_count = len(core_pool)

    if core_count > 5:
        errors.append(f"交易核心池有{core_count}只，超过5只上限")
    if len(watch_pool) > 3:
        errors.append(f"观察锚有{len(watch_pool)}只，超过3只上限")

    if any(blocks):
        for index, block in enumerate(blocks[:8], start=1):
            if TECHNICAL_PATTERN.search(block):
                errors.append(f"第{index}步出现MA、RSI9或BIAS20；技术指标只能出现在第9步")

        step2 = blocks[1]
        for dimension in ("宽度", "核心强度", "持续性", "成交承载", "扩散"):
            if dimension not in step2:
                errors.append(f"第2步缺少赚钱效应维度：{dimension}")
        if re.search(r"不属于当日(?:普遍)?赚钱方向|整体负反馈|整体下跌家数占优", step2):
            errors.append("第2步混入明确不属于当日赚钱效应的方向")

        step3 = blocks[2]
        direction_sections = _subsections(step3)
        has_retreat_direction = False
        if direction_sections:
            for title, body in direction_sections:
                if not re.search(r"主线|支线|轮动|观察", title):
                    errors.append(f"第3步‘{title}’缺少市场地位")
                if not re.search(r"新启动|强化|分歧|修复|退潮|待确认", title):
                    errors.append(f"第3步‘{title}’缺少生命周期")
                for field in ("关键证据", "地位上限约束", "转弱", "失效", "交易影响"):
                    if field not in body:
                        errors.append(f"第3步‘{title}’缺少：{field}")
                if not re.search(r"转强|巩固", body):
                    errors.append(f"第3步‘{title}’缺少转强或巩固条件")
                previous_position = re.search(
                    r"前期地位\s*[:：]\s*(主线|支线|轮动|观察)", body
                )
                current_position = re.search(r"主线|支线|轮动|观察", title)
                if (
                    previous_position
                    and current_position
                    and previous_position.group(1) == current_position.group(0)
                ):
                    errors.append(
                        f"第3步‘{title}’前期地位与当前地位相同；未发生变化时应省略该字段"
                    )
                if "退潮" in title:
                    has_retreat_direction = True
                    retreat_fields = {
                        "核心负反馈": r"核心负反馈",
                        "宽度恶化": r"宽度(?:恶化)?",
                        "近期参与者盈亏": r"(?:近期|昨日)?参与者盈亏",
                        "成交承载/资金撤离": r"成交承载|资金撤离",
                        "资金迁移": r"资金迁移|迁移方向",
                    }
                    for field, pattern in retreat_fields.items():
                        if not re.search(pattern, body):
                            errors.append(f"第3步退潮方向‘{title}’缺少证据字段：{field}")
        elif not re.search(r"暂无(?:清晰|可判定).{0,8}(?:主线|方向)", step3):
            errors.append("第3步没有方向小节，也没有说明暂无清晰主线/可判定方向")

        if _frontmatter_scalar(text, "data_completeness") == "severe_missing":
            if not ("观察" in step3 and "待确认" in step3 and re.search(r"低置信度|置信度\s*[:：]\s*低", step3)):
                errors.append("数据严重缺失时，第3步必须使用‘观察 × 待确认｜低置信度’")

        step4 = blocks[3]
        if has_retreat_direction and "风险锚" not in step4:
            errors.append("第3步存在退潮方向时，第4步必须输出风险锚")

        step5 = blocks[4]
        if not re.search(r"明显强|偏强|中性|偏弱|明显弱|未提供持仓", step5):
            errors.append("第5步没有给出持仓相对强弱，或没有说明未提供持仓")
        holdings: list[str] = []
        risk_holdings: list[str] = []
        if "未提供持仓" not in step5:
            holding_rows = _table_rows(step5)
            for row in holding_rows:
                if len(row) < 7:
                    errors.append(
                        f"第5步持仓‘{row[0] if row else '未知'}’缺少‘需第⑨B风险执行’列"
                    )
                    continue
                holding = row[0]
                flag = row[6].strip()
                holdings.append(holding)
                if flag not in {"是", "否"}:
                    errors.append(f"第5步持仓‘{holding}’的第⑨B标记必须为‘是’或‘否’")
                elif flag == "是":
                    risk_holdings.append(holding)

        step6 = blocks[5]
        if not re.search(r"正确决策|错误决策|做对|做错|未提供今日交易记录", step6):
            errors.append("第6步没有评价今日交易做对/做错，或没有说明未提供交易记录")

        step7 = blocks[6]
        core_section = _find_subsection(step7, "交易核心池")
        if not core_section:
            errors.append("第7步缺少‘交易核心池’小节")
        else:
            core_rows = _table_rows(core_section[1])
            if len(core_rows) != core_count:
                errors.append(
                    f"第7步交易核心池表有{len(core_rows)}行，但frontmatter core_pool有{core_count}只"
                )
            for item in core_pool:
                if not any(_identifier_matches(item, row[0]) for row in core_rows):
                    errors.append(f"第7步交易核心池表缺少：{item}")
            for row in core_rows:
                if row and not any(_identifier_matches(item, row[0]) for item in core_pool):
                    errors.append(f"第7步交易核心池表出现frontmatter之外的股票：{row[0]}")

        near_section = _find_subsection(step7, "近线淘汰")
        near_items: list[str] = []
        if not near_section:
            errors.append("第7步缺少‘近线淘汰’小节")
        elif "无近线淘汰候选" not in near_section[1]:
            near_rows = _table_rows(near_section[1])
            near_items = [row[0] for row in near_rows if row]
            if len(near_items) > 3:
                errors.append(f"近线淘汰有{len(near_items)}只，超过3只上限")
            for row in near_rows:
                if len(row) < 2 or not row[1].strip():
                    errors.append(f"近线淘汰‘{row[0] if row else '未知'}’缺少决定性淘汰原因")

        for near_item in near_items:
            if any(_identifier_matches(item, near_item) for item in core_pool):
                errors.append(f"近线淘汰与核心池重复：{near_item}")
            if any(_identifier_matches(item, near_item) for item in watch_pool):
                errors.append(f"近线淘汰与观察锚重复：{near_item}")

        step8 = blocks[7]
        _validate_stock_subsections(
            step8,
            core_pool,
            errors,
            step_name="第8步",
            required_labels=("超预期", "符合预期", "低于预期"),
        )
        if not core_pool and not re.search(r"三情景不适用|核心池为0", step8):
            errors.append("核心池为0时，第8步应明确三情景不适用")

        step9 = blocks[8]
        step9a = _find_subsection(step9, "第⑨A")
        step9b = _find_subsection(step9, "第⑨B")
        if not step9a:
            errors.append("第9步缺少‘第⑨A：新增 / 核心池技术执行’小节")
            a_bodies: dict[str, str] = {}
            a_sections: list[tuple[str, str]] = []
        else:
            a_sections = _nested_subsections(step9a[1])
            a_bodies = _validate_named_sections(
                a_sections,
                core_pool,
                errors,
                section_name="第⑨A",
                required_labels=(
                    "MA",
                    "RSI9",
                    "BIAS20",
                    "关键支撑",
                    "不追条件",
                    "趋势确认",
                    "新增买入",
                    "减仓",
                    "指标截止与复权",
                ),
            )
            if not core_pool and not re.search(r"新增/核心池技术执行不适用|核心池为0", step9a[1]):
                errors.append("核心池为0时，第⑨A应明确新增/核心池技术执行不适用")

        expected_risk_holdings = [
            holding
            for holding in risk_holdings
            if not any(_identifier_matches(core, holding) for core in core_pool)
        ]
        if expected_risk_holdings and not step9b:
            errors.append("存在非核心风险持仓时，第9步缺少‘第⑨B：已有持仓风险执行’小节")
            b_sections: list[tuple[str, str]] = []
        elif not expected_risk_holdings and step9b:
            errors.append("没有非核心风险持仓时，应省略整个第⑨B及其标题")
            b_sections = _nested_subsections(step9b[1])
        else:
            b_sections = _nested_subsections(step9b[1]) if step9b else []
            b_bodies = _validate_named_sections(
                b_sections,
                expected_risk_holdings,
                errors,
                section_name="第⑨B",
                required_labels=(
                    "风险状态",
                    "MA",
                    "RSI9",
                    "BIAS20",
                    "关键防守位",
                    "减仓",
                    "继续观察持有",
                    "指标截止与复权",
                ),
            )
            for item, body in b_bodies.items():
                if not re.search(r"减仓\s*/\s*退出|减仓.*退出", body):
                    errors.append(f"第⑨B‘{item}’缺少减仓/退出条件")
                if B_FORBIDDEN_ACTION_PATTERN.search(body):
                    errors.append(f"第⑨B‘{item}’出现禁止动作：新增/补仓/加仓/摊低成本/重进核心池")

        a_titles = [title for title, _ in a_sections]
        b_titles = [title for title, _ in b_sections]
        for a_title in a_titles:
            if any(_identifier_matches(a_title, b_title) for b_title in b_titles):
                errors.append(f"第⑨A与第⑨B重复出现同一股票：{a_title}")

        for core in core_pool:
            if any(_identifier_matches(core, holding) for holding in holdings):
                body = a_bodies.get(core, "")
                for label in ("已有仓位管理", "是否允许新增"):
                    if label not in body:
                        errors.append(f"核心池持仓‘{core}’在第⑨A缺少：{label}")
        for item, body in a_bodies.items():
            if not re.search(r"减仓\s*/\s*退出|减仓.*退出", body):
                errors.append(f"第⑨A‘{item}’缺少减仓/退出触发")

    if TOOL_LOG_PATTERN.search(text):
        errors.append("用户正文疑似混入工具调用流水账")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Markdown报告路径；使用-从stdin读取")
    parser.add_argument("--json", action="store_true", help="以JSON输出检查结果")
    args = parser.parse_args()

    try:
        text = _read_text(args.input)
    except (OSError, UnicodeError) as exc:
        errors = [f"无法读取报告：{exc}"]
    else:
        errors = validate(text)

    result = {"valid": not errors, "errors": errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print("FAIL: 复盘输出未通过九步契约检查")
        for error in errors:
            print(f"- {error}")
    else:
        print("PASS: 复盘输出已通过九步契约检查")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
