"""Same training seed/actions across just reference and resident direct transport."""
import argparse,hashlib,json,os,sqlite3,statistics,subprocess,sys,time
from pathlib import Path
from environment import Environment,canonical_state
from vector_env import VectorEnv
from transport import RpcClient
from isolation import load
LAB=Path(__file__).resolve().parents[1];ROOT=LAB.parents[1]

class JustClient:
    def __init__(self,manifest,just,python):
        self.manifest=manifest;self.just=just;self.env=os.environ.copy()
        self.env['PATH']=str(Path(python).parent)+os.pathsep+str(Path(just).parent)+os.pathsep+self.env['PATH']
        self.env['PYTHONIOENCODING']='utf-8'
    def call(self,method,params=None):
        out=subprocess.run([str(self.just),'agent-call',method,json.dumps(params or {},ensure_ascii=False),str(self.manifest['port'])],cwd=self.manifest['checkout'],env=self.env,capture_output=True,timeout=60)
        if out.returncode:raise RuntimeError(out.stderr.decode('utf8','replace'))
        data=json.loads(out.stdout)
        if 'error' in data:raise RuntimeError(data['error'])
        return data['result']
    def close(self):pass

def run(manifests,seed_id,steps,just,python):
    target=LAB/'results/headless';target.mkdir(exist_ok=True)
    with sqlite3.connect(f'file:{(ROOT/"work/experiments/registry.sqlite").as_posix()}?mode=ro',uri=True) as con:
        row=con.execute("SELECT seed,commitment FROM seeds WHERE id=? AND partition='train'",(seed_id,)).fetchone()
    if row is None:raise ValueError('Explicit registered training seed required')
    seed,commitment=row
    report={'kind':'engineering differential, not independent strategy trial','seed_id':seed_id,'seed_commitment':commitment,
        'instances':[{'port':m['port'],'identity':m['identity']} for m in manifests],'comparisons':[],'performance':{}}
    refs=[JustClient(manifests[0],just,python),RpcClient(manifests[1]['port'],timeout=60)]
    envs=[]
    try:
        for m,client in zip(manifests,refs):envs.append(Environment(m['port'],m['identity'],Path(m['root'])/'transitions',client=client))
        # Read-only overhead benchmark: same endpoint, sequential per client.
        for name,client in zip(('just','direct'),refs):
            times=[]
            for _ in range(20):
                started=time.perf_counter();client.call('gamestate');times.append(time.perf_counter()-started)
            report['performance'][name]={'calls':20,'mean_seconds':statistics.mean(times),'median_seconds':statistics.median(times)}
        with VectorEnv(envs) as vector:
            states=vector.reset([seed,seed])
            def compare(states,label):
                if not all(x['ok'] for x in states):raise RuntimeError(str(states))
                left,right=[canonical_state(x['result']) for x in states]
                same=left==right
                report['comparisons'].append({'step':label,'equal':same,'state':left.get('state'),
                    'sha256':hashlib.sha256(json.dumps(left,sort_keys=True).encode()).hexdigest()})
                if not same:
                    (target/'mismatch.json').write_text(json.dumps({'step':label,'left':left,'right':right},ensure_ascii=False,indent=2),encoding='utf8')
                    raise AssertionError('Public game state mismatch at '+str(label))
            compare(states,'reset')
            sys.path[:0]=[str(LAB/'experiments/policies/route_v2'),str(LAB/'cli')]
            import policy
            from belief import Belief
            belief=Belief();start=time.perf_counter()
            for index in range(steps):
                left=states[0]['result']
                if left.get('state')=='GAME_OVER' or left.get('won'):break
                ctx=envs[0].context();visible=belief.observe(left,ctx['collection'],ctx['targets'])
                action=policy.action(visible)
                if not action:raise RuntimeError('No policy action')
                states=vector.step([action,action]);compare(states,index+1)
            report['paired_action_seconds']=time.perf_counter()-start
            report['passed']=True
    except Exception as exc:
        report['passed']=False;report['error']=str(exc)
        raise
    finally:
        for env in envs:env.close()
        (target/'parallel-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',action='append',required=True);ap.add_argument('--seed-id',type=int,required=True)
    ap.add_argument('--steps',type=int,default=24);ap.add_argument('--just',type=Path,required=True);ap.add_argument('--python',type=Path,required=True);a=ap.parse_args()
    if len(a.manifest)!=2:ap.error('Exactly two isolated manifests required')
    run([load(x) for x in a.manifest],a.seed_id,a.steps,a.just,a.python)
