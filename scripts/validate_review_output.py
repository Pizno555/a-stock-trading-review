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
DIRECTION_ID_PATTERN = re.compile(r"^D[1-5]$", re.IGNORECASE)
CHAIN_ID_PATTERN = re.compile(
    r"^D[1-5](?:[a-z])?(?:\+D[1-5](?:[a-z])?)*$", re.IGNORECASE
)
RISK_ID_PATTERN = re.compile(r"^R[1-3]$", re.IGNORECASE)
FORMAL_LIFECYCLES = ("新启动", "强化", "分歧", "修复", "退潮")
NO_NEW_POSITION_PATTERN = re.compile(
    r"不新增|取消新增|不执行|只观察|保持观察|继续观察|放弃新增"
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


def _labeled_segment(body: str, label: str, next_labels: tuple[str, ...]) -> str:
    next_part = "|".join(re.escape(item) for item in next_labels)
    match = re.search(
        rf"\*\*{re.escape(label)}\s*[:：]?\*\*\s*[:：]?(.*?)(?=\n\s*-?\s*\*\*(?:{next_part})\s*[:：]?\*\*|\Z)",
        body,
        re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _table_rows(body: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if cells[0] in {"股票", "方向", "方向ID", "链路ID", "风险ID"}:
            continue
        if any(cells):
            rows.append(cells)
    return rows


def _direction_ids(value: str) -> list[str]:
    return [match.upper() for match in re.findall(r"(?<![A-Za-z0-9])D[1-5](?![A-Za-z0-9])", value, re.IGNORECASE)]


def _base_direction_ids(chain_id: str) -> list[str]:
    return [match.upper() for match in re.findall(r"D[1-5]", chain_id, re.IGNORECASE)]


def _normalized_exact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _validate_retreat_evidence(
    evidence: str, identifier: str, errors: list[str]
) -> None:
    fields = {
        "核心负反馈": r"核心负反馈",
        "宽度恶化": r"宽度(?:恶化)?",
        "近期参与者盈亏": r"(?:近期|昨日)?参与者盈亏",
        "成交承载/资金撤离": r"成交承载|资金撤离",
        "资金迁移": r"资金迁移|迁移方向",
    }
    for field, pattern in fields.items():
        if not re.search(pattern, evidence):
            errors.append(f"第3步退潮方向‘{identifier}’缺少证据字段：{field}")


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

        step2_rows = _table_rows(step2)
        step2_ids: list[str] = []
        step2_names: list[str] = []
        if len(step2_rows) > 5:
            errors.append(f"第2步赚钱方向有{len(step2_rows)}个，超过5个上限")
        for row in step2_rows:
            if len(row) < 8:
                errors.append(f"第2步方向行列数不足：{' | '.join(row)}")
                continue
            direction_id = row[0].upper()
            if not DIRECTION_ID_PATTERN.fullmatch(direction_id):
                errors.append(f"第2步方向ID不合法：{row[0]}；只允许D1～D5")
                continue
            if direction_id in step2_ids:
                errors.append(f"第2步方向ID重复：{direction_id}")
            step2_ids.append(direction_id)
            step2_names.append(row[1])
        expected_step2_ids = [f"D{index}" for index in range(1, len(step2_ids) + 1)]
        if step2_ids != expected_step2_ids:
            errors.append(f"第2步方向ID必须按行连续使用D1～D{len(step2_ids)}")

        step3 = blocks[2]
        step3a = _find_subsection(step3, "③A")
        step3b = _find_subsection(step3, "③B")
        chain_ids: list[str] = []
        chain_names: list[str] = []
        retreat_chain_ids: set[str] = set()
        risk_ids: list[str] = []
        risk_names: list[str] = []
        has_retreat_direction = False

        if not step3a:
            errors.append("第3步缺少‘③A：正向方向承接’小节")
            step3a_rows: list[list[str]] = []
        else:
            step3a_rows = _table_rows(step3a[1])
            covered_step2_ids: set[str] = set()
            for row in step3a_rows:
                if len(row) < 8:
                    errors.append(f"第3步③A方向行列数不足：{' | '.join(row)}")
                    continue
                chain_id = row[0].upper()
                source_ids = _direction_ids(row[1])
                if not CHAIN_ID_PATTERN.fullmatch(chain_id):
                    errors.append(f"第3步③A链路ID不合法：{row[0]}")
                    continue
                if chain_id in chain_ids:
                    errors.append(f"第3步③A链路ID重复：{chain_id}")
                chain_ids.append(chain_id)
                chain_names.append(row[2])
                if not source_ids:
                    errors.append(f"第3步③A‘{chain_id}’缺少承接第②的D ID")
                for source_id in source_ids:
                    if source_id not in step2_ids:
                        errors.append(f"第3步③A‘{chain_id}’引用不存在的第②方向：{source_id}")
                    covered_step2_ids.add(source_id)
                if set(_base_direction_ids(chain_id)) != set(source_ids):
                    errors.append(
                        f"第3步③A‘{chain_id}’与承接第②‘{row[1]}’不一致；拆分链用D2a/D2b，合并链用D2+D4"
                    )
                state = row[3]
                if not re.search(r"主线|支线|轮动|观察", state):
                    errors.append(f"第3步③A‘{chain_id}’缺少市场地位")
                if not re.search(r"新启动|强化|分歧|修复|退潮|待确认", state):
                    errors.append(f"第3步③A‘{chain_id}’缺少生命周期")
                if any(stage in state for stage in FORMAL_LIFECYCLES) and not row[4].strip():
                    errors.append(f"第3步③A‘{chain_id}’缺少阶段依据")
                for index, label in ((5, "关键证据"), (6, "上限/巩固条件"), (7, "失效/交易影响")):
                    if not row[index].strip():
                        errors.append(f"第3步③A‘{chain_id}’缺少{label}")
                if "退潮" in state:
                    has_retreat_direction = True
                    retreat_chain_ids.add(chain_id)
                    _validate_retreat_evidence(row[5], chain_id, errors)
            for direction_id in step2_ids:
                if direction_id not in covered_step2_ids:
                    errors.append(f"第2步方向‘{direction_id}’未被第3步③A承接")
            if not step2_ids and step3a_rows:
                errors.append("第2步没有赚钱方向时，第3步③A不应生成D方向")

        if not step3b:
            errors.append("第3步缺少‘③B：重要风险方向’小节")
            step3b_rows: list[list[str]] = []
        else:
            step3b_rows = _table_rows(step3b[1])
            if len(step3b_rows) > 3:
                errors.append(f"第3步③B风险方向有{len(step3b_rows)}个，超过3个上限")
            for row in step3b_rows:
                if len(row) < 8:
                    errors.append(f"第3步③B风险行列数不足：{' | '.join(row)}")
                    continue
                risk_id = row[0].upper()
                if not RISK_ID_PATTERN.fullmatch(risk_id):
                    errors.append(f"第3步③B风险ID不合法：{row[0]}；只允许R1～R3")
                    continue
                if risk_id in risk_ids:
                    errors.append(f"第3步③B风险ID重复：{risk_id}")
                risk_ids.append(risk_id)
                risk_names.append(row[1])
                if not row[2].strip():
                    errors.append(f"第3步③B‘{risk_id}’缺少纳入原因")
                state = row[3]
                if not re.search(r"主线|支线|轮动|观察", state):
                    errors.append(f"第3步③B‘{risk_id}’缺少市场地位")
                if not re.search(r"新启动|强化|分歧|修复|退潮|待确认", state):
                    errors.append(f"第3步③B‘{risk_id}’缺少生命周期")
                if any(stage in state for stage in FORMAL_LIFECYCLES) and not row[4].strip():
                    errors.append(f"第3步③B‘{risk_id}’缺少阶段依据")
                for index, label in ((5, "核心风险证据"), (6, "修复条件"), (7, "交易影响")):
                    if not row[index].strip():
                        errors.append(f"第3步③B‘{risk_id}’缺少{label}")
                if "退潮" in state:
                    has_retreat_direction = True
                    _validate_retreat_evidence(row[5], risk_id, errors)
            expected_risk_ids = [f"R{index}" for index in range(1, len(risk_ids) + 1)]
            if risk_ids != expected_risk_ids:
                errors.append(f"第3步③B风险ID必须按行连续使用R1～R{len(risk_ids)}")

        positive_exact_names = {_normalized_exact(name) for name in step2_names + chain_names if name}
        for risk_id, risk_name in zip(risk_ids, risk_names):
            if _normalized_exact(risk_name) in positive_exact_names:
                errors.append(f"第3步③B‘{risk_id}’与第2步/③A使用完全相同方向名称；应在③A处理风险")

        if _frontmatter_scalar(text, "data_completeness") == "severe_missing":
            if not ("观察" in step3 and "待确认" in step3 and re.search(r"低置信度|置信度\s*[:：]\s*低", step3)):
                errors.append("数据严重缺失时，第3步必须使用‘观察 × 待确认｜低置信度’")

        step4 = blocks[3]
        step4a = _find_subsection(step4, "④A")
        step4b = _find_subsection(step4, "④B")
        if not step4a:
            errors.append("第4步缺少‘④A：D方向核心 / 观察锚’小节")
            step4a_rows: list[list[str]] = []
        else:
            step4a_rows = _table_rows(step4a[1])
            represented_chains: set[str] = set()
            for row in step4a_rows:
                if len(row) < 7:
                    errors.append(f"第4步④A行列数不足：{' | '.join(row)}")
                    continue
                source_chain = row[0].upper()
                if source_chain not in chain_ids:
                    errors.append(f"第4步④A引用不存在的D链路：{row[0]}")
                represented_chains.add(source_chain)
                if not row[2].strip() or not row[3].strip() or not row[4].strip():
                    errors.append(f"第4步④A‘{source_chain}’缺少股票、角色或强点")
            for chain_id in chain_ids:
                if chain_id not in represented_chains:
                    errors.append(f"第3步③A链路‘{chain_id}’未被第4步④A承接")

        if not step4b:
            errors.append("第4步缺少‘④B：R方向风险锚’小节")
            step4b_rows: list[list[str]] = []
        else:
            step4b_rows = _table_rows(step4b[1])
            represented_risks: set[str] = set()
            for row in step4b_rows:
                if len(row) < 6:
                    errors.append(f"第4步④B行列数不足：{' | '.join(row)}")
                    continue
                risk_id = row[0].upper()
                if risk_id not in risk_ids:
                    errors.append(f"第4步④B引用不存在的R方向：{row[0]}")
                represented_risks.add(risk_id)
                if not row[2].strip() or not row[3].strip() or not row[4].strip():
                    errors.append(f"第4步④B‘{risk_id}’缺少风险锚或风险证据")
            for risk_id in risk_ids:
                if risk_id not in represented_risks:
                    errors.append(f"第3步③B风险‘{risk_id}’未被第4步④B承接")
            if not risk_ids and step4b_rows:
                errors.append("第3步③B没有R方向时，第4步④B不应生成风险锚")

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
            core_rows: list[list[str]] = []
            core_priorities: dict[str, str] = {}
        else:
            core_rows = _table_rows(core_section[1])
            core_priorities = {}
            if len(core_rows) != core_count:
                errors.append(
                    f"第7步交易核心池表有{len(core_rows)}行，但frontmatter core_pool有{core_count}只"
                )
            for item in core_pool:
                if not any(_identifier_matches(item, row[0]) for row in core_rows):
                    errors.append(f"第7步交易核心池表缺少：{item}")
            for row in core_rows:
                if len(row) < 9:
                    errors.append(f"第7步核心池行列数不足：{' | '.join(row)}")
                    continue
                if not any(_identifier_matches(item, row[0]) for item in core_pool):
                    errors.append(f"第7步交易核心池表出现frontmatter之外的股票：{row[0]}")
                source_chain = row[1].upper()
                if source_chain not in chain_ids:
                    errors.append(f"第7步核心池‘{row[0]}’引用不存在或非D的链路：{row[1]}")
                if source_chain in retreat_chain_ids:
                    errors.append(f"第7步核心池‘{row[0]}’来自退潮链路：{source_chain}")
                priority = row[3].strip()
                if priority not in {"优先执行", "条件执行"}:
                    errors.append(f"第7步核心池‘{row[0]}’执行优先级必须是‘优先执行’或‘条件执行’")
                else:
                    core_priorities[row[0]] = priority
                if priority == "条件执行" and "超预期" not in row[7]:
                    errors.append(f"第7步条件执行候选‘{row[0]}’的最早触发路径必须明确严格超预期触发")

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
                if len(row) < 3:
                    errors.append(f"近线淘汰行列数不足：{' | '.join(row)}")
                    continue
                if row[1].upper() not in chain_ids:
                    errors.append(f"近线淘汰‘{row[0]}’引用不存在或非D的链路：{row[1]}")
                if not row[2].strip():
                    errors.append(f"近线淘汰‘{row[0] if row else '未知'}’缺少决定性淘汰原因")

        watch_section = _find_subsection(step7, "观察锚")
        if not watch_section:
            errors.append("第7步缺少‘观察锚’小节")
            watch_rows: list[list[str]] = []
        else:
            watch_rows = _table_rows(watch_section[1])
            if len(watch_rows) != len(watch_pool):
                errors.append(
                    f"第7步观察锚表有{len(watch_rows)}行，但frontmatter watch_pool有{len(watch_pool)}只"
                )
            for item in watch_pool:
                if not any(row and _identifier_matches(item, row[0]) for row in watch_rows):
                    errors.append(f"第7步观察锚表缺少：{item}")
            for row in watch_rows:
                if len(row) < 6:
                    errors.append(f"第7步观察锚行列数不足：{' | '.join(row)}")
                    continue
                if not any(_identifier_matches(item, row[0]) for item in watch_pool):
                    errors.append(f"第7步观察锚表出现frontmatter之外的股票：{row[0]}")
                source_chain = row[1].upper()
                if source_chain not in chain_ids:
                    errors.append(f"第7步观察锚‘{row[0]}’引用不存在或非D的链路：{row[1]}")
                if source_chain in retreat_chain_ids:
                    errors.append(f"第7步观察锚‘{row[0]}’来自退潮链路：{source_chain}")

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
        step8_sections = _subsections(step8)
        for stock, priority in core_priorities.items():
            if priority != "条件执行":
                continue
            matches = [body for title, body in step8_sections if _identifier_matches(stock, title)]
            if len(matches) != 1:
                continue
            body = matches[0]
            over_expected = _labeled_segment(body, "超预期", ("符合预期", "低于预期"))
            normal_expected = _labeled_segment(body, "符合预期", ("低于预期",))
            below_expected = _labeled_segment(body, "低于预期", ("__END__",))
            if "触发" not in over_expected:
                errors.append(f"第8步条件执行候选‘{stock}’的超预期情景缺少明确触发")
            if not NO_NEW_POSITION_PATTERN.search(normal_expected):
                errors.append(f"第8步条件执行候选‘{stock}’在符合预期情景必须明确不新增")
            if not NO_NEW_POSITION_PATTERN.search(below_expected):
                errors.append(f"第8步条件执行候选‘{stock}’在低于预期情景必须明确不新增")
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
        for stock, priority in core_priorities.items():
            if priority != "条件执行":
                continue
            body = next(
                (candidate_body for item, candidate_body in a_bodies.items() if _identifier_matches(stock, item)),
                "",
            )
            if body and not re.search(r"新增买入触发.{0,160}超预期", body, re.DOTALL):
                errors.append(f"第⑨A条件执行候选‘{stock}’的新增买入触发必须以前序超预期成立为前提")

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
