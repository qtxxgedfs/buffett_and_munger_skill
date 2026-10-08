#!/usr/bin/env python3
"""Find issuer filings from official SSE/CNINFO disclosure endpoints.

Examples:
  python official_filings.py 601918 --from 2026-01-01 --to 2026-10-08
  python official_filings.py 000001 --name 平安银行 --from 2025-01-01 --to 2026-10-08
"""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

SSE_API = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
SSE_STATIC = "https://static.sse.com.cn"
CNINFO_API = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC = "https://static.cninfo.com.cn/"
CNINFO_SECURITY_API = "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo"
CNINFO_IRM = "https://irm.cninfo.com.cn"
SSE_INTERACTION = "https://sns.sseinfo.com/company.do?stockcode={code}"
SZSE_INTERACTION = "https://irm.cninfo.com.cn/ircs/company/companyDetail?stockcode={code}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://www.sse.com.cn/",
}
PERIODIC_RE = re.compile(r"年度报告|年报|半年度报告|半年报|第一季度报告|一季度报告|季度报告|第三季度报告|三季度报告")
EVENT_RE = re.compile(r"控制权|控股股东|实际控制人|收购|重大资产|关联交易|利润分配|分红|业绩预告|业绩快报|诉讼|仲裁|停产|安全生产|减值|担保|融资|债券|股权|增持|减持|回购|项目投产|重大投资|重大合同")


def iso_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_sse(code: str, start: date, end: date) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    rows: list[dict[str, Any]] = []
    for page in range(1, 31):
        params = {
            "isPagination": "true",
            "productId": code,
            "securityType": "0101,120100",
            "reportType2": "DQGG",
            "reportType": "YEARLY",
            "beginDate": start.isoformat(),
            "endDate": end.isoformat(),
            "pageHelp.pageSize": "100",
            "pageHelp.pageNo": str(page),
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "30",
            "_": str(int(time.time() * 1000)),
        }
        response = session.get(SSE_API, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        batch = (payload.get("pageHelp") or {}).get("data") or []
        if not batch:
            break
        for item in batch:
            path = item.get("URL") or ""
            rows.append({
                "code": code,
                "company": item.get("SECURITY_NAME", ""),
                "title": item.get("TITLE", ""),
                "disclosure_date": item.get("SSEDATE", ""),
                "posted_at": item.get("ADDDATE", ""),
                "category": item.get("BULLETIN_TYPE", ""),
                "pdf_url": urljoin(SSE_STATIC, path) if path else "",
                "source": "SSE",
            })
        if len(batch) < 100:
            break
    return unique_rows(rows)


def cninfo_datetime(ms: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


def resolve_cninfo_security(code: str, session: requests.Session) -> tuple[str, str]:
    """Resolve the current issuer name and organization ID from CNINFO by ticker."""
    response = session.post(
        CNINFO_SECURITY_API,
        data={"keyWord": code},
        headers={"Referer": f"{CNINFO_IRM}/", "X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    matches = [
        item for item in (payload.get("data") or [])
        if str(item.get("stockCode", "")).zfill(6) == code.zfill(6)
    ]
    if not matches:
        raise RuntimeError(f"CNINFO 未能按证券代码 {code} 解析公司信息")
    item = matches[0]
    return str(item.get("shortName") or ""), str(item.get("secid") or "")


def parse_cninfo(code: str, name: str | None, start: date, end: date) -> list[dict[str, Any]]:
    plate = "sz" if code.startswith(("0", "3")) else "sh"
    column = "szse" if plate == "sz" else "sse"
    session = requests.Session()
    session.headers.update({**HEADERS, "Referer": "https://www.cninfo.com.cn/"})

    # Code is the stable key. Resolve the current short name and CNINFO org ID each run;
    # a user-provided name is only an extra search alias (useful for renamed issuers).
    current_name, org_id = "", ""
    try:
        current_name, org_id = resolve_cninfo_security(code, session)
    except (requests.RequestException, ValueError, RuntimeError):
        if not name:
            raise
    search_names = list(dict.fromkeys(x for x in (current_name, name) if x))
    if not search_names:
        raise RuntimeError(f"无法解析 {code} 的公司简称；可临时通过 --name 提供检索词")

    rows: list[dict[str, Any]] = []
    for search_name in search_names:
        for page in range(1, 31):
            form = {
                "pageNum": str(page),
                "pageSize": "100",
                "column": column,
                "tabName": "fulltext",
                "plate": plate,
                "stock": f"{code},{org_id}" if org_id else "",
                "searchkey": search_name,
                "secid": "",
                "category": "",
                "trade": "",
                "seDate": f"{start.isoformat()}~{end.isoformat()}",
                "sortName": "",
                "sortType": "desc",
                "isHLtitle": "false",
            }
            response = session.post(CNINFO_API, data=form, timeout=30)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("announcements") or []
            if not batch:
                break
            for item in batch:
                if str(item.get("secCode", "")).zfill(6) != code.zfill(6):
                    continue
                adjunct = item.get("adjunctUrl") or ""
                rows.append({
                    "code": code,
                    "company": re.sub(r"</?em>", "", item.get("secName", search_name)),
                    "title": re.sub(r"</?em>", "", item.get("announcementTitle", "")),
                    "disclosure_date": cninfo_datetime(item.get("announcementTime"))[:10],
                    "posted_at": cninfo_datetime(item.get("announcementTime")),
                    "category": item.get("announcementTypeName", ""),
                    "pdf_url": urljoin(CNINFO_STATIC, adjunct) if adjunct else "",
                    "source": "CNINFO",
                })
            if len(batch) < 100:
                break
    return unique_rows(rows)


def unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:
        key = (row.get("title", ""), row.get("pdf_url", ""))
        if key not in seen:
            seen.add(key)
            result.append(row)
    return sorted(result, key=lambda x: (x.get("disclosure_date", ""), x.get("posted_at", "")), reverse=True)


def safe_filename(text: str) -> str:
    text = re.sub(r"[<>:\\|?*\"/]", "_", text).strip(" ._")
    return (text[:100] or "announcement") + ".pdf"


def download_rows(rows: list[dict[str, Any]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    selected = [row for row in rows if PERIODIC_RE.search(row.get("title", "")) or EVENT_RE.search(row.get("title", ""))]
    for row in selected:
        url = row.get("pdf_url")
        if not url:
            continue
        candidates = [url, row.get("alternate_pdf_url")]
        last_error = "返回内容不是 PDF"
        downloaded = False
        for candidate in dict.fromkeys(x for x in candidates if x):
            try:
                response = session.get(candidate, timeout=60)
                response.raise_for_status()
                if not response.content.startswith(b"%PDF"):
                    last_error = "返回内容不是 PDF"
                    continue
                filename = safe_filename(f"{row['disclosure_date']}_{row['title']}")
                target = directory / filename
                target.write_bytes(response.content)
                row["local_pdf"] = str(target)
                row["download_url"] = candidate
                row["download_status"] = "已下载"
                downloaded = True
                break
            except requests.RequestException as exc:
                last_error = str(exc)
        if not downloaded:
            row["download_status"] = f"下载失败：{last_error}（保留官方链接，可用浏览器打开）"


def render_markdown(code: str, rows: list[dict[str, Any]], start: date, end: date) -> str:
    periodic = [r for r in rows if PERIODIC_RE.search(r.get("title", ""))]
    events = [r for r in rows if EVENT_RE.search(r.get("title", "")) and r not in periodic]
    lines = [
        f"# {code} 官方公告检索清单",
        "",
        f"- 检索区间：{start.isoformat()} 至 {end.isoformat()}",
        "- 来源：上交所或巨潮资讯官方披露接口；本清单不包含研报。证券代码是主键，公司简称仅作动态检索词。",
        "",
        "## 定期报告",
    ]
    if not periodic:
        lines.append("- 未检索到匹配的定期报告标题；请核对代码、公司名称和日期区间。")
    for row in periodic:
        lines.append(f"- {row['disclosure_date']}｜{row['title']}｜[官方 PDF]({row['pdf_url']})")
    lines += ["", "## 期间内可能重要的公司公告"]
    if not events:
        lines.append("- 未检索到匹配关键词的公告；请仍检查官方公告列表。")
    for row in events[:80]:
        lines.append(f"- {row['disclosure_date']}｜{row['title']}｜[官方 PDF]({row['pdf_url']})")
    interaction_url = SSE_INTERACTION.format(code=code) if code.startswith(("6", "9")) else SZSE_INTERACTION.format(code=code)
    interaction_label = "上证 e 互动" if code.startswith(("6", "9")) else "深交所互动易"
    lines += [
        "",
        "## 公司投资者互动平台（补充材料）",
        f"- [{interaction_label}]({interaction_url})",
        "- 互动问答仅用于了解投资者关注点和公司交流口径，不代替法定信息披露；涉及经营、财务或重大事项的事实应回到定期报告、公告及指定披露渠道核实。",
        "",
        "> 关键词筛选仅用于缩小人工检查范围，不代表完整性或重要性判断。引用前请打开原始公告核对正文及日期。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="按证券代码从上交所/巨潮资讯检索定期报告和近期重要公告")
    parser.add_argument("code", help="证券代码（稳定主键），例如 601918 或 000001")
    parser.add_argument("--name", help="可选历史简称/别名，用作额外检索词；通常无需提供")
    parser.add_argument("--from", dest="start", default=f"{date.today().year - 1}-01-01", help="起始日期 YYYY-MM-DD（默认上一年 1 月 1 日）")
    parser.add_argument("--to", dest="end", default=date.today().isoformat(), help="截止日期 YYYY-MM-DD")
    parser.add_argument("--out", type=Path, help="Markdown 清单输出路径；默认打印到终端")
    parser.add_argument("--json", dest="json_out", type=Path, help="可选 JSON 原始元数据输出路径")
    parser.add_argument("--download-dir", type=Path, help="可选：下载匹配报告和公告 PDF")
    args = parser.parse_args()
    raw_code = args.code.strip()
    if not raw_code.isdigit() or len(raw_code) > 6:
        parser.error("代码应为不超过 6 位的数字")
    code = raw_code.zfill(6)
    if not code.startswith(("0", "3", "6", "9")):
        parser.error("当前官方检索器支持上交所 6/9 开头、深交所 0/3 开头的代码；其他市场请从对应交易所官网检索")
    start, end = iso_date(args.start), iso_date(args.end)
    if start > end:
        parser.error("--from 不能晚于 --to")

    if code.startswith(("6", "9")):
        rows = parse_sse(code, start, end)
        # 巨潮资讯作为上交所公告的官方回退/下载备份；仅在用户给出名称时按代码精确匹配。
        if not rows or args.download_dir:
            cninfo_rows = parse_cninfo(code, args.name, start, end)
            if not rows:
                rows = cninfo_rows
            elif args.download_dir:
                for row in rows:
                    same_day = [x for x in cninfo_rows if x["disclosure_date"] == row["disclosure_date"] and x.get("pdf_url")]
                    match = max(same_day, key=lambda x: SequenceMatcher(None, row["title"], x["title"]).ratio(), default=None)
                    if match and SequenceMatcher(None, row["title"], match["title"]).ratio() >= 0.85:
                        row["alternate_pdf_url"] = match["pdf_url"]
    else:
        rows = parse_cninfo(code, args.name, start, end)

    if args.download_dir:
        download_rows(rows, args.download_dir)
    markdown = render_markdown(code, rows, start, end)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
