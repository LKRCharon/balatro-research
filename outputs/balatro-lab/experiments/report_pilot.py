"""Report the predeclared training/validation pilot without reading test seed values."""
import collections, json, math, statistics
from pathlib import Path
import protocol as p
LAB=p.LAB;HERE=Path(__file__).resolve().parent

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def wilson(w,n):
    if not n:return [None,None]
    z=1.959963984540054;center=(w/n+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt((w/n)*(1-w/n)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0,center-half),min(1,center+half)]

def load_jobs():
    with p.connect(p.DEFAULT_DB) as con:
        rows=con.execute('''SELECT j.*,c.partition,s.commitment FROM jobs j
                  JOIN campaigns c ON j.campaign_id=c.id JOIN seeds s ON j.seed_id=s.id
                  WHERE c.partition IN ('train','validation') ORDER BY j.rowid''').fetchall()
    return [dict(r) for r in rows]

def trajectory(rid):
    rows=[json.loads(x) for x in (LAB/f'results/cli-runs/run-{rid:02d}.jsonl').read_text(encoding='utf-8').splitlines()]
    hands=collections.Counter();acquired=collections.Counter();used=collections.Counter();replaced=[]
    prev=None;offers={};observed_jokers=set();purchase_cost=0;reroll_cost=0
    for row in rows:
        s=row.get('result',{});method=row['method'];args=row.get('params',{})
        if prev and not row.get('error'):
            if method=='play':
                name=s.get('round',{}).get('last_hand',{}).get('name','unknown');hands[name]+=1
            if method=='use':
                i=args.get('consumable')
                if isinstance(i,int) and i<len(prev['consumables']['cards']):used[prev['consumables']['cards'][i]['key']]+=1
            if method in {'buy','pack'}:
                for param,area in ([('card','shop'),('pack','packs'),('voucher','vouchers')] if method=='buy' else [('card','pack')]):
                    i=args.get(param)
                    if isinstance(i,int) and i<len(prev.get(area,{}).get('cards',[])):
                        c=prev[area]['cards'][i];acquired[c['key']]+=1
                        if method=='buy':purchase_cost+=c.get('cost',{}).get('buy',0)
                        if args.get('use') or (method=='pack' and c.get('set') in {'PLANET','TAROT'}):used[c['key']]+=1
            if method=='reroll':reroll_cost+=prev['round'].get('reroll_cost',0)
            if method=='sell' and 'joker' in args:replaced.append(prev['jokers']['cards'][args['joker']]['key'])
        if 'state' in s:
            prev=s
            for c in s.get('jokers',{}).get('cards',[]):observed_jokers.add(c['key'])
            for area in ('shop','pack'):
                for c in s.get(area,{}).get('cards',[]):
                    if c.get('set')=='JOKER':offers[c.get('id',str(c))]=c['key']
    return {'hands':dict(hands),'acquired':dict(acquired),'consumables_used':dict(used),
            'jokers_sold':replaced,'jokers_owned':sorted(observed_jokers),'distinct_joker_offers':dict(collections.Counter(offers.values())),
            'purchase_cost':purchase_cost,'reroll_cost':reroll_cost}

def summarize(rows):
    results=[json.loads(j['result']) for j in rows if j['result']]
    statuses=collections.Counter(j['status'] for j in rows);n=len(rows);w=statuses['win']
    complete=[r for r in results if r['status'] in {'win','loss'}]
    blinds=[24 if r['status']=='win' else max(0,(r.get('round') or 1)-1) for r in complete]
    settled=not any(statuses[k] for k in ('running','planned'))
    return {'assigned':n,'completed':len(complete),'counts':dict(statuses),'wins_per_assigned':w/n if n and settled else None,
            'wilson95':wilson(w,n) if settled else [None,None],'mean_completed_blinds':statistics.mean(blinds) if blinds else None,
            'failures':dict(collections.Counter(r.get('blind','unknown') for r in results if r['status']=='loss')),
            'mean_seconds':statistics.mean(r['elapsed_seconds'] for r in complete) if complete else None,
            'total_actions':sum(r.get('actions',0) for r in results),
            'prediction_checks':sum(r.get('predictions',{}).get('deterministic',0) for r in results),
            'prediction_within_one':sum(r.get('predictions',{}).get('within_one',0) for r in results),
            'prediction_mismatches':sum(len(r.get('predictions',{}).get('mismatches',[])) for r in results)}

def main():
    plan=read(HERE/'pilot-v1-plan.json');rows=load_jobs();variants={v['policy_id']:v for v in plan['variants']}
    groups={}
    for role in ('train','validation'):
        for ident,v in variants.items():
            jr=[j for j in rows if j['partition']==role and j['policy_id']==ident]
            if jr:groups[role+':'+v['name']]=summarize(jr)
    runrows=[]
    for j in rows:
        r=json.loads(j['result']) if j['result'] else {}
        runrows.append({'partition':j['partition'],'policy':variants[j['policy_id']]['name'],
                        'seed_group':j['seed_id'],'seed_commitment':j['commitment'],'status':j['status'],
                        **{k:r.get(k) for k in ('run','ante','round','blind','score','target','elapsed_seconds','predictions')},
                        'trajectory':trajectory(r['run']) if r.get('run') else None})
    paired=[]
    train=[r for r in runrows if r['partition']=='train']
    for seed in sorted({r['seed_group'] for r in train}):
        block=sorted([r for r in train if r['seed_group']==seed],key=lambda r:r['policy'])
        if len(block)==2 and all(r['status'] in {'win','loss'} for r in block):
            progress=lambda r:24 if r['status']=='win' else r['round']-1
            paired.append({'seed_group':seed,'order':[r['policy'] for r in block],
                           'wins':[r['status']=='win' for r in block],
                           'completed_blinds':[progress(r) for r in block],
                           'tail60_minus_tail20_blinds':progress(block[1])-progress(block[0])})
    selection=read(LAB/'results/pilot-v1-selection.json') if (LAB/'results/pilot-v1-selection.json').exists() else None
    public=p.public_summary(p.DEFAULT_DB)
    report={'created_utc':p.now(),'groups':groups,'selection':selection,'paired_training':paired,'runs':runrows,
            'partition_assignment_unchanged':public['assignment_sha256']==plan['assignment_sha256'],
            'final_test_allocated':public['final_test_campaign_allocated'],
            'test_jobs':sum(len(c['seed_ids'])*len(c['policy_ids']) for c in public['campaigns'] if c['partition']=='test'),
            'limits':['Two-parameter-grid pilot, not reinforcement learning.','Validation is development evidence, not final test.',
                      'Training confidence intervals are descriptive after model selection.',
                      'Restricted card support; policy losses cannot establish card weakness.']}
    write(LAB/'results/pilot-v1-report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('runs','selection')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
