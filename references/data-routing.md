# 数据路由与指标口径

## 目录

1. 数据职责边界
2. 交易日与完整度
3. 标准数据契约
4. 数据源优先级
5. 候选覆盖数据
6. 脚本用法
7. 指标口径
8. 失败降级与证据纪律
9. 编码与临时文件

## 1. 数据职责边界

将数据分为两类：

- **行情数据**：指数、个股、板块、成交额、涨跌家数、涨跌停、量价和技术指标；
- **公司/产业事实**：公告、财报、订单、客户、产品、技术、产能、价格、政策和景气。

行情决定市场、板块和技术状态；搜索只能发现事实线索，不能替代原始披露。不要把市场观点写成公司事实。

## 2. 交易日与完整度

用户指定日期时优先核验该日。未指定时，以数据源返回的最新完整A股交易日为准，时间只作辅助。

用市场级数据确认 `review_date`：主要指数日线、全市场成交额、涨跌家数及涨跌停统计。板块或个股局部缺失只影响对应结论，不得把已确认的市场交易日整体退回前一天。

报告级数据完整度只使用：

- `complete`：市场级必需数据齐全，候选分析所需数据无实质缺口；
- `partial`：市场日期可确认，但部分板块、个股或资讯缺失；
- `severe_missing`：无法可靠确认市场日期，或市场环境所需多个关键维度缺失。

方向级数据也按相同三档判断。即使报告级为`complete`或`partial`，某一方向若同时缺少持续性、核心强度、成交承载、扩散等多个关键维度，该方向仍按严重缺失处理：市场地位只能写“观察”，生命周期只能写“待确认”，置信度为低。没查到某方向数据不等于该方向不存在。

盘前没有新的完整日K时，沿用上一交易日MA、RSI9和BIAS20，只更新隔夜变量。

## 3. 标准数据契约

Adapter输出UTF-8 JSON。所有结果包含：

```json
{
  "schema_version": "1.0",
  "kind": "market_snapshot|theme_candidates|price_history|market_search",
  "source": "mx-data|mx-search|fallback",
  "query": "原始查询",
  "as_of_date": "YYYY-MM-DD或null",
  "fetched_at": "ISO-8601时间",
  "completeness": "complete|partial|severe_missing",
  "records": [],
  "missing": [],
  "warnings": []
}
```

### MarketSnapshot记录

```json
{
  "entity_code": "000001.SH",
  "entity_name": "上证指数",
  "date": "YYYY-MM-DD",
  "metrics": {"收盘": 0, "涨跌幅": 0},
  "units": {"涨跌幅": "%"}
}
```

市场快照还应尽量包含全市场成交额、上涨/下跌家数、涨停/跌停家数。缺项写入`missing`，不得补造。

### ThemeCandidate记录

```json
{
  "entity_code": "300394.SZ",
  "entity_name": "天孚通信",
  "date": "YYYY-MM-DD或null",
  "metrics": {"涨跌幅": 0, "成交额": 0, "权重": 0},
  "coverage_tags": ["provider_anchor", "index_weight", "liquidity", "daily_strength"]
}
```

`coverage_tags`只解释股票为何进入内部候选全集，不是核心评级。成分表未附交易日或未提供多日连续性时，结果为`partial`；调用者必须与已确认的市场交易日对齐，并在压缩名单前补充必要的价格历史。

### PriceBar记录

```json
{
  "symbol": "300750.SZ",
  "date": "YYYY-MM-DD",
  "open": 0,
  "high": 0,
  "low": 0,
  "close": 0,
  "volume": 0,
  "amount": 0,
  "adjustment_type": "qfq|none|unknown"
}
```

价格历史必须按日期升序。无法确认复权口径时使用`unknown`并产生警告。

### 错误契约

脚本失败仍输出结构化JSON：

```json
{
  "ok": false,
  "error": {"code": "AUTH|NETWORK|RATE_LIMIT|EMPTY|PARSE", "message": "不含密钥的说明", "retryable": true}
}
```

禁止在stdout、stderr、存档或错误信息中显示`MX_APIKEY`。

## 4. 数据源优先级

### 行情

1. 使用现有`mx-data`或`scripts/market_data_adapter.py`获取权威及时数据；
2. 主源失败时只切换一次已有备用行情能力，例如`a-stock-data`；
3. 仍失败则降低完整度并跳过受影响判断。

### 资讯与事件

1. 使用`mx-search`或Adapter的`search`模式发现最新线索；
2. 回到公司公告、交易所、监管、政策原文或其他原始来源核验；
3. 对会改变主线、核心股或持仓结论的关键事实，调用`a-stock-evidence-research`做快速核验；
4. 无法核验时标记“未证实”，不得把搜索摘要当作硬证据。

### 深度公司分析

只有新变量足以改变公司质量、盈利、估值或同行排序时，才调用`a-stock-investment-analysis`的最小充分范围。每日复盘不重复完整深研。

## 5. 候选覆盖数据

第2步赚钱效应和第3步方向判断优先保证五类证据：

- 宽度：板块上涨/下跌家数、大涨与涨停数量；
- 核心强度：盘面、趋势、容量核心表现；
- 持续性：昨日核心溢价和多日连续性；
- 成交承载：核心股成交额、流动性与大资金参与能力；
- 扩散：从核心细分向上下游或相关环节的扩散路径。

对与近期主线、用户持仓、昨日赚钱方向、高位风险或次日计划相关的重要退潮方向，另按镜像口径获取：

- 前期龙头、趋势核心和容量核心的连续负反馈；
- 板块上涨/下跌家数、大跌股、涨跌停变化；
- 昨日核心、追涨盘和补涨股的近期参与者盈亏；
- 缩量无人承接或放量兑现等成交承载/资金撤离证据；
- 资金是否迁往可识别方向。没有可靠迁移证据时记录“方向不清晰”，不推断为某个承接板块。

关键数字尽量记录日期、口径和来源。只有单一涨停、单一涨幅榜或搜索热度时，不得补齐为完整赚钱效应或主线证据。

确认重点方向后、压缩核心股名单前，为每条方向获取一次候选快照。候选集合应覆盖产业锚、上一期核心、成交活跃股、多日相对强势股和事件核心；最终1～3只上限不得反向限制数据获取。

候选快照优先包含：

- 股票代码和名称；
- 当日涨跌幅、成交额、换手与涨跌停状态；
- 近5/20/60日涨跌幅或相对板块强弱；
- 近期新高/回撤状态；
- 所属细分方向和事件标签。

不得用MA、RSI9或BIAS20建立候选集合。先用产业地位、多日连续性、相对强弱与流动性完成名单压缩，第9步才为`core_pool`以及第5步已标记的非核心风险持仓获取完整日线并计算具体执行位置。技术数据不得把淘汰股、观察锚或其他非持仓重新加入分析。

数据不足以覆盖重要同行时，将完整度降为`partial`，并在输出中说明未覆盖范围；不得把“没有查到”写成“不是核心”。

## 6. 脚本用法

### 妙想桥接

```powershell
python scripts/mx_bridge.py data --query "查询上证指数最新完整交易日收盘和涨跌幅" --output result.json
python scripts/mx_bridge.py search --query "光模块 最新公告 产业变化" --output news.json
```

桥接脚本只依赖Python标准库，从环境变量读取`MX_APIKEY`。

### 标准Adapter

```powershell
python scripts/market_data_adapter.py market --date latest --output market.json
python scripts/market_data_adapter.py candidates --theme "CPO" --date latest --limit 20 --output candidates.json
python scripts/market_data_adapter.py history --symbol 300750.SZ --bars 120 --adjustment qfq --output bars.json
python scripts/market_data_adapter.py search --query "隔夜AI产业重大变化" --output search.json
```

函数接口：

- `get_market_data(review_date=None)`
- `get_theme_candidates(theme, review_date=None, limit=20)`
- `get_price_history(symbol, bars=120, adjustment="qfq")`
- `search_market_info(query, limit=20)`

### 技术指标

```powershell
python scripts/calculate_indicators.py --input bars.json --output indicators.json
```

输入可为Adapter完整结果、PriceBar数组或包含`bars`/`records`的JSON。输出至少包含最新指标值及数据元信息。

## 7. 指标口径

优先使用至少60根前复权日线，日期升序且收盘价有效：

- `MA(n)`：最近n个收盘价的简单平均；
- `RSI9`：Wilder算法。先用前9个涨跌计算初始平均涨/跌，此后按`(前值×8+当日值)/9`平滑；只有涨无跌为100，只有跌无涨为0，全无涨跌为50；
- `BIAS20=(Close-MA20)/MA20×100%`。

指标输出固定包含：

- `as_of_date`
- `adjustment_type`
- `bar_count`
- `data_start`
- `data_end`
- `ma5/ma10/ma20/ma60`
- `rsi9`
- `bias20`
- `warnings`

不足60根时不输出完整技术执行结论；不复权或未知复权时允许计算，但必须警告除权影响。

## 8. 失败降级与证据纪律

执行：主源失败 → 备用源一次 → 降低置信度 → 跳过受影响结论。

判定降级固定为：

- 数据充分：正常判断；
- 部分缺失：可以判断，但明确缺失项、受影响维度并降低置信度；
- 严重缺失：只输出“观察 × 待确认｜低置信度”，禁止认定为主线、强化、退潮或其他强结论。

每次复盘记录：

- 行情基准日、消息事件日、来源发布日期和检索截止时间；
- 数据来源和单位；
- 是否前复权；
- 已知缺口、冲突和受影响步骤。

不同来源冲突时优先检查日期、复权、单位、板块口径和“事件发生日/报道日”差异。无法消除时并列披露，不擅自选取更符合观点的数字。

## 9. 编码与临时文件

- 所有Markdown和JSON固定使用UTF-8。Windows PowerShell读取时显式使用`-Encoding utf8`，运行Python时设置`PYTHONUTF8=1`，不得为正常UTF-8文件临时编写乱码修复脚本。
- 优先复用本Skill脚本及现有A股数据能力，不在工作区编写一次性行情采集器、汇总器或指标脚本。
- 中间文件写入系统临时目录或本次运行独立临时目录，不写入项目根目录的固定`.review-work`。
- 成功后清理临时目录；清理受限或执行失败时保留现场并在最终答复中明确路径、文件数量和原因。正式复盘存档不得被清理。
