# buffett_and_munger

巴菲特的完整投资思维体系 + 查理·芒格的认知操作系统,双人协作模式。

一个纯文本知识库形式的 WorkBuddy Skill:收到投资问题时,**巴菲特先出系统化企业质量与估值分析,芒格后出批判审视**,两者意见不一致时如实呈现分歧,不做强行调和。

> "Risk comes from not knowing what you are doing." — Buffett
>
> "It is remarkable how much long-term advantage people like us have gotten by trying to be consistently not stupid." — Munger

**声明:这不是两人本人**,是基于公开信息(伯克希尔股东信、演讲、访谈、《穷查理宝典》等)提炼的思维系统。

## 安装

### 方式一:clone 后复制(推荐)

```bash
git clone https://github.com/qtxxgedfs/buffett_and_munger_skill.git
# 把仓库目录名改成 buffett_and_munger,或直接复制内部文件
```

然后把仓库放到用户级 skill 目录:

| 系统 | 路径 |
|------|------|
| Windows | `C:\Users\<用户名>\.workbuddy\skills\buffett_and_munger\` |
| macOS / Linux | `~/.workbuddy/skills/buffett_and_munger/` |

**重启 WorkBuddy** 后生效。

最终结构必须是:

```
~/.workbuddy/skills/buffett_and_munger/
├── SKILL.md                ← 必须在这一层
└── references/
    ├── buffett/
    └── munger/
```

### 方式二:直接下载 zip

在Releases 或 Code → Download ZIP 下载,解压后把内部文件复制到 skills 目录。

### 方式三:项目级安装

只想在某个项目里生效,把整个目录放到 `<项目根目录>/.workbuddy/skills/buffett_and_munger/`。项目级优先级低于用户级。

## 验证

重启后在任意对话中问:

```
用芒格的视角分析一下宁德时代
```

能触发双人协作输出即安装成功。也可以在技能列表里确认是否出现 `buffett_and_munger`。

## 触发场景

即使用户不提"巴菲特""芒格",以下情况会自动触发:

- 分析任何股票或公司、评估投资机会
- 解读财报 / 年报 / 股东信
- 判断护城河或竞争优势、评估管理层质量与诚信
- 买入 / 持有 / 卖出决策
- 价值投资核心概念:复利、内在价值、安全边际、能力圈、市场先生
- 行业分析:保险 / 银行 / 消费 / 媒体 / 能源 / 铁路 / 科技
- 资本配置 / 回购 / 分红、市场情绪与宏观风险
- 认知偏误检查、逆向思考、跨学科分析、Lollapalooza 效应

## 退出协议

在对话中说「退出」「切回正常」「不用扮演了」可立即恢复普通助手模式。说「只要巴菲特」或「只要芒格」可只保留单人模式。

## 目录结构

```
buffett_and_munger/
├── SKILL.md                              # 主入口:协作协议 + 8问筛选 + 模块路由
└── references/
    ├── buffett/                          # 巴菲特模块
    │   ├── 01-thinking-frameworks.md      # 思维框架
    │   ├── 02-investment-philosophy.md    # 投资哲学
    │   ├── 03-business-moat.md            # 护城河
    │   ├── 04-management-governance.md   # 管理层与治理
    │   ├── 05-financial-metrics.md# 财务指标
    │   ├── 06-valuation-capital.md       # 估值与资本配置
    │   ├── 07-risk-behavior.md           # 风险与行为
    │   └── 08-industry-playbooks.md# 行业 playbook
    └── munger/                           # 芒格模块
        ├── 25-biases.md                  # 25 种人类误判心理倾向
        ├── research.md                   # 芒格思想体系研究索引
        ├── thought-system-research-20260404.md
        └── expression-style-dna.md        # 表达风格参考
└── tools/                                 # 官方公告、PDF/OCR、财务校验工具
```

工具依赖及用法见 [`tools/README.md`](tools/README.md)。基础依赖可通过 `python -m pip install -r tools/requirements.txt` 安装；中文 OCR 为可选依赖，详见 `tools/requirements-ocr.txt`。

## 工作流

1. **问题分类** —— 区分「需要联网查证的事实问题」「纯框架问题」「混合问题」,禁止凭训练语料编造具体公司数据
2. **巴菲特回答** —— 系统化分析,先结论后依据,第一人称语气
3. **芒格回答** —— 逆向找漏掉的风险路径、认知偏误检查(尤其 Lollapalooza 效应)、激励结构对齐检查
4. **共识/分歧小结** —— 1-3 句总结,分歧时点明分歧本质

## 常见问题

**装了不生效?**
- 确认 `SKILL.md` 在 `skills\buffett_and_munger\` 第一层,没有多套一层目录
- 确认 `SKILL.md` frontmatter 里 `name: buffett_and_munger` 与文件夹名一致
- 必须重启 WorkBuddy(skill 列表在启动时扫描)

**中文乱码?**
所有文档均为 UTF-8 编码。避免用会转 GBK 的工具另存,用 git 或 zip 传输不会有问题。

## License

MIT — 可自由使用、修改、二次分发。
