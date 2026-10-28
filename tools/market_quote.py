#!/usr/bin/env python3
"""Fetch a timestamped A-share quote from Tencent and Sina for cross-checking.

Prices are parsed from human-readable quote fields in CNY, not guessed from
scaled integer fields. One provider may fail; both raw provider outcomes are
preserved in the JSON output.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


TENCENT_URL = "https://qt.gtimg.cn/q={symbol}"
SINA_URL = "https://hq.sinajs.cn/list={symbol}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://gu.qq.com/",
}


def configure_console_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def exchange_symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "2", "3")):
        return f"sz{code}"
    raise ValueError(f"暂不支持的A股证券代码：{code}")


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session


def parse_tencent(code: str, body: str) -> dict[str, Any]:
    match = re.search(r'v_(?:sh|sz)(\d{6})="([^"]*)"', body)
    if not match or match.group(1) != code:
        raise ValueError("腾讯行情返回中未找到匹配证券代码")
    fields = match.group(2).split("~")
    if len(fields) < 4 or not fields[3]:
        raise ValueError("腾讯行情返回字段不完整")
    time_match = re.search(r"~(\d{14})~", match.group(2))
    if not time_match:
        raise ValueError("腾讯行情返回未包含可识别的时间戳")
    stamp = datetime.strptime(time_match.group(1), "%Y%m%d%H%M%S")
    price = float(fields[3])
    if price <= 0:
        raise ValueError(f"腾讯行情价格无效：{fields[3]}")
    return {
        "provider": "Tencent",
        "code": code,
        "name": fields[1],
        "price_cny": price,
        "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "raw_timestamp": time_match.group(1),
        "timestamp_timezone": "Asia/Shanghai",
    }


def parse_sina(code: str, body: str) -> dict[str, Any]:
    match = re.search(r'hq_str_(?:sh|sz)(\d{6})="([^"]*)"', body)
    if not match or match.group(1) != code:
        raise ValueError("新浪行情返回中未找到匹配证券代码")
    fields = match.group(2).split(",")
    if len(fields) < 32 or not fields[3]:
        raise ValueError("新浪行情返回字段不完整")
    stamp_text = f"{fields[30]} {fields[31]}"
    stamp = datetime.strptime(stamp_text, "%Y-%m-%d %H:%M:%S")
    price = float(fields[3])
    if price <= 0:
        raise ValueError(f"新浪行情价格无效：{fields[3]}")
    return {
        "provider": "Sina",
        "code": code,
        "name": fields[0],
        "price_cny": price,
        "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "raw_timestamp": stamp_text,
        "timestamp_timezone": "Asia/Shanghai",
    }


def fetch_one(session: requests.Session, provider: str, code: str, symbol: str) -> dict[str, Any]:
    if provider == "Tencent":
        url = TENCENT_URL.format(symbol=symbol)
        parser = parse_tencent
    else:
        url = SINA_URL.format(symbol=symbol)
        parser = parse_sina
    provider_headers = {"Referer": "https://finance.sina.com.cn/"} if provider == "Sina" else {"Referer": "https://gu.qq.com/"}
    response = session.get(url, headers=provider_headers, timeout=20)
    response.raise_for_status()
    body = response.content.decode("gb18030", errors="replace")
    quote = parser(code, body)
    quote["source_url"] = url
    return quote


def main() -> int:
    configure_console_utf8()
    parser = argparse.ArgumentParser(description="获取带时间戳的腾讯/新浪A股行情快照并交叉核验")
    parser.add_argument("code", help="六位A股代码，例如 600519")
    parser.add_argument("--out", type=Path, help="可选：将 JSON 结果保存到指定路径")
    args = parser.parse_args()
    code = args.code.strip()
    if not re.fullmatch(r"\d{6}", code):
        parser.error("证券代码必须是六位数字")
    try:
        symbol = exchange_symbol(code)
    except ValueError as exc:
        parser.error(str(exc))

    session = make_session()
    providers: list[dict[str, Any]] = []
    for provider in ("Tencent", "Sina"):
        try:
            providers.append(fetch_one(session, provider, code, symbol))
        except (requests.RequestException, ValueError, UnicodeError) as exc:
            providers.append({"provider": provider, "code": code, "error": str(exc)})

    quotes = [item for item in providers if "price_cny" in item]
    agreement: dict[str, Any] = {
        "checked": len(quotes) == 2,
        "timestamp_difference_seconds": None,
        "difference_cny": None,
        "relative_difference_pct": None,
        "close_within_0_1pct_and_120s": None,
    }
    if len(quotes) == 2:
        difference = abs(quotes[0]["price_cny"] - quotes[1]["price_cny"])
        time_a = datetime.strptime(quotes[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
        time_b = datetime.strptime(quotes[1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        seconds = abs((time_a - time_b).total_seconds())
        average_price = (quotes[0]["price_cny"] + quotes[1]["price_cny"]) / 2
        relative_pct = difference / average_price * 100 if average_price else None
        agreement["timestamp_difference_seconds"] = int(seconds)
        agreement["difference_cny"] = round(difference, 4)
        agreement["relative_difference_pct"] = round(relative_pct, 4) if relative_pct is not None else None
        agreement["close_within_0_1pct_and_120s"] = seconds <= 120 and relative_pct is not None and relative_pct <= 0.1

    result = {
        "code": code,
        "currency": "CNY",
        "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "quotes": providers,
        "cross_check": agreement,
        "note": "行情为第三方价格输入，不替代交易所信息披露；不同来源时间戳可能略有差异。",
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if quotes else 1


if __name__ == "__main__":
    raise SystemExit(main())
