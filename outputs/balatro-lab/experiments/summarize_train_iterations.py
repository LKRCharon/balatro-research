"""Public-safe fixed TRAIN comparison across complete or active iteration shards.

Repeat --iteration LABEL=SHARD for a sharded cohort. Only finished episodes'
logs are read. No raw seeds, source paths or card-level observations are exported.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
import statistics


def read(path):return json.loads(path.read_text(encoding='utf8'))
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines() if x.strip()] if path.exists() else []
def avg(values):return round(statistics.mean(values),3) if values else None


def summarize(groups):
    report={'purpose':'fixed_train_iteration_comparison','independent_winrate_eligible':False,'iterations':[]}
    comparison=defaultdict(dict)
    for label,shards in groups.items():
        if not re.fullmatch('[A-Za-z0-9_-]+',label):raise ValueError('Public iteration labels must not be paths')
        assigned=set();sessions=[];active=[];cash_by_ante=defaultdict(list)
        for shard in shards:
            protocol=read(shard/'protocol.json');assert protocol['partition']=='train' and protocol['strategy_winrate_eligible'] is False
            ids={j['seed_id'] for j in protocol['jobs']}
            if assigned&ids:raise ValueError('Duplicate seed across shards of one iteration')
            assigned|=ids
            for seed_id in sorted(ids):
                root=shard/f'train-{seed_id}'
                if not (root/'result.json').exists():
                    if root.exists():active.append(seed_id)
                    continue
                result=read(root/'result.json');status=result['status']
                if status not in ('win','loss','error','truncated'):raise ValueError('Unknown status')
                # Failed startup/error attempts remain in denominator, even without logs.
                decisions=rows(root/'decisions.jsonl');economy=rows(root/'economy.jsonl')
                predictions=rows(root/'predictions.jsonl');solver=rows(root/'solver.jsonl')
                counts=Counter(d['method'] for d in decisions if d['method']!='start')
                modes=Counter(r.get('diagnostics',{}).get('mode','unspecified') for r in solver)
                cash=[e['money_after'] for e in economy if isinstance(e.get('money_after'),(int,float))]
                for e in economy:
                    if isinstance(e.get('ante'),int) and isinstance(e.get('money_after'),(int,float)):cash_by_ante[e['ante']].append(e['money_after'])
                row={'seed_id':seed_id,'status':status,'terminal':bool(result.get('terminal')),
                    'ante':result.get('ante'),'actions':sum(counts.values()),'action_counts':dict(counts),
                    'final_cash':result.get('money'),'min_observed_cash':min(cash) if cash else None,
                    'max_observed_cash':max(cash) if cash else None,'mean_action_snapshot_cash':avg(cash),
                    'solver_decisions':len(solver),'solver_modes':dict(modes),
                    'prediction_checks':sum(p.get('within_one') is not None for p in predictions),
                    'prediction_mismatches':sum(p.get('within_one') is False for p in predictions),
                    'uncertain_predictions':sum(p.get('within_one') is None for p in predictions)}
                sessions.append(row);comparison[seed_id][label]={k:row[k] for k in ('status','ante','actions','final_cash')}
        modes=Counter();actions=Counter()
        for s in sessions:modes.update(s['solver_modes']);actions.update(s['action_counts'])
        report['iterations'].append({'iteration':label,'assigned':len(assigned),'completed':len(sessions),
            'wins':sum(s['status']=='win' for s in sessions),'status_counts':dict(Counter(s['status'] for s in sessions)),
            'active_uninspected':sorted(active),'not_started':sorted(assigned-{s['seed_id'] for s in sessions}-set(active)),
            'actions':sum(s['actions'] for s in sessions),'action_counts':dict(actions),
            'mean_terminal_ante':avg([s['ante'] for s in sessions if s['ante'] is not None]),
            'mean_final_cash':avg([s['final_cash'] for s in sessions if s['final_cash'] is not None]),
            'mean_action_snapshot_cash_by_ante':{str(k):avg(v) for k,v in sorted(cash_by_ante.items())},
            'solver_decisions':sum(s['solver_decisions'] for s in sessions),'solver_modes':dict(modes),
            'prediction_checks':sum(s['prediction_checks'] for s in sessions),
            'prediction_mismatches':sum(s['prediction_mismatches'] for s in sessions),
            'uncertain_predictions':sum(s['uncertain_predictions'] for s in sessions),
            'sessions':sorted(sessions,key=lambda x:x['seed_id'])})
    report['seed_comparison']=[{'seed_id':i,'iterations':v} for i,v in sorted(comparison.items())]
    report['limitations']=['Repeated TRAIN data, not independent win-rate evidence.',
        'Cash averages are action-snapshot weighted, not equal-round causal measures.',
        'Scorer matches cover only observed chosen actions; uncertain cases excluded.',
        'Aggregates complement an integrity audit; they do not themselves prove no-save/load.']
    return report


def markdown(report):
    lines=['# TRAIN iteration comparison','','| Iteration | Complete | Wins | Actions | Mean terminal ante | Exact checks | Mismatches | Uncertain |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in report['iterations']:
        lines.append(f"| {r['iteration']} | {r['completed']}/{r['assigned']} | {r['wins']} | {r['actions']} | {r['mean_terminal_ante']} | {r['prediction_checks']} | {r['prediction_mismatches']} | {r['uncertain_predictions']} |")
    labels=[r['iteration'] for r in report['iterations']]
    lines+=['','Per-seed entries: outcome / terminal ante / actions.','','| TRAIN ID | '+' | '.join(labels)+' |','|---|'+'---|'*len(labels)]
    for row in report['seed_comparison']:
        cells=[]
        for label in labels:
            s=row['iterations'].get(label);cells.append(f"{s['status']} / {s['ante']} / {s['actions']}" if s else 'pending')
        lines.append('| '+str(row['seed_id'])+' | '+' | '.join(cells)+' |')
    lines+=['']+['- '+s for s in report['limitations']]
    return '\n'.join(lines)+'\n'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--iteration',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    groups=defaultdict(list)
    for entry in a.iteration:
        label,folder=entry.split('=',1);groups[label].append(Path(folder))
    result=summarize(groups);output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    output.with_suffix('.md').write_text(markdown(result),encoding='utf8')
    print(json.dumps([{k:r[k] for k in ('iteration','assigned','completed','wins','actions')} for r in result['iterations']]))
