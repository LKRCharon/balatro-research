"""Read training results only; paired outcomes retain errors and missing partners."""
import argparse,collections,json,statistics
from pathlib import Path
import protocol as p
LAB=Path(__file__).resolve().parents[1]

def build(campaign):
    with p.connect(p.DEFAULT_DB) as con:
        c=con.execute('SELECT partition FROM campaigns WHERE id=?',(campaign,)).fetchone()
        if not c or c['partition']!='train':raise ValueError('Training reports only')
        rows=con.execute('SELECT j.*,pol.name FROM jobs j JOIN policies pol ON pol.id=j.policy_id WHERE campaign_id=? ORDER BY j.rowid',(campaign,)).fetchall()
    groups={};pairs=collections.defaultdict(dict);decision_times=[];total_actions=0;observations=0;unmatched=0
    out=LAB/'results/experiment-runs'
    for row in rows:
        g=groups.setdefault(row['name'],{'assigned':0,'outcomes':collections.Counter(),'antes':[],'actions':0,'seconds':0,'deterministic_predictions':0,'within_one':0,'mismatches':[]})
        g['assigned']+=1;g['outcomes'][row['status']]+=1;pairs[row['seed_id']][row['name']]=row['status']
        r=json.loads(row['result']) if row['result'] else {}
        if r.get('ante') is not None:g['antes'].append(r['ante'])
        g['actions']+=r.get('actions',0);g['seconds']+=r.get('elapsed_seconds',0);total_actions+=r.get('actions',0)
        pred=r.get('predictions',{});g['deterministic_predictions']+=pred.get('deterministic',0);g['within_one']+=pred.get('within_one',0)
        g['mismatches'] += [{'run':r.get('run'),**x} for x in pred.get('mismatches',[])]
        dp=out/(row['id']+'-decisions.jsonl');op=out/(row['id']+'-observations.jsonl')
        ds=[json.loads(x) for x in dp.read_text(encoding='utf8').splitlines()] if dp.exists() else []
        obs=[json.loads(x) for x in op.read_text(encoding='utf8').splitlines()] if op.exists() else []
        oi={x['intent_id'] for x in obs};observations+=len(obs)
        unmatched+=sum(x.get('intent_id') not in oi for x in ds)
        decision_times.extend(x['decision_seconds'] for x in ds if 'decision_seconds' in x)
    names=sorted(groups);paired=collections.Counter()
    for pair in pairs.values():
        states=[pair.get(n,'missing') for n in names]
        if len(states)!=2 or any(s not in ('win','loss') for s in states):paired['incomplete_or_error']+=1
        elif states[0]==states[1]:paired['both_'+states[0]]+=1
        else:paired['only_'+names[states.index('win')]]+=1
    for g in groups.values():
        g['wins_per_assigned']=g['outcomes']['win']/g['assigned']
        g['mean_ante']=statistics.mean(g['antes']) if g['antes'] else None
    result={'campaign':campaign,'partition':'train','policies':groups,'paired':dict(paired),'successful_actions':total_actions,
            'predecision_observations':observations,'decisions_missing_observations':unmatched,
            'decision_seconds_mean':statistics.mean(decision_times) if decision_times else None,
            'decision_seconds_max':max(decision_times,default=None),
            'interpretation':'Exploratory training comparison; no validation/test results or causal card strength claims.'}
    target=out/('analysis-'+campaign[:12]+'.json');target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('campaign');build(ap.parse_args().campaign)
