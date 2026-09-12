# a-stock-trading-review

面向A股交易者的证据化七步复盘 Skill（V2.4.6 Recall & Output Stability）。它先用后台Step 0完成市场、情绪、成交风格、方向、资讯和个人输入覆盖，再判断双向盈亏效应、方向、核心股与账户交易，最后形成次日三情景和技术执行计划。

## 七步流程

1. 市场环境与风险偏好；
2. 赚钱效应与亏钱效应；
3. 方向判断；
4. 核心股定位；
5. 账户与交易复盘；
6. 明日重点；
7. 明日剧本与执行计划。

完整复盘固定输出0～5只不凑数的`core_pool`、0～3只`watch_pool`、必要时0～3只风险锚，以及市场和核心票的超预期/基准或符合预期/低于预期剧本。技术指标只能在⑦C负责执行位置，不能生成或捞回候选。

## 使用

```text
使用 $a-stock-trading-review 复盘最近一个完整A股交易日，并制定下一交易日计划。
```

```text
使用 $a-stock-trading-review 做盘前更新，只检查隔夜新增变量和上一计划变化。
```

可选输入包括交易日、持仓与原始逻辑、相对成本位置、当日交易和当时依据、上一复盘、重点方向或材料。没有个人输入时不会编造。

## 关键纪律

- 完整复盘必须尝试六类后台扫描；`theme_discovery`进一步按六视角广扫：板块宽度、涨停/连板簇、成交额/容量、逆势相对强弱/持续、事件Driver、亏钱/风险簇。数据允许时去重后内部目标8～12个候选、优先约10个；正式D仍只保留0～5个。
- 高度相关指标按信号族去重后再交叉验证，避免把同一风险偏好现象重复计权。
- D正向方向与R风险方向隔离；同一方向原则上不同时建立D和R。
- 单一事件不得无证据扩大为行业主线；Driver与市场Confirmation分开。
- 每个生命周期结论提供阶段依据、最大反证及升级/降级条件。
- 每条重要D方向先覆盖候选和同行，再压缩到核心角色；方向遗漏审计要求至少两个独立信号族支持，且与已有D高度重叠时先合并/拆分检查，避免为召回而过度拆方向。
- `core_pool`可为0；风向标不等于买入候选，风险锚不进入核心池或观察池。
- 交易评价区分决策质量和结果；单次失败只记录`rule_candidate`。
- 趋势确认不等于新增买点；非核心风险持仓禁止因超卖补仓。
- 没有用户冻结的百分比模型时，只输出档位仓位及升降条件。
- 研究层保持完整，用户正文做“最小充分表达”：②负责效应与Driver，③只写阶段/预期/证伪，④只写核心股相对优势；同一事实不在②③④重复展开。
- 研究资源采用“六视角广扫→去重→轻核验→条件化深研→最终反证扫尾”。Discovery首轮只允许中性查询；本轮尚未发现的具体板块/股票不得提前写进搜索词。候选达到8～12个仍不能替代六Lens充分性证明；每个Lens必须明确signal_found/no_material_signal/partial，必要时每Lens最多1次中性coverage repair，并受总<=28预算约束。
- Stability & Resource Discipline与Core Identity / Execution Separation继续有效：Evidence Reuse、条件化deep search、正常完整日query-bearing研究事件目标<=28、仓位上调至少两个独立确认族、身份通过但当前blocked的核心仍保留。V2.4.5新增Environment Budget Gate，V2.4.6新增Lens Sufficiency与输出事实归属门：环境风险预算只由Step①的宽度、流动性、接力、趋势容量与指数证据决定；显著弱市/强市设置矛盾硬锚，中性结构市保留弹性，候选/D/core/watch数量不得参与。完整source与后台审计留在process JSONL，用户报告保持最小充分。
- 候选数量不是KPI：同一Driver/产业链/代表股集合的别名方向先合并再计数，避免通过拆概念凑“高召回”。
- 正式D冻结前再做一次跨候选合并终审：Discovery可以拆开看，上下游/相邻概念若最终共享主要Driver和次日验证链，正式D必须合回去。
- Discovery候选数、D数量和watch数量不得自动抬高仓位；仓位只由市场风险、主线/核心质量、真正可执行机会、位置赔率、亏钱效应和重大风险决定。
- 最终反证若改变决策，过程JSONL必须留下带来源的`material_news_hit → decision_reopened → decision_change`；测试runner可用Validator的`--process-jsonl`一起校验。最终扫尾优先按D/R链路批量核验，同链多个主体不机械逐股重复；命中、冲突或独特公告/监管/业绩暴露时再单体升级。
- 技术数据缺失只能限制执行，不能单独否定已经确认的核心身份；条件核心可保留，但技术数据恢复前禁止新增执行。两只及以上核心具有完全相同技术缺口时允许使用“全局技术执行门”统一声明missing与冻结新增，逐股只保留不追/失效差异。
- 正式冻结前只对D/R、`core_pool/watch_pool`及关键主体做截止时间内的重大反证扫尾；命中反证只重开受影响链路，不重新扫描全市场。

## 数据与兼容

本Skill**不绑定固定行情Provider、外部API或其他Skill**。执行器使用当前运行环境实际可用的公开市场数据、搜索、网页、文件或行情能力完成Step 0；数据能力属于运行环境，不属于本Skill的方法论依赖。

无论底层来源是什么，都必须遵守`references/data-routing.md`中的统一数据契约、交易日锁定、`complete/partial/severe_missing`降级、`missing/warnings`记录、历史`data_as_of`截止和证据核验纪律。无法可靠取得的字段必须降级，不得为了补齐字段临时要求安装其他Skill、连接固定第三方API或伪造数据。

本Skill只保留两个本地脚本：技术指标计算与报告Validator；不内置第三方行情连接器。默认新存档写入`outputs/a-stock-trading-review`；为保持历史连续性，仅在使用默认存档路径且新目录找不到上一完整复盘时，允许**只读**回退到旧目录`outputs/a-stock-review-audit`，旧目录不再写入、不迁移、不修改。

## 文件结构

```text
a-stock-trading-review/
├── SKILL.md
├── README.md
├── agents/openai.yaml
├── references/
│   ├── review-rules.md
│   ├── data-routing.md
│   └── output-and-archive.md
├── scripts/
│   ├── calculate_indicators.py
│   └── validate_review_output.py
└── evals/
    ├── blind-evaluator.md
    ├── regression-cases.md
    └── release-gate.md
```

正式报告交付前必须通过七步 Validator。匿名质量比较按`evals/blind-evaluator.md`执行；结构回归按`evals/regression-cases.md`执行；版本研发/发布使用`evals/release-gate.md`，任何关键维度低于v2.4.2均不得升级。
