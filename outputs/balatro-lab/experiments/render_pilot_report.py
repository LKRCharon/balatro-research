"""Render a completed pilot's measured results and explicit limits to Chinese Markdown."""
import json
from pathlib import Path
LAB=Path(__file__).resolve().parents[1]
def main():
    r=json.loads((LAB/'results/pilot-v1-report.json').read_text(encoding='utf-8'))
    if any(x['status'] in {'planned','running'} for x in r['runs']):raise ValueError('Pilot incomplete')
    selected=r['selection']['winner'];val=next(v for k,v in r['groups'].items() if k.startswith('validation:'))
    n=val['assigned'];w=val['counts'].get('win',0)
    rows=[]
    for label,g in r['groups'].items():
        role,name=label.split(':');weight='0.2' if name.endswith('20') else '0.6'
        ci=g['wilson95'];interval=f'{ci[0]*100:.1f}%–{ci[1]*100:.1f}%'
        rows.append(f'| {"训练" if role=="train" else "验证"} | {weight} | {g["assigned"]} | {g["counts"].get("win",0)} | {g["counts"].get("loss",0)} | {g["counts"].get("error",0)} | {g["mean_completed_blinds"]:.2f} / 24 | {interval} |')
    pairrows=['| '+str(i)+' | '+' | '.join(map(str,b['completed_blinds']))+' | '+f'{b["tail60_minus_tail20_blinds"]:+d}'+' |' for i,b in enumerate(r['paired_training'],1)]
    detailed=[]
    for x in r['runs']:
        score=f'{x["score"]:,} / {x["target"]:,}' if x['score'] is not None and x['target'] is not None else '—'
        detailed.append(f'| {x["run"]} | {"训练" if x["partition"]=="train" else "验证"} | {"0.2" if x["policy"].endswith("20") else "0.6"} | {x["seed_group"]} | {x["status"]} | {x["ante"]} | {x["blind"] or "—"} | {score} |')
    checks=sum(g['prediction_checks'] for g in r['groups'].values());matches=sum(g['prediction_within_one'] for g in r['groups'].values())
    actions=sum(g['total_actions'] for g in r['groups'].values())
    message=(f'**验证 {w}/{n} 通关，当前固定策略尚未证明高成功率。**' if w<n else f'**验证 {w}/{n} 通关，但样本仍小，不能视为金注连胜保证。**')
    text=f'''# 第一轮训练与验证：蓝色牌组金注

{message} 本轮完成 6 个训练种子 × 2 组参数，以及 8 个独立验证种子，共 20 局、{actions:,} 个动作。训练按事前规则选出风险权重 **{selected['tail_weight']}**，随后原样验证。最终测试集 **0 局，256 个种子继续封存**。

这是固定规则控制器的参数搜索，不是神经网络训练。局内没有人工或大模型接管，不读真实未来牌序，按真实引擎完整运行到胜负。后台静音、无画面、独立实验存档，未开启加速。

## 实测结果

| 分组 | 弃牌风险权重 | 种子数 | 胜 | 负 | 技术错误 | 平均通过盲注 | 胜率 Wilson 95% 区间 |
|---|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

通过 24 个盲注即胜。本轮不跳盲注。训练数据经过选优，区间只作描述；验证也属于开发阶段，不能冒充最终测试成绩。{n} 个验证种子不足以精确估计高胜率。错误任务留在分母，未偷偷排除。

![训练和验证推进情况](figures/pilot-v1-train-validation.png)

## 训练到底学了什么

冻结同一版规则、购买逻辑与路线，只调整弃牌目标中的低分位权重：

`Vλ = (1−λ) × 补牌后得分均值 + λ × 补牌后得分的下四分位数`

每个弃牌候选抽样 12 次。得分截断到本轮剩余目标，并给主牌型 4% 偏好。权重 0.6 更看重差手，0.2 更看重平均收益。这是启发式目标，不是通关概率。

事前选优顺序：胜局数、平均通过盲注数、失败时目标完成比例，最后才按较低风险权重决定。此次选择完全来自训练集，选择文件写入后才领取验证任务。

| 配对训练种子 | 权重 0.2 已过盲注 | 权重 0.6 已过盲注 | 0.6 减 0.2 |
|---|---:|---:|---:|
{chr(10).join(pairrows)}

两版在每个种子有共同起点；动作不同后，随机流可能分叉，不能说后续每个商店都相同。这 12 局只有 6 个独立种子组，不能当作 12 个独立训练种子。

## 质量与范围

本轮记录 {checks} 次确定性计分检查，其中 {matches} 次在 1 分容差内，{checks-matches} 次超出。随机触发、钩子、牛及隐藏信息单列为不确定预测，没有混入这一准确度分母。1 分容差用于界面倍率精度与浮点累计差异。

开跑前用原版 Lua 验证 8,010 个牌型案例；固定支持范围的 330 个历史确定性出牌中，329 个完全相同，另 1 个相差 1 分。四指、手臂、蔚蓝之铃、翠绿之叶及公开牌组记忆有专门检查。这个结果不等于全游戏所有交互已完全复刻。

策略有 79 种小丑的购买白名单，保留了简单成长、小牌、人头重触发、顺子和同花路线。暂不覆盖增删牌与改点数/花色路线，也没有完整实现整轮搜索。公开强化会记忆，已打弃牌会排除；背面牌身份仍有不确定性。不能据此给 150 张小丑做完整平衡排名。

## 失败如何指导下一版

第 22 局到第 5 底注大盲注时，阵容有抽象小丑、未断选票、备用裤子和二重奏，空一槽，五手实际合计 24,460，目标 37,500。按那五手的原始计分轨迹，仅作算术假设：若额外得到稳定 +50 筹码，总分增加 16,600 到 41,060。**这不是重放通关，也没有证明当时商店能买到这个组件**；它说明只调弃牌风险权重解决不了所有阵容短板。

下一版最值得比较的是两项结构性改变，而非继续细分 0.2/0.6：

1. 把单手均分目标换成“剩余手数内过关率”的有限深度束搜索，明确处理嘴巴锁型、坏手和弃牌耗尽。
2. 商店按整套阵容的边际收益、实际牌型频率和生命周期补短板；同时保留主力与备用牌型，减少只堆同一种倍率或只追稀有高分牌型。

这些是待验证方向，本轮没有给它们加上实测胜率。关于卡牌强弱，必须继续区分“卡牌条件价值低”和“控制器不会使用”。趣味性也尚未测量玩家评价，路线多样性只能作为代理指标。

## 每局底账

| Run | 分组 | 权重 | 种子组编号 | 结果 | 结束底注 | 结束盲注 | 得分 / 目标 |
|---|---|---:|---:|---|---:|---|---:|
{chr(10).join(detailed)}

原始动作、原因和真实计分在 [cli-runs](results/cli-runs/)，冻结策略结果和决策指标在 [experiment-runs](results/experiment-runs/)。已完成局的开局日志可复现种子；保留测试种子不在研究包中。

复现入口与约束见 [实验 README](experiments/README.md)。证据：[预登记计划](experiments/pilot-v1-plan.json)、[训练选择](results/pilot-v1-selection.json)、[验证分配](results/pilot-v1-validation-plan.json)、[全量统计 JSON](results/pilot-v1-report.json)、[完整性核验](results/pilot-v1-audit.json)、[模型定义](experiments/策略模型说明.md)。
'''
    (LAB/'第一轮训练与验证报告.md').write_text(text,encoding='utf-8')

if __name__=='__main__':main()
