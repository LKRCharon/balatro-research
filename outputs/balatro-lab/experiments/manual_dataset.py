"""Offline demonstration export. Outcomes never enter decision features."""
import hashlib,json,sqlite3
from pathlib import Path
LAB=Path(__file__).resolve().parents[1]
RUNS=(18,19,20,30,31,32,33,34,35,36)
ACTIONS=set('play discard rearrange sell use buy pack select cash_out next_round reroll continue skip'.split())
FIELDS=set('money hands stake state round blinds deck ante_num used_vouchers round_num consumables jokers cards hand shop vouchers packs pack'.split())

def clean(value):
    if isinstance(value,list):return [clean(v) for v in value]
    if not isinstance(value,dict):return value
    if value.get('state',{}).__class__ is dict and (value.get('state',{}).get('hidden') or value.get('state',{}).get('face_down')):
        return {'hidden':True}
    return {k:clean(v) for k,v in value.items() if not any(w in k.lower() for w in ('seed','rng','draw_order','future'))}

def extract(rows,run,group):
    before=None;inputs=[];labels=[];outcome='unknown'
    for line,row in enumerate(rows,1):
        result=row.get('result') or {}
        if row['method'] in ACTIONS and before is not None:
            key=f'{run}:{line}'
            inputs.append({'id':key,'run':run,'seed_group':group,'partition':'train','source_line':line,
                'features':clean({k:v for k,v in before.items() if k in FIELDS})})
            params=row.get('params',{})
            labels.append({'id':key,'action':row['method'],'params':{k:v for k,v in params.items() if k!='reason'},
                'reason':params.get('reason'),'error':row.get('error'),
                'money_after':result.get('money'),'actual_score':result.get('round',{}).get('last_hand',{}).get('total') if row['method']=='play' else None,
                'demonstration_is_optimal':False})
        if not row.get('error') and 'state' in result:
            before=result
            if result['state']=='GAME_OVER':outcome='loss'
            elif result.get('overlay')=='win':outcome='win'
    for label in labels:label['run_outcome']=outcome
    return inputs,labels,outcome

def build():
    dest=LAB/'results/manual-ten';dest.mkdir(exist_ok=True)
    db=LAB.parents[1]/'work/experiments/registry.sqlite'
    inputs=[];labels=[];summary=[];groups=set()
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as con:
        for run in RUNS:
            path=LAB/f'results/cli-runs/run-{run:02}.jsonl';raw=path.read_bytes()
            rows=[json.loads(x) for x in raw.decode('utf8').splitlines()]
            start=next(r['params'] for r in rows if r['method']=='start')
            group=start.get('seed_commitment_sha256') or hashlib.sha256(start['seed'].encode()).hexdigest()
            entry=con.execute('SELECT partition FROM seeds WHERE commitment=?',(group,)).fetchone()
            if entry!=('train',):raise ValueError(f'Run {run} is not registered train')
            if group in groups:raise ValueError('Duplicate independent seed')
            groups.add(group)
            ins,labs,outcome=extract(rows,run,group);inputs.extend(ins);labels.extend(labs)
            summary.append({'run':run,'outcome':outcome,'decisions':len(ins),'source_sha256':hashlib.sha256(raw).hexdigest()})
    manifest={'schema':1,'runs':summary,'independent_seeds':len(groups),'decisions':len(inputs),
        'wins':sum(r['outcome']=='win' for r in summary),'losses':sum(r['outcome']=='loss' for r in summary),
        'missing_reasons':sum(not x['reason'] for x in labels),'failed_actions':sum(bool(x['error']) for x in labels),
        'excluded_replay_runs':[21],'context_policy':'Only preceding public state; lab_context not reconstructed; no future RNG or outcomes in features.',
        'usage':'Training demonstrations, not optimal labels. Group all splits and uncertainty estimates by seed. Validation/test not opened.'}
    for name,data in [('decisions.jsonl',inputs),('labels.jsonl',labels)]:
        temp=dest/(name+'.tmp');temp.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data),encoding='utf8');temp.replace(dest/name)
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':build()
