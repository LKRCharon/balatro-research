"""Complete the interrupted training game without overwriting its registered error.

Decision source remains v1. Public history rebuilds belief; only file-write retries differ.
This continuation is exploratory recovery, never another independent scored trial.
"""
import hashlib,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;LAB=HERE.parent
sys.path[:0]=[str(HERE/'policies/route_v1'),str(LAB/'cli')]
import balatro_cli as cli
import policy,tactics
from belief import Belief

def main():
    session=cli.read(cli.RUNS/'session.json');rid=session['run']
    assert rid==26 and session['active'],'Only the audited interrupted run 26 may be resumed'
    original_write=cli.write
    def durable(path,data):
        for attempt in range(20):
            try:return original_write(path,data)
            except PermissionError:
                if attempt==19:raise
                time.sleep(.05)
    cli.write=durable
    belief=Belief()
    for line in (cli.RUNS/'run-26.jsonl').read_text(encoding='utf-8').splitlines():
        row=json.loads(line);s=row.get('result',{})
        if s.get('state'):belief.observe(s)
    tactics.TAIL_WEIGHT=.6;tactics.SAMPLES=12
    s=cli.call('gamestate');n=0
    while not cli.terminal(s):
        method,params=policy.action(belief.observe(s));s=cli.call(method,params);n+=1
        if n%10==0:print(json.dumps({'recovery_run':rid,'actions':n,'ante':s.get('ante_num'),'state':s.get('state')}),flush=True)
        if n>=500:raise RuntimeError('Recovery budget reached; game retained')
    result={'run':rid,'terminal':True,'won':bool(s.get('won')),'ante':s.get('ante_num'),'round':s.get('round_num'),
            'continuation_actions':n,'original_registered_result':'error, retained unchanged',
            'independent_trial':False,'reason':'Windows progress.json sharing violation',
            'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    cli.write(LAB/'results/run26-technical-recovery.json',result)
    outcome=cli.read(cli.RUNS/'run-26-outcome.json');outcome.update({'policy':'v1 interrupted training, exploratory continuation','independent_trial':False})
    cli.write(cli.RUNS/'run-26-outcome.json',outcome);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
