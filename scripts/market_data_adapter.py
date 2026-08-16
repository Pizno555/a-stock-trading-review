#!/usr/bin/env python3
"""Provider-neutral JSON adapter for A-share review data."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from mx_bridge import BridgeError, request_mx, write_json


SCHEMA_VERSION = "1.0"
SCRIPT_INTERFACE = "cli"
SYMBOL_RE = re.compile(r"^\d{6}(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
THEME_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,60}$")


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _find_first(payload: Any, key: str) -> Any:
    for node in _walk(payload):
        if isinstance(node, dict) and key in node:
            return node[key]
    return None


def _to_number(value: Any) -> Any:
    if value in (None, "", "--", "-"):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value).strip().replace(",", "")
    for suffix in ("%", "点", "元", "股", "手", "家"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    multiplier = 1.0
    for suffix, factor in (("万亿", 1e12), ("亿", 1e8), ("万", 1e4)):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            multiplier = factor
            break
    try:
        return float(text) * multiplier
    except ValueError:
        return value


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else None


def _ordered_keys(block: dict[str, Any], table: dict[str, Any]) -> list[str]:
    raw = block.get("indicatorOrder") or []
    if isinstance(raw, str):
        raw = raw.split()
    keys = [str(item) for item in raw if str(item) in table and str(item) != "headName"]
    for key in table:
        if key != "headName" and key not in keys:
            keys.append(key)
    return keys


def _normalize_blocks(response: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    blocks = _find_first(response, "dataTableDTOList")
    if not isinstance(blocks, list):
        return [], ["MX response did not contain dataTableDTOList."]

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        table = block.get("table") or block.get("rawTable") or {}
        if not isinstance(table, dict):
            warnings.append(f"Skipped non-tabular block: {block.get('title') or block.get('code')}")
            continue
        headers = table.get("headName") or []
        if not isinstance(headers, list):
            headers = [headers]
        name_map = block.get("nameMap") or {}
        if not isinstance(name_map, dict):
            name_map = {}
        row_keys = [str(key) for key in table if str(key) != "headName"]
        row_oriented = bool(headers and row_keys) and all(
            isinstance(table.get(key), list) and len(table.get(key)) == len(headers)
            for key in row_keys
        ) and any(SYMBOL_RE.fullmatch(str(name_map.get(key) or "")) for key in row_keys)
        if row_oriented:
            row_date = _date_text(block.get("entityName"))
            for key in row_keys:
                entity_code = str(name_map.get(key) or "")
                if not SYMBOL_RE.fullmatch(entity_code):
                    continue
                values = table.get(key) or []
                metrics = {
                    str(label): _to_number(values[index]) if index < len(values) else None
                    for index, label in enumerate(headers)
                }
                entity_name = str(values[0] or entity_code) if values else entity_code
                records.append(
                    {
                        "entity_code": entity_code,
                        "entity_name": entity_name,
                        "date": row_date,
                        "metrics": metrics,
                        "title": str(block.get("title") or ""),
                    }
                )
            continue
        keys = _ordered_keys(block, table)
        tags = block.get("entityTagDTOList") or []
        if not isinstance(tags, list):
            tags = []
        entity_codes = block.get("entityCodes") or []
        if not isinstance(entity_codes, list):
            entity_codes = []
        max_rows = max([len(headers)] + [len(table.get(key, [])) if isinstance(table.get(key), list) else 1 for key in keys])
        if max_rows == 0:
            continue
        for index in range(max_rows):
            metrics: dict[str, Any] = {}
            for key in keys:
                values = table.get(key)
                if isinstance(values, list):
                    value = values[index] if index < len(values) else None
                else:
                    value = values if index == 0 else None
                label = str(name_map.get(key) or key)
                metrics[label] = _to_number(value)
            header = headers[index] if index < len(headers) else None
            row_is_entity = len(tags) == max_rows and max_rows > 1
            tag = tags[index] if row_is_entity and index < len(tags) and isinstance(tags[index], dict) else {}
            if row_is_entity:
                entity_code = str(entity_codes[index]) if index < len(entity_codes) else ""
                if not entity_code:
                    entity_code = f"{tag.get('secuCode') or ''}{tag.get('marketChar') or ''}"
                entity_name = str(tag.get("shortName") or tag.get("fullName") or tag.get("matchWord") or header or "")
                row_date = _date_text(block.get("entityName"))
            else:
                entity_code = str(block.get("code") or "")
                entity_name = str(block.get("entityName") or tag.get("shortName") or tag.get("fullName") or "")
                row_date = _date_text(header) or _date_text(block.get("entityName"))
            record = {
                "entity_code": entity_code,
                "entity_name": entity_name,
                "date": row_date,
                "metrics": metrics,
                "title": str(block.get("title") or ""),
            }
            records.append(record)
    return records, warnings


def _latest_date(records: list[dict[str, Any]]) -> str | None:
    dates = sorted({_date_text(record.get("date")) for record in records if _date_text(record.get("date"))})
    return dates[-1] if dates else None


def _consolidate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge provider blocks that describe the same entity and trade date."""
    merged: dict[tuple[str, str | None], dict[str, Any]] = {}
    for record in records:
        key = (str(record.get("entity_code") or record.get("entity_name") or ""), _date_text(record.get("date")))
        if key not in merged:
            merged[key] = dict(record)
            merged[key]["metrics"] = dict(record.get("metrics") or {})
            continue
        target = merged[key]
        if record.get("entity_name"):
            target["entity_name"] = record["entity_name"]
        if record.get("title"):
            target["title"] = record["title"]
        for label, value in (record.get("metrics") or {}).items():
            if value is not None or label not in target["metrics"]:
                target["metrics"][label] = value
    return list(merged.values())


MARKET_INDEX_TERMS = ("上证", "沪深300", "创业板", "科创50")
MARKET_BREADTH_TERMS = ("成交额", "上涨家数", "下跌家数", "涨停家数", "跌停家数")


def _market_missing(records: list[dict[str, Any]]) -> list[str]:
    """Return required close/breadth fields absent from one trade-date slice."""
    missing: list[str] = []
    for term in MARKET_INDEX_TERMS:
        matching = [record for record in records if term in str(record.get("entity_name") or "")]
        if not matching:
            missing.append(term)
            continue
        if not any(any("收盘" in str(label) and value is not None for label, value in (record.get("metrics") or {}).items()) for record in matching):
            missing.append(f"{term}收盘")

    labels = {
        str(label)
        for record in records
        for label, value in (record.get("metrics") or {}).items()
        if value is not None
    }
    for term in MARKET_BREADTH_TERMS:
        if not any(term in label for label in labels):
            missing.append(term)
    return missing


def _select_complete_market_date(
    records: list[dict[str, Any]], requested_date: str | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select one date only; prefer the latest complete close instead of mixing dates."""
    dates = sorted(
        {_date_text(record.get("date")) for record in records if _date_text(record.get("date"))},
        reverse=True,
    )
    if requested_date and requested_date != "latest":
        dates = [requested_date]
    if not dates:
        return records, ["交易日期"]

    fallback: tuple[list[dict[str, Any]], list[str]] | None = None
    for trade_date in dates:
        dated_records = [record for record in records if _date_text(record.get("date")) == trade_date]
        missing = _market_missing(dated_records)
        if fallback is None:
            fallback = (dated_records, missing)
        if not missing:
            return dated_records, []
    return fallback or ([], ["交易日期"])


def _result(kind: str, source: str, query: str, fetched_at: str, records: list[dict[str, Any]], warnings: list[str], missing: list[str] | None = None) -> dict[str, Any]:
    missing = missing or []
    if not records:
        completeness = "severe_missing"
    elif missing or warnings:
        completeness = "partial"
    else:
        completeness = "complete"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "source": source,
        "query": query,
        "as_of_date": _latest_date(records),
        "fetched_at": fetched_at,
        "completeness": completeness,
        "records": records,
        "missing": missing,
        "warnings": warnings,
    }


def get_market_data(review_date: str | None = None) -> dict[str, Any]:
    date_phrase = "最新完整交易日" if not review_date or review_date == "latest" else review_date
    query = (
        f"查询{date_phrase}上证指数、沪深300、创业板指、科创50的收盘点位和涨跌幅，"
        "以及全部A股成交额、上涨家数、下跌家数、涨停家数、跌停家数"
    )
    response = request_mx("data", query)
    records, warnings = _normalize_blocks(response)
    records = _consolidate_records(records)
    records, missing = _select_complete_market_date(records, review_date)
    return _result("market_snapshot", "mx-data", query, response["fetched_at"], records, warnings, missing)


def get_theme_candidates(theme: str, review_date: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Fetch a broad preselection universe without using MA/RSI/BIAS filters."""
    theme = theme.strip()
    if not THEME_RE.fullmatch(theme):
        raise BridgeError("INPUT", "theme must be 1-60 printable characters.")
    if limit < 5 or limit > 50:
        raise BridgeError("INPUT", "limit must be between 5 and 50.")
    date_phrase = "最新完整交易日" if not review_date or review_date == "latest" else review_date
    query = f"查询{date_phrase}{theme}概念板块成分股，返回股票代码和名称"
    response = request_mx("data", query)
    records, warnings = _normalize_blocks(response)
    records = _consolidate_records(records)
    components = [record for record in records if SYMBOL_RE.fullmatch(str(record.get("entity_code") or ""))]

    def ranked(metric_aliases: tuple[str, ...]) -> list[dict[str, Any]]:
        def numeric_value(record: dict[str, Any]) -> float:
            value = _metric(record.get("metrics") or {}, metric_aliases)
            return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else float("-inf")

        return sorted(
            components,
            key=numeric_value,
            reverse=True,
        )

    selected: list[dict[str, Any]] = []
    selected_codes: set[str] = set()
    bucket_size = max(3, limit // 4)
    buckets = (
        (components[:bucket_size], "provider_anchor"),
        (ranked(("权重",))[:bucket_size], "index_weight"),
        (ranked(("成交额", "amount"))[:bucket_size], "liquidity"),
        (ranked(("涨跌幅", "change_rate"))[:bucket_size], "daily_strength"),
    )
    for bucket, tag in buckets:
        for record in bucket:
            code = str(record.get("entity_code") or "")
            if code in selected_codes:
                for existing in selected:
                    if existing.get("entity_code") == code and tag not in existing["coverage_tags"]:
                        existing["coverage_tags"].append(tag)
                continue
            copied = dict(record)
            copied["coverage_tags"] = [tag]
            selected.append(copied)
            selected_codes.add(code)
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break
    for record in components:
        if len(selected) >= limit:
            break
        code = str(record.get("entity_code") or "")
        if code not in selected_codes:
            copied = dict(record)
            copied["coverage_tags"] = ["component_fill"]
            selected.append(copied)
            selected_codes.add(code)

    usable = selected
    if usable and not any(_date_text(record.get("date")) for record in usable):
        warnings.append("Provider did not attach a trade date to component rows; reconcile with the confirmed market review date.")
    if usable:
        warnings.append("Multi-day continuity is not included in the component snapshot; compare price history before final compression.")
    missing = [] if usable else ["候选股票"]
    result = _result("theme_candidates", "mx-data", query, response["fetched_at"], usable, warnings, missing)
    result["theme"] = theme
    result["candidate_limit"] = limit
    return result


def _metric(metrics: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for label, value in metrics.items():
        normalized = label.lower().replace(" ", "")
        if any(alias.lower() in normalized for alias in aliases):
            return value
    return None


def get_price_history(symbol: str, bars: int = 120, adjustment: str = "qfq") -> dict[str, Any]:
    symbol = symbol.upper().strip()
    if not SYMBOL_RE.fullmatch(symbol):
        raise BridgeError("INPUT", "Symbol must be a six-digit A-share code with optional .SH/.SZ/.BJ suffix.")
    if bars < 60 or bars > 500:
        raise BridgeError("INPUT", "bars must be between 60 and 500.")
    if adjustment not in {"qfq", "none", "unknown"}:
        raise BridgeError("INPUT", "adjustment must be qfq, none, or unknown.")
    adjustment_text = {"qfq": "前复权", "none": "不复权", "unknown": ""}[adjustment]
    query = f"查询{symbol}最近{bars}个完整交易日{adjustment_text}的日期、开盘价、最高价、最低价、收盘价、成交量和成交额"
    response = request_mx("data", query)
    generic, warnings = _normalize_blocks(response)
    price_bars: list[dict[str, Any]] = []
    for record in generic:
        metrics = record.get("metrics") or {}
        date = record.get("date")
        close = _metric(metrics, ("收盘", "close", "最新价"))
        if not date or close is None:
            continue
        price_bars.append(
            {
                "symbol": symbol,
                "date": date,
                "open": _metric(metrics, ("开盘", "open")),
                "high": _metric(metrics, ("最高", "high")),
                "low": _metric(metrics, ("最低", "low")),
                "close": close,
                "volume": _metric(metrics, ("成交量", "volume", "vol")),
                "amount": _metric(metrics, ("成交额", "amount")),
                "adjustment_type": adjustment,
            }
        )
    price_bars.sort(key=lambda row: row["date"])
    if len(price_bars) < 60:
        warnings.append(f"Only {len(price_bars)} usable price bars were returned; at least 60 are required.")
    result = _result("price_history", "mx-data", query, response["fetched_at"], price_bars, warnings)
    result["as_of_date"] = price_bars[-1]["date"] if price_bars else None
    result["completeness"] = "complete" if len(price_bars) >= 60 and not warnings else ("partial" if price_bars else "severe_missing")
    return result


def search_market_info(query: str, limit: int = 20) -> dict[str, Any]:
    if limit < 1 or limit > 50:
        raise BridgeError("INPUT", "limit must be between 1 and 50.")
    response = request_mx("search", query)
    items = _find_first(response, "llmSearchResponse")
    if isinstance(items, dict):
        items = items.get("data") or []
    if not isinstance(items, list):
        items = []
    records = [item for item in items[:limit] if isinstance(item, dict)]
    warnings = [] if records else ["MX search returned no structured news items."]
    return _result("market_search", "mx-search", query, response["fetched_at"], records, warnings)


def _write_or_print(payload: dict[str, Any], output: str | None) -> None:
    if output:
        target = write_json(output, payload)
        print(json.dumps({"ok": True, "output": str(target), "kind": payload.get("kind")}, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    market = sub.add_parser("market")
    market.add_argument("--date", default="latest")
    market.add_argument("--output")

    candidates = sub.add_parser("candidates")
    candidates.add_argument("--theme", required=True)
    candidates.add_argument("--date", default="latest")
    candidates.add_argument("--limit", type=int, default=20)
    candidates.add_argument("--output")

    history = sub.add_parser("history")
    history.add_argument("--symbol", required=True)
    history.add_argument("--bars", type=int, default=120)
    history.add_argument("--adjustment", choices=("qfq", "none", "unknown"), default="qfq")
    history.add_argument("--output")

    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command in {"market", "candidates"}:
            if args.date != "latest" and not DATE_RE.fullmatch(args.date):
                raise BridgeError("INPUT", "date must be latest or YYYY-MM-DD.")
        if args.command == "market":
            payload = get_market_data(args.date)
        elif args.command == "candidates":
            payload = get_theme_candidates(args.theme, args.date, args.limit)
        elif args.command == "history":
            payload = get_price_history(args.symbol, args.bars, args.adjustment)
        else:
            payload = search_market_info(args.query, args.limit)
    except BridgeError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code, "message": str(exc), "retryable": exc.retryable}}, ensure_ascii=False, indent=2))
        return 2
    _write_or_print(payload, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
