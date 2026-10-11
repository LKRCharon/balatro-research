# 经验库检索与建模使用说明

这里是归档检索工具，不接入当前牌局、不自动选择动作，也不访问进行中的手牌。`build_casebook.py` 对新人工十局只纳入已有终局 result 的目录；仍在运行的目录在读取 decisions 前排除，并单列数量。

当前最终快照包含历史 6506 个案例，加上 TRAIN 32–41 全十局的 1567 个游戏动作尝试，共 8073 个。新批次 2 胜 8 负，全部由主模型逐步操作，脚本决策为 0，属于自适应 TRAIN 演示，**不是冻结策略评估**。1567 个尝试含 2 次明确未执行拒绝，成功游戏动作是 1565；包含开局的 controller decisions 为 1577，另有 2 次终局清理，计数口径不可混用。它也不能同历史验证/脚本结果混算胜率。

## 命令入口

机制条目可以独立检索，无需加载案例、结果或当前游戏：

```powershell
python outputs/balatro-lab/experiments/casebook_query.py --rules outputs/balatro-lab/docs/prospective-mechanisms.json --joker j_perkeo
```

整批 TRAIN 32–41 现已终局并完成严格审计。`--manual-runs` 可限制重建范围；本次最终构建显式指定 32 至 41。以后新批次仍应先排除运行中的目录，完成前不把阶段草稿当最终结果。

下列命令从研究工作区根目录执行。命令示例仅查询历史归档，不表示当前局面应该买哪张牌。

```powershell
# 重建；排除没有终局结果的新人工目录
python outputs/balatro-lab/experiments/build_casebook.py --lab outputs/balatro-lab --work work --output outputs/balatro-lab/results/casebook/decision-casebook.json

# 查看批次、分区、控制来源、动作与完整度计数
python outputs/balatro-lab/experiments/casebook_query.py outputs/balatro-lab/results/casebook/decision-casebook.json --inventory

# 取出低现金、存在易腐组件的历史购买案例；默认只取 TRAIN 且不返回事后结果
python outputs/balatro-lab/experiments/casebook_query.py outputs/balatro-lab/results/casebook/decision-casebook.json --method buy --perishable --cash-max 10 --limit 10

# 以阵容中持有或本次选购的小丑筛选
python outputs/balatro-lab/experiments/casebook_query.py outputs/balatro-lab/results/casebook/decision-casebook.json --joker j_blueprint --cohort manual-ten --limit 10

# 只有明确复盘模式才能返回实际分数/最终结果；已消耗验证还需单独开关
python outputs/balatro-lab/experiments/casebook_query.py outputs/balatro-lab/results/casebook/decision-casebook.json --research --include-consumed-validation --cohort formal-validation-001 --ante-max 2 --limit 10
```

另支持 `--boss "The Water"`、`--origin root_agent`、`--ante-min`、`--cash-max` 和 `--output 文件路径`。排列按归档顺序，不是优劣排序；limit 限制返回条数，不表示完整分母。默认不会返回未知分区、TEST 或已消耗验证，也不会附带 labels。研究模式仍不会读取 TEST。

## 字段怎样用

|字段|可复用用途|边界/缺失|
|---|---|---|
|lineage、controller_origin、policy_hash|分离全手动、混合和脚本；锁定版本、只比较适当队列|旧源不一定有精确模型/推理档位；控制来源不是最优标签|
|input 的现金、资源、底注、Boss 目标|经济断层、资源短缺、目标增长分析|不是剩余局面真实胜率；现金变化尚未分解租金/利息/触发收入|
|lineup 与贴纸、joker_limit|易腐依赖、永恒占槽、租赁和复制组合检索|不含全部动态计数或倒计时；不能还原完整结算器|
|hand_levels 的 chips/mult/level/played|比较牌型投资和基础筹码/倍率结构|不是整手最终 C/M，也不含手牌或未来抽牌|
|decision 的 method/target_key/selected_count/predicted_score|购买、消耗、出弃牌模式与预测偏差定位|不给完整候选集合、概率树或实际牌索引，不能直接重放|
|evidence 哈希与连接方式|定位原始证据是否改变，审计前后状态关联|公共摘要不含原始日志；完整复核需本地受控档案|
|labels|仅用于离线复盘、结果分析|实际分数、后续金币、最终胜负不得成为当步决策输入|
|plan.recorded|识别源中是否存在显式计划引用|历史计划多缺失；未导出自由计划文本，不事后推断目标|

已有报价/稀有度/券/包/价格变化统计保存在专门 telemetry，而不是重复塞进每条案例。以 card key 连接冻结事实目录时必须保留目录哈希和 rarity_source；报价曝光的分母是去重、实际访问过的选项，不能叫无条件生成概率。

## 下一轮复用顺序

先按 Boss/机制提取回归案例，再对成对训练种子做策略比较。模型训练必须回到私有注册表按 seed_group 分组；此公开案例库刻意不提供原始种子，不能拿随机打散动作行代替种子隔离。人工理由未导出，避免文字中包含未来结果、完整手牌或种子；需要加入时应独立审核并只作标签/解释。

本次全十局完成后已经重跑构建器与 inventory，并保留失败及拒绝证据。385 次预测中 326 次可核对值全部一致，59 次不确定预测单列；这不证明每种规则或最优出牌已覆盖。最终 TEST 仍是 0 次任务；玩家四个原存档哈希一致，旧冻结版本通过完整性检查。只有另行冻结模型/提示/工具/策略、预注册新留出队列之后，才可做新的正式评估。
