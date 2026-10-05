"""Public-observation JSONL interface for one owned, isolated engine."""
import argparse,json,sys
from pathlib import Path
from environment import Environment
from isolation import load

def serve(env,source=sys.stdin,sink=sys.stdout):
    for line in source:
        request={}
        try:
            request=json.loads(line);method=request['method'];params=request.get('params',{})
            if method not in ('reset','observe','step','context','action_space'):raise ValueError('Unsupported environment method')
            result=getattr(env,method)(**params)
            response={'id':request.get('id'),'result':result}
        except Exception as exc:
            response={'id':request.get('id') if isinstance(request,dict) else None,'error':str(exc),'type':type(exc).__name__}
            if env.pending:
                response['needs_reconciliation']=True
                print(json.dumps(response,ensure_ascii=False),file=sink,flush=True)
                return 2
        print(json.dumps(response,ensure_ascii=False),file=sink,flush=True)
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest');p.add_argument('--logs',type=Path);args=p.parse_args()
    m=load(args.manifest)
    with Environment(m['port'],m['identity'],args.logs or Path(m['root'])/'env-cli') as env:
        raise SystemExit(serve(env))
