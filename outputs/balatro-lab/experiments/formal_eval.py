"""Preregistered original-engine scripted validation; held-out test is never read.

prepare emits the commitment to publish before run. Each process owns one engine;
any technical error stops that process, retaining its unfinished game. No retries.
"""
from __future__ import annotations
import argparse, hashlib, importlib, json, math, os, shutil, subprocess, sys, time
from collections import Counter
from pathlib import Path
import protocol as p

HERE=Path(__file__).resolve().parent
LAB=HERE.parent
sys.path[:0]=[str(LAB/'headless'),str(LAB/'cli')]
from environment import Environment, terminal

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');os.replace(temp,path)

def append(path,value):
    with Path(path).open('a',encoding='utf8') as f:
        f.write(json.dumps(value,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())

def prepare(db,out,count=16,instances=()):
    out=Path(out)
    if (out/'protocol.json').exists():raise ValueError('Protocol already prepared; do not allocate again')
    with p.connect(db) as con:
        rows=con.execute("SELECT id,already_seen FROM seeds WHERE partition='validation' ORDER BY already_seen,id LIMIT ?",(count,)).fetchall()
        ids=[r['id'] for r in rows]
        if len(ids)!=count or any(r['already_seen'] for r in rows):raise ValueError('Not enough untouched validation seeds')
        if con.execute("SELECT 1 FROM jobs WHERE status!='withdrawn_before_execution' AND seed_id IN ("+','.join('?'*count)+')',ids).fetchone():raise ValueError('Validation seeds already allocated; no repeat evaluation')
    source=HERE/'policies/route_v2'
    digest=hashlib.sha256(b''.join(f.relative_to(source).as_posix().encode()+f.read_bytes() for f in sorted(source.rglob('*')) if f.is_file() and '__pycache__' not in f.parts)).hexdigest()
    snapshot=HERE/'policies'/('formal_public_route_v2_'+digest[:12])
    if not snapshot.exists():
        shutil.copytree(source,snapshot,ignore=shutil.ignore_patterns('__pycache__'))
        specs=json.loads((snapshot/'joker_specs.json').read_text(encoding='utf8'))
        specs={key:{k:v for k,v in value.items() if k in ('blueprint_compat','rarity','config')} for key,value in specs.items()}
        (snapshot/'joker_specs.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    config={'tail_weight':.3,'discard_samples':12,'max_actions':800,'deck':'BLUE','stake':'GOLD','controller':'scripted_no_llm','skip_blinds':False}
    contexts=[Path(__file__),HERE/'protocol.py',LAB/'headless/environment.py',LAB/'headless/transport.py',LAB/'cli/observations.py',LAB/'cli/balatro_cli.py']
    contexts+=sorted((LAB.parents[1]/'work/balatro-source/mods').rglob('*.lua'))
    engines=[json.loads(Path(file).read_text(encoding='utf8')) for file in instances]
    if not engines:raise ValueError('Bind staged engine manifests before freezing')
    engine_hashes=engines[0]['input_hashes']
    for engine in engines:
        if engine['input_hashes']!=engine_hashes:raise ValueError('Different staged engine inputs')
        for relative,expected in engine_hashes.items():
            if hashlib.sha256((Path(engine['checkout'])/relative).read_bytes()).hexdigest()!=expected:raise ValueError('Staged engine source changed')
    ident=p.register_policy(db,'formal_scripted_route_v2',snapshot,config,contexts)
    campaign=p.schedule(db,'validation',[ident],count)
    with p.connect(db) as con:
        jobs=[dict(r) for r in con.execute('SELECT j.id AS job_id,j.seed_id,s.commitment FROM jobs j JOIN seeds s ON s.id=j.seed_id WHERE j.campaign_id=? ORDER BY j.seed_id',(campaign,))]
    spec={'schema':1,'campaign_id':campaign,'policy_id':ident,'created_utc':p.now(),'partition':'validation','config':config,'assigned':count,'jobs':jobs,
          'primary_metric':'wins / all assigned jobs; technical errors remain in denominator',
          'streak_order':'ascending preregistered seed_id, never completion order',
          'intervention':'none; no restart; stop worker on technical error; retain all attempts',
          'test_partition':'sealed, not read','statistics':'Wilson 95% interval for assigned-job success; descriptive small sample',
          'engine':'original engine on private background desktop, muted CLI; rendering not fully removed',
          'engine_input_hashes':engine_hashes,'policy_selection':'a priori fixed baseline; not selected from ongoing training outcomes',
          'limitations':'scripted baseline, not an LLM benchmark; finite validation sample; model scoring mismatches retained',
          'source_files':{f.relative_to(snapshot).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in snapshot.rglob('*') if f.is_file() and '__pycache__' not in f.parts},
          'context_files':{str(f.relative_to(LAB)) if f.is_relative_to(LAB) else 'private-engine/'+str(f.relative_to(LAB.parents[1]/'work/balatro-source')):hashlib.sha256(f.read_bytes()).hexdigest() for f in contexts}}
    write(out/'protocol.json',spec)
    return spec

def wilson(wins,n):
    if not n:return [0,1]
    z=1.959963984540054;v=wins/n;d=1+z*z/n
    center=(v+z*z/(2*n))/d;delta=z*math.sqrt(v*(1-v)/n+z*z/(4*n*n))/d
    return [max(0,center-delta),min(1,center+delta)]

def summarize(rows):
    rows=sorted(rows,key=lambda r:r['seed_id']);counts=Counter(r['status'] for r in rows)
    longest=current=0
    for row in rows:
        current=current+1 if row['status']=='win' else 0;longest=max(longest,current)
    return {'assigned':len(rows),'counts':dict(counts),'wins_per_assigned':counts['win']/len(rows) if rows else 0,
            'wilson_95':wilson(counts['win'],len(rows)),'longest_streak_in_registered_order':longest,
            'complete':all(r['status'] in ('win','loss','error') for r in rows),'jobs':rows}

def report(db,campaign,out):
    with p.connect(db) as con:
        rows=[dict(r) for r in con.execute('SELECT id AS job_id,seed_id,status,result FROM jobs WHERE campaign_id=? ORDER BY seed_id',(campaign,))]
    for row in rows:row['result']=json.loads(row['result']) if row['result'] else None
    result={'campaign_id':campaign,'updated_utc':p.now(),**summarize(rows)}
    write(Path(out)/'summary.json',result);return result

def run_job(db,job,instance,out):
    claim=p.claim_job(db,job,'validation')
    with p.connect(db) as con:manifest=p.verify_policy(con,claim['policy_id'])
    sys.path.insert(0,manifest['source_root'])
    policy=importlib.import_module('policy');a=importlib.import_module('advisor');tactics=importlib.import_module('tactics')
    Belief=importlib.import_module('belief').Belief;validate=importlib.import_module('execution').validate
    config=manifest['config'];tactics.TAIL_WEIGHT=config['tail_weight'];tactics.SAMPLES=config['discard_samples']
    memory=Belief();counts=Counter();predictions=[];s={};errors=[];start=time.monotonic()
    dest=Path(out)/'jobs'/job;dest.mkdir(parents=True,exist_ok=False)
    try:
        spec=json.loads((Path(out)/'protocol.json').read_text(encoding='utf8'))
        if instance['input_hashes']!=spec['engine_input_hashes']:raise ValueError('Engine manifest differs from frozen protocol')
        for relative,expected in spec['engine_input_hashes'].items():
            if hashlib.sha256((Path(instance['checkout'])/relative).read_bytes()).hexdigest()!=expected:raise ValueError('Engine source changed since freeze')
        with Environment(instance['port'],instance['identity'],dest,registry=db) as env:
            s=env.reset(claim['seed'],intended_partition='validation',job_id=job)
            if s.get('deck')!='BLUE' or s.get('stake')!='GOLD':raise ValueError('Engine did not start requested Blue/Gold conditions')
            for index in range(config['max_actions']):
                if terminal(s):break
                context=env.context()
                public_jokers={card.get('key') for area in ('jokers','shop','pack') for card in s.get(area,{}).get('cards',[]) if not card.get('state',{}).get('hidden')}
                context['targets']['targets']=[target for target in context['targets'].get('targets',[]) if target.get('key') in public_jokers]
                visible=memory.observe(s,context['collection'],context['targets'])
                begin=time.monotonic();chosen=policy.action(visible);duration=time.monotonic()-begin
                if not chosen:raise ValueError('No action before terminal')
                method,params=chosen
                if method in {'start','menu','lab_stop','skip'}:raise ValueError('Forbidden policy action')
                validate(s,method,params)
                predicted=a.score(visible,params['cards'])[0] if method=='play' else None
                uncertain=a.uncertain(visible) if method=='play' else False
                append(dest/'decisions.jsonl',{'action':index+1,'before':visible,'method':method,'params':params,'decision_seconds':duration,'predicted':predicted,'uncertain':uncertain})
                before=s;s=env.step(method,params);counts[method]+=1
                if method=='play':
                    actual=s.get('round',{}).get('last_hand',{}).get('total')
                    if s.get('round',{}).get('chips')==before.get('round',{}).get('chips'):actual=0
                    prediction={'action':index+1,'predicted':predicted,'actual':actual,'uncertain':uncertain,'within_one':None if uncertain or actual is None else abs(predicted-actual)<=1}
                    predictions.append(prediction);append(dest/'predictions.jsonl',prediction)
                write(dest/'progress.json',{'job_id':job,'action':index+1,'state':s.get('state'),'ante':s.get('ante_num'),'round':s.get('round_num'),'elapsed_seconds':time.monotonic()-start})
            if not terminal(s):raise RuntimeError('Action budget exhausted; unfinished episode retained')
    except Exception as exc:
        # Public diagnostics deliberately omit traceback and local paths.
        errors.append({'type':type(exc).__name__,'message':str(exc).replace(claim['seed'],'[private seed]')})
    won=s.get('state')!='GAME_OVER' and bool(s.get('overlay')=='win' or s.get('won')) and s.get('ante_num',0)>=8
    checks=[x for x in predictions if x['within_one'] is not None]
    result={'status':'error' if errors else 'win' if won else 'loss','terminal':terminal(s),'won':won,'ante':s.get('ante_num'),'round':s.get('round_num'),
            'actions':sum(counts.values()),'counts':dict(counts),'elapsed_seconds':time.monotonic()-start,'errors':errors,
            'prediction_checks':len(checks),'prediction_mismatches':[x for x in checks if not x['within_one']],
            'money':s.get('money'),'score':s.get('round',{}).get('chips'),'policy_id':claim['policy_id'],'controller':'scripted_no_llm'}
    write(dest/'result.json',result)
    p.record_result(db,job,'validation',claim['seed'],claim['policy_id'],result)
    return result

def worker(db,campaign,instance_file,out,slot,total):
    instance=json.loads(Path(instance_file).read_text(encoding='utf8'))
    with p.connect(db) as con:jobs=[r['id'] for r in con.execute('SELECT id FROM jobs WHERE campaign_id=? ORDER BY seed_id',(campaign,))]
    for job in jobs[slot::total]:
        result=run_job(db,job,instance,out)
        print(json.dumps({'job_id':job,'status':result['status'],'actions':result['actions']}),flush=True)
        if result['status']=='error':return 1
    return 0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['prepare','run','worker','report'])
    ap.add_argument('--db',type=Path,default=p.DEFAULT_DB);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--count',type=int,default=16);ap.add_argument('--campaign');ap.add_argument('--instances',nargs='+')
    ap.add_argument('--slot',type=int,default=0);ap.add_argument('--workers',type=int,default=1);args=ap.parse_args()
    if args.command=='prepare':print(json.dumps(prepare(args.db,args.output,args.count,args.instances or [])));return
    if args.command=='report':print(json.dumps(report(args.db,args.campaign,args.output)));return
    if args.command=='worker':raise SystemExit(worker(args.db,args.campaign,args.instances[0],args.output,args.slot,args.workers))
    spec=json.loads((args.output/'protocol.json').read_text(encoding='utf8'))
    if spec['campaign_id']!=args.campaign:raise ValueError('Campaign does not match published protocol')
    processes=[];handles=[]
    for slot,instance in enumerate(args.instances):
        handle=(args.output/f'worker-{slot}.log').open('w',encoding='utf8');handles.append(handle)
        cmd=[sys.executable,str(Path(__file__)),'worker','--db',str(args.db),'--output',str(args.output),'--campaign',args.campaign,'--instances',instance,'--slot',str(slot),'--workers',str(len(args.instances))]
        processes.append(subprocess.Popen(cmd,stdout=handle,stderr=subprocess.STDOUT))
    while any(proc.poll() is None for proc in processes):
        report(args.db,args.campaign,args.output);time.sleep(5)
    for handle in handles:handle.close()
    result=report(args.db,args.campaign,args.output)
    print(json.dumps(result));raise SystemExit(0 if result['complete'] else 1)

if __name__=='__main__':main()
