"""Independent process policies and engines on explicitly registered train seeds.

Engineering development runner, not a replacement for the frozen experiment
registry. Bounded trajectories are marked truncated and never counted as losses.
"""
import argparse,collections,hashlib,json,multiprocessing,sqlite3,sys,time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from environment import Environment,terminal
from isolation import load
LAB=Path(__file__).resolve().parents[1];ROOT=LAB.parents[1]

def policy_hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((LAB/'experiments/policies/route_v2').glob('*.py'))}

def episode(task):
    manifest,seed_id,max_actions=task
    if (Path(manifest['root'])/'episode').exists():raise FileExistsError('Prior episode retained; use a new isolated instance')
    with sqlite3.connect(f'file:{(ROOT/"work/experiments/registry.sqlite").as_posix()}?mode=ro',uri=True) as con:
        row=con.execute("SELECT seed,commitment FROM seeds WHERE id=? AND partition='train'",(seed_id,)).fetchone()
    if row is None:raise ValueError('Only registered training seeds allowed')
    seed,commitment=row;started=time.perf_counter();source_hashes=policy_hashes()
    sys.path[:0]=[str(LAB/'experiments/policies/route_v2'),str(LAB/'cli')]
    import policy,advisor
    from belief import Belief
    memory=Belief();counts=collections.Counter();mismatches=[];status='truncated';error=None
    log_dir=Path(manifest['root'])/'episode'
    # Never mix attempts or overwrite a previous result, including technical failures.
    log_dir.mkdir(exist_ok=False)
    decisions=log_dir/'decisions.jsonl';observations=log_dir/'observations.jsonl'
    try:
        with Environment(manifest['port'],manifest['identity'],log_dir) as env:
            s=env.reset(seed)
            for _ in range(max_actions):
                if terminal(s):break
                ctx=env.context();visible=memory.observe(s,ctx['collection'],ctx['targets'])
                t=time.perf_counter();action=policy.action(visible);thinking=time.perf_counter()-t
                if action is None:raise RuntimeError('Policy returned no action')
                method,params=action;ident=env.sequence+1
                expected=advisor.score(visible,params['cards'])[0] if method=='play' else None
                uncertain=advisor.uncertain(visible) if method=='play' else None
                with observations.open('a',encoding='utf8') as f:f.write(json.dumps({'intent_id':ident,'features':visible},ensure_ascii=False)+'\n')
                before=s;s=env.step(method,params);counts[method]+=1
                actual=s.get('round',{}).get('last_hand',{}).get('total') if method=='play' else None
                if method=='play' and s.get('round',{}).get('chips')==before.get('round',{}).get('chips'):actual=0
                r={'intent_id':ident,'method':method,'params':params,'decision_seconds':thinking,'expected':expected,'actual':actual,'uncertain':uncertain}
                with decisions.open('a',encoding='utf8') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
                if method=='play' and not uncertain and actual is not None and abs(expected-actual)>1:mismatches.append(r)
            if terminal(s):status='loss' if s.get('state')=='GAME_OVER' else 'win'
    except Exception as exc:status='error';error=f'{type(exc).__name__}: {exc}'
    source_unchanged=source_hashes==policy_hashes()
    if not source_unchanged:status='error';error='Policy source changed during episode'
    result={'seed_id':seed_id,'seed_commitment':commitment,'port':manifest['port'],'identity':manifest['identity'],
        'status':status,'error':error,'actions':sum(counts.values()),'counts':dict(counts),'seconds':time.perf_counter()-started,
        'mismatches':mismatches,'purpose':'engineering_train_only','strategy_winrate_eligible':False,
        'ante':locals().get('s',{}).get('ante_num'),'terminal':terminal(locals().get('s',{})),
        'policy_source_sha256':source_hashes,'policy_source_unchanged':source_unchanged}
    (log_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',action='append',required=True);p.add_argument('--seed-id',action='append',type=int,required=True)
    p.add_argument('--max-actions',type=int,default=800);args=p.parse_args()
    if len(args.manifest)!=len(args.seed_id):p.error('One training seed per isolated instance')
    if not 1<=args.max_actions<=10000:p.error('max-actions must be 1..10000')
    manifests=[load(x) for x in args.manifest]
    if len({m['port'] for m in manifests})!=len(manifests) or len({m['identity'] for m in manifests})!=len(manifests):p.error('Duplicate instance')
    started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=len(manifests),mp_context=multiprocessing.get_context('spawn')) as pool:
        results=list(pool.map(episode,[(m,seed,args.max_actions) for m,seed in zip(manifests,args.seed_id)]))
    report={'wall_seconds':time.perf_counter()-started,'workers':len(manifests),'results':results,'not_a_serial_speedup_benchmark':True}
    out=LAB/'results/headless';out.mkdir(exist_ok=True)
    (out/'multi-seed-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if any(r['status']=='error' for r in results):raise SystemExit(1)

if __name__=='__main__':main()
