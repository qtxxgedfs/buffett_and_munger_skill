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
from task_log import timed
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
PERIODIC_RE = re.compile(r"年度报告|年报|半年度报告|半年报|中期报告|中报|第一季度报告|一季度报告|季度报告|第三季度报告|三季度报告")
EVENT_RE = re.compile(r"控制权|控股股东|实际控制人|收购|重大资产|关联交易|利润分配|分红|业绩预告|业绩快报|诉讼|仲裁|停产|安全生产|减值|担保|融资|债券|股权|增持|减持|回购|项目投产|重大投资|重大合同")


def configure_console_utf8() -> None:
    """Keep Chinese diagnostics readable in Windows terminals when supported."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def new_session(extra_headers: dict[str, str] | None = None) -> requests.Session:
    """Create a session with bounded retries for transient official-site failures."""
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    if extra_headers:
        session.headers.update(extra_headers)
    return session


def iso_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_sse(code: str, start: date, end: date) -> list[dict[str, Any]]:
    session = new_session()
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
    session = new_session({"Referer": "https://www.cninfo.com.cn/"})

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


def report_kind(row: dict[str, Any]) -> str:
    """Conservative subject classification; unknown subjects require human review."""
    title = row.get('title', '')
    category = row.get('category') or ''
    if not (PERIODIC_RE.search(title) or re.search(r'半年报|年报|季报', category)):
        return 'event'
    if re.search(r'关于.*披露|关于.*报告|[:：]', title):
        return 'forwarded_or_notice'
    company = row.get('company', '')
    if not company or not title.startswith(company):
        return 'subject_unverified'
    rest = title[len(company):].strip()
    if not re.match(r'(?:\d{4}年|年度|半年度|中期|第一季度|第三季度)', rest):
        return 'subject_unverified'
    return 'issuer_summary' if '摘要' in title else 'issuer_report'


def attach_alternates(rows: list[dict[str, Any]], backups: list[dict[str, Any]]) -> None:
    # Never fuzzy-match a report to its summary or a different subsidiary report.
    normalize = lambda s: re.sub(r'[\s：:]', '', s)
    for row in rows:
        matches = [x for x in backups if x.get('code') == row.get('code')
                   and x.get('disclosure_date') == row.get('disclosure_date')
                   and normalize(x.get('title', '')) == normalize(row.get('title', ''))
                   and x.get('pdf_url')]
        if len({x['pdf_url'] for x in matches}) == 1:
            row['alternate_pdf_url'] = matches[0]['pdf_url']


def download_rows(rows: list[dict[str, Any]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    session = new_session()
    selected = [row for row in rows if report_kind(row) in ('issuer_report', 'issuer_summary') or EVENT_RE.search(row.get('title', ''))]
    selected.sort(key=lambda r: (report_kind(r) == 'issuer_report', r.get('disclosure_date', '')), reverse=True)
    # A URL returning HTML is terminal for this run, even if repeated in metadata.
    failed_urls: dict[str, str] = {}
    for row in selected:
        url = row.get("pdf_url")
        if not url:
            continue
        candidates = [url, row.get("alternate_pdf_url")]
        last_error = "返回内容不是 PDF"
        downloaded = False
        for candidate in dict.fromkeys(x for x in candidates if x):
            if candidate in failed_urls:
                last_error = failed_urls[candidate]
                continue
            try:
                with timed('download_pdf', 'network', url=candidate) as metrics:
                    response = session.get(candidate, timeout=60)
                    metrics['status_code'] = response.status_code
                    retries = getattr(getattr(response, 'raw', None), 'retries', None)
                    metrics['retries'] = len(getattr(retries, 'history', ()))
                    metrics['bytes'] = len(response.content)
                    metrics['valid_pdf'] = response.content.startswith(b'%PDF')
                    response.raise_for_status()
                if not response.content.startswith(b"%PDF"):
                    last_error = "返回内容不是 PDF（HTML/挑战页/空内容），不重复请求此URL"
                    failed_urls[candidate] = last_error
                    row.setdefault('download_attempts', []).append({'url': candidate, 'error': last_error})
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
                failed_urls[candidate] = last_error
                row.setdefault('download_attempts', []).append({'url': candidate, 'error': last_error})
        if not downloaded:
            row["download_status"] = f"下载失败：{last_error}"
            row['next_action'] = '巨潮按代码补查精确标题；仍失败则从发行人官网报告目录定位原文，不猜URL；未完成记资料缺口'
            row['verified'] = False


def render_markdown(code: str, rows: list[dict[str, Any]], start: date, end: date) -> str:
    periodic = [r for r in rows if report_kind(r) in ('issuer_report', 'issuer_summary')]
    periodic.sort(key=lambda r: (r.get('disclosure_date', ''), report_kind(r) == 'issuer_report'), reverse=True)
    other_reports = [r for r in rows if report_kind(r) in ('forwarded_or_notice', 'subject_unverified')]
    events = [r for r in rows if EVENT_RE.search(r.get("title", "")) and r not in periodic and r not in other_reports]
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
    lines += ['', '## 转披露、报告相关公告及主体待核验（不作为母公司最新财报）']
    for row in other_reports:
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
    configure_console_utf8()
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
        sse_error: Exception | None = None
        try:
            rows = parse_sse(code, start, end)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            rows = []
            sse_error = exc

        # 巨潮资讯是上交所公告的官方回退/下载备份。不要猜文件编号，按代码解析并匹配官方附件。
        if not rows or args.download_dir:
            try:
                cninfo_rows = parse_cninfo(code, args.name, start, end)
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                if not rows:
                    raise RuntimeError(f"上交所检索失败（{sse_error or '无结果'}）；巨潮资讯官方回退也失败：{exc}") from exc
                cninfo_rows = []
                print(f"警告：巨潮资讯备用检索失败，保留上交所清单：{exc}", file=sys.stderr)
            if not rows:
                rows = cninfo_rows
            elif args.download_dir:
                attach_alternates(rows, cninfo_rows)
        if sse_error and rows:
            print(f"提示：上交所检索失败，已使用巨潮资讯官方结果：{sse_error}", file=sys.stderr)
    else:
        rows = parse_cninfo(code, args.name, start, end)

    for row in rows:
        row['report_kind'] = report_kind(row)
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
