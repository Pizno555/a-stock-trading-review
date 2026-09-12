# 数据路由与覆盖完成门

## 数据纪律

行情决定市场、方向和技术状态；搜索只发现资讯线索，不能替代公告、交易所、监管或其他原始证据。不得把市场观点写成公司事实，也不得用估算值伪装行情。

用户指定日期时优先核验该日；否则以主要指数、全市场成交额和市场宽度共同确认最新可证明交易日。一旦交易日确认即锁定：局部字段缺失只能降为`partial`并写入`missing`，不得为了取得更完整字段把日期退回前一天。

报告与方向完整度只用：

- `complete`：关键市场扫描和全市场方向发现均完成，候选判断无实质缺口；
- `partial`：市场日期可确认，但一个或多个必要字段、扫描或方向证据不完整；
- `severe_missing`：无法可靠确认日期，或市场环境多个关键维度缺失。

## Step 0覆盖完成门

完整盘后复盘必须尝试并记录：

| scan | 目标 | 允许状态 |
|---|---|---|
| market_core | 指数、成交额、涨跌家数、涨跌停 | ok/partial/missing |
| sentiment | 炸板、昨日涨停反馈、连板、高位反馈 | ok/partial/missing |
| turnover_style | 成交额Top20及整体表现 | ok/partial/missing |
| theme_discovery | 全市场正负方向发现 | ok/partial/missing |
| material_news | 会改变方向或个股判断的重要资讯 | ok/partial/missing |
| user_holdings_focus | 用户持仓与交易输入 | ok/partial/missing/not_applicable |

`not_applicable`只适用于个人输入类。`market_core`或`theme_discovery`未真正完成时不得标记`complete`。`theme_discovery=ok`要求六视角均已通过Lens Sufficiency Gate逐项完成，不仅是“查询过”：每个Lens必须明确为`signal_found/no_material_signal/partial`并给出证据；去重后通常形成8～12个独立候选/异常。候选数量只表示正常范围，不能替代Lens完成证明。若少于8个，必须明确记录“六视角已完成 + 市场本身稀疏/无更多显著候选”的理由，否则至少为`partial`。其余扫描为`partial/missing`时通常至少降为`partial`。覆盖表是完成门，不是免责声明。

`material_news`包含两个阶段：发现期的重要资讯核验，以及正式D/R和`core_pool/watch_pool`冻结前的最终重大反证扫尾。后者未可靠完成时，`material_news`不得标记为`ok`。

## Discovery矩阵、研究资源分层与停止条件

研究遵循“多视角广扫 → 去重 → 轻核验 → 条件化深研 → 正式D合并终审 → 最终反证扫尾”，不对所有候选平均投入。

### 六视角Discovery矩阵

| 视角 | 主要发现对象 | 典型入口 | 防漏目的 |
|---|---|---|---|
| sector_breadth | 板块领涨/领跌与内部宽度 | 全市场板块涨跌、行业/概念联动 | 防止只盯熟悉赛道 |
| emotion_cluster | 涨停簇、连板梯队、新题材聚集 | 涨停/连板/炸板分布 | 捕捉情绪型新方向 |
| turnover_capacity | 成交额Top、容量核心聚类 | 成交额排行、大票联动 | 捕捉未进入涨幅榜前列的容量趋势 |
| relative_strength | 逆势抗跌、多日持续、弱转强 | 相对指数/板块强弱、连续性 | 捕捉趋势与早期修复 |
| driver_event | 政策、价格、订单、业绩、产业事件 | 当日重大财经/公告/产业变化 | 捕捉事件先于板块排名的机会 |
| loss_risk | 跌停/大面/高位补跌/退潮簇 | 跌幅榜、负反馈、风险事件 | 捕捉风险方向和资金迁移 |

第一轮查询必须保持中性：在当前运行没有先由证据发现某板块/股票前，不允许把它直接写进Discovery首轮搜索词。命名查询只能发生在`candidate_discovered`之后。

1. **广扫**：六视角全部尝试。数据允许时，去重后的内部候选目标为8～12个、优先约10个；候选必须按共同Driver、代表股集合和生命周期去重，不能靠概念别名或同一产业链拆分凑数。
2. **Lens Sufficiency Gate**：广扫停止前，`breadth/limit_cluster/turnover_capacity/relative_strength_persistence/driver_event/loss_risk`六个Lens各记录1条`discovery_lens_scan`，字段至少为`lens/status/candidate_names/evidence/high_salience_unresolved`。`status`只能为`signal_found/no_material_signal/partial`。`turnover_capacity`必须显式检查高成交容量核心内部是否存在重要分歧；`driver_event`必须显式检查价格/政策/订单/业绩等独立Driver；`loss_risk`必须显式检查高位/高beta/容量核心负反馈簇。8～12个候选不能替代此Gate。
3. **Coverage Repair**：某Lens=`partial`且`high_salience_unresolved=true`时，允许该Lens最多1次`coverage_repair_query`。query必须中性；尚未被本轮证据发现的精确方向/股票不得写入。已从Top成交、榜单或广扫结果中出现的主体可用于核对内部强弱。repair计入Research Budget；无法repair时必须解释并将`theme_discovery`降级为`partial`，不得伪装ok。
4. **轻核验**：每个高显著候选只取得足以判断“值得保留/淘汰/待确认”的结构证据与独立逻辑，不做完整公司深研。先执行Evidence Reuse Gate：广扫证据已足够时直接判断，不新增查询。确需命名查询时，只用于本轮已发现候选；若两个候选属于同一来源族且一条query可以清晰区分，允许最多2个候选组成`candidate_light_bundle`，禁止无关候选捆绑。
5. **条件化深研**：仅当候选准备成为正式D/R、进入`core_pool/watch_pool`、Driver不清、关键证据冲突、存在重大事件暴露，或新增证据可能改变仓位/动作时触发。每次deep query记录`unresolved_question/decision_field/expected_flip`；默认每候选1次，第二次必须记录`deep_budget_exception`。已被一个决定性门槛淘汰且新增证据不会改变身份时，不得继续深研。
6. **广扫停止条件**：只有六个Lens逐项通过Sufficiency Gate且去重候选处于8～12个正常范围时才停止Discovery；若Lens仍partial且存在高显著未决信号，先按Coverage Repair处理。若六Lens完成仍少于8个，可对覆盖不足Lens最多追加一次中性repair后停止并记录稀疏/缺失；不得为凑数继续搜索。
7. **深研停止条件**：分类、地位、核心角色和动作已经稳定，且新增检索只重复同一事实或不会改变决策时停止；不得为了“搜得更深”继续堆转载和同义证据。
8. **最终反证扫尾**：只对拟冻结的D/R、`core_pool/watch_pool`及关键主体，优先按正式链路做`chain_sweep`（一条D/R可在同一query列出多个关键主体），检查`data_as_of`之前足以推翻或显著改变判断的公告、监管、事故、政策、订单、业绩、供需/价格和重大产业事实。命中后只重开受影响链路，不重新扫描全市场。若某主体存在独特公告/监管/业绩暴露，或chain_sweep命中/冲突，则追加`standalone_sweep`；不得为了逐股形式完整而对同链所有主体机械重复搜索。
9. **Research Budget Gate**：正常完整日从首轮Discovery到最终反证扫尾，query-bearing研究事件目标`<=28`。六视角完成且已有8～12个去重候选后，默认停止广扫；轻核验必须先复用已有证据，不能按候选名单机械一股/一方向一搜。若总量将超过28，只有仍存在可能翻转正式决策的关键问题时才继续，并先记录`research_budget_exception`。
10. **预算结束记录**：过程JSONL建议在冻结前记录`research_budget_summary`，至少包含`discovery_queries/light_queries/deep_queries/material_sweeps/total_query_events/exceptions/stop_reason`。这用于审计“完成必要覆盖的最小有效成本”，不用于压低召回。

若测试runner记录过程JSONL，V2.4.6从`run_start.contract_version="2.4.6"`开始，并记录：`candidate_light_bundle`（最多2个同来源族候选）、`evidence_reuse`（已有证据直接完成轻核验）、`deep_budget_exception`（第二次深研原因）、`research_budget_exception`、`research_budget_summary`、`material_sweep_bundle`（链路、关键主体、query、cutoff）；以及`discovery_lens_scan`（lens/status/candidate_names/evidence/high_salience_unresolved）与必要的`coverage_repair_query`（lens/query/reason）、`candidate_discovered`（候选、来源视角）、`candidate_merged`（去重/合并原因）、`discovery_coverage_summary`（已尝试视角数、去重候选数、不足原因）；正式D压缩记录`formal_d_merge_check`；池子冻结记录`core_selection_audit`（selected逐只写`identity_value/identity_status/execution_status/execution_reason`，并记录同D重复/新启动/扩池例外；同D重复需写`role_difference/validation_difference`）；若存在正式D但`core_pool=0`，还必须记录`core_zero_audit`逐D说明候选与真正的identity failure，低仓/不可执行/无买点/技术missing不得充当identity failure；①环境预算冻结先记录`environment_budget_audit`（market_state/dominant_style/breadth_state/liquidity_state/relay_state/capacity_state/index_state/budget/evidence，必要时附environment_budget_override）；仓位冻结再记录`position_decision`（environment_budget/final_stance/upward_confirmation_families/downward_risks/reason），且其environment_budget必须与audit一致；反证覆盖记录`counterevidence_coverage`（每条正式D/R写最大反证文本与最终sweep状态）。最终扫尾至少记录`sweep_scope/cutoff/result`；若扫尾命中且改变决策，必须连续形成`material_news_hit`（source/title/published_at/fact/affected_chain）→`decision_reopened`（affected_chain/fields）→`decision_change`（before/after/reason）证据链。若命中但不改变决策，记录`material_news_hit`后写`decision_unchanged`。输出压缩审计另记录`output_compression_audit`（report_chars/target_chars/fact_owner_status/decision_changing_facts）；超过8700字符时记录结构化`output_budget_exception`。这些是可审计事件，不记录隐藏思维链。

## 运行环境数据能力契约

本Skill不要求固定Adapter、Provider、API Key或其他外部Skill。执行器可以使用当前环境实际可用的公开市场数据、搜索、网页、文件或行情能力，但**所有来源都必须先映射到同一套可审计数据语义**，再进入复盘判断。

每一类扫描或数据请求至少应能表达以下字段；底层实现形式可以是工具返回、JSON、表格或等价结构：

```json
{
  "schema_version": "1.0",
  "kind": "market_snapshot|market_sentiment|turnover_leaders|theme_candidates|price_history|market_search",
  "source": "实际来源或工具标识",
  "query": "实际查询或请求摘要",
  "as_of_date": "YYYY-MM-DD或null",
  "fetched_at": "ISO-8601时间或可核验抓取时点",
  "completeness": "complete|partial|severe_missing",
  "records": [],
  "missing": [],
  "warnings": []
}
```

若运行环境无法形成完整结构化对象，也必须在过程日志或报告覆盖表中保留等价的`source/as_of/completeness/missing/warnings`信息。工具失败、限流、网络错误、空结果或解析失败不得静默吞掉；应记录安全错误摘要并按“已有备用能力一次切换 → 降级 → 跳过受影响判断”的顺序处理。不得泄露密钥、Cookie或授权信息。

### 必要数据能力

执行器按当前环境能力尽力取得：

- **market_snapshot**：主要指数、全市场成交额、涨跌家数、涨停/跌停等市场核心；
- **market_sentiment**：炸板、昨日涨停今日正收益占比/中位数（至少一项才能把昨日涨停反馈视为已取得）、连板梯队与高位反馈；
- **turnover_leaders**：成交额Top及股票代码/名称/涨跌幅，目标Top20；
- **theme_candidates**：本轮Discovery已经发现方向的代表股、宽度、成交承载与相对强弱；
- **price_history**：核心对象技术执行所需的历史日线与复权口径；
- **market_search**：重大资讯、公告、监管、政策、价格、订单、业绩与产业事件的发现和核验。

这些是**数据能力要求，不是固定函数接口**。不得因为当前环境没有某个Provider就回退方法论；取得不到的字段进入`missing`并按`partial/severe_missing`降级。不得为了补齐字段临时安装其他Skill、绑定固定第三方API、新建数据库或批量拉取全A历史K线。全A站上20/60日线比例、成交集中度、Gini、HHI、龙虎榜精细席位等只有当前环境已有可靠结果时才使用。

### 日期与口径约束

- 一旦通过主要指数、全市场成交额和市场宽度共同确认交易日，即锁定该日；局部字段缺失只能`partial/missing`，不得回退前一交易日换取“更完整”数据。
- 情绪数据只有“昨日涨停数量”而无今日正收益占比/收益中位数时，必须将“昨日涨停今日反馈”标记为`待确认/缺失`，不得用少数具名样本冒充全样本。
- 成交额Top数据不足目标Top20时按实际覆盖披露，不得用Top5推断完整Top20风格。
- 候选与核心比较中实际使用涨跌幅、成交额、宽度等字段时，检索或数据请求必须真实覆盖这些字段；未取得即降级。
- 历史盲测严格按发布时间/可获得时间受`data_as_of`约束；后续报道即使描述测试日事实，也不能倒灌进当时决策。

## 候选覆盖与证据

方向发现先高召回，再压缩。D方向至少检查宽度、核心强度、持续性、成交承载和扩散；R方向检查核心负反馈、宽度恶化、近期参与者盈亏、成交承载/资金撤离和资金迁移。

候选全集覆盖产业锚、上一期核心、当日成交活跃与相对强势、多日持续趋势、公告/订单/业绩/事件核心。不得用MA、RSI9或BIAS20建候选集。重要同行数据不全时降为`partial`，不能把“没查到”写成“不是核心”。

资讯优先从现有搜索能力发现，再回到原始来源核验。只有关键事实会改变方向、核心股或持仓结论时才做增量证据研究；日常复盘不重复完整公司深研。正式D/R和池子冻结前必须按上节完成最终重大反证扫尾；扫尾优先官方、交易所/监管、公司与权威原始来源，并严格受`data_as_of`约束。

## 技术指标口径

优先使用至少60根前复权日线：MA为简单移动平均；RSI9使用Wilder平滑；`BIAS20=(Close-MA20)/MA20×100%`。输出日期、复权口径、bar数量、数据起止、MA5/10/20/60、RSI9、BIAS20和warnings。

盘前没有新完整日K时沿用上一完整交易日指标。未知复权或不足60根时披露限制，不伪造完整结论。若使用`scripts/calculate_indicators.py`，先把当前环境取得且已核验截止/复权口径的历史日线整理为JSON数组，或包含`bars/records/data`数组的JSON对象；脚本只做本地指标计算，不负责获取外部行情。

## 失败与临时文件

执行顺序：主源失败 → 仅切换一次已有备用能力 → 降低完整度 → 跳过受影响判断。不同来源冲突时检查日期、单位、复权、板块口径和事件日/报道日；无法消除则并列披露。

中间文件写系统临时目录或本次独立临时目录。自测不得写入正式复盘存档；成功后清理临时目录。不得新增无关依赖或固定工作区临时目录。
