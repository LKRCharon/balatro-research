# no-sl-003 独立审计说明

严格审计通过：13 局全部自然失败，其中 8 局为已知失败种子的 hindsight replay，5 局为此前未使用的 TRAIN。两组必须分别报告，不能把重打样本解释为新种子胜率，也不能将本轮称为冻结策略的独立验证集评估。

共 839 次控制器决策、460 次脚本战斗决策；1,286 次游戏动作。1,311 条逻辑 transition = 1,299 次决策 + 12 次开局前 MENU 清理。首局从 MENU 开始，其余各局先由已结束的上一局返回 MENU，再执行唯一一次 start。审计逐局确认这些 MENU 位于 start 之前且来源为终局，不是中途重开或存读档。每个协议种子有唯一独占 claim，无重复会话、无未解决 mutation。

378 条出牌预测中，299 条可核验且全部在允许误差内，79 条不确定预测未计入误差率。零误差不表示全部机制已被正确建模。脚本动作均与 solver 记录匹配，限制在战斗阶段 play/discard/rearrange；策略动作由控制器提交。

记录中隐藏牌共出现 104 次，全部为 key=hidden、空 value、空 modifier 的脱敏占位。environment.public 在交给求解器之前删除隐藏身份，advisor 对这些占位产生的数字只是当前模型近似；conservative_score 遇隐藏牌返回未知，forward search 的 support guard 也拒绝隐藏身份状态。静态检查 work/research_ctl.py：只转述已脱敏快照和 numerical_scores，没有查询隐藏身份或实际未来抽牌顺序。不过该展示包装器省略了 numerical_scores 的 uncertain 字段，可能让近似分数看起来过于精确；这是显示限制，不能把这些数字解释为隐藏牌的真实分值。包装器未列入本轮冻结清单，当前静态检查也不能证明其历史每次调用内容完全相同。

原玩家 4 个存档文件与本轮及历史基线一致；TRAIN/validation/test 分区承诺未变，test campaign 数为 0。历史正式评估的 15 个 source 与 236 个 context 文件、上一轮 manual 冻结源码及 8 个失败结果、本轮协议列出的源码和引擎哈希均通过。research_session 固定导入 no_sl_solver；新建的 v2 求解器未列入或替换本轮冻结执行链。

本审计核查持久化日志、代码边界、独占分配和文件哈希，不能替代对所有操作系统行为的独立监控。errors.jsonl 的零条目也不代表所有本地包装器拒绝均被完整记录。未读取或公开原始种子；未修改冻结文件。
