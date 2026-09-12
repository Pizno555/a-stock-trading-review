#!/usr/bin/env python3
"""Validate the user-facing seven-step A-share review V2.4.6 contract with backward-compatible process checks."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_SECTIONS = [
    "## 一、市场环境与风险偏好",
    "## 二、赚钱效应与亏钱效应",
    "## 三、方向判断",
    "## 四、核心股定位",
    "## 五、账户与交易复盘",
    "## 六、明日重点",
    "## 七、明日剧本与执行计划",
]
REQUIRED_FRONTMATTER = (
    "review_schema",
    "market_state",
    "dominant_style",
    "position_stance",
    "main_themes",
    "core_pool",
    "watch_pool",
    "previous_review",
    "data_completeness",
    "privacy",
)
TECHNICAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])MA(?:5|10|20|60)?(?![A-Za-z0-9])|RSI\s*9|BIAS\s*20",
    re.IGNORECASE,
)
FORBIDDEN_RISK_ACTION = re.compile(r"新增(?:买入)?|补仓|加仓|摊低成本|升级.{0,8}core_pool|升级.{0,8}核心池")
LIFECYCLES = ("新启动", "强化", "分歧", "修复", "退潮")
VALID_SCAN_STATUS = {"ok", "partial", "missing", "not_applicable"}
REQUIRED_SCANS = (
    "market_core",
    "sentiment",
    "turnover_style",
    "theme_discovery",
    "material_news",
    "user_holdings_focus",
)

TURNOVER_TOP20_PATTERN = re.compile(
    r"(?:成交额\s*(?:Top\s*20|前\s*20)|(?:Top\s*20|前\s*20)\s*(?:成交额|成交)|成交额排行榜.{0,4}前\s*20)",
    re.IGNORECASE,
)
DIRECTION_OMISSION_PATTERN = re.compile(r"方向遗漏审计\s*[:：]")


def _read_text(input_path: str) -> str:
    if input_path == "-":
        return sys.stdin.read()
    return Path(input_path).read_text(encoding="utf-8")


def parse_review_frontmatter(text: str) -> dict[str, Any]:
    """Parse the simple frontmatter used by both legacy v1 and V2 reviews."""
    match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, re.DOTALL)
    if not match:
        return {}
    result: dict[str, Any] = {}
    for raw_line in match.group(1).splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        key, raw_value = key.strip(), raw_value.strip()
        if raw_value in {"null", "~"}:
            value: Any = None
        elif raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                value = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError):
                value = raw_value
        else:
            value = raw_value.strip("\"'")
        result[key] = value
    return result


def is_legacy_review(frontmatter: dict[str, Any]) -> bool:
    return "review_schema" not in frontmatter


def _section_blocks(text: str, errors: list[str]) -> list[str]:
    positions: list[int] = []
    for heading in EXPECTED_SECTIONS:
        matches = list(re.finditer(rf"(?m)^{re.escape(heading)}\s*$", text))
        if len(matches) != 1:
            errors.append(f"固定标题应出现且只出现一次：{heading}")
            positions.append(-1)
        else:
            positions.append(matches[0].start())
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        errors.append("七步标题顺序不符合复盘流程")
    if any(position < 0 for position in positions):
        return [""] * len(EXPECTED_SECTIONS)
    blocks: list[str] = []
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(text)
        block = text[start:end]
        blocks.append(block)
        if not block.split("\n", 1)[-1].strip():
            errors.append(f"步骤{index + 1}只有标题，没有正文")
    return blocks


def _table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if cells[0] in {"D ID", "R ID", "链路ID", "股票", "检查项", "情景", "交易", "标的/变量", "变量", "scan"}:
            continue
        rows.append(cells)
    return rows


def _find_subsection(block: str, prefix: str) -> str:
    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", block))
    for index, heading in enumerate(headings):
        if heading.group(1).strip().startswith(prefix):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(block)
            return block[heading.end():end]
    return ""


def _nested_sections(block: str) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^####\s+(.+?)\s*$", block))
    result: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(block)
        result.append((heading.group(1).strip(), block[heading.end():end]))
    return result


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _matches(item: str, title: str) -> bool:
    return bool(_norm(item) and _norm(item) == _norm(title))


def _validate_stock_scenarios(block: str, core_pool: list[str], errors: list[str]) -> None:
    sections = _nested_sections(block)
    if not core_pool:
        if sections:
            errors.append("核心池为0时，⑦B不应出现股票小节")
        if "不适用" not in block and "核心池为0" not in block:
            errors.append("核心池为0时，⑦B应明确逐股三情景不适用")
        return
    for stock in core_pool:
        matches = [body for title, body in sections if _matches(stock, title)]
        if len(matches) != 1:
            errors.append(f"⑦B对核心池‘{stock}’的覆盖次数为{len(matches)}，应为1")
            continue
        for label in ("超预期", "符合预期", "低于预期"):
            if label not in matches[0]:
                errors.append(f"⑦B‘{stock}’缺少{label}情景")
    for title, _ in sections:
        if not any(_matches(stock, title) for stock in core_pool):
            errors.append(f"⑦B出现非核心池股票：{title}")


def _scan_statuses(text: str) -> dict[str, str]:
    data_block = text.split("## 数据限制", 1)[1] if "## 数据限制" in text else ""
    statuses: dict[str, str] = {}
    for row in _table_rows(data_block):
        if len(row) >= 2 and row[0] in REQUIRED_SCANS:
            statuses[row[0]] = row[1]
    return statuses


def _scan_rows(text: str) -> dict[str, list[str]]:
    data_block = text.split("## 数据限制", 1)[1] if "## 数据限制" in text else ""
    rows: dict[str, list[str]] = {}
    for row in _table_rows(data_block):
        if row and row[0] in REQUIRED_SCANS:
            rows[row[0]] = row
    return rows



def _read_process_jsonl(input_path: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for lineno, raw in enumerate(Path(input_path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"process JSONL第{lineno}行不是合法JSON：{exc}") from exc
        if not isinstance(item, dict) or not isinstance(item.get("event"), str):
            raise ValueError(f"process JSONL第{lineno}行必须是含event字段的JSON对象")
        events.append(item)
    return events


def _event_target(event: dict[str, Any]) -> str:
    for key in ("affected_chain", "target_chain", "name", "direction_id"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return _norm(value)
    return ""


def _has_source_binding(event: dict[str, Any]) -> bool:
    published = event.get("published_at")
    source = event.get("source")
    if isinstance(source, dict):
        return bool(published or source.get("published_at")) and bool(source.get("url") or source.get("title"))
    return bool(published) and bool(event.get("url") or event.get("title") or source)


POSITION_LEVELS = {"low": 0, "medium_low": 1, "medium": 2, "medium_high": 3, "high": 4, "低仓": 0, "中低仓": 1, "中仓": 2, "中高仓": 3, "高仓": 4}
QUERY_EVENTS = {"search", "search_query", "candidate_light_bundle", "material_sweep_bundle", "standalone_sweep", "coverage_repair_query"}
DISCOVERY_LENSES = {"breadth", "limit_cluster", "turnover_capacity", "relative_strength_persistence", "driver_event", "loss_risk"}
LENS_STATUS = {"signal_found", "no_material_signal", "partial"}
OUTPUT_TARGET_CHARS = 8500
OUTPUT_REVIEW_THRESHOLD = 8700
FORBIDDEN_POSITION_FAMILY = re.compile(r"candidate|候选|D数量|方向数量|watch|观察池|core数量|核心数量", re.I)
ENV_BREADTH = {"strong_positive", "positive", "mixed", "negative", "severe_negative", "missing"}
ENV_LIQUIDITY = {"expansion", "stable", "contraction", "missing"}
ENV_RELAY = {"high", "medium", "low", "missing"}
ENV_CAPACITY = {"strong", "neutral", "weak", "missing"}
ENV_INDEX = {"strong", "neutral", "weak", "missing"}


def _contract_version(events: list[dict[str, Any]], version: str) -> bool:
    for event in events:
        if event.get("event") == "run_start" and str(event.get("contract_version", "")).strip() == version:
            return True
    return False


FORBIDDEN_IDENTITY_FAILURE = re.compile(
    r"低仓|中低仓|不可执行|不新增|没有买点|无买点|不追|execution\s*=*\s*blocked|\bblocked\b|"
    r"技术.{0,12}(?:missing|缺失|不足|不可得)|MA(?:5|10|20|60)?|RSI|BIAS",
    re.I,
)


def _query_event_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for e in events if e.get("event") in QUERY_EVENTS and isinstance(e.get("query"), str) and e.get("query").strip())


def _position_level(value: Any) -> int | None:
    if value is None:
        return None
    return POSITION_LEVELS.get(str(value).strip())


def _extract_report_position(text: str, label: str) -> int | None:
    match = re.search(rf"(?:\*\*)?{re.escape(label)}\s*[:：](?:\*\*)?\s*(低仓|中低仓|中仓|中高仓|高仓)", text)
    return _position_level(match.group(1)) if match else None


def validate_process_report_consistency(text: str, events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not (_contract_version(events, "2.4.5") or _contract_version(events, "2.4.6")):
        return errors
    audits = [e for e in events if e.get("event") == "environment_budget_audit"]
    positions = [e for e in events if e.get("event") == "position_decision"]
    if len(audits) == 1:
        audited = _position_level(audits[0].get("budget"))
        reported = _extract_report_position(text, "环境风险预算")
        if audited is not None and reported is not None and audited != reported:
            errors.append("用户报告的环境风险预算必须与environment_budget_audit.budget一致")
    if len(positions) == 1:
        final = _position_level(positions[0].get("final_stance"))
        reported_final = _extract_report_position(text, "最终仓位建议")
        frontmatter = parse_review_frontmatter(text)
        fm_final = _position_level(frontmatter.get("position_stance")) if frontmatter else None
        if final is not None and reported_final is not None and final != reported_final:
            errors.append("用户报告的最终仓位建议必须与position_decision.final_stance一致")
        if final is not None and fm_final is not None and final != fm_final:
            errors.append("frontmatter.position_stance必须与position_decision.final_stance一致")

    if _contract_version(events, "2.4.6"):
        audits = [e for e in events if e.get("event") == "output_compression_audit"]
        if len(audits) != 1:
            errors.append("v2.4.6过程必须且只能有1个output_compression_audit")
        else:
            audit = audits[0]
            if audit.get("report_chars") != len(text):
                errors.append(f"output_compression_audit.report_chars={audit.get('report_chars')}与实际字符数{len(text)}不一致")
            if audit.get("target_chars") != OUTPUT_TARGET_CHARS:
                errors.append(f"output_compression_audit.target_chars必须为{OUTPUT_TARGET_CHARS}")
            if audit.get("fact_owner_status") != "pass":
                errors.append("output_compression_audit.fact_owner_status必须为pass")
        if len(text) > OUTPUT_REVIEW_THRESHOLD:
            exceptions = [e for e in events if e.get("event") == "output_budget_exception"]
            valid = False
            for event in exceptions:
                sections = event.get("irreducible_sections") or []
                chains = event.get("decision_or_risk_chains") or []
                if (isinstance(sections, list) and len(sections) >= 2 and isinstance(chains, list) and len(chains) >= 2
                        and event.get("why_each_extra_section_changes_action") and event.get("compression_attempted") is True):
                    valid = True
            if not valid:
                errors.append(f"v2.4.6报告{len(text)}字符，超过{OUTPUT_REVIEW_THRESHOLD}且没有合格output_budget_exception")
    return errors


def validate_process_jsonl(events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    v243 = _contract_version(events, "2.4.3")
    v244 = _contract_version(events, "2.4.4")
    v245 = _contract_version(events, "2.4.5")
    v246 = _contract_version(events, "2.4.6")
    discipline_contract = v243 or v244 or v245 or v246
    query_count = _query_event_count(events)
    budget_exceptions = [e for e in events if e.get("event") == "research_budget_exception"]
    if query_count > 28:
        valid_exception = False
        for event in budget_exceptions:
            required = ("unresolved_question", "decision_field", "expected_flip", "why_existing_evidence_insufficient", "stop_condition")
            if all(event.get(key) not in (None, "", [], {}) for key in required):
                valid_exception = True
            else:
                errors.append("research_budget_exception字段不完整，必须记录unresolved_question/decision_field/expected_flip/why_existing_evidence_insufficient/stop_condition")
        if not valid_exception:
            errors.append(f"query-bearing研究事件为{query_count}，超过正常路径28且没有完整research_budget_exception")

    if discipline_contract:
        summaries = [e for e in events if e.get("event") == "research_budget_summary"]
        if len(summaries) != 1:
            errors.append("v2.4.3+过程必须且只能有1个research_budget_summary")
        else:
            summary = summaries[0]
            if summary.get("total_query_events") != query_count:
                errors.append(f"research_budget_summary.total_query_events={summary.get('total_query_events')}与实际query-bearing事件{query_count}不一致")
            if not summary.get("stop_reason"):
                errors.append("research_budget_summary缺少stop_reason")

        coverage = [e for e in events if e.get("event") == "discovery_coverage_summary"]
        if len(coverage) != 1:
            errors.append("v2.4.3+过程必须且只能有1个discovery_coverage_summary")
        else:
            c = coverage[0]
            attempted = c.get("lenses_attempted")
            total = c.get("lenses_total")
            count = c.get("dedup_candidate_count")
            if attempted != 6 or total != 6:
                errors.append("theme_discovery=ok前必须完成六视角Discovery 6/6")
            if isinstance(count, int):
                if count < 8 and not any(c.get(k) for k in ("sparse_reason", "missing_reason", "reason")):
                    errors.append("去重候选少于8个时必须记录市场稀疏/数据缺失理由")
                if count > 12:
                    errors.append("去重候选超过12个时必须先合并/压缩再进入正式D选择")

        if v246:
            lens_events = [e for e in events if e.get("event") == "discovery_lens_scan"]
            by_lens: dict[str, list[dict[str, Any]]] = {}
            for event in lens_events:
                lens = str(event.get("lens", ""))
                by_lens.setdefault(lens, []).append(event)
            if set(by_lens) != DISCOVERY_LENSES or any(len(items) != 1 for items in by_lens.values()):
                errors.append("v2.4.6必须对六个Discovery Lens各记录且只记录1条discovery_lens_scan")
            repairs = [e for e in events if e.get("event") == "coverage_repair_query"]
            repair_by_lens: dict[str, list[dict[str, Any]]] = {}
            for event in repairs:
                lens = str(event.get("lens", ""))
                repair_by_lens.setdefault(lens, []).append(event)
                if lens not in DISCOVERY_LENSES or not event.get("query") or not event.get("reason"):
                    errors.append("coverage_repair_query必须记录合法lens/query/reason")
            for lens in DISCOVERY_LENSES:
                items = by_lens.get(lens, [])
                if len(items) != 1:
                    continue
                event = items[0]
                if event.get("status") not in LENS_STATUS:
                    errors.append(f"discovery_lens_scan.{lens}.status非法")
                if not isinstance(event.get("candidate_names"), list):
                    errors.append(f"discovery_lens_scan.{lens}.candidate_names必须为列表")
                if not event.get("evidence"):
                    errors.append(f"discovery_lens_scan.{lens}.evidence不能为空")
                unresolved = event.get("high_salience_unresolved") is True
                lens_repairs = repair_by_lens.get(lens, [])
                if len(lens_repairs) > 1:
                    errors.append(f"每个Discovery Lens最多1次coverage_repair_query：{lens}")
                if event.get("status") == "partial" and unresolved and not lens_repairs and not event.get("coverage_degraded_reason"):
                    errors.append(f"Discovery Lens {lens}仍有高显著未决信号时必须repair或记录coverage_degraded_reason")

        if v245 or v246:
            env_audits = [e for e in events if e.get("event") == "environment_budget_audit"]
            if len(env_audits) != 1:
                errors.append("v2.4.5过程必须且只能有1个environment_budget_audit")
                env_audit = {}
            else:
                env_audit = env_audits[0]
                required = ("market_state", "dominant_style", "breadth_state", "liquidity_state", "relay_state", "capacity_state", "index_state", "budget", "evidence")
                for key in required:
                    if env_audit.get(key) in (None, "", [], {}):
                        errors.append(f"environment_budget_audit缺少{key}")
                breadth = str(env_audit.get("breadth_state", ""))
                liquidity = str(env_audit.get("liquidity_state", ""))
                relay = str(env_audit.get("relay_state", ""))
                capacity = str(env_audit.get("capacity_state", ""))
                index = str(env_audit.get("index_state", ""))
                if breadth not in ENV_BREADTH:
                    errors.append("environment_budget_audit.breadth_state取值非法")
                if liquidity not in ENV_LIQUIDITY:
                    errors.append("environment_budget_audit.liquidity_state取值非法")
                if relay not in ENV_RELAY:
                    errors.append("environment_budget_audit.relay_state取值非法")
                if capacity not in ENV_CAPACITY:
                    errors.append("environment_budget_audit.capacity_state取值非法")
                if index not in ENV_INDEX:
                    errors.append("environment_budget_audit.index_state取值非法")
                budget_level = _position_level(env_audit.get("budget"))
                if budget_level is None:
                    errors.append("environment_budget_audit.budget必须使用五档仓位")
                evidence_text = str(env_audit.get("evidence", ""))
                override = env_audit.get("environment_budget_override")
                if FORBIDDEN_POSITION_FAMILY.search(evidence_text) or (override and FORBIDDEN_POSITION_FAMILY.search(str(override))):
                    errors.append("环境风险预算不得使用候选/D/watch/core数量作为依据")
                market_state = str(env_audit.get("market_state", "")).lower()
                style = str(env_audit.get("dominant_style", "")).lower()
                weak_families = sum([liquidity == "contraction", relay == "low", capacity == "weak"])
                weak_anchor = market_state == "weak" and style == "defensive" and breadth == "severe_negative" and weak_families >= 2
                strong_anchor = market_state == "strong" and breadth in {"positive", "strong_positive"} and relay == "high" and (liquidity in {"expansion", "stable"} or capacity == "strong")
                if weak_anchor and budget_level is not None and budget_level > 0:
                    valid = isinstance(override, dict) and len({str(x).strip() for x in (override.get("support_families") or []) if str(x).strip()}) >= 2 and override.get("breadth_or_liquidity_repair") is True and bool(override.get("reason"))
                    if not valid:
                        errors.append("触发weak-defense low anchor时环境预算必须为低仓，除非有两个独立反向支持族且包含宽度/流动性修复override")
                if strong_anchor and budget_level is not None and budget_level < 3:
                    valid = isinstance(override, dict) and len({str(x).strip() for x in (override.get("risk_families") or []) if str(x).strip()}) >= 2 and bool(override.get("reason"))
                    if not valid:
                        errors.append("触发strong-risk-on floor时环境预算不得低于中高仓，除非有两个独立负向风险族override")

        pos_events = [e for e in events if e.get("event") == "position_decision"]
        if len(pos_events) != 1:
            errors.append("v2.4.3+过程必须且只能有1个position_decision")
        else:
            pos = pos_events[0]
            env = _position_level(pos.get("environment_budget"))
            final = _position_level(pos.get("final_stance"))
            families = pos.get("upward_confirmation_families") or []
            if env is None or final is None:
                errors.append("position_decision的environment_budget/final_stance必须使用五档仓位")
            if (v245 or v246) and 'env_audit' in locals() and env_audit:
                audited_env = _position_level(env_audit.get("budget"))
                if audited_env is not None and env is not None and audited_env != env:
                    errors.append("position_decision.environment_budget必须与environment_budget_audit.budget一致")
            if not isinstance(families, list):
                errors.append("position_decision.upward_confirmation_families必须为列表")
                families = []
            if any(FORBIDDEN_POSITION_FAMILY.search(str(item)) for item in families):
                errors.append("候选/D/watch/core数量不得作为仓位上调确认族")
            if env is not None and final is not None and final > env and len({_norm(str(x)) for x in families if str(x).strip()}) < 2:
                errors.append("最终仓位高于环境风险预算时，至少需要2个独立上调确认族")

        pool_events = [e for e in events if e.get("event") == "pool_selection"]
        audit_events = [e for e in events if e.get("event") == "core_selection_audit"]
        if len(audit_events) != 1:
            errors.append("v2.4.3+过程必须且只能有1个core_selection_audit")
        else:
            audit = audit_events[0]
            selected = audit.get("selected") or []
            if not isinstance(selected, list) or not all(isinstance(x, dict) for x in selected):
                errors.append("core_selection_audit.selected必须为对象列表")
                selected = []
            pool = []
            if pool_events:
                pool = pool_events[-1].get("core_pool") or []
                selected_names = [x.get("name") for x in selected if x.get("name")]
                if {_norm(str(x)) for x in pool} != {_norm(str(x)) for x in selected_names}:
                    errors.append("core_selection_audit.selected必须与pool_selection.core_pool一致")

            by_direction: dict[str, list[dict[str, Any]]] = {}
            for item in selected:
                direction = str(item.get("direction_id", "")).upper()
                if direction:
                    by_direction.setdefault(direction, []).append(item)
                if v244 or v245 or v246:
                    for key in ("name", "direction_id", "role", "peer_advantage", "identity_value", "lifecycle", "identity_status", "execution_status", "execution_reason"):
                        if item.get(key) in (None, "", [], {}):
                            errors.append(f"core_selection_audit.selected缺少{key}字段")
                    if str(item.get("identity_status", "")).lower() != "pass":
                        errors.append(f"已进入core_pool的标的identity_status必须为pass：{item.get('name','未知')}")
                    if str(item.get("execution_status", "")).lower() not in {"allowed", "conditional", "blocked"}:
                        errors.append(f"execution_status必须为allowed/conditional/blocked：{item.get('name','未知')}")
                else:
                    for key in ("name", "direction_id", "role", "peer_advantage", "unique_action_value", "lifecycle", "execution_status"):
                        if item.get(key) in (None, "", [], {}):
                            errors.append(f"core_selection_audit.selected缺少{key}字段")

            duplicate_audits = audit.get("same_direction_duplicates") or []
            for direction, items in by_direction.items():
                if len(items) >= 2:
                    match = next((x for x in duplicate_audits if str(x.get("direction_id", "")).upper() == direction), None)
                    if (
                        not match
                        or match.get("distinct_role") is not True
                        or match.get("distinct_validation") is not True
                        or not match.get("role_difference")
                        or not match.get("validation_difference")
                        or not match.get("reason")
                    ):
                        errors.append(f"同一D选择{len(items)}只core时必须证明角色差异与次日验证差异：{direction}")

            new_start_audits = audit.get("new_start_cores") or []
            for item in selected:
                if "新启动" in str(item.get("lifecycle", "")):
                    name = _norm(str(item.get("name", "")))
                    match = next((x for x in new_start_audits if _norm(str(x.get("name", x.get("stock", "")))) == name), None)
                    required_value = "identity_value" if (v244 or v245 or v246) else "unique_action_value"
                    if not match or not match.get("independent_driver") or not match.get("capacity_or_peer_confirmation") or not match.get(required_value):
                        errors.append(f"新启动core必须有独立Driver、容量/同行确认和独特身份/动作价值：{item.get('name','未知')}")

            pos = pos_events[0] if len(pos_events) == 1 else {}
            env = _position_level(pos.get("environment_budget"))
            if env is not None and env <= 1 and len(selected) > 3:
                expand = audit.get("core_pool_expansion_exception")
                if v244 or v245 or v246:
                    required = ("independent_chains", "unique_identity_value", "coverage_gap", "reason")
                    if not isinstance(expand, dict) or not all(expand.get(k) for k in required):
                        errors.append("低仓/中低仓环境预算下core>3必须记录core_pool_expansion_exception并证明独立链/身份价值/前三只覆盖缺口")
                else:
                    if not isinstance(expand, dict) or not all(expand.get(k) for k in ("independent_chains", "unique_action_value", "executable_conditions", "reason")):
                        errors.append("低仓/中低仓环境预算下core>3必须记录core_pool_expansion_exception并证明独立链/动作价值/可执行条件")

            if (v244 or v245 or v246) and not selected:
                promoted_d_ids = {
                    str(e.get("direction_id", "")).upper()
                    for e in events
                    if e.get("event") == "candidate_promoted" and re.fullmatch(r"D[1-5]", str(e.get("direction_id", "")).upper())
                }
                zero_audits = [e for e in events if e.get("event") == "core_zero_audit"]
                if promoted_d_ids:
                    if len(zero_audits) != 1:
                        errors.append("core_pool=0且存在正式D时必须且只能有1个core_zero_audit")
                    else:
                        chains = zero_audits[0].get("chains") or []
                        if not isinstance(chains, list):
                            errors.append("core_zero_audit.chains必须为列表")
                            chains = []
                        by_id = {str(x.get("direction_id", "")).upper(): x for x in chains if isinstance(x, dict)}
                        for did in sorted(promoted_d_ids):
                            item = by_id.get(did)
                            if not item:
                                errors.append(f"core_zero_audit漏掉正式D：{did}")
                                continue
                            if not item.get("candidates_considered") or not item.get("identity_failure"):
                                errors.append(f"core_zero_audit.{did}必须记录candidates_considered与identity_failure")
                                continue
                            if FORBIDDEN_IDENTITY_FAILURE.search(str(item.get("identity_failure", ""))):
                                errors.append(f"core_zero_audit.{did}不得用低仓/不可执行/无买点/技术缺失冒充identity failure")

        promoted = [e for e in events if e.get("event") == "candidate_promoted" and re.fullmatch(r"[DR][1-5]", str(e.get("direction_id", "")).upper())]
        coverage_events = [e for e in events if e.get("event") == "counterevidence_coverage"]
        if len(coverage_events) != 1:
            errors.append("v2.4.3+过程必须且只能有1个counterevidence_coverage")
        else:
            chains = coverage_events[0].get("chains") or []
            if not isinstance(chains, list):
                errors.append("counterevidence_coverage.chains必须为列表")
                chains = []
            by_id = {str(x.get("direction_id", "")).upper(): x for x in chains if isinstance(x, dict)}
            for item in promoted:
                did = str(item.get("direction_id", "")).upper()
                c = by_id.get(did)
                if not c:
                    errors.append(f"counterevidence_coverage漏掉正式链：{did}")
                else:
                    if c.get("max_counterevidence_present") is not True or not c.get("max_counterevidence"):
                        errors.append(f"正式链{did}缺最大反证覆盖/文本")
                    if c.get("sweep_status") not in {"ok", "partial", "missing"}:
                        errors.append(f"正式链{did}缺最终反证扫尾状态")
    promoted_d = [e for e in events if e.get("event") == "candidate_promoted" and str(e.get("direction_id", "")).upper().startswith("D")]
    merge_checks = [e for e in events if e.get("event") == "formal_d_merge_check"]
    if len(promoted_d) >= 2 and not merge_checks:
        errors.append("process JSONL缺少正式D合并终审事件formal_d_merge_check")
    for event in merge_checks:
        if not any(event.get(key) not in (None, "", [], {}) for key in ("result", "merge_or_split", "decisions", "candidate_pairs_considered")):
            errors.append("formal_d_merge_check不能是空占位，必须记录终审结果或候选对检查摘要")

    hit_indices = [i for i, e in enumerate(events) if e.get("event") == "material_news_hit"]
    for i in hit_indices:
        event = events[i]
        if not _event_target(event):
            errors.append("material_news_hit缺少affected_chain/name等受影响对象")
        if not _has_source_binding(event):
            errors.append("material_news_hit缺少来源/发布时间绑定")

    for i, event in enumerate(events):
        kind = event.get("event")
        target = _event_target(event)
        if kind == "decision_change":
            for key in ("before", "after", "reason"):
                if not event.get(key):
                    errors.append(f"decision_change缺少{key}字段")
            prior_hit_indices = [j for j, e in enumerate(events[:i]) if e.get("event") == "material_news_hit" and (not target or _event_target(e) == target)]
            prior_reopen_indices = [j for j, e in enumerate(events[:i]) if e.get("event") == "decision_reopened" and (not target or _event_target(e) == target)]
            ordered_chain = any(hit < reopen < i for hit in prior_hit_indices for reopen in prior_reopen_indices)
            if not ordered_chain:
                errors.append("decision_change之前必须按material_news_hit → decision_reopened → decision_change顺序记录同一受影响对象")

        if kind == "candidate_rejected" and re.search(r"反证|澄清|事故|火灾|爆炸|监管|制裁|处罚|调查|重大公告", str(event.get("reason", ""))):
            prior_hits = [e for e in events[:i] if e.get("event") == "material_news_hit" and (not target or _event_target(e) == target)]
            if not prior_hits:
                errors.append(f"事件/反证导致候选淘汰‘{event.get('name','未知')}’时缺少带来源的material_news_hit")
    return errors

def validate(text: str) -> list[str]:
    errors: list[str] = []
    frontmatter = parse_review_frontmatter(text)
    if not frontmatter:
        errors.append("缺少可解析的frontmatter")
    for key in REQUIRED_FRONTMATTER:
        if key not in frontmatter:
            errors.append(f"frontmatter缺少必填字段：{key}")
    if frontmatter.get("review_schema") != "2.0":
        errors.append('新版复盘review_schema必须为"2.0"')
    core_pool = frontmatter.get("core_pool", [])
    watch_pool = frontmatter.get("watch_pool", [])
    if not isinstance(core_pool, list) or not all(isinstance(item, str) for item in core_pool):
        errors.append("frontmatter的core_pool必须是字符串列表")
        core_pool = []
    if not isinstance(watch_pool, list) or not all(isinstance(item, str) for item in watch_pool):
        errors.append("frontmatter的watch_pool必须是字符串列表")
        watch_pool = []
    if len(core_pool) > 5:
        errors.append(f"core_pool有{len(core_pool)}只，超过5只上限")
    if len(watch_pool) > 3:
        errors.append(f"watch_pool有{len(watch_pool)}只，超过3只上限")
    conclusion_match = re.search(r"(?m)^## 先说结论\s*$", text)
    if not conclusion_match:
        errors.append("缺少顶部‘## 先说结论’")
    else:
        conclusion_end = text.find(EXPECTED_SECTIONS[0], conclusion_match.end())
        conclusion_block = text[conclusion_match.end(): conclusion_end if conclusion_end >= 0 else len(text)]
        for label in ("市场", "风格", "主线", "机会", "风险", "仓位"):
            if not re.search(rf"(?:\*\*)?{label}(?:\*\*)?\s*[:：]", conclusion_block):
                errors.append(f"‘先说结论’缺少六要素字段：{label}")

    overlap = [stock for stock in core_pool if any(_matches(stock, other) for other in watch_pool)]
    if overlap:
        errors.append(f"core_pool与watch_pool不得重复：{', '.join(overlap)}")

    blocks = _section_blocks(text, errors)
    if not any(blocks):
        return errors

    for index, block in enumerate(blocks[:6], start=1):
        if TECHNICAL_PATTERN.search(block):
            errors.append(f"第{index}步出现个股MA、RSI9或BIAS20；技术指标只能用于⑦C")

    step1 = blocks[0]
    for label in ("市场环境", "环境风险预算", "短线情绪", "昨日涨停反馈", "接力容错率", "主导交易风格"):
        if label not in step1:
            errors.append(f"第①步缺少：{label}")
    if not TURNOVER_TOP20_PATTERN.search(step1):
        errors.append("第①步缺少成交额Top20/成交额前20整体反馈")
    if TURNOVER_TOP20_PATTERN.search(step1) and re.search(r"机构进场", step1):
        # 只在文本把Top20与机构进场直接绑定时拦截；存在其他独立席位/净流入证据时应明确写出。
        if not re.search(r"(?:龙虎榜|机构席位|净流入|席位证据|独立证据).{0,80}机构进场|机构进场.{0,80}(?:龙虎榜|机构席位|净流入|席位证据|独立证据)", step1, re.DOTALL):
            errors.append("不得仅凭成交额Top20/前20上涨判断机构进场；若有独立席位或净流入证据需明确写出")
    feedback_match = re.search(r"(?m)^\s*(?:\*\*)?昨日涨停反馈\s*[:：]?\s*(?:\*\*)?\s*[:：]?\s*(正|中性|负|待确认|缺失)", step1)
    if feedback_match and feedback_match.group(1) in {"正", "中性", "负"}:
        if re.search(r"(?:全样本|收益分布|正收益占比|收益中位数).{0,40}(?:缺失|未取得|未完整)", step1):
            errors.append("昨日涨停全样本收益分布缺失时，不得仅凭具名样本直接判‘正/中性/负’，应降为待确认或缺失")

    step2 = blocks[1]
    if "赚钱模式" not in step2 or "亏钱模式" not in step2 or "亏钱效应" not in step2:
        errors.append("第②步必须同时输出赚钱模式、亏钱模式和亏钱效应")
    if not DIRECTION_OMISSION_PATTERN.search(step2):
        errors.append("第②步缺少‘方向遗漏审计’")
    d_rows = [row for row in _table_rows(_find_subsection(step2, "赚钱模式")) if row and re.fullmatch(r"D[1-5]", row[0], re.I)]
    r_rows = [row for row in _table_rows(_find_subsection(step2, "亏钱模式")) if row and re.fullmatch(r"R[1-3]", row[0], re.I)]
    d_ids = [row[0].upper() for row in d_rows]
    r_ids = [row[0].upper() for row in r_rows]
    for row in d_rows:
        if len(row) < 6 or any(not cell.strip() for cell in row[:6]):
            errors.append(f"第②步D方向行字段不完整：{' | '.join(row)}")
    for row in r_rows:
        if len(row) < 6 or any(not cell.strip() for cell in row[:6]):
            errors.append(f"第②步R方向行字段不完整：{' | '.join(row)}")
    if d_ids != [f"D{i}" for i in range(1, len(d_ids) + 1)]:
        errors.append("第②步D ID必须连续使用D1～D5")
    if r_ids != [f"R{i}" for i in range(1, len(r_ids) + 1)]:
        errors.append("第②步R ID必须连续使用R1～R3")
    if len(d_rows) > 5 or len(r_rows) > 3:
        errors.append("第②步方向数量超过D≤5或R≤3上限")
    d_names = {_norm(row[1]) for row in d_rows if len(row) > 1}
    r_names = {_norm(row[1]) for row in r_rows if len(row) > 1}
    if d_names & r_names:
        errors.append("同一方向不得同时建立D和R")

    step3_rows = _table_rows(blocks[2])
    chain_ids: set[str] = set()
    step3_d_chains: set[str] = set()
    step3_r_chains: set[str] = set()
    for row in step3_rows:
        if not row or not re.fullmatch(r"(?:D[1-5][a-z]?|R[1-3])", row[0], re.I):
            continue
        chain_id = row[0].upper()
        chain_ids.add(chain_id)
        (step3_d_chains if chain_id.startswith("D") else step3_r_chains).add(chain_id)
        if len(row) < 8:
            errors.append(f"第③步‘{chain_id}’字段不完整")
            continue
        state, basis = row[2], row[3]
        if not re.search(r"主线|支线|轮动|观察", state) or not re.search(r"新启动|强化|分歧|修复|退潮|待确认", state):
            errors.append(f"第③步‘{chain_id}’缺少地位或生命周期")
        if any(stage in state for stage in LIFECYCLES) and not basis.strip():
            errors.append(f"第③步‘{chain_id}’缺少阶段依据/相对强弱")
        for index, label in ((4, "Driver状态"), (5, "预期差/最大反证"), (6, "升级条件"), (7, "降级/失效条件")):
            if not row[index].strip():
                errors.append(f"第③步‘{chain_id}’缺少{label}")
    for direction_id in d_ids + r_ids:
        if not any(chain.startswith(direction_id) for chain in chain_ids):
            errors.append(f"第②步方向‘{direction_id}’未被第③步承接")

    step4 = blocks[3]
    d_core_rows = [
        row for row in _table_rows(_find_subsection(step4, "D方向核心比较"))
        if row and re.fullmatch(r"D[1-5][a-z]?", row[0], re.I)
    ]
    for row in d_core_rows:
        if len(row) < 6 or any(not cell.strip() for cell in row[:6]):
            errors.append(f"第④步D核心比较行字段不完整：{' | '.join(row)}")
    step4_d_chains = {row[0].upper() for row in d_core_rows}
    risk_anchor_rows = [
        row for row in _table_rows(_find_subsection(step4, "R方向风险锚"))
        if row and re.fullmatch(r"R[1-3]", row[0], re.I)
    ]
    for row in risk_anchor_rows:
        if len(row) < 5 or any(not cell.strip() for cell in row[:5]):
            errors.append(f"第④步R风险锚行字段不完整：{' | '.join(row)}")
    step4_r_chains = {row[0].upper() for row in risk_anchor_rows}
    for chain_id in sorted(step3_d_chains):
        if chain_id not in step4_d_chains:
            errors.append(f"第③步D链‘{chain_id}’未被第④步核心股定位承接")
    for chain_id in sorted(step3_r_chains):
        if chain_id not in step4_r_chains:
            errors.append(f"第③步R链‘{chain_id}’未被第④步风险锚承接")
    risk_anchor_stocks = [row[1] for row in risk_anchor_rows if len(row) > 1]
    for stock in risk_anchor_stocks:
        if any(_matches(stock, item) for item in core_pool + watch_pool):
            errors.append(f"风险锚不得进入core_pool/watch_pool：{stock}")

    step5 = blocks[4]
    if "持仓复盘" not in step5 or "交易复盘" not in step5:
        errors.append("第⑤步必须合并持仓复盘和交易复盘")
    if not re.search(r"正确决策|错误决策|未提供.*交易", step5):
        errors.append("第⑤步缺少决策×结果评价或缺失说明")

    step6 = blocks[5]
    core_rows = _table_rows(_find_subsection(step6, "core_pool"))
    watch_rows = _table_rows(_find_subsection(step6, "watch_pool"))
    step6_risk_rows = _table_rows(_find_subsection(step6, "风险锚"))
    if len(core_rows) != len(core_pool):
        errors.append("第⑥步core_pool表与frontmatter不一致")
    if len(watch_rows) != len(watch_pool):
        errors.append("第⑥步watch_pool表与frontmatter不一致")
    if len(step6_risk_rows) > 3:
        errors.append("第⑥步风险锚超过3只上限")
    for item in core_pool:
        if not any(row and _matches(item, row[0]) for row in core_rows):
            errors.append(f"第⑥步core_pool缺少：{item}")
    for item in watch_pool:
        if not any(row and _matches(item, row[0]) for row in watch_rows):
            errors.append(f"第⑥步watch_pool缺少：{item}")

    def validate_d_selection(row: list[str], pool_name: str) -> None:
        if len(row) < 2:
            errors.append(f"第⑥步{pool_name}行缺少D链路：{row[0] if row else '未知'}")
            return
        source = row[1].upper()
        if source.startswith("R"):
            errors.append(f"R方向不得进入core_pool/watch_pool：{row[0]}")
            return
        if source not in step3_d_chains:
            errors.append(f"第⑥步{pool_name}‘{row[0]}’引用不存在的第③步D链：{row[1]}")
            return
        same_chain_rows = [item for item in d_core_rows if item and item[0].upper() == source]
        if not same_chain_rows:
            errors.append(f"第⑥步{pool_name}‘{row[0]}’的D链未在第④步承接：{source}")
        elif not any(len(item) > 1 and _matches(row[0], item[1]) for item in same_chain_rows):
            errors.append(f"第⑥步{pool_name}‘{row[0]}’未在第④步同链核心比较中出现：{source}")

    for row in core_rows:
        validate_d_selection(row, "core_pool")
    for row in watch_rows:
        validate_d_selection(row, "watch_pool")

    step6_r_chains: set[str] = set()
    for row in step6_risk_rows:
        if len(row) < 2:
            errors.append(f"第⑥步风险锚行缺少R链路：{row[0] if row else '未知'}")
            continue
        source = row[1].upper()
        step6_r_chains.add(source)
        if source not in step3_r_chains:
            errors.append(f"第⑥步风险锚‘{row[0]}’引用不存在的第③步R链：{row[1]}")
        if source not in step4_r_chains:
            errors.append(f"第⑥步风险锚‘{row[0]}’的R链未在第④步承接：{source}")
        if any(_matches(row[0], item) for item in core_pool + watch_pool):
            errors.append(f"风险锚不得进入core_pool/watch_pool：{row[0]}")
    for source in sorted(step3_r_chains):
        if source not in step6_r_chains:
            errors.append(f"第③步R链‘{source}’未被第⑥步风险锚承接")
    if "近线淘汰" in step6:
        errors.append("正式日报不得输出近线淘汰栏目")

    step7 = blocks[6]
    for subsection in ("⑦A", "⑦B", "⑦C"):
        if not _find_subsection(step7, subsection):
            errors.append(f"第⑦步缺少{subsection}子阶段")
    market_script = _find_subsection(step7, "⑦A")
    for scenario in ("超预期", "基准", "低于预期"):
        if scenario not in market_script:
            errors.append(f"⑦A缺少市场{scenario}情景")
    scenario_block = _find_subsection(step7, "⑦B")
    _validate_stock_scenarios(scenario_block, core_pool, errors)
    technical_block = _find_subsection(step7, "⑦C")
    technical_sections = _nested_sections(technical_block)
    global_gates = [(title, body) for title, body in technical_sections if title.startswith("全局技术执行门")]
    if len(global_gates) > 1:
        errors.append("⑦C全局技术执行门最多1个")
    global_gate_body = global_gates[0][1] if global_gates else ""
    global_gate_valid = bool(
        global_gate_body
        and all(label in global_gate_body for label in ("MA", "RSI9", "BIAS20"))
        and re.search(r"missing|缺失|不足|不可得", global_gate_body, re.I)
        and re.search(r"技术执行数据恢复前.{0,20}(?:不新增|不可执行)|冻结新增|不允许新增", global_gate_body)
    )
    global_affected = {stock for stock in core_pool if global_gate_body and _norm(stock) in _norm(global_gate_body)}
    if global_gate_body and not global_gate_valid:
        errors.append("⑦C全局技术执行门字段不完整，必须包含MA/RSI9/BIAS20缺口与冻结新增结论")

    for stock in core_pool:
        matches = [body for title, body in technical_sections if _matches(stock, title)]
        if len(matches) != 1:
            errors.append(f"⑦C对核心池‘{stock}’的覆盖次数为{len(matches)}，应为1")
            continue
        body = matches[0]
        if stock in global_affected and global_gate_valid:
            if "不追条件" not in body or not re.search(r"失效条件|减仓/退出", body):
                errors.append(f"⑦C‘{stock}’被全局技术门覆盖时仍需保留不追条件与失效/退出条件")
            continue
        if not all(label in body for label in ("MA", "RSI9", "BIAS20", "不追条件", "趋势确认", "新增买入", "减仓/退出")):
            errors.append(f"⑦C‘{stock}’技术执行字段不完整")
        else:
            tech_missing = re.search(r"(?:MA(?:5|10|20|60)?|RSI9|BIAS20)[^\n]{0,100}(?:missing|缺失|不足|不可得)", body, re.I)
            if tech_missing and not re.search(r"技术执行数据恢复前.{0,20}(?:不新增|不可执行)|冻结新增|不允许新增", body):
                errors.append(f"⑦C‘{stock}’技术数据缺失时必须明确冻结新增执行")
    for title, body in technical_sections:
        if title.startswith("非核心风险持仓") and FORBIDDEN_RISK_ACTION.search(body):
            errors.append(f"{title}出现禁止的新增/补仓/摊低/升级动作")
    for label in ("最终仓位建议", "较前状态", "提高条件", "降低条件"):
        if label not in step7:
            errors.append(f"第⑦步缺少仓位字段：{label}")
    if re.search(r"最终仓位建议.{0,40}\d+\s*%", step7) and "冻结" not in step7 and "用户仓位模型" not in step7:
        errors.append("未声明冻结仓位模型时不得给精确百分比仓位")

    completeness = frontmatter.get("data_completeness")
    if completeness == "severe_missing":
        for row in step3_rows:
            if not row or not re.fullmatch(r"(?:D[1-5][a-z]?|R[1-3])", row[0], re.I):
                continue
            state = row[3] if len(row) > 3 else ""
            row_text = " | ".join(row)
            if not ("观察" in state and "待确认" in state and "低置信度" in row_text):
                errors.append(f"严重数据缺失时第③步‘{row[0]}’必须降级为‘观察 × 待确认｜低置信度’")
    statuses = _scan_statuses(text)
    scan_rows = _scan_rows(text)
    for scan in REQUIRED_SCANS:
        if scan not in statuses:
            errors.append(f"数据限制覆盖表缺少扫描：{scan}")
        elif statuses[scan] not in VALID_SCAN_STATUS:
            errors.append(f"扫描{scan}状态不合法：{statuses[scan]}")
        elif scan != "user_holdings_focus" and statuses[scan] == "not_applicable":
            errors.append(f"只有个人输入扫描可使用not_applicable：{scan}")
    if completeness == "complete" and any(statuses.get(scan) != "ok" for scan in REQUIRED_SCANS[:5]):
        errors.append("关键扫描未全部ok时data_completeness不得为complete")
    theme_row = scan_rows.get("theme_discovery", [])
    theme_note = theme_row[2] if len(theme_row) >= 3 else ""
    if theme_row and not (
        re.search(r"视角|发现面|发现维度|lens", theme_note, re.I)
        and re.search(r"候选|candidate|方向.?异常", theme_note, re.I)
    ):
        errors.append("数据限制的theme_discovery行必须简要记录发现视角与去重候选覆盖")
    material_row = scan_rows.get("material_news", [])
    material_note = material_row[2] if len(material_row) >= 3 else ""
    if material_row and not re.search(r"(?:最终|重大)?反证扫尾", material_note):
        errors.append("数据限制的material_news行必须记录最终反证扫尾状态")
    if re.search(r"tool_call_id|custom_tool_call|exec_command|search_query\s*[:=]", text, re.I):
        errors.append("用户正文疑似混入工具调用流水账")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Markdown报告路径；使用-从stdin读取")
    parser.add_argument("--json", action="store_true", help="以JSON输出检查结果")
    parser.add_argument("--process-jsonl", help="可选：过程审计JSONL路径；提供时同时检查D合并终审与重大反证证据链")
    args = parser.parse_args()
    try:
        text = _read_text(args.input)
        errors = validate(text)
        if args.process_jsonl:
            events = _read_process_jsonl(args.process_jsonl)
            errors.extend(validate_process_jsonl(events))
            errors.extend(validate_process_report_consistency(text, events))
    except (OSError, UnicodeError, ValueError) as exc:
        errors = [f"无法读取报告：{exc}"]
    result = {"valid": not errors, "errors": errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print("FAIL: 复盘输出未通过七步契约检查")
        for error in errors:
            print(f"- {error}")
    else:
        print("PASS: 复盘输出已通过七步契约检查")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
