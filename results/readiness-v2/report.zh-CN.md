# 消耗牌就绪竞态修复

这是机制回归实验，不计入策略胜率。使用登记 TRAIN seed ID 1；两边都用管理接口加入星球牌并设置筹码、金币，以固定 cash_out 与 pack 边界。未读取验证或最终测试种子。

## 原因与修复

旧 cash_out 回调在 SHOP、STATE_COMPLETE 和商品存在时返回，pack 回调同样只等待阶段/卡包条件。此刻控制器锁或 STOP_USE 仍可能未释放，正常 can_use_consumeable 检查会拒绝星球牌。SHOP 不等于动作已就绪。

原创 readiness_v2.lua 在 use/pack 执行前、cash_out/buy/pack/use 成功返回前等待控制器锁、STOP_USE 和 play 区清空。保留原接口合法性检查；不设置 skip_check，不重发任何动作。15 秒超时会区分动作开始前和动作开始后，后者必须保留为结果不确定。

安装器只允许修改从未启动的新隔离实例，并更新实例输入哈希。原游戏目录、旧冻结策略、旧实例均不变。

## 匹配验证

相同训练种子与相同行为顺序，两个独立静音、无渲染实例：

- 未修补对照：cash_out 成功后立即 use Jupiter，复现 `Consumable 'Jupiter' cannot be used at this time`。停止该对照，不重试。
- 修补实例：cash_out → Jupiter 与 pack skip → Saturn 均成功，中间无轮询、延时或重发；各对应牌型等级恰好 +1、消耗牌槽归零。
- 修补统计：3 次完成屏障等待，0 次超时。
- 8 项单元回归通过，覆盖锁等待、观察刷新、合法性拒绝、执行前/后超时、阶段变化、play 区残留以及禁止修改旧实例。Lua 行为测试需 `pip install lupa`；缺依赖会明确 skip。

机器结果见 `control.json`、`patched.json`。`tools/probe_readiness.py` 可在新建隔离实例上重现实验。管理接口构造的机制测试不是正式游戏局，不能拿来计算胜率或连胜。

## v3 补充：商店购买并立即使用

v2 的两个完整 TRAIN 策略试跑保持原 helper 不变。代码审查另发现 `buy(use=true)` 同样会调用消耗牌可用性检查，因此单独发布 v3（只增加 buy 执行前的屏障），安装器默认 v3，可显式 `--version 2` 复现前版。

新隔离实例上重跑相同 cash_out/pack 机制测试，通过。接着在该 TRAIN fixture 中设置金币1000、添加普通小丑，执行 sell → buy(card=1,use=true)，二者之间没有查询或等待。商店自然生成的星球牌令 Pair 等级恰好 +1；新增 1 次执行前屏障等待，0 超时。结果见 `patched-v3.json` 与 `sell-buy-v3.json`。这同样不是策略评估，管理操作不能进入 win-rate 样本。

全部 16 项回归测试通过：v2 的原 7 项行为测试、v3 的同 7 项及 buy 执行前锁测试、1 项安装保护测试。v2 helper 字节未变。
