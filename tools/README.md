# 投研资料处理工具

这些脚本为具体公司分析准备官方资料、处理财报 PDF，并复核人工摘录的财务计算。

## 依赖

- Python 3.10+
- 必需：`requests`、`PyMuPDF`；可用 `python -m pip install -r .pi/skills/buffett-and-munger/tools/requirements.txt` 安装。
- PDF 原生版面文本优先使用 Poppler 的 `pdftotext -layout`；没有时回退到 PyMuPDF。
- 可选中文 OCR：`python -m pip install -r .pi/skills/buffett-and-munger/tools/requirements-ocr.txt`
  - 当前工作环境已安装 `rapidocr_onnxruntime`。OCR 输出可能错字或错序，重要数据必须回看 PDF 原页。
  - `pdf_ingest.py --ocr` 优先使用安装了 `chi_sim` 的 Tesseract；否则使用 RapidOCR。

## 0. 实时计时与串行执行

使用 `task_log.py`，不再事后手填精确秒数。日志为追加式JSONL，时间戳带时区；命令用单调时钟测耗时，人工阅读/分析跨进程使用墙钟。

```bash
python -X utf8 .pi/skills/buffett-and-munger/tools/task_log.py --log work/work_601318/timing.jsonl start 阅读与分析
# 阅读和分析结束后立即记录：
python -X utf8 .pi/skills/buffett-and-munger/tools/task_log.py --log work/work_601318/timing.jsonl end 阅读与分析

python -X utf8 .pi/skills/buffett-and-munger/tools/task_log.py --log work/work_601318/timing.jsonl run --step 公告检索 -- python -X utf8 .pi/skills/buffett-and-munger/tools/official_filings.py 601318 --out work/work_601318/filings.md --json work/work_601318/filings.json --download-dir work/work_601318/pdfs
```

`run` 串行执行一个命令，并继承 `INVEST_LOG` 给子工具，记录返回码。下载请求记录URL、状态、字节数、PDF校验和可获取的重试历史；PDF工具记录原生抽取耗时，OCR详细页数/耗时追加到PDF处理目录（`--outdir`）的 `ocr_metrics.jsonl`，不是最终报告的 `reports/` 目录。请求耗时包含重试等待，未单独测量的纯网络等待、模型思考时间不能杜撰。汇总Markdown时保留未结束步骤，不重复累加父子耗时。只在开始、关键障碍、完成时发送进度消息。

## 1. 官方公告检索

证券代码（含交易所/市场）是稳定主键；简称、ST 标记和其他前缀都可能变化，不要用简称做公司身份标识。脚本会通过巨潮资讯的证券代码检索接口动态解析当前简称和机构 ID，再按代码精确过滤公告；`--name` 是可选的历史简称/别名补充，不是必填项。公告清单仅从上交所或巨潮资讯官方接口生成。每只股票的中间资料独立放在 `work/work_{证券代码}/`，例如 `work/work_600519/`；中间文件保留，最终上市公司分析报告统一保存到项目根目录下的 `reports/`（不存在则创建），命名为 `{股票名}_{年份}_{最新财报披露月份}_{最新财报披露日}.md`，日期使用本公司最新财报披露日。计时日志及其Markdown汇总仍放在对应 `work/work_{证券代码}/` 中，不混入最终报告目录；已有根目录报告不自动迁移。

```bash
# 推荐使用 UTF-8 模式，并将该股票的资料统一收在独立目录
python -X utf8 .pi/skills/buffett-and-munger/tools/official_filings.py 600519 \
  --out work/work_600519/filings.md \
  --json work/work_600519/filings.json \
  --download-dir work/work_600519/pdfs

# 若公司曾更名，可把历史简称作为额外检索词
python -X utf8 .pi/skills/buffett-and-munger/tools/official_filings.py 000001 \
  --name 历史简称 \
  --out work/work_000001/filings.md \
  --json work/work_000001/filings.json \
  --download-dir work/work_000001/pdfs
```

检索清单区分母公司全文/摘要、子公司转披露及主体待核验报告、按关键词筛出的可能重要公告。支持“中期报告/中报”和“半年度报告/半年报”，转披露不能用作母公司最新报告。备用附件按代码、日期和去空白/冒号后的精确标题匹配；不再用模糊标题把全文误配摘要。不能精确匹配时保留缺口，人工按代码补查。关键词只缩小范围，不能代替完整公告审阅。脚本对短暂网络错误和服务端限流/错误会有限重试；上交所接口报错或无结果时会回退到巨潮资讯官方接口，下载时优先尝试检索所得的备用官方 PDF 链接。不要手工猜测 PDF 文件编号。脚本会检查下载内容是否以 `%PDF` 开头；若官方站点返回 HTML/挑战页，保留链接、注明失败，再尝试另一官方来源，不绕过站点访问控制。同一URL返回HTML/挑战页后，本轮不再重复请求，立即尝试已有巨潮官方备用链接。若精确匹配未得到备用链接，按代码/期间补查巨潮，再从发行人官网报告目录定位；这两步由分析流程执行，脚本不猜官网或PDF编号，`next_action`仅为待办而非已完成回退。成功或失败状态、失败尝试及实际下载地址写入 JSON。

清单另附公司投资者互动平台入口：上交所 [上证 e 互动](https://sns.sseinfo.com/)，深交所[互动易](https://irm.cninfo.com.cn/)。这两个平台适合了解投资者关切和公司回应，但互动内容应作为补充材料；关键事实、经营数据和重大事项要回到法定公告/定期报告核实。互动页的前端接口并非稳定公开 API，且平台使用条款/内容授权可能限制自动采集，因此当前只提供来源入口，不做批量抓取。

建议顺序：最新一期定期报告、前一期定期报告、最近一期年报；然后检查最新报告发布日至分析时点的控股权、重大投资/重组、分红、关联交易、安全生产等公司公告。

## 2. 官方接口失败时的网页搜索兜底

若公告接口超时、返回错误或结果不完整，先用可用的 `WebSearch` 搜索官方域名，关键词至少包含证券代码，并可并列现简称、历史简称、公告主题和日期，例如：

- `site:cninfo.com.cn 601918 新集能源 2025 年年度报告`
- `site:sse.com.cn 601918 新集能源 公告`
- `site:公司官网域名 601918 投资者关系`

搜索结果只用于定位页面，不把摘要、转载或搜索排名当作证据。打开结果后确认发行人、证券代码、披露日期，并优先进入交易所、巨潮资讯或发行人官网原文。没有 WebSearch 工具时，直接使用上述互动平台/交易所/巨潮资讯网页检索。记录实际核验的原文 URL；未能确认原文时明确标记“待核验”，不要用搜索摘要补造数据。脚本不自动抓取搜索引擎结果。

## 3. PDF 抽取、渲染与 OCR

先对整份 PDF 做一次全文原生抽取，不渲染或 OCR：

```bash
python -X utf8 .pi/skills/buffett-and-munger/tools/pdf_ingest.py \
  work/work_600519/pdfs/2026-08-15_report.pdf \
  --outdir work/work_600519/2026_H1 --native-only
```

原生抽取会在Poppler中文缺失时比较PyMuPDF文本，优先选择中文更完整的结果，避免不必要OCR。根据目录与页分隔，先记录“问题→指标→PDF物理页码→理由”。首轮通常6–12页；原生文字可读时只渲染必要页面回看，不OCR。OCR必须显式传 `--pages`，超过12页须写明原因并加 `--allow-large-ocr`。示例：

```bash
python -X utf8 .pi/skills/buffett-and-munger/tools/pdf_ingest.py \
  work/work_600519/pdfs/2026-08-15_report.pdf \
  --outdir work/work_600519/2026_H1 \
  --pages 5-7,25-28,60-62 --dpi 220 --ocr
```

工具会生成 `native_text.txt`、选定页 PNG、可选 `ocr_selected_pages.txt` 和处理说明。`--native-only` 只抽取全文并检查中文字符可读性，不渲染页面。若后来确需补页，复用原 `--outdir`，只传新增页并加 `--merge-ocr`；OCR 文本按 PDF 页码合并，重复页以新结果替换。不要为同一报告重叠页反复 OCR。乱码可能来自 PDF 字体映射，也可能只是 Windows 控制台编码；使用 `python -X utf8`，并优先用 `read` 查看 UTF-8 文件。OCR 只作定位和抄录辅助，重要数据必须回看 PDF 原页，不能把 OCR 当权威数据源。

## 4. 行情快照与交叉核验

价格只是估值输入，必须留存行情源和明确时间戳。可用内置脚本同时读取腾讯与新浪行情，并将核验结果保存到该股票目录：

```bash
python -X utf8 .pi/skills/buffett-and-munger/tools/market_quote.py 600519 \
  --out work/work_600519/market_quote.json
```

脚本尽可能返回两个来源的人民币价格和行情时间；某来源失败时保留错误说明，不把单源结果伪装成交叉验证。手动使用其他行情接口时，先确认原始字段单位/缩放，再与另一独立来源比较；不要凭字段名猜价格单位。报告记录采用的价格、来源、时间戳及来源间差异。

## 5. 财务数据交叉校验

先生成 JSON 模板，把从报告原页确认的数据按人民币元、股数按股录入：

```bash
python .pi/skills/buffett-and-munger/tools/financial_sanity.py \
  --template work/financial_input.json
# 编辑 financial_input.json 后：
python .pi/skills/buffett-and-munger/tools/financial_sanity.py \
  work/financial_input.json --out work/financial_checks.md
```

校验器计算市值、TTM 归母净利润/EPS/PE、现金转化、经营现金流减长期资产购建支出的代理值、有息债务与净债务、资产负债率和利息保障倍数。TTM 需要完整年度、本期累计及上年同期三项同口径数据。缺失字段填 `null`；不要把 OCR 结果未经核对直接录入。计算结果仍需结合报告原文解释。
