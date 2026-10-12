# 可见手牌的结构边际分析

`experiments/strength_probe.py` 只读已终局 TRAIN 的 decisions.before（含当时公开 belief），默认取每局末尾三次出牌观察。工具不读取种子注册表、不执行游戏，也不保存手牌原文。样本是失败诊断用的尾部局面，不是随机样本。

```powershell
python outputs/balatro-lab/experiments/strength_probe.py --runs-root work/experiments/manual-ten-002 --runs 32 33 34 35 36 37 38 39 40 41 --max-per-run 1 --output outputs/balatro-lab/results/manual-ten-002/strength-probe.json
```

每个状态固定同一可见手牌，重新搜索基线最优出牌、逐小丑结构移除、逐位置重排，以及每一种星球升一级的最优出牌分。`relative_delta = alternative / baseline - 1`，不是通关率变化。已暴露商店的可负担小丑也按直接添加/替换逐项比较；现金、负片槽位和永恒约束只作结构筛选，`execution_legal_verified=false`。不把战斗阶段残留商店列表当成可以立即购买的动作。

抽象、模具由现有 scorer 重算；侠盗的显示倍率依赖其他小丑售价，工具先在复制状态中刷新这一数值。蓝图/头脑风暴随位置变化重新计算复制链。易腐、租赁等原状态保留；租赁额外报告每轮3元负担。永恒小丑仍可做理论移除实验，但明确标记不能正常出售。

移除是瞬时结构反事实，**不是实际执行卖牌**：不触发营火、礼品卡等动态交易机制，不额外注入卖价；商店替换只计已知售价和报价，不模拟售卖触发链。因此不能把 delta 直接解释为建议出售。星球升级也仅改变牌型等级，尚未模拟天文台消耗保留、星座成长或消耗牌使用触发。

随机牌、隐藏牌、已标记不确定组件或不支持的小丑返回空值并排除。其他条目只标为 `deterministic_route_v3_model_not_engine_proof`：确定性模型预测仍需原引擎复核，并非声称所有规则已精确实现。该工具不会分解出虚假的筹码/倍率归因；非线性交互使用完整阵容重新估分。
