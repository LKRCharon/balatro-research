# 已采集数据与用途：以实际落盘为准

核查日期：2026-10-05。已检查当前 8 个成对训练任务的 `decisions.jsonl`、`transitions.jsonl`、`blind_entries.jsonl`，以及既有 `results/telemetry/run-46.json`、正式验证公开汇总和新增混合控制驱动。新旧轨迹已有各自统计适配器，尚非统一的分析数据库。

## 当前实际保存

|数据|实际存放与字段|可以做什么|
|---|---|---|
|每一步决策|`decisions.jsonl`：action、before、method、params（含理由）、predicted、uncertain、decision_seconds|复盘动作、查错估分、分析耗时；理由是解释文本，不等于可验证因果证据|
|动作前后状态|`transitions.jsonl`：intent 的 id/method/params/before，result 的同 id/after|核对动作是否完成、金币变化、库存变化、真实计分；未匹配 intent 必须保留为不确定执行结果|
|进盲注前后|`blind_entries.jsonl`：action/before/after|定位商店结束时阵容与实际开战状态的差异，检查选盲注接口是否就绪|
|金币与资源|状态内 money、round 的 hands_left/discards_left/chips/reroll_cost/cashout_dollars，jokers/consumables/cards/hand|生成回合金币曲线、资源消耗、利息阈值、入战现金/强度曲线；单次金币差额可能混合购置、收入和费用|
|商店与卡包可见内容|状态内 shop/vouchers/packs/pack 的 card id/key/set、cost.buy/sell、modifier、卡槽与数量；used_vouchers|复原曝光、报价、可负担性、购买与没购买的选项、卡包实际打开后的内容；不开包的内部内容不采集|
|牌组和牌型|公开 belief 的 deck/unseen 多重集、starting_size，当前手牌、hands 的等级/基础筹码倍率/使用次数，公开动态目标|研究牌组构成、路线转型、抽牌机会与复制目标；不包含实际未来抽牌顺序|
|v4 搜索诊断|solver_diagnostics：attempted/supported/used/fallback_reason/action_changed、candidate_count/samples、样本两动作达标比例、耗时/缓存规模|测搜索覆盖率、回退分布、相对 v3 的动作变化与计算代价；样本达标比例不是实际胜率|
|每局结果与实验身份|result/protocol：任务与种子分组 ID/承诺、policy/engine 哈希、status、ante、动作计数、预测偏差、错误、总耗时|区分真实输局、错误和截断；成对比较相同训练种子；验证版本完整性和分区隔离|

## 已有派生统计和尚待接通的部分

旧 `cli/telemetry.py` 已经对历史 RPC 日志生成 schema 2：去重报价、初始/最新/实际购买价格、贴纸变化、稀有度、可负担性、卡包类型/参数、母卡包与已观察包内选项、回合进场/通关/结算/离店现金。核查的 run-46 文件确实存在这些字段，并非仅有代码设计。

正式验证公开 `telemetry.json` 比原始轨迹精简：已有金币/阶段曲线、选盲注与结算金币检查点、去重商店小丑稀有度数量、优惠券/卡包报价次数与已返回购买动作数量，以及失败盲注、目标和最终分数。**它没有完整报价价格表、包内结构表、贴纸分布或逐条购买后库存核验。**

当前成对训练使用 intent/result 格式，旧统计器读取另一种 RPC 格式，不能直接把它当作已经统一的数据库。现已另加 `headless/summarize_trace.py` 并通过事件去重/购买关联/混合来源及目录来源测试，为 8 个已完成任务生成 `results/combat-compare-001/telemetry.json`：974 个已返回动作金币检查点，811 个去重报价（304 个商店选项、92 个优惠券、192 个卡包、223 个已打开包内选项）。198 个商店小丑报价的原始 rarity 字段均缺失；本次明确以冻结 route_v3 事实目录补充，得到普通 126、不常见 58、稀有 14。报告记录目录 SHA-256 和每条 rarity_source；有原始 rarity 时原始值优先，二者都缺失才标 unknown。旧批次无逐步明确来源，974 条来源都保持 unknown，不按动作序号猜测控制来源。

## 不能从现有记录直接得到的结论

- 旧 scripted 批次只有整体控制来源；新 `hybrid_session.py` 已写每步 `sequence` 与 `origin=controller/script`，可和 transition id 精确关联。controller 不自动等于特定模型版本或人工来源，旧数据不回填冒充当时记录。
- 没有保存每个候选的全部估值、所有搜索场景和分数树；当前保存的是最终选择及诊断，不能完整还原当时所有备选排序。
- 没有逐组件收入归因表、单次 RPC/渲染等待耗时、统一绝对事件时间戳，也没有 LLM token/费用统计。现有 decision_seconds 是策略决策耗时，不能当作整步引擎耗时。
- 没有未访问商店、未打开包的内容、隐藏牌身份、未来牌序；也没有玩家主观趣味性、选择困难程度或反事实卡牌替换后的真实结果。
- 不能用“小丑购买后的胜率”直接判平衡。购买受到价格、存活阶段、已有阵容和策略偏好影响。稀有度出现率的分母应为去重的已观察商店小丑报价；它是此策略访问分布，不是无条件游戏生成概率。

## 混合控制的最小记录建议

新混合驱动已支持主控制器处理商店/成长、脚本处理允许的战斗动作，落盘 `sequence`、`origin`、before、method/params、predicted、at_utc，以及独立 economy 记录。下一步仍建议补齐 `controller_version`、`decision_id`、`parent_plan_id`、`policy_proposal`、`executed_action`、`override_reason` 与 `observation_hash`；这些不能写成已全部实现。若 agent 只定目标，由脚本执行，同样区分目标制定者与动作制定者。

在每次商店退出时保存结构化计划：目标路线、当前短板、现金下限、近期 Boss 风险、保留/替换组件及计划失效条件。战斗脚本只能使用当下公开状态与该计划；遇到不支持的机制显式回退并保留来源。计划、脚本提案与执行动作分别保存，才能衡量 agent 的成长规划是否改善结果，以及额外人工/LLM干预有多大。

混合局必须单独标记为 hybrid development。不能混入“冻结脚本无人干预”或“冻结 LLM 独立连胜”成绩。要比较纯脚本与混合策略，应事先固定训练种子队列、参与权限和每局预算，保留全部失败/错误；不能看到结果后挑选有利局计入统计。
