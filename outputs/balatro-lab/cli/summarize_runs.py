"""Build an honest exploratory report from completed CLI logs (never queries the running game)."""
import collections, hashlib, json, math
from pathlib import Path
import balatro_cli as cli

def main():
    summaries=[]; seen=set(); observed_runs=collections.defaultdict(set);held_runs=collections.defaultdict(set);triggers=collections.Counter(); events=0
    for p in sorted(cli.RUNS.glob('run-??-outcome.json')):
        out=cli.read(p); rid=out['run']
        rows=[json.loads(line) for line in (cli.RUNS/('run-%02d.jsonl'%rid)).read_text(encoding='utf-8').splitlines()]
        states=[r['result'] for r in rows if 'state' in r.get('result',{})]
        final=next(s for s in reversed(states) if cli.terminal(s))
        blind=next((b for b in final.get('blinds',{}).values() if b['status']=='CURRENT'),final.get('blinds',{}).get('boss',{}))
        for row in rows:
            s=row.get('result',{})
            for area in ('shop','pack','jokers'):
                for card in s.get(area,{}).get('cards',[]):
                    if card.get('set')=='JOKER':
                        seen.add(card['key']);observed_runs[card['key']].add(rid)
                        if area=='jokers':held_runs[card['key']].add(rid)
            if row['method']=='play':
                for step in s.get('round',{}).get('last_hand',{}).get('steps',[]):
                    if step.get('by','').startswith('j_'):triggers[step['by']]+=1
        acts=sum(r['method'] not in cli.READ_ONLY and r['method']!='lab_stop' for r in rows)
        events+=acts
        ph=cli.read(cli.RUNS/('run-%02d-policy.json'%rid),[])
        if isinstance(ph,dict):ph=[ph]
        frozen=bool(ph) and len({p['code_sha256'] for p in ph})==1
        commitment=next((r['params'].get('seed_commitment_sha256') for r in rows if r['method']=='start'),None)
        commitment_ok=bool(commitment and out.get('seed') and hashlib.sha256(out['seed'].encode()).hexdigest()==commitment)
        summaries.append({'run':rid,'seed':out.get('seed'),'sampling':out['sampling'],'win':out['win'],
                          'ante':out['ante'],'round':out['round'],'boss_or_blind':blind.get('name'),
                          'score':final.get('round',{}).get('chips'),'target':blind.get('score'),
                          'actions':acts,'policy':ph[-1]['policy'] if ph else 'manual','policy_revisions':len(ph),
                          'started_policy':ph[0]['policy'] if ph else 'manual',
                          'policy_hash':ph[0]['code_sha256'] if ph else None,'final_policy_hash':ph[-1]['code_sha256'] if ph else None,
                          'completed_with_frozen_code':frozen,'autonomous_win':bool(out['win'] and frozen),'seed_commitment_verified':commitment_ok,
                          'valid_for_winrate':out['sampling']=='randomized_seed' and bool(ph) and commitment_ok,
                          'exclusion': 'adapter calibration and technical restores' if rid==1 else ('explicit seed / development comparison' if out['sampling']=='seeded_repeat' else ('native cursor-dependent seeds; independence not established' if out['sampling']=='unseeded' else (None if commitment_ok else 'missing seed commitment')))})
    predictions=[json.loads(x) for x in (cli.RUNS/'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    known=[p for p in predictions if not p.get('uncertain') and p.get('actual') is not None]
    matches=sum(abs(p['predicted']-p['actual'])<1e-6 for p in known)
    fixed=[s for s in summaries if s['valid_for_winrate']]
    cohorts=collections.defaultdict(list)
    for s in fixed:cohorts[s['policy_hash']].append(s)
    cohort_rows=[]
    for code,ss in cohorts.items():
        nn=len(ss);ww=sum(s['autonomous_win'] for s in ss);z=1.959963984540054;p=ww/nn;den=1+z*z/nn
        mid=(p+z*z/(2*nn))/den;half=z*math.sqrt(p*(1-p)/nn+z*z/(4*nn*nn))/den
        cohort_rows.append({'policy':ss[0]['started_policy'],'hash':code,'runs':[s['run'] for s in ss],'wins':ww,'n':nn,
                            'technical_interventions':sum(not s['completed_with_frozen_code'] for s in ss),
                            'estimand':'Autonomous clear: any technical intervention is counted as failure, never dropped.',
                            'wilson95':[max(0,mid-half),min(1,mid+half)]})
    # Do not pool different policy hashes for the reported policy win rate.
    fixed=cohorts[cohort_rows[-1]['hash']] if cohort_rows else []
    wins=sum(s['autonomous_win'] for s in fixed); n=len(fixed)
    z=1.959963984540054
    if n:
        phat=wins/n; den=1+z*z/n;mid=(phat+z*z/(2*n))/den;half=z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/den
        interval=[max(0,mid-half),min(1,mid+half)]
    else:interval=None
    summary={'completed_runs':len(summaries),'runs':summaries,'actions_logged':events,'observed_jokers':sorted(seen),
             'observed_joker_count':len(seen),'observed_scoring_steps_by_joker':dict(triggers),
             'deterministic_predictions':len(known),'exact_matches':matches,'all_predictions':len(predictions),
             'fixed_policy_random_runs':n,'fixed_policy_wins':wins,'wilson_95_interval':interval,
             'frozen_randomized_cohorts':cohort_rows,'native_seed_independence_retracted':True,
             'seed_population':'Uniform 8-character seeds from 1-9,A-Z via OS entropy, passed as seeded games and hidden from policy until termination. Not the native cursor-seed distribution.',
             'warning':'Small exploratory sample. Repeated seeds, cursor-derived native seeds and calibration are not independent win-rate evidence. Modded backend parity is incomplete.'}
    cli.write(cli.LAB/'results/cli-summary.json',summary)
    table='\n'.join('| {run} | {sampling} | {policy} | {ante} / {round} | {boss_or_blind} | {score:,} / {target:,} | {result} |'.format(**s,result='胜' if s['win'] else '负') for s in summaries)
    ci='未取得符合独立抽样条件的完整局' if not n else f'{wins}/{n} 胜；Wilson 95% 区间约 {interval[0]:.1%}–{interval[1]:.1%}'
    cohort_table='\n'.join(f'| {c["policy"]} / {c["hash"][:12]} | {c["runs"]} | {c["wins"]}/{c["n"]} | {c["wilson95"][0]:.1%}–{c["wilson95"][1]:.1%} |' for c in cohort_rows)
    register=cli.read(cli.LAB/'data/card_balance_register.json')
    for card in register['cards']:
        k=card['id'];card['live_descriptive_evidence']={'observed_in_runs':sorted(observed_runs[k]),'held_in_runs':sorted(held_runs[k]),'scoring_log_steps':triggers[k],
            'interpretation':'Exposure and triggers only; not causal card value or a tier ranking.'}
        if held_runs[k]:card['runtime_balance_evaluation_status']='full_run_exposure_recorded; causal_value_not_estimated'
    cli.write(cli.LAB/'data/card_balance_register.json',register)
    design=cli.read(cli.LAB/'data/experiment_design.json')
    design['actual_live_games_played']=len(summaries)
    design['current_live_backend']='Pinned azazo1 modded backend; whole-run vanilla parity unproven.'
    design['sampling_revision']='Native headless cursor-derived seeds repeat; exclude from iid estimates. New randomized_seed runs use private OS entropy and disclose seed after outcome.'
    design['live_save_protocol']='Original Balatro root is read-only and hash-checked. Experimental profile 1 belongs to a separate Balatro-Lab-20261004-CLI identity.'
    cli.write(cli.LAB/'data/experiment_design.json',design)
    text=rf'''# CLI 实战与固定范式：第一轮研究

这轮已经把游戏接入无画面的 CLI，并做出不调用大模型的规则脚本。**目前是可检验的策略原型，还不是高成功率通关方案。** 正式判断卡牌平衡，也不能把脚本不会使用某张牌直接解释为那张牌设计差。

## 已完成与实测结果

- 蓝色牌组、金注、第 8 底注首领算胜。全部解锁，不改钱、分数、商店概率或抽牌结果。
- 使用独立 `Balatro-Lab-20261004-CLI` 存档。用户原存档 4 个文件先备份，最终逐文件核对 SHA-256；验收在 `results/cli-environment-verification.json`。
- 最终后端运行在不可见的 Windows 桌面，绘制关闭，音频总输出和游戏各音量均为 0。没有通过鼠标操作游戏画面。
- 记录 {len(summaries)} 局完整结果、{events} 次操作，实验实际见过 {len(seen)} 种小丑；不是 150 张牌都完成了实战评估。
- {len(known)} 次没有标注随机或隐藏信息的得分预测中，{matches} 次与实际得分完全一致。它只验证这些遇到的组合，不能外推成全规则验证。

| 局 | 抽样方式 | 脚本版本 | 底注 / 回合 | 最后盲注 | 累计分 / 目标 | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
{table}

![逐局通过盲注数量；不同抽样方式分色，不能把开发局与重复种子混成胜率](figures/cli_runs.png)

预先启动的独立抽样批次，自主通关率为：**{ci}**。发生技术中断或需要修改代码的局一律按该原始策略失败计入分母。样本量和当前结果不支持“高成功率”的说法。这个区间只描述该脚本、该后端与本次种子分布，不代表蓝色牌组上限，也不是原版无种子连胜纪录。

| 固定策略 / 代码哈希前缀 | 局号 | 通关 | Wilson 95% 区间 |
| --- | --- | --- | --- |
{cohort_table}

**抽样审计修正：** 日志中旧标签 `unseeded` 仅表示调用时没有指定种子，不能证明独立随机。原版 `generate_starting_seed()` 读取鼠标位置和停留时间；无画面运行中第 12 局实际重复了第 6 局种子。因此撤回先前把第 4–6 局直接用于独立随机胜率区间的做法；旧局仍保留作实战与开发记录。从第 13 局起改用操作系统随机源，在 `1–9,A–Z` 的 35 个字符中均匀抽取 8 位种子，通过种子模式运行。策略看不到种子和抽牌顺序，开局只留下 SHA-256 承诺，结束后核对并公开种子。这是明确的实验抽样总体，不等同于原版鼠标生成器的分布。

第 1 局是接口校准：曾少领第 2 回合的 4 元奖励，还为修复程序恢复过同一局的技术检查点，故排除胜率统计。第 2–3 局用于开发策略，其中第 3 局复用了第 2 局种子；两局不能当作两个独立随机样本。其余局以各自保存的策略代码哈希为准。

## 实战带来的修正

1. **贴纸决定持有成本。** 两张租赁牌每回合合计扣 6 元。易腐牌失效后继续占槽；如果又带租赁，仍然扣钱。v0.4 会卖出可出售的失效牌，限制新购租赁牌数量，并限制永恒过渡牌。
2. **成长牌必须配套行动。** 全息影像没有加牌来源时仍然是 X1。仅仅看“稀有成长乘倍”标签会高估它。固定规则现在要求已有 DNA / 证书等加牌来源才主动购买它。
3. **保留已经成型的牌。** 旧弃牌启发式可能拆掉现成同花去追四张顺子。现在对已经形成的顺子、同花、葫芦等，只考虑更换组合外的牌。
4. **背面牌需要主动获得信息。** “房屋”首领的背面起手让旧脚本连续打小牌，无法组织有效组合。新规则先弃掉背面牌获取可见牌；弃牌用完时通过一次打出多张牌改善后续信息。
5. **蓝色额外一手有三种用途。** 它可以增加过关余量、留下来换 1 元，或付出这 1 元机会成本换取绿色小丑 / 公交车 / 超新星等成长。当前脚本仅在保留现成过关组合、且还剩至少 3 手时尝试这种成长操作。

第 1 局最后面对“墙”需要 36,000 分，只打出 10,464 分；两张临时牌失效和缺少有效乘倍是可直接观察到的瓶颈。第 2–3 局同种子比较从第 2 底注小盲推进到了首领，说明这些规则会改变结果；一次对照不能量化平均收益。

v0.5 又加入保守得分覆盖率：使用独立的固定随机数，对标准 52 张牌抽样 16 组假想手牌，估算每组当前阵容的最佳得分，取下四分位数 \(q_{{25}}\)。定义 \(\rho=hq_{{25}}/T\)，当 \(\rho<1.25\) 时降低现金保留门槛、优先补强。第 7 局用第 6 局的种子复打，从第 3 底注首领推进到第 4 底注小盲，仍然失败。这说明规则有所改变，不足以说明平均胜率提高。

v0.6 修正了主牌型选择、空槽购买与可见牌的计分顺序，并加入有限候选的弃牌抽样。然而第 8 局把黑板 X3 换成了条件加倍率牌，较同种子的第 5 局更早失败。v0.7 改为比较替换前后**整套阵容**的 \(0.4q_{{25}}+0.6q_{{50}}\)，要求至少改善 12% 才进行普通替换；第 9 局到第 5 底注首领，43,496 / 50,000 分，仍然失败。v0.8 在得分压力下允许支付绿色小丑等的弃牌成本，通过抽样比较净改善，避免“有绿色就永远不弃牌”的僵化规则。所有阈值都是待验证的策略参数。

这个 \(\rho\) 不是过关概率：抽样没有完整模拟多手牌消耗、弃牌、增强牌与所有首领限制，阈值 1.25 也是待验证的参数。它比“无论多弱都存钱”多使用了一项明确的数学信号，但仍需要独立测试集校准。

## 数学建模方式

把可见状态记为

$$s=(a,b,h,d,\$,J,L,H,\mathcal D,\tau).$$

分别表示底注、盲注限制、剩余出牌与弃牌、现金、小丑阵容、牌型等级、可见手牌、已知牌库构成和贴纸期限。对背面牌及未来摸牌维护信念分布，而不读取真实隐藏值。动作是出牌、弃牌、购买、出售、使用消耗牌和换线路。

完整目标应是最大化第 8 底注过关概率，而不是最大化当前这一手分数：

$$V(s)=\max_u\mathbb E[V(s')\mid s,u],\quad V(\text{{胜}})=1,\ V(\text{{负}})=0.$$

当前代码没有求解完整的这个方程。它使用一个可审计近似：列举可见手牌的合法 1–5 张组合估分，套用弃牌规则，再用价格、贴纸、空槽与协同规则管理商店。这些规则不需要语言模型；未知机制或确定性估分不一致时暂停，保留局面供检查。

对常见计分链，可先写成

$$S=(C_0+C_+)\,(M_0+M_+)\prod_i X_i.$$

于是加筹码的价值取决于现有倍率，加倍率的价值取决于现有筹码，乘倍的价值取决于其作用顺序与已有总量。人头重触发、留手钢牌、逐牌倍率等要扩展成有顺序的触发图，不能硬塞成同一个乘积。

衡量稳健性时，应关注剩余多手总分越过目标的概率

$$P\!\left(\sum_{{t=1}}^h S_t\ge T\mid s\right),$$

并检查最差首领、得分下分位数和备用牌型。单手最高分很容易掩盖抽不到核心牌型时的失败风险。

租赁牌持有 \(r\) 个回合的直接净成本近似为

$$K=\text{{买价}}+3r-\text{{卖价}}+\text{{损失的利息}},$$

还要加上被占用槽位的机会成本。易腐牌的收益窗口只计算剩余有效回合，不能把它当作永久强度。

## 三条候选范式

这些是后续需要用独立种子验证的线路模板，**不是本轮已经证实稳定通关的三条线路**。当前脚本只实现其中一部分，许多规划和转型条件仍是启发式。

| 线路 | 进入条件 | 中期目标 | 后期缺口与退出条件 |
| --- | --- | --- | --- |
| 小牌成长 | 绿色小丑、公交车、超新星或半张小丑等能稳定支持高牌 / 对子 | 成长倍率 + 稳定筹码来源；集中升级主牌型；在安全时用额外手数成长 | 补稳定 X 倍率；成长过晚、经济透支或特殊首领限制时转型 |
| 人头重触发 | 照片 / 悬挂选票 / 喜与悲等已有可用组件；不能只等梦想中的组合 | 提高人头出现率和基础牌型倍率；按触发顺序排列打出的牌 | 不能仅靠白板照片 + 选票就假定足够；需等级、筹码或后续乘倍，留非人头备用方案 |
| 牌型等级与条件乘倍 | 土星、跑步选手支持顺子，或已有对子等级与二重奏等配合 | 集中等级投资、改善手牌与弃牌资源，达到多手稳健过线 | 牌型成型率不足就退出；防“眼睛”“嘴”“针”等改变手数或牌型约束的首领 |

可以把线路选择写成有限状态控制器：过渡保命 → 已取得组件匹配的线路 → 检查未来目标的覆盖率 → 补缺口 / 转型。线路并不固定对应某 5 张小丑，优先表达“筹码、加倍率、乘倍率、经济、获取牌型”五类功能。

衡量一条线路时，需要分别估计“足够早凑到核心的概率”和“凑到核心之后的过关率”。只统计成型后的胜率，会把难以出现的线路误报为稳定路线。

## 把路线目标写成可检查的数值

安装版金注的普通小盲基础目标依次为 300、1,000、3,200、9,000、25,000、60,000、110,000、200,000；普通大盲乘 1.5，普通首领乘 2，特殊首领另算。因此第 5 底注普通首领为 50,000，第 8 底注普通首领为 400,000，紫罗兰容器则为 1,200,000。可见“前期每手几千分”距离后期强度还有很大缺口。来源：本机 `functions/misc_functions.lua:get_blind_amount` 与首领原型，不是从本轮最高进度外推。

可以预留一手缓冲，用 \(q_{{25}}\ge T/(h-1)\) 作为候选强度目标（仅启发式，不是概率保证）。蓝色通常有 5 手，则普通第 8 底注首领要求下四分位单手约 100,000 分。小牌线路的一组示例是 \(C=250,M=45,X=9\)，单手 101,250；人头线路要把基础牌型等级、逐牌加倍率、照片重触发和后续 X 倍率按顺序相乘。这里的数字是待达到的组合功能，并不保证一局能获得对应组件。

真实连胜还要比通关均值更严格。若各局胜率稳定且独立，预先指定连续 \(k\) 局全胜概率为 \(p^k\)；即使 \(p=0.95\)，20 连胜也只有约 35.8%。固定样本设计中，要在“全部成功”的情况下取得单侧 95% 精确下界超过 90%，也至少需要预先确定的 29 个独立测试局全胜；不能从大量失败中挑出一段 29 连胜再套这个结论。本轮远未达到这一证据标准。

## 如何评估卡牌平衡与趣味性

最终每张牌应估计条件边际价值：

$$\Delta_j(s)=P(\text{{胜}}\mid s,\text{{拿 }}j)-P(\text{{胜}}\mid s,\text{{最好的替代动作}}).$$

同一个种子从同一决策点采用两种方案，能减少随机差异；但行动改变后，随机序列的消费顺序也会改变，所以不能假设后续商店仍逐项相同。统计应按种子聚类，训练用种子与最终测试种子分开。

“设计差”至少分为三种假设：数值回报低、合理使用场景过窄、理解 / 操作负担与收益不匹配。需要在不同线路、底注、金注贴纸和价钱条件下比较，避免把专精卡对通用脚本的不适配当作低强度。

趣味性不能从胜率直接推出。可量化的代理指标包括：有竞争力的选择数量、转型次数、可行线路多样性、重复动作比例，以及失败是否由可理解的决策造成。仍需玩家评价来判断这些指标是否真的对应有趣。

原有 `data/card_balance_register.json` 覆盖全部 150 张小丑；未测得的全局胜率贡献和玩家趣味性继续保留空值。本轮看到或使用某张牌，不等于已经测出了它的平衡程度。

## 后端可信度与复现

后端来自 `azazo1/balatro` 固定提交 `71c8f71e450ef06aeb5dafc5dcb761cc58ac0ae0`，基础版本 1.0.1o，带 Steamodded 和 CLI 适配。原版安装未修改。此前静态目录和局部计分已与安装版核对，但这个有模组的整局后端尚未完成逐种子对原版的全流程一致性证明。

本轮修复了两个可复现接口缺陷：结算就绪必须认本轮按钮；卖牌完成必须比较卡对象，不能把可能重复的 `sort_id` 当唯一身份。另修复了计分日志把逐张选牌时的高牌预览记作最终基础分的问题。

第 13–17 局是事先启动的 5 局独立抽样批次。第 17 局遇到“嘴”：脚本错误地把一次被封禁的高牌也当成可继续使用的牌型，预测 30 分，实际 0 分，因核对失败自动暂停。v0.8.1 改为从公开出牌历史锁定首手牌型；从原局面继续，没有读档或重打，最终仍失败。其中 4 局由原固定代码完整结束，1 局经历技术中断；自主通关仍按原始 v0.8 策略 0/5 成功计数，不剔除中断局。修复后局面仅作为开发记录，不给原策略补计成功。

在线预测记录保留修复前的这一次错误，报告不会把历史数字改成全对。`cli-replay-validation.json` 则检验当前修正后的模型在已记录、确定性且可见的出牌上的回算一致性；两者是不同的验证问题。Lua 测试文件 24 项通过、1 项 Android 媒体 FFI 失败、3 项 POSIX 依赖跳过；Python 启动器测试 5 项通过、1 项跳过。完整仓库测试未全部通过，整局对原版的随机流程一致性也未证明。

启动、运行、同种子复打和停止命令见 `cli/README.md`。逐动作记录、所有失败、策略哈希和出牌预测均在 `results/cli-runs/`；汇总机器数据为 `results/cli-summary.json`。
'''
    (cli.LAB/'CLI实战与固定范式.md').write_text(text.replace(chr(92)*2,chr(92)),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('completed_runs','actions_logged','observed_joker_count','deterministic_predictions','exact_matches','fixed_policy_random_runs','fixed_policy_wins')},ensure_ascii=False))

if __name__=='__main__':main()
