# buffett-and-munger

巴菲特的企业质量与估值分析，加上芒格的跨学科审视与认知偏误检查，采用**双人独立判断**模式。

> "Risk comes from not knowing what you are doing." — Buffett
>
> "It is remarkable how much long-term advantage people like us have gotten by trying to be consistently not stupid." — Munger

**声明：这不是两人本人**，是基于公开信息（伯克希尔股东信、演讲、访谈、《穷查理宝典》等）提炼的思维系统，不构成投资建议。

## 安装

> **命名规则**：skill 名称只支持连字符，不支持下划线。目录名必须与 `SKILL.md` frontmatter 里的 `name` 一致，即 `buffett-and-munger`。

### 方式一：clone（推荐）

```bash
git clone https://github.com/qtxxgedfs/buffett_and_munger_skill.git buffett-and-munger
```

注意：仓库名（`buffett_and_munger_skill`）保留原名，但**clone 后的目录名必须是 `buffett-and-munger`**。

然后把目录放到 pi 的 skill 目录：

| 用途 | 路径 |
|------|------|
| 项目级（只在该项目生效） | `<项目根目录>/.pi/skills/buffett-and-munger/` |
| 用户级（所有项目生效） | `~/.pi/agent/skills/buffett-and-munger/` |

Windows 用户级对应 `C:\Users\<用户名>\.pi\agent\skills\buffett-and-munger\`。项目级与用户级同名时，一般以项目级为准。放好后**重启客户端**（skill 列表在启动时扫描）。

### 方式二：下载 zip

Code → Download ZIP 下载，解压后把内部文件复制到上面的 skill 目录，目录名同样改为 `buffett-and-munger`。

### 方式三：只复制内部文件

已有 skill 目录时，把本仓库的 `SKILL.md`、`references/`、`tools/` 覆盖进去即可。最终结构必须是：

```
buffett-and-munger/
├── SKILL.md                ← 必须在这一层，没有多套一层目录
├── references/
│   ├── buffett/
│   └── munger/
└── tools/
```

## 验证

重启后在任意对话中问：

```
用芒格的视角分析一下宁德时代
```

能触发双人独立输出即安装成功。也可以在技能列表里确认是否出现 `buffett-and-munger`。

## 触发场景

即使用户不提"巴菲特""芒格"，以下情况会自动触发：

- 分析任何股票或公司、评估投资机会、买入 / 持有 / 卖出决策
- 解读财报 / 年报 / 股东信，建立事实底稿并按官方披露核验
- 判断护城河或竞争优势、评估管理层质量与诚信、资本配置
- 价值投资核心概念：复利、内在价值、安全边际、能力圈、市场先生
- 行业分析：保险 / 银行 / 消费 / 媒体 / 能源 / 铁路 / 科技
- 认知偏误检查、逆向思考、跨学科分析、Lollapalooza 效应
- 芒格语气模仿、金句与引言溯源、书单与演讲、错误与争议

## 目录结构

```
buffett-and-munger/
├── SKILL.md                              # 主入口：角色规则 + 资料路由 + 执行顺序 + 输出结构
├── references/
│   ├── buffett/                          # 巴菲特模块 B1–B8
│   │   ├── 01-thinking-frameworks.md     # B1 思维框架：能力圈、逆向、市场先生、耐心
│   │   ├── 02-investment-philosophy.md   # B2 投资哲学：复利、内在价值、集中与分散
│   │   ├── 03-business-moat.md           # B3 企业与护城河
│   │   ├── 04-management-governance.md   # B4 管理与治理
│   │   ├── 05-financial-metrics.md       # B5 财务指标：ROIC、所有者收益、透视盈余
│   │   ├── 06-valuation-capital.md       # B6 估值与资本配置：回购、分红、套利
│   │   ├── 07-risk-behavior.md           # B7 风险与行为：价值陷阱、杠杆、四条卖出标准
│   │   └── 08-industry-playbooks.md      # B8 行业手册
│   └── munger/                           # 芒格模块 M1–M4
│       ├── 25-biases.md                  # M1 25 种人类误判心理倾向
│       ├── thought-system-research-20260404.md  # M2 思想体系调研（思考主干）
│       ├── expression-style-dna.md       # M3 表达风格 DNA
│       └── research.md                   # M4 研究索引：引言溯源、矛盾与待验证
└── tools/                                # 官方公告、PDF/OCR、行情、财务校验、计时
```

工具依赖及用法见 [`tools/README.md`](tools/README.md)。基础依赖：`python -m pip install -r tools/requirements.txt`；中文 OCR 为可选依赖，见 `tools/requirements-ocr.txt`。

## 工作流

1. **任务入口与资料路由** —— 先区分公司判断、快速筛选、深度分析，还是概念/表达任务；概念归属与引言出处分别按 M2 第二节、M4「关键引用」核对，不凭记忆编造
2. **事实底稿**（具体公司）——
   - 以证券代码 + 交易所为稳定主键；中间资料存 `work/work_{证券代码}/`
   - `tools/official_filings.py` 检索官方定期报告与公告，核对最新一期与前一期，检查最新披露日至分析时点的重大公告
   - `tools/pdf_ingest.py --native-only` 先抽原生文本，仅在不足时显式选页 OCR，重要数据回看 PDF 原页
   - 人工录入后可用 `tools/financial_sanity.py` 复核 TTM、现金转化、资本开支代理值、债务与估值
   - `tools/market_quote.py` 取行情快照，记录价格来源与时间戳；行情只是价格输入
   - 最终报告写入项目根目录 `reports/{股票名}_{年份}_{披露月份}_{披露日}.md`
3. **巴菲特：从生意到价格** —— 先过三个必答问题（能力圈 / 三条亏钱路径 / 十年的生意），再按企业质量 → 财务与估值 → 风险 → 行业四个环节展开
4. **芒格：独立判断** —— 三筐分类（Yes / No / Too Hard）→ 多元模型解释同一件事 → 逆向与愚蠢清单 → 激励与偏误叠加（Lollapalooza）→ 主动反证与意见资格 → 落到做、不做、等待或 Too Hard
5. **共识与分歧** —— 1–3 句中立说明一致在哪、分歧在哪、分歧本质是什么

## 快速筛选：八问

两个负面结果需要强理由才能继续；四个负面结果直接放弃；Q7 诚信问题一票否决。

| # | 维度 | 问题 | 负面结果 |
|---|---|---|---|
| 1 | 能力圈 | 能否用一段话讲清公司怎么赚钱？ | 不能：圈外 |
| 2 | 持久性 | 十年后公司还在并且更有竞争力吗？ | 否：技术或模式颠覆风险 |
| 3 | 护城河 | 竞争对手认真砸钱，能复制核心优势吗？ | 能：没有护城河 |
| 4 | 定价权 | 提价 5–10% 能不流失大量客户吗？ | 不能：商品型企业 |
| 5 | 盈利质量 | 利润真的变成现金，而不是会计技巧吗？ | 否：盈利质量差 |
| 6 | 债务安全 | 行业最差情景、营收下降 30% 时能活吗？ | 不能：杠杆风险 |
| 7 | 管理层诚信 | 管理层诚实面对问题，而非掩盖吗？ | 否：一票否决 |
| 8 | 价格合理 | 现价与内在价值之间的差距足够大吗？ | 否：等待或跳过 |

## 输出结构

公司分析输出三块：**巴菲特报告**（结论 / 能力圈 / 关键假设 / 企业质量 / 财务快照 / 估值 / 卖出标准逐条检验 / 主要风险 / 监控指标 / 综合判断）、**芒格回答**（定性 / 逆向检查 / 偏误扫描 / 激励诊断 / 意见资格 / 独立观点 / 综合判断）、**共识与分歧**。

- 芒格默认沉默：巴菲特判断正确且充分时，只答 `I have nothing to add.`，不为凑双人发言制造异议
- 有分歧就保留，可直说 `I disagree with Warren here.`
- 两人都不懂就直接进 Too Hard 筐，不硬给结论

## 退出协议

说「退出」「切回正常」「不用扮演了」可立即恢复普通助手模式；说「只要巴菲特」或「只要芒格」可只保留单人模式。

## 常见问题

**装了不生效？**
- 确认 `SKILL.md` 在 `skills/buffett-and-munger/` 第一层，没有多套一层目录
- 确认 `SKILL.md` frontmatter 里 `name: buffett-and-munger` 与文件夹名完全一致；名称只支持连字符，写成下划线（`buffett_and_munger`）不会被识别
- 必须重启客户端（skill 列表在启动时扫描）

**中文乱码？**
所有文档均为 UTF-8 编码。脚本报编码错误时先用 `python -X utf8` 重跑，或读取 UTF-8 输出文件核验；避免用会转 GBK 的工具另存。

**公告接口报错或结果可疑？**
先用公告 JSON 里的备用官方链接，或用 WebSearch 限定巨潮资讯 / 交易所 / 发行人官网定位原文，打开后核实公司代码、披露日期与内容并记录 URL；摘要不作证据，未核实的结果标为待核验。

## License

MIT — 可自由使用、修改、二次分发。
