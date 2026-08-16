#!/usr/bin/env python3
"""Calculate MA5/10/20/60, Wilder RSI9, and BIAS20 from daily bars."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


MIN_BARS = 60
SCRIPT_INTERFACE = "cli"


class IndicatorError(ValueError):
    pass


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).replace(",", "").strip()
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
        result = float(text) * multiplier
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)[:10]
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def _metric_close(row: dict[str, Any]) -> Any:
    if "close" in row:
        return row.get("close")
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return None
    for label, value in metrics.items():
        normalized = str(label).lower().replace(" ", "")
        if any(alias in normalized for alias in ("收盘", "close", "最新价")):
            return value
    return None


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("bars") or payload.get("records") or payload.get("data") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def normalize_bars(payload: Any) -> tuple[list[dict[str, Any]], list[str], str]:
    rows = _extract_rows(payload)
    if not rows:
        raise IndicatorError("Input does not contain a bar array.")

    warnings: list[str] = []
    by_date: dict[str, dict[str, Any]] = {}
    adjustment_types: set[str] = set()
    invalid = 0
    for row in rows:
        date = _date(row.get("date") or row.get("datetime") or row.get("trade_date"))
        close = _number(_metric_close(row))
        if not date or close is None or close <= 0:
            invalid += 1
            continue
        adjustment = str(row.get("adjustment_type") or "unknown").lower()
        if adjustment not in {"qfq", "none", "unknown"}:
            adjustment = "unknown"
        adjustment_types.add(adjustment)
        if date in by_date:
            warnings.append(f"Duplicate date {date}; kept the last valid row.")
        by_date[date] = {"date": date, "close": close, "adjustment_type": adjustment}

    if invalid:
        warnings.append(f"Skipped {invalid} rows with invalid date or close.")
    bars = [by_date[key] for key in sorted(by_date)]
    if len(bars) < MIN_BARS:
        raise IndicatorError(f"At least {MIN_BARS} valid daily bars are required; got {len(bars)}.")

    if len(adjustment_types) == 1:
        adjustment_type = next(iter(adjustment_types))
    else:
        adjustment_type = "mixed"
        warnings.append("Input contains mixed adjustment types.")
    if adjustment_type in {"none", "unknown", "mixed"}:
        warnings.append("Price adjustment is not confirmed as qfq; ex-right events may distort indicators.")
    return bars, warnings, adjustment_type


def sma(values: list[float], period: int) -> float:
    if len(values) < period:
        raise IndicatorError(f"MA{period} requires {period} values.")
    return sum(values[-period:]) / period


def wilder_rsi(values: list[float], period: int = 9) -> float:
    if len(values) < period + 1:
        raise IndicatorError(f"RSI{period} requires at least {period + 1} values.")
    changes = [current - previous for previous, current in zip(values, values[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def calculate(payload: Any) -> dict[str, Any]:
    bars, warnings, adjustment_type = normalize_bars(payload)
    closes = [row["close"] for row in bars]
    ma20 = sma(closes, 20)
    latest = closes[-1]
    result = {
        "schema_version": "1.0",
        "as_of_date": bars[-1]["date"],
        "adjustment_type": adjustment_type,
        "bar_count": len(bars),
        "data_start": bars[0]["date"],
        "data_end": bars[-1]["date"],
        "close": latest,
        "ma5": sma(closes, 5),
        "ma10": sma(closes, 10),
        "ma20": ma20,
        "ma60": sma(closes, 60),
        "rsi9": wilder_rsi(closes, 9),
        "bias20": (latest - ma20) / ma20 * 100.0,
        "warnings": warnings,
    }
    for key in ("close", "ma5", "ma10", "ma20", "ma60", "rsi9", "bias20"):
        result[key] = round(float(result[key]), 6)
    return result


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=target.parent, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, target)
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        with Path(args.input).expanduser().open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        result = calculate(payload)
    except (OSError, json.JSONDecodeError, IndicatorError) as exc:
        print(json.dumps({"ok": False, "error": {"code": "INPUT", "message": str(exc), "retryable": False}}, ensure_ascii=False, indent=2))
        return 2

    if args.output:
        target = write_json(args.output, result)
        print(json.dumps({"ok": True, "output": str(target), "as_of_date": result["as_of_date"]}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
