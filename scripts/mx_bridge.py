#!/usr/bin/env python3
"""Minimal standard-library bridge for Eastmoney MX data and news APIs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENDPOINTS = {
    "data": ("https://mkapi2.dfcfs.com/finskillshub/api/claw/query", "toolQuery"),
    "search": ("https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search", "query"),
}
SCRIPT_INTERFACE = "cli"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _error_payload(error: BridgeError) -> dict[str, Any]:
    return {
        "ok": False,
        "fetched_at": _now(),
        "error": {
            "code": error.code,
            "message": str(error),
            "retryable": error.retryable,
        },
    }


def request_mx(mode: str, query: str, timeout: float = 30.0) -> dict[str, Any]:
    """Call a fixed MX endpoint and return its decoded JSON response."""
    if mode not in ENDPOINTS:
        raise BridgeError("INPUT", f"Unsupported mode: {mode}")
    query = query.strip()
    if not query:
        raise BridgeError("INPUT", "Query must not be empty.")

    api_key = os.environ.get("MX_APIKEY")
    if not api_key:
        raise BridgeError("AUTH", "MX_APIKEY is not configured.")

    url, query_field = ENDPOINTS[mode]
    body = json.dumps({query_field: query}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "apikey": api_key,
            "User-Agent": "a-stock-trading-review/0.1",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise BridgeError("AUTH", f"MX API rejected the request (HTTP {exc.code}).") from exc
        if exc.code == 429:
            raise BridgeError("RATE_LIMIT", "MX API rate limit reached.", True) from exc
        raise BridgeError("NETWORK", f"MX API returned HTTP {exc.code}.", exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BridgeError("NETWORK", f"MX API request failed: {exc.reason if hasattr(exc, 'reason') else exc}", True) from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise BridgeError("PARSE", "MX API response exceeded the 20 MiB safety limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("PARSE", "MX API returned invalid UTF-8 JSON.") from exc

    if not isinstance(payload, dict):
        raise BridgeError("PARSE", "MX API response root is not an object.")
    if payload.get("success") is False or payload.get("code") not in (None, 0):
        message = str(payload.get("message") or "MX API reported a request failure.")
        code = "RATE_LIMIT" if str(payload.get("code")) == "113" else "EMPTY"
        raise BridgeError(code, message, code == "RATE_LIMIT")
    return {
        "ok": True,
        "mode": mode,
        "query": query,
        "fetched_at": _now(),
        "provider": "eastmoney-mx",
        "payload": payload,
    }


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
    parser.add_argument("mode", choices=sorted(ENDPOINTS))
    parser.add_argument("--query", required=True)
    parser.add_argument("--output")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = request_mx(args.mode, args.query, args.timeout)
    except BridgeError as exc:
        result = _error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    if args.output:
        target = write_json(args.output, result)
        print(json.dumps({"ok": True, "output": str(target), "fetched_at": result["fetched_at"]}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
