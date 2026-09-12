# 回归场景

测试统一使用系统临时目录，不写正式`archive_root`。结构测试验证契约；语义测试验证“格式合法但认知退化”的情况。测试目标是可观察行为，不比较固定措辞。

## A. 结构与工程回归

1. 合格七步报告：含V2 frontmatter、六要素结论、七步、D/R链路、三情景、覆盖表和仓位，Validator通过。
2. 删除任一步，或`core_pool>5`/`watch_pool>3`：Validator失败。
3. 同一股票同时进入`core_pool`与`watch_pool`：Validator失败。
4. ②存在D/R但③未承接；③存在链路但④未承接；⑥引用不存在的D/R链：Validator失败。
5. ⑥核心池/观察池股票没有在④同链核心比较中出现：Validator失败。
6. R或风险锚进入`core_pool/watch_pool`：Validator失败。
7. ①～⑥对单股使用MA/RSI9/BIAS20：Validator失败；①出现“全A站上20/60日线比例”不误报。
8. `severe_missing`时，文字出现“无法判断主线”不应误杀；真正输出“主线×强化”等强结论应失败。
9. 任一`core_pool`股票缺超预期/符合预期/低于预期之一，或⑦C逐股技术字段不全：Validator失败。
10. 非核心风险持仓出现新增、补仓、加仓、摊低成本或升级核心池：Validator失败。
11. 最新交易日某字段缺失而前一日完整：数据路由层必须锁定最新已确认交易日并返回/记录`partial/missing`，不得为了字段完整回退前一日。
12. 情绪数据只有“昨日涨停数量”而无正收益占比/收益中位数：必须标记“昨日涨停今日表现”缺失/待确认；不得用少数具名样本冒充全样本。候选判断若使用涨跌幅和成交额，实际数据请求/检索必须覆盖这些字段。
13. 第①步写`Top20`、`成交额前20`等等价表述时不应因措辞失败，但仍必须存在大成交核心整体反馈。
14. 第②步缺少`方向遗漏审计`：Validator失败；写`方向遗漏审计：无`或`方向｜决定性原因`可通过结构检查。
15. 数据限制`material_news`行没有记录`最终反证扫尾`状态：Validator失败；记录“最终反证扫尾：完成/partial/missing”可通过结构检查。
16. 测试runner提供`--process-jsonl`且正式D不少于2条时，缺少`formal_d_merge_check`：Validator失败；有明确合并终审事件可通过。
17. `decision_change`前没有同一受影响对象的`material_news_hit`和`decision_reopened`，或`material_news_hit`缺来源/发布时间：Validator失败。
18. 候选因重大事故/监管/澄清等事件反证被淘汰，但JSONL没有对应带来源的`material_news_hit`：Validator失败。
19. `core_pool`股票的MA/RSI9/BIAS20字段出现`missing/缺失/不足/不可得`时，若⑦C未明确“技术执行数据恢复前不新增/不可执行”：Validator失败；明确冻结新增执行可通过。
20. 两只及以上core共用`全局技术执行门`时，门内必须包含affected core、MA/RSI9/BIAS20缺口和冻结新增结论；任一core不在门内则必须使用完整逐股技术字段。
21. 被全局技术门覆盖的core仍必须逐股保留`不追条件`与`失效/退出条件`；删除任一则Validator失败。

## B. 36个语义回归场景

1. **指数涨、宽度弱**：指数上涨但大多数股票下跌，应识别窄幅领导而非“全面强市”。
2. **连板强、趋势容量弱**：短线接力火热但大成交核心走弱，应拆分情绪小票与趋势容量，不把整个市场判强。
3. **连板弱、趋势容量强**：接力退潮但容量趋势走强，不得把整个市场机械判为退潮。
4. **用户偏爱科技、主线在非科技**：先发现真实全市场主线，再单独检查科技；用户偏好不得污染D/主线排序。
5. **单股事件未扩散**：单一公司涨停且同行无共同机制，不得升级为行业主线。
6. **主线首次分歧**：核心仍有承接、宽度未崩，不能因一天分歧机械判退潮。
7. **高成交但极度集中**：总成交额不弱但集中于少数股票，应提示脆弱/拥挤，不把“放量”单独当健康。
8. **好市场但没有好买点**：环境偏进攻、核心票普遍过度扩张时，允许`core_pool=0`或维持较低实际仓位。
9. **严重数据缺失**：关键扫描缺失时必须降级，不能用确定语气补齐主线或催化。
10. **正确交易但结果亏损**：按计划、依据合理但随机亏损，应判“正确决策+错误结果”，不能以盈亏倒推错误。
11. **亏钱效应收敛**：大面/负反馈减少只说明风险改善，不能自动生成买点或加仓。
12. **Top20多数上涨**：可判趋势容量风格增强，但没有席位/资金净流入证据时不得直接写“机构进场”。
13. **独立强方向漏报**：一个未入D方向同时出现多核心强势、独立Driver/资金逻辑和容量确认时，应升级为D；若与已有D高度重叠或证据仍不足，必须在方向遗漏审计中写1个决定性未纳入原因。
14. **方向遗漏审计过度晋升**：同一批股票当日大涨同时被当成“多核心强势”和“容量确认”，但没有第二独立信号族，不得仅靠重复价格证据升级为D。
15. **相邻方向过度拆分**：两个候选共享同一Driver、同一代表股集合和相同生命周期时，应合并而非拆成两个D；若Driver、代表股集合或生命周期至少一项实质不同且有独立验证链，才允许拆分。
16. **昨日涨停样本不完整**：只有少数具名高标负反馈而缺少全样本正收益占比/收益中位数时，第①步不得直接输出“昨日涨停反馈：负”，只能`待确认/缺失`并说明偏负线索。
17. **同证据重复输出**：②已完整写Driver与强度，③④不得逐字重复同一数字/故事；压缩后必须保持主线、风险、核心股和执行结论不丢失。
18. **正式D盘后出现重大反证**：某方向盘面和产业证据均强，但`data_as_of`前出现重大事故/监管/公告足以改变次日风险收益；最终扫尾必须抓到并重开该链路，不能按扫尾前状态冻结。
19. **不必要深研**：普通轮动候选已经证据充分地被淘汰，后续搜索不会改变D/R/池子/仓位；应停止，不得为了“更深”继续做公司级研究。
20. **必要深研触发**：候选准备进入D或`core_pool`但Driver不清或来源冲突；必须触发深研，不能因追求轻量而直接冻结。
21. **扫尾范围失控**：最终反证扫尾不得重新遍历全部行业/涨幅榜；只能检查拟冻结D/R、`core_pool/watch_pool`及关键主体。
22. **研究加深但正文不膨胀**：内部因深研新增多条证据但最终只强化既有结论时，正文仅保留会改变排序/角色/动作的增量，不把搜索过程搬进用户报告。

每次修改规则、数据路由契约或Validator后至少重跑A组全部案例；影响市场认知逻辑时同时重跑B组。失败案例必须能复现后才允许新增规则，避免因单日结果继续膨胀Skill。
23. **Discovery广度不足**：板块榜只发现6～7个候选，但成交额Top、逆势相对强弱和事件面仍存在独立显著方向；不得提前进入D压缩，必须继续完成六视角或将`theme_discovery`降级。
24. **候选数量灌水**：把CPO、光模块、光通信、光互连等同一Driver与高度重叠代表股拆成多个候选来凑8～12；必须先合并再计数。
25. **答案导向型首轮搜索**：当前运行尚未发现某板块时，第一轮query直接写该板块/股票或精确已知答案；过程审计应判为Discovery污染，不得把该结果当独立召回证据。
26. **容量型方向未进涨幅榜前列**：某方向涨幅一般但成交额Top多只容量核心同步走强；必须至少进入内部候选轻核验，不能只按板块涨幅发现。
27. **事件先于板块排名**：重大政策/价格/订单/产业事件在当日已发布，多只相关股出现早期确认但板块排名尚不突出；`driver_event`视角应发现并轻核验，不能等涨幅榜确认后才看见。
28. **广扫成本失控或稀疏市场例外**：六视角已完成且去重候选达到8～12后应停止Discovery；若六视角完成仍少于8个，可在覆盖不足视角各追加一次广义检索后停止并记录市场稀疏/数据缺失，不得为凑数无限搜索。
29. **Discovery拆开、正式D应合并**：电子布/玻纤与PCB在Discovery中分别成为候选，但最终共享同一涨价/AI需求传导、核心股集合高度关联、生命周期与次日验证条件基本相同；正式D冻结前必须合并为一条产业链D，不能因Discovery广度要求重复占用D名额。
30. **候选变多但仓位不应上调**：相比对照运行新增多个观察候选，但市场宽度、成交、亏钱效应、主线质量和真正可执行核心均未改善；最终仓位不得仅因候选/D/watch数量增加而从低仓升到中低仓或更高。
31. **反证改变决策但JSONL无来源链**：最终扫尾因重大事故/监管/公告撤销某D或改变core/watch/仓位，但过程日志只有`candidate_rejected`或一句结论，没有带来源的`material_news_hit → decision_reopened → decision_change`；Blind过程审计应判证据链不完整。
32. **技术数据缺失不否定核心身份**：某股已通过D链、同行比较、产业/角色和风险收益筛选，但60根历史日线不足，MA/RSI/BIAS无法完整计算；不得仅因技术数据缺失将其踢出`core_pool`。允许保留为条件核心，但⑦C所有缺失字段如实标记，并在技术数据恢复前禁止新增执行。


33. **Evidence Reuse优先**：广扫结果已足够把普通候选淘汰，额外命名检索不会改变D/R/池子/仓位；应直接记录evidence_reuse并停止，不得机械进入deep search。
34. **Deep query必须可翻转决策**：候选需要第二次deep query时，必须能说明未解决问题、受影响decision field与expected flip；只是寻找更多同义证据不得追加。
35. **链路扫尾而非逐股机械扫尾**：同一D链有多个core/watch时，优先一条chain sweep覆盖关键主体；若命中、冲突或某主体存在独特公告/监管/业绩暴露，再standalone escalation。不得为了减少query而遗漏正式对象。
36. **共享技术缺口压缩**：三只core因同一cutoff历史数据不可得而全部MA/RSI/BIAS missing时，允许一次全局技术门+逐股差异化不追/失效；不得把同一missing模板复制三遍，也不得因压缩删除逐股风险边界。
26. **研究预算失控**：正常完整日query-bearing事件>28且没有`research_budget_exception`：process Validator失败；有完整例外字段时允许继续。
27. **仓位上调无独立证据**：`position_decision.final_stance`高于`environment_budget`，但`upward_confirmation_families`少于2个独立族，或把candidate/D/watch/core数量当上调证据：失败。
28. **同D重复核心无边际价值**：同一D选择>=2只core，但`core_selection_audit`没有写明`role_difference/validation_difference`并证明角色/同行优势和次日验证价值均实质不同：失败。
29. **新启动核心只靠单日强度**：生命周期含`新启动`的core缺独立Driver或容量/同行确认：失败。
30. **低风险预算扩池无例外**：环境预算为低仓/中低仓且core>3，没有`core_pool_expansion_exception`及独立链/动作价值/可执行条件：失败。
31. **Discovery覆盖伪ok**：v2.4.4过程声明theme_discovery ok，但六视角未全尝试，或候选<8且没有稀疏/缺失理由，或候选>12未先去重压缩：失败。
32. **反证覆盖不完整**：正式D/R存在但`counterevidence_coverage`漏链、最大反证文本缺失或最终sweep状态缺失：失败。



## V2.4.4 Core Identity / Execution Separation 回归

33. **低仓不等于无核心**：存在正式D且候选已通过D链、角色/产业地位、同行优势与身份持续性比较，仅因环境预算低仓或“今天不适合买”把`core_pool`归零：失败。
34. **Execution blocked保留身份**：候选通过Identity Gate，但因弱市/位置过高/技术缺失执行状态为`blocked`；允许进入`core_pool`，不得仅因此降为watch。
35. **真正无核心仍允许0**：所有正式D候选均有明确identity failure（如缺同行优势、角色不独特、身份仅单日情绪、结构性反证过强），并有完整`core_zero_audit`逐D覆盖：通过。
36. **core_zero_audit禁用执行理由冒充身份失败**：identity_failure仅写低仓、不可执行、无买点、技术missing、不追：失败。
37. **同D双core均blocked但身份互补**：角色不同、同行优势不同、验证价值不同，即使execution均为blocked，仍可同时为core；仓位不得因此上调。
38. **低风险预算第4/5只core**：不再要求当前可执行，但必须有独立链路、独特身份/验证价值及前三只无法覆盖的信息；缺任一项失败。
39. **为恢复core增加搜索**：Identity判断已有④同行比较和deep证据足够时，不得额外机械检索；正常完整日仍受<=28 Research Budget Gate约束。


## V2.4.5 Environment Budget Stability 回归

40. **弱市硬锚仍给中低仓**：market_state=weak、dominant_style=defensive、breadth=severe_negative，且liquidity=contraction、relay=low、capacity=weak中至少两项成立；无有效override却给中低仓或更高：失败。
41. **弱市override伪造**：触发low anchor后想提高预算，但override只写“D多/core多/机会多”或只有一个独立反向族：失败。
42. **强市被机械压低**：market_state=strong、breadth正向、relay=high，且liquidity不收缩或capacity=strong；无两个独立负向override却给中仓或更低：失败。
43. **结构市不能被low anchor误杀**：market_state=neutral，即使breadth severe_negative且liquidity contraction，只要capacity/index有真实强确认，允许中仓；不得因弱市硬锚误报失败。
44. **中性轮动市中低仓**：market_state=neutral、breadth negative、liquidity contraction、relay=medium、capacity neutral，允许中低仓。
45. **环境预算与最终仓位分层**：`environment_budget_audit.budget`必须与`position_decision.environment_budget`一致；之后final_stance如高于预算仍按原规则要求两个独立确认族。
46. **环境预算禁止机会数量污染**：audit evidence/override引用候选数量、D数量、core数量或watch数量作为正向依据：失败。
47. **环境预算不增加搜索**：Environment Budget Gate只复用Step①证据，不得新增专门query；正常完整日仍受<=28 Research Budget Gate。
48. **过程与用户报告预算不一致**：process audit为低仓但报告第①步写中低仓，或position_decision为低仓但frontmatter/第⑦步写中低仓：失败。

## V2.4.6 Recall & Output Stability 回归

49. **候选数达标但Lens未完成**：已有10个候选，但turnover_capacity仍只有Top5且未检查内部强弱分歧；不得仅因10个候选而停止Discovery，必须完成Lens Sufficiency或降级theme_discovery。
50. **六Lens只写总6/6不够**：缺少任一`discovery_lens_scan`，或同一Lens重复记录多次：v2.4.6 process失败。
51. **容量分歧防漏**：高成交容量核心出现显著强弱分化，即使板块未进涨幅榜前列，也必须进入内部candidate或明确记录为何不是material signal；不得直接跳过。
52. **Driver Lens防漏**：价格/政策/订单/业绩存在独立显著Driver而板块涨幅一般时，必须进入candidate或明确`no_material_signal`理由。
53. **partial Lens repair**：Lens=`partial`且`high_salience_unresolved=true`，必须最多追加1次中性`coverage_repair_query`；无repair时必须有`coverage_degraded_reason`并降级，不得伪装ok。
54. **repair答案导向污染**：尚未被本轮证据发现的具体板块/股票直接写进coverage repair query，视为Discovery污染；已从Top成交/榜单出现的主体可用于核对其内部强弱。
55. **repair预算失控**：同一Lens出现2次及以上coverage repair，或repair使正常完整日总query>28且无研究预算例外：失败。
56. **新候选不得自动晋升**：capacity divergence/price-driver repair新增候选，只代表召回恢复；正式D/R仍必须通过原有独立Driver、宽度/容量、生命周期与风险门槛。
57. **新候选不得污染仓位/Core**：Candidate Recall提升后，若Environment证据与Core Identity证据未变化，仓位和core不得仅因候选变多上调/扩池。
58. **Fact Ownership压缩**：decision-changing重大事实必须至少完整出现1次，但不得在②③④⑥⑦和数据限制多处重复完整故事；后续只允许链路ID+增量动作。
59. **压缩不得删除决策链**：为缩短报告删除R2、material-news决策变化、core执行状态或技术冻结条件：Blind/Validator失败。
60. **输出预算正常日**：v2.4.6标准完整报告目标<=8500；>8700且无合格`output_budget_exception`：失败。
61. **空泛output exception**：只写“市场复杂/证据较多/为了完整”不能绕过输出门；例外必须有>=2个独立不可压缩链、不可压缩章节和“为何删掉会改变动作”的说明。
62. **发布跨维度否决**：目标Bug修好但任一关键能力明确低于v2.4.2 baseline，release gate必须NO-GO，不得以总分更高抵消。
