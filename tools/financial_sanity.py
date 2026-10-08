#!/usr/bin/env python3
"""Reproducible cross-checks for manually verified financial-statement figures.

All monetary inputs are CNY (元), share counts are shares. Missing fields may be null.
  python financial_sanity.py --template inputs.json
  python financial_sanity.py inputs.json --out checks.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TEMPLATE = {
    "company": "",
    "code": "",
    "as_of_date": "",
    "quote_date": "",
    "sources": {
        "latest_report": "",
        "prior_ytd_report": "",
        "annual_report": "",
        "quote": ""
    },
    "market": {
        "price_cny": None,
        "shares_outstanding": None,
        "parent_equity_cny": None,
        "dividend_per_share_cny": None
    },
    "earnings_cash_flow": {
        "fy_parent_net_income_cny": None,
        "current_ytd_parent_net_income_cny": None,
        "prior_ytd_parent_net_income_cny": None,
        "fy_consolidated_net_income_cny": None,
        "fy_operating_cash_flow_cny": None,
        "current_ytd_consolidated_net_income_cny": None,
        "current_ytd_operating_cash_flow_cny": None,
        "current_ytd_capex_cash_cny": None
    },
    "balance_sheet": {
        "cash_and_equivalents_cny": None,
        "short_term_borrowings_cny": None,
        "current_maturities_long_term_debt_cny": None,
        "long_term_borrowings_cny": None,
        "total_assets_cny": None,
        "total_liabilities_cny": None
    },
    "interest": {
        "current_ytd_ebit_cny": None,
        "current_ytd_interest_expense_cny": None
    }
}


def get(obj: dict[str, Any], *path: str) -> float | None:
    value: Any = obj
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    if value is None or value == "":
        return None
    return float(value)


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return a / b


def rmb(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"¥{value / 1e8:,.{digits}f} 亿元"


def pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def multiple(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}x"


def calculate(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    price = get(data, "market", "price_cny")
    shares = get(data, "market", "shares_outstanding")
    market_cap = price * shares if price is not None and shares is not None else None
    fy_parent = get(data, "earnings_cash_flow", "fy_parent_net_income_cny")
    current_ytd_parent = get(data, "earnings_cash_flow", "current_ytd_parent_net_income_cny")
    prior_ytd_parent = get(data, "earnings_cash_flow", "prior_ytd_parent_net_income_cny")
    ttm_parent = None
    if None not in (fy_parent, current_ytd_parent, prior_ytd_parent):
        ttm_parent = fy_parent + current_ytd_parent - prior_ytd_parent

    fy_cfo = get(data, "earnings_cash_flow", "fy_operating_cash_flow_cny")
    fy_net = get(data, "earnings_cash_flow", "fy_consolidated_net_income_cny")
    ytd_cfo = get(data, "earnings_cash_flow", "current_ytd_operating_cash_flow_cny")
    ytd_net = get(data, "earnings_cash_flow", "current_ytd_consolidated_net_income_cny")
    ytd_capex = get(data, "earnings_cash_flow", "current_ytd_capex_cash_cny")
    cash = get(data, "balance_sheet", "cash_and_equivalents_cny")
    debt_parts = [
        get(data, "balance_sheet", "short_term_borrowings_cny"),
        get(data, "balance_sheet", "current_maturities_long_term_debt_cny"),
        get(data, "balance_sheet", "long_term_borrowings_cny"),
    ]
    interest_debt = sum(debt_parts) if all(x is not None for x in debt_parts) else None
    net_debt = interest_debt - cash if interest_debt is not None and cash is not None else None
    total_assets = get(data, "balance_sheet", "total_assets_cny")
    total_liabilities = get(data, "balance_sheet", "total_liabilities_cny")
    ebit = get(data, "interest", "current_ytd_ebit_cny")
    interest_expense = get(data, "interest", "current_ytd_interest_expense_cny")
    dividend = get(data, "market", "dividend_per_share_cny")
    equity = get(data, "market", "parent_equity_cny")

    results = {
        "market_cap_cny": market_cap,
        "ttm_parent_net_income_cny": ttm_parent,
        "ttm_eps_cny": div(ttm_parent, shares),
        "ttm_pe": div(market_cap, ttm_parent),
        "parent_pb": div(market_cap, equity),
        "dividend_yield": div(dividend, price),
        "fy_cash_conversion": div(fy_cfo, fy_net),
        "ytd_cash_conversion": div(ytd_cfo, ytd_net),
        "ytd_capex_minus_cfo_cny": (ytd_cfo - ytd_capex) if ytd_cfo is not None and ytd_capex is not None else None,
        "interest_bearing_debt_cny": interest_debt,
        "net_interest_bearing_debt_cny": net_debt,
        "net_debt_to_parent_equity": div(net_debt, equity),
        "liabilities_to_assets": div(total_liabilities, total_assets),
        "ytd_interest_coverage": div(ebit, interest_expense),
    }
    warnings = [
        "TTM 归母净利润按：最近完整年度 + 本期累计归母净利润 − 上年同期累计归母净利润。请确认报告期间一致、会计口径一致。",
        "现金转化率用合并口径经营现金流 / 合并净利润；不要拿归母净利润与合并现金流混用。",
        "购建长期资产支出通常混有维持性和成长性支出；经营现金流减资本开支只是 FCF 代理值，不等同于所有者收益。",
        "有息债务合计仅加总输入的短借、一年内到期长期债务和长期借款；若有债券、租赁负债等需另行评估。",
        "半年 EBIT / 利息费用的保障倍数是期间口径，不要与全年倍数直接比较；季节性显著时不要简单年化。",
    ]
    return results, warnings


def render(data: dict[str, Any], result: dict[str, Any], warnings: list[str]) -> str:
    eps_text = "—" if result["ttm_eps_cny"] is None else f"¥{result['ttm_eps_cny']:.3f}"
    lines = [
        f"# {data.get('company') or '公司'} 财务交叉校验",
        "",
        f"- 代码：{data.get('code') or '—'}",
        f"- 财报时点：{data.get('as_of_date') or '—'}；行情时点：{data.get('quote_date') or '—'}",
        "- 输入金额单位：人民币元；以下输出金额换算为亿元。",
        "",
        "## 计算结果",
        "",
        "| 指标 | 计算值 |",
        "|---|---:|",
        f"| 市值（股价 × 总股本） | {rmb(result['market_cap_cny'])} |",
        f"| TTM 归母净利润 | {rmb(result['ttm_parent_net_income_cny'])} |",
        f"| TTM EPS | {eps_text} |",
        f"| TTM 市盈率 | {multiple(result['ttm_pe'])} |",
        f"| 市净率（归母权益口径） | {multiple(result['parent_pb'])} |",
        f"| 股息率（输入每股现金分红） | {pct(result['dividend_yield'], 2)} |",
        f"| 年度现金转化率（合并口径） | {pct(result['fy_cash_conversion'])} |",
        f"| 本期累计现金转化率（合并口径） | {pct(result['ytd_cash_conversion'])} |",
        f"| 本期累计 CFO 减长期资产购建现金 | {rmb(result['ytd_capex_minus_cfo_cny'])} |",
        f"| 输入范围内有息债务 | {rmb(result['interest_bearing_debt_cny'])} |",
        f"| 净有息债务（有息债务减现金） | {rmb(result['net_interest_bearing_debt_cny'])} |",
        f"| 净债务 / 归母权益 | {multiple(result['net_debt_to_parent_equity'])} |",
        f"| 资产负债率 | {pct(result['liabilities_to_assets'])} |",
        f"| 本期累计 EBIT / 利息费用 | {multiple(result['ytd_interest_coverage'])} |",
        "",
        "## 口径提醒",
        "",
    ]
    lines.extend(f"- {item}" for item in warnings)
    sources = data.get("sources") or {}
    filled = [f"- {key}: {value}" for key, value in sources.items() if value]
    if filled:
        lines += ["", "## 来源", "", *filled]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验财报录入数据并计算常用估值/现金流/债务指标")
    parser.add_argument("input", nargs="?", type=Path, help="按模板录入的 JSON 文件")
    parser.add_argument("--template", type=Path, help="写出空白输入模板并退出")
    parser.add_argument("--out", type=Path, help="Markdown 结果输出路径；默认打印到终端")
    args = parser.parse_args()
    if args.template:
        args.template.parent.mkdir(parents=True, exist_ok=True)
        args.template.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"模板已写入：{args.template}")
        return 0
    if not args.input:
        parser.error("请提供 input.json，或使用 --template 生成模板")
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"无法读取 JSON：{exc}")
    result, warnings = calculate(data)
    markdown = render(data, result, warnings)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"校验结果已写入：{args.out}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
