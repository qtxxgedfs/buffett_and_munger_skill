# 投研资料处理工具

这些脚本为具体公司分析准备官方资料、处理财报 PDF，并复核人工摘录的财务计算。

## 依赖

- Python 3.10+
- 必需：`requests`、`PyMuPDF`；可用 `python -m pip install -r .pi/skills/buffett_and_munger/tools/requirements.txt` 安装。
- PDF 原生版面文本优先使用 Poppler 的 `pdftotext -layout`；没有时回退到 PyMuPDF。
- 可选中文 OCR：`python -m pip install -r .pi/skills/buffett_and_munger/tools/requirements-ocr.txt`
  - 当前工作环境已安装 `rapidocr_onnxruntime`。OCR 输出可能错字或错序，重要数据必须回看 PDF 原页。
  - `pdf_ingest.py --ocr` 优先使用安装了 `chi_sim` 的 Tesseract；否则使用 RapidOCR。

## 1. 官方公告检索

证券代码（含交易所/市场）是稳定主键；简称、ST 标记和其他前缀都可能变化，不要用简称做公司身份标识。脚本会通过巨潮资讯的证券代码检索接口动态解析当前简称和机构 ID，再按代码精确过滤公告；`--name` 是可选的历史简称/别名补充，不是必填项。公告清单仅从上交所或巨潮资讯官方接口生成。

```bash
python .pi/skills/buffett_and_munger/tools/official_filings.py 601918 \
  --out work/601918_filings.md --json work/601918_filings.json \
  --download-dir work/601918_pdfs

python .pi/skills/buffett_and_munger/tools/official_filings.py 000001 \
  --out work/000001_filings.md

# 若公司曾更名，可把历史简称作为额外检索词
python .pi/skills/buffett_and_munger/tools/official_filings.py 000001 \
  --name 历史简称 --out work/000001_filings.md
```

检索清单分为定期报告和按关键词筛出的可能重要公告。关键词只缩小范围，不能代替完整公告审阅。上交所接口无结果或需要下载备份时，脚本会使用巨潮资讯官方接口；若官方站点仍不可用，则保留原始链接并注明失败，不尝试绕过站点访问控制。

清单另附公司投资者互动平台入口：上交所 [上证 e 互动](https://sns.sseinfo.com/)，深交所[互动易](https://irm.cninfo.com.cn/)。这两个平台适合了解投资者关切和公司回应，但互动内容应作为补充材料；关键事实、经营数据和重大事项要回到法定公告/定期报告核实。互动页的前端接口并非稳定公开 API，且平台使用条款/内容授权可能限制自动采集，因此当前只提供来源入口，不做批量抓取。

建议顺序：最新一期定期报告、前一期定期报告、最近一期年报；然后检查最新报告发布日至分析时点的控股权、重大投资/重组、分红、关联交易、安全生产等公司公告。

## 2. 官方接口失败时的网页搜索兜底

若公告接口超时、返回错误或结果不完整，先用可用的 `WebSearch` 搜索官方域名，关键词至少包含证券代码，并可并列现简称、历史简称、公告主题和日期，例如：

- `site:cninfo.com.cn 601918 新集能源 2025 年年度报告`
- `site:sse.com.cn 601918 新集能源 公告`
- `site:公司官网域名 601918 投资者关系`

搜索结果只用于定位页面，不把摘要、转载或搜索排名当作证据。打开结果后确认发行人、证券代码、披露日期，并优先进入交易所、巨潮资讯或发行人官网原文。没有 WebSearch 工具时，直接使用上述互动平台/交易所/巨潮资讯网页检索。记录实际核验的原文 URL；未能确认原文时明确标记“待核验”，不要用搜索摘要补造数据。脚本不自动抓取搜索引擎结果。

## 3. PDF 抽取、渲染与 OCR

```bash
python .pi/skills/buffett_and_munger/tools/pdf_ingest.py work/601918_pdfs/report.pdf \
  --outdir work/report_pages --pages 1-12,27-40 --dpi 220 --ocr
```

工具会生成 `native_text.txt`、选定页 PNG、可选 `ocr_selected_pages.txt` 和处理说明。中文字符提取过少时会警告。优先按目录/报表位置选择关键页，避免无必要地渲染整本年报。OCR 适合定位和抄录辅助，不能直接当权威数据源。

## 4. 财务数据交叉校验

先生成 JSON 模板，把从报告原页确认的数据按人民币元、股数按股录入：

```bash
python .pi/skills/buffett_and_munger/tools/financial_sanity.py \
  --template work/financial_input.json
# 编辑 financial_input.json 后：
python .pi/skills/buffett_and_munger/tools/financial_sanity.py \
  work/financial_input.json --out work/financial_checks.md
```

校验器计算市值、TTM 归母净利润/EPS/PE、现金转化、经营现金流减长期资产购建支出的代理值、有息债务与净债务、资产负债率和利息保障倍数。TTM 需要完整年度、本期累计及上年同期三项同口径数据。缺失字段填 `null`；不要把 OCR 结果未经核对直接录入。计算结果仍需结合报告原文解释。
