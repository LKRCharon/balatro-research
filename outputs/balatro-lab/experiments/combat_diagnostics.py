"""Read-only last-blind diagnostics; local score gaps are NOT global policy regret."""
import argparse
from collections import Counter
import importlib
import json
from pathlib import Path
import sys


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def analyze(episode, policy_root):
    sys.path[:0] = [str(policy_root), str(policy_root.parents[2] / 'cli')]
    a = importlib.import_module('advisor')
    result = json.loads((episode/'result.json').read_text(encoding='utf8'))
    decisions = read_lines(episode/'decisions.jsonl')
    combat = [row for row in decisions if row['before'].get('state') == 'SELECTING_HAND']
    reasons = Counter()
    coverage = Counter(combat_decisions=len(combat))
    for row in combat:
        diagnostic = row.get('solver_diagnostics') or {}
        for flag in ('attempted','supported','used','action_changed'):
            coverage[flag] += bool(diagnostic.get(flag))
        if diagnostic.get('fallback_reason'):
            reasons[diagnostic['fallback_reason']] += 1
    if not combat:
        return {'job_id':result.get('job_id'),'status':result['status'],'coverage':dict(coverage),'last_blind':None}
    last_round = combat[-1]['before'].get('round_num')
    rows = [row for row in combat if row['before'].get('round_num') == last_round]
    gaps = []
    for row in rows:
        s = row['before']
        if row['method'] not in ('play','discard'):
            continue
        blind = next(b for b in s['blinds'].values() if b['status'] == 'CURRENT')
        best = a.options(s)[0]
        need = blind['score'] - s['round']['chips']
        selected_score = a.score(s,row['params']['cards'])[0] if row['method'] == 'play' else None
        best_floor = a.conservative_score(s,best[1],best[0])
        uncertain = a.uncertain(s)
        gaps.append({'action':row['action'],'method':row['method'],
                     'remaining_score':need,'hands_left':s['round']['hands_left'],
                     'discards_left':s['round']['discards_left'],
                     'chosen_immediate_model_score':selected_score,
                     'best_immediate_model_score':best[0],
                     'myopic_score_gap':None if selected_score is None else best[0]-selected_score,
                     'model_uncertain':uncertain,
                     'model_immediate_clear_available':not uncertain and best_floor is not None and best_floor>=need,
                     'solver_diagnostics':row.get('solver_diagnostics')})
    first = rows[0]['before']
    blind = next(b for b in first['blinds'].values() if b['status']=='CURRENT')
    return {'job_id':result.get('job_id'),'seed_id':result.get('seed_id'),'policy':result.get('policy'),
            'status':result['status'],'ante':result.get('ante'),'coverage':dict(coverage),
            'combat_fallback_reasons':dict(reasons),
            'last_blind':{'round_num':last_round,'name':blind['name'],'target':blind['score'],
                          'is_failed_blind':result['status']=='loss','decisions':gaps},
            'interpretation':'Myopic score gaps use the frozen scorer at visited public states. A gap may buy draws, economy or future value. It is not counterfactual engine regret, an optimal survival bound, or proof that another action would win.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode',type=Path,required=True)
    parser.add_argument('--policy-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    value=analyze(args.episode.resolve(),args.policy_root.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'job_id':value.get('job_id'),'status':value['status'],'coverage':value['coverage']}))
