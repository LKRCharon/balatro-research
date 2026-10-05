"""Frozen public-state policy worker. Receives configuration and job id, never a seed."""
import argparse, datetime, json, sys, time, traceback
from collections import Counter
from pathlib import Path
LAB=Path(__file__).resolve().parents[3]
sys.path.append(str(LAB/'cli'))
import balatro_cli as cli
import advisor as a
import policy, tactics
from belief import Belief
from execution import Journal

def run(config,job_id,partition,policy_id):
    tactics.TAIL_WEIGHT=config['tail_weight'];tactics.SAMPLES=config['discard_samples']
    memory=Belief();counts=Counter();predictions=[];actions=0;errors=[]
    start=time.monotonic();s=cli.call('gamestate');rid=cli.read(cli.RUNS/'session.json')['run']
    outdir=LAB/'results/experiment-runs';outdir.mkdir(exist_ok=True)
    decisions=outdir/(job_id+'-decisions.jsonl')
    meta={'run':rid,'job_id':job_id,'partition':partition,'policy_id':policy_id,'config':config,
          'policy':'frozen scripted route policy','no_llm':True,'seed_in_policy_input':False}
    cli.write(cli.RUNS/f'run-{rid:02d}-policy.json',meta)
    history_path=cli.RUNS/f'run-{rid:02d}-policy-history.json'
    history=cli.read(history_path,[]);history.append(meta);cli.write(history_path,history)
    def progress():
        cli.write(outdir/'progress.json',{**meta,'actions':actions,'ante':s.get('ante_num'),
                  'round':s.get('round_num'),'state':s.get('state'),'money':s.get('money'),
                  'elapsed_seconds':round(time.monotonic()-start,1),'time':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    try:
        journal=Journal(outdir/(job_id+'-journal.jsonl'))
        for actions in range(1,config['max_actions']+1):
            if cli.terminal(s):break
            visible=memory.observe(s,cli.call('lab_context'),cli.call('dynamics',{'targets':True,'cards':False}))
            assert 'seed' not in visible and set(visible.get('cards',{}))<= {'count','limit'}
            decision_start=time.monotonic()
            chosen=policy.action(visible)
            decision_seconds=time.monotonic()-decision_start
            if not chosen:raise ValueError('Policy returned no action before terminal state')
            method,params=chosen
            if method in {'start','menu','lab_stop','skip'}:raise ValueError('Worker cannot reset, stop or skip a run')
            prediction=a.score(visible,params['cards'])[0] if method=='play' else None
            uncertain=a.uncertain(visible) if method=='play' else False
            record={'action':actions,'ante':s.get('ante_num'),'round':s.get('round_num'),
                    'method':method,'params':params,'predicted':prediction,'uncertain':uncertain,
                    'decision_seconds':decision_seconds}
            before=s
            intent=journal.begin(s,method,params)
            record['intent_id']=intent;record['state_before_sha256']=journal.pending['before_sha256']
            with (outdir/(job_id+'-observations.jsonl')).open('a',encoding='utf-8') as f:
                f.write(json.dumps({'intent_id':intent,'action':actions,'features':visible},ensure_ascii=False)+'\n')
                f.flush()
            s=cli.call(method,params);journal.finish(s);counts[method]+=1
            if method=='play':
                actual=s.get('round',{}).get('last_hand',{}).get('total')
                blocked=s.get('round',{}).get('chips')==before.get('round',{}).get('chips')
                if blocked:actual=0
                p={'action':actions,'predicted':prediction,'actual':actual,'uncertain':uncertain,
                   'within_one':None if uncertain or actual is None else abs(prediction-actual)<=1}
                predictions.append(p);record.update(p)
            with decisions.open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
            progress()
            if actions%15==0:print(json.dumps({'run':rid,'actions':actions,'ante':s.get('ante_num'),'state':s.get('state'),'counts':dict(counts)}),flush=True)
        if not cli.terminal(s):raise RuntimeError('Action budget reached; unfinished game retained')
    except Exception as exc:
        errors.append({'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
        # Read back only. A timed-out mutation is never blindly repeated.
        try:s=cli.call('gamestate')
        except Exception:pass
    current=next((b for b in s.get('blinds',{}).values() if b.get('status')=='CURRENT'),{})
    won=cli.victory(s)
    checks=[p for p in predictions if p['within_one'] is not None]
    result={**meta,'status':'error' if errors else 'win' if won else 'loss',
            'terminal':cli.terminal(s),'won':won,'ante':s.get('ante_num'),'round':s.get('round_num'),
            'money':s.get('money'),'blind':current.get('name'),'score':s.get('round',{}).get('chips'),
            'target':current.get('score'),'counts':dict(counts),'actions':sum(counts.values()),
            'elapsed_seconds':round(time.monotonic()-start,3),'errors':errors,
            'predictions':{'total':len(predictions),'deterministic':len(checks),
                           'within_one':sum(bool(p['within_one']) for p in checks),
                           'mismatches':[p for p in checks if not p['within_one']]},
            'jokers':s.get('jokers',{}).get('cards',[]),'route':policy.main_hand(s)}
    cli.write(outdir/(job_id+'-result.json'),result)
    outcome=cli.RUNS/f'run-{rid:02d}-outcome.json'
    if outcome.exists():
        old=cli.read(outcome);old.update(meta);old['sampling']='registered_'+partition;cli.write(outcome,old)
    progress();print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True,type=Path)
    p.add_argument('--job',required=True);p.add_argument('--partition',choices=['train','validation'],required=True)
    p.add_argument('--policy-id',required=True);args=p.parse_args()
    r=run(json.loads(args.config.read_text(encoding='utf-8')),args.job,args.partition,args.policy_id)
    if r['status']=='error':raise SystemExit(1)
