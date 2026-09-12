# Cross-Dimension Release Gate

本文件只用于版本研发/评测，不属于日常盘后运行步骤。目标是防止“修A伤B”：任何新版本只有在所有关键维度不低于冻结基线、且至少一个目标维度显著改善时才允许制造/发布。

## 1. Baseline Contract

### v2.4.2稳定性底线（18-run）
- Top3 D semantic >= 0.8519
- Top2 R semantic >= 0.8889
- core Jaccard >= 0.7646
- candidate semantic Jaccard >= 0.8063
- position / market_state / dominant_style consistency = 1.0
- validator pass = 100%

这些是多样本release floor，不要求单次运行完全相同。

### 同日工程基准（2026-09-10）
- 正常研究事件：约25
- 报告字符：约8722
- 关键决策：低仓、核心身份与执行分离、重大反证可重开决策链。

同日MVP必须说明差异来自方法改进、数据差异还是随机运行差异；不得用“整体更好”掩盖某关键维度退化。

## 2. Design Expert Panel

设计前必须由六个角色做Cross-Dimension Impact Matrix：
1. 市场结构专家；
2. Discovery / Information Retrieval专家；
3. 产业证据 / Counterevidence专家；
4. Portfolio / Risk专家；
5. Trading / Execution专家；
6. Reliability / Information Architecture专家。

采用Veto而非多数投票：任一角色证明方案会使关键维度低于baseline，方案退回。

## 3. Red Team

至少攻击：
- 目标Bug修复后是否损伤其他维度；
- 是否通过增加query/报告长度换表面质量；
- 是否通过固定答案、固定候选数、固定core数过拟合；
- 是否绕过cutoff、missing、Provider-independent、仓位与Core边界；
- Validator/例外机制是否可被空泛文本绕过。

## 4. Independent Review Expert Panel

Review Panel不参与方案设计，只看：
- baseline contract；
- 新旧报告与process；
- MVP/回归指标；
- Red Team结果。

每个关键维度给`PASS / CONDITIONAL / FAIL`。任一`FAIL`即NO-GO；不得以其他维度更优抵消。

## 5. Blind Evaluator

Blind Evaluator不看设计意图，只看匿名产物：
- opportunity/risk recall；
- D/R/Core/position；
- source/cutoff/missing；
- query efficiency；
- report information density；
- next-day executability。

## 6. Release Decision

只有同时满足：
1. 所有关键维度 >= v2.4.2；
2. 目标修复项在MVP和至少一组反例中有效；
3. 未出现新的一级决策回归；
4. 至少一个目标维度显著优于baseline；
5. package clean、Provider-independent、Validator/regression通过；

才允许制造正式版本。

正式Freeze仍需该版本自己的多Regime独立稳定性测试，不得继承旧版本数值后直接宣布稳定。
