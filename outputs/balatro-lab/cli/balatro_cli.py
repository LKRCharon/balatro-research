"""Audited CLI for the isolated Balatro backend. Every game action goes through just.

Examples: python balatro_cli.py status
          python balatro_cli.py start
          python balatro_cli.py play '{"cards":[0,2],"reason":"..."}'
          python balatro_cli.py lookup '{"keys":["j_blue_joker"]}'
Seeded repeats are explicitly labelled and excluded from independent random-run statistics.
No mid-run resets, save loading, or debug mutations are allowed through this client.
"""
from __future__ import annotations
import argparse, copy, datetime, hashlib, json, os, secrets, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path
import observations

ROOT = Path(__file__).resolve().parents[3]
LAB = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get('BALATRO_LAB_REPO', ROOT / 'work/balatro-source'))
JUST = Path(os.environ.get('BALATRO_LAB_JUST', ROOT / 'work/tools/just.exe'))
RUNS = LAB / 'results/cli-runs'
RUNS.mkdir(parents=True, exist_ok=True)
ALLOWED = {'gamestate','health','lab_info','lab_stop','start','select','skip','play','discard',
           'cash_out','next_round','buy','pack','use','sell','rearrange','reroll','reroll_boss',
           'menu','continue','lookup','docs_search','docs_read','docs_index','dynamics'}
READ_ONLY = {'gamestate','health','lab_info','lookup','docs_search','docs_read','docs_index','dynamics'}

def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def victory(s):
    # Original end_round sets won even on a losing Ante 8 Boss.
    return s.get('state') != 'GAME_OVER' and bool(s.get('overlay') == 'win' or s.get('won'))

def terminal(s):
    return s.get('state') == 'GAME_OVER' or s.get('overlay') == 'win' or s.get('won') is True

def sanitize(s):
    """No seed or draw order reaches the policy or its observation log."""
    s = copy.deepcopy(s)
    s.pop('seed', None)
    for area in ('hand','jokers','consumables','shop','vouchers','packs','pack'):
        for card in s.get(area,{}).get('cards',[]):
            for field in ('value','modifier','state','cost'):
                if card.get(field)==[]: card[field]={}
    if 'cards' in s and isinstance(s['cards'], dict):
        s['cards'] = {k:v for k,v in s['cards'].items() if k in ('count','limit')}
    return s

@contextmanager
def rpc_lock():
    import msvcrt
    lock_path=ROOT/'work/cli-rpc.lock'
    with lock_path.open('a+b') as f:
        if f.tell()==0: f.write(b'0'); f.flush()
        deadline=time.monotonic()+90
        while True:
            f.seek(0)
            try: msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1); break
            except OSError:
                if time.monotonic()>=deadline: raise TimeoutError('Another CLI request owns the backend')
                time.sleep(0.1)
        try: yield
        finally: f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def call(method, params=None):
    with rpc_lock(): return _call(method,params)

def _call(method, params=None):
    params = params or {}
    if method not in ALLOWED:
        raise ValueError('Method excluded from research play: ' + method)
    session = read(RUNS / 'session.json', {'run':0, 'active':False})
    current = read(RUNS / 'current.json', {})
    randomized_start=False
    if method == 'start':
        if params.get('deck','BLUE') != 'BLUE' or params.get('stake','GOLD') != 'GOLD':
            raise ValueError('This experiment requires Blue / Gold')
        if session.get('active'):
            raise ValueError('Finish the current run; no opening resets')
        params = {'deck':'BLUE','stake':'GOLD', **params}
        if not params.get('seed'):
            # Native generation depends on cursor state and is unsuitable for independent
            # headless trials. Sample outside the game; never reveal it to the policy.
            randomized_start=True
            params['seed']=''.join(secrets.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(8))
    if method == 'menu' and session.get('active') and not terminal(current):
        raise ValueError('Cannot abandon a measured run')
    if method == 'dynamics' and params.get('deck') == 'list':
        raise ValueError('Ordered draw-pile access excluded; use stats')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    # Python 3.12 is needed by repository packaging; calls also use that stable runtime.
    runtime = Path(os.environ.get('BALATRO_LAB_PYTHON',r'C:\Users\charon\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')).parent
    env['PATH'] = str(runtime) + os.pathsep + str(JUST.parent) + os.pathsep + env['PATH']
    logged_params=copy.deepcopy(params)
    if randomized_start:
        logged_params.pop('seed')
        logged_params['seed_commitment_sha256']=hashlib.sha256(params['seed'].encode()).hexdigest()
        logged_params['sampling']='randomized_seed'
    with (RUNS/'attempts.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'run':session['run'], 'method':method,'params':logged_params},ensure_ascii=False)+'\n')
    process = subprocess.Popen([str(JUST),'agent-call',method,json.dumps(params,ensure_ascii=False)],
                               cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try: stdout,stderr=process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True)
        process.communicate(timeout=5)
        raise TimeoutError('Request timed out; inspect gamestate before retrying: '+method)
    if process.returncode:
        raise RuntimeError(stderr.decode('utf-8','replace') + stdout.decode('utf-8','replace'))
    response = json.loads(stdout)
    raw_seed=response.get('result',{}).get('seed')
    data = sanitize(response.get('result', {}))
    observations.enrich(data,current)
    if data.get('state') and data.get('round',{}).get('hands_played') and not data.get('round',{}).get('mouth_hand'):
        boss=next((b['name'] for b in data.get('blinds',{}).values() if b['status']=='CURRENT'),'')
        if boss=='The Mouth':
            # Resume after an older client: the first played hand is public recorded history.
            log=RUNS/('run-%02d.jsonl'%session['run'])
            for line in log.read_text(encoding='utf-8').splitlines():
                row=json.loads(line);old=row.get('result',{})
                if row['method']=='play' and old.get('round_num')==data['round_num']:
                    name=old.get('round',{}).get('last_hand',{}).get('name')
                    data['round']['mouth_hand']=observations.ZH_TO_EN.get(name,name);break
    if method == 'start' and 'error' not in response:
        session['run'] += 1
        session['active'] = True
        session['sampling'] = 'randomized_seed' if randomized_start else 'seeded_repeat'
    if raw_seed:
        private=ROOT/'work/private-seeds.json'
        seeds=read(private,{})
        seeds[str(session['run'])]=raw_seed
        write(private,seeds)
    entry = {'time':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'run':session['run'],
             'method':method, 'params':logged_params, 'result':data}
    if 'error' in response:
        entry['error'] = response['error']
    with (RUNS / ('run-%02d.jsonl' % session['run'])).open('a',encoding='utf-8') as f:
        f.write(json.dumps(entry,ensure_ascii=False)+'\n')
    if 'error' in response:
        raise RuntimeError(json.dumps(response['error'],ensure_ascii=False))
    if 'state' in data:
        write(RUNS / 'current.json', data)
    if terminal(data) and session.get('active'):
        session['active'] = False
        write(RUNS / ('run-%02d-outcome.json' % session['run']),
              {'run':session['run'], 'win':victory(data), 'ante':data.get('ante_num'),
               'round':data.get('round_num'), 'money':data.get('money'), 'state':data.get('state'),
               'jokers':data.get('jokers'), 'last_hand':data.get('round',{}).get('last_hand'),
               'time':entry['time'], 'sampling':session.get('sampling','unseeded'),
               'seed':read(ROOT/'work/private-seeds.json',{}).get(str(session['run'])),
               'policy':'adaptive exploratory policy; no within-run resets'})
    write(RUNS / 'session.json',session)
    if method=='cash_out' and current.get('round',{}).get('cashout_dollars') is not None:
        expected=current['money']+current['round']['cashout_dollars']
        if data.get('money')!=expected:
            raise RuntimeError('Cashout audit mismatch: expected %s, got %s. Stop and inspect.'%(expected,data.get('money')))
    return data

def compact(s):
    if 'state' not in s:
        return s
    out = {k:s[k] for k in ('state','overlay','won','ante_num','round_num','money','deck','stake') if k in s}
    out['round'] = {k:v for k,v in s.get('round',{}).items() if k!='last_hand'}
    out['blinds'] = s.get('blinds')
    out['levels'] = {k:{'level':v['level'],'chips':v['chips'],'mult':v['mult'],'played':v.get('played',0)}
                     for k,v in s.get('hands',{}).items() if v.get('level',1)>1 or v.get('played',0)>0}
    for area in ('hand','jokers','consumables','shop','vouchers','packs','pack'):
        if s.get(area,{}).get('cards'):
            out[area] = []
            for i,c in enumerate(s[area]['cards']):
                out[area].append({'i':i,'key':c['key'],'effect':c.get('value',{}).get('effect',''),
                                  'mod':c.get('modifier'), 'state':c.get('state'), 'cost':c.get('cost')})
    if s.get('round',{}).get('last_hand'):
        h=s['round']['last_hand']
        out['last_hand'] = h.get('text',h)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('method',nargs='?',default='status')
    p.add_argument('params',nargs='?',default='{}')
    args=p.parse_args()
    if args.method=='batch':
        for method,params in json.loads(args.params):
            show(call(method,params))
        return
    method='gamestate' if args.method=='status' else args.method
    result=call(method,json.loads(args.params))
    show(result)

def show(s):
    if 'state' not in s:
        print(json.dumps(s,ensure_ascii=False,indent=2)); return
    r=s.get('round',{})
    print('%s overlay=%s won=%s | ante=%s round=%s $%s | score=%s hands=%s discards=%s' %
          (s['state'],s.get('overlay'),s.get('won'),s.get('ante_num'),s.get('round_num'),s.get('money'),
           r.get('chips'),r.get('hands_left'),r.get('discards_left')))
    for name,b in s.get('blinds',{}).items():
        if b.get('status') in ('SELECT','CURRENT') or name=='boss':
            print('%s %s %s target=%s %s | skip=%s %s' %
                  (name,b['status'],b['name'],b['score'],b.get('effect',''),b.get('tag_name',''),b.get('tag_effect','')))
    levels={k:(v['level'],v['chips'],v['mult']) for k,v in s.get('hands',{}).items() if v.get('level',1)>1}
    if levels: print('levels:',json.dumps(levels,ensure_ascii=False))
    for area in ('hand','jokers','consumables','shop','vouchers','packs','pack'):
        cards=s.get(area,{}).get('cards',[])
        if not cards: continue
        print(area+': '+ ' | '.join('%d:%s%s%s%s' %
              (i,c.get('key','?'), ' '+str(c['modifier']) if c.get('modifier') else '',
               ' '+str(c['state']) if c.get('state') else '',
               ' $%s %s' % (c.get('cost',{}).get('buy'), c.get('value',{}).get('effect','')) if area!='hand' else '')
               for i,c in enumerate(cards)))
    h=r.get('last_hand')
    if h: print('last:', h.get('text',json.dumps(h,ensure_ascii=False)))

if __name__ == '__main__':
    main()
