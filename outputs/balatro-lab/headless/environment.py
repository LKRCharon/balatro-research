"""AI environment over an isolated reference engine; no rendering dependency here.

This adapter still uses the complete Lua game behind RPC. It is not a rewritten
rules simulator. Mutations are journaled before sending and never auto-retried.
"""
from __future__ import annotations
import copy,hashlib,importlib.util,json,os,re,sqlite3,threading
from contextlib import closing
from pathlib import Path
from transport import RpcClient

LAB=Path(__file__).resolve().parents[1]
_spec=importlib.util.spec_from_file_location('headless_public_history',LAB/'cli/observations.py')
_history=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_history)
ACTIONS=set('select skip play discard cash_out next_round buy pack use sell rearrange reroll reroll_boss continue'.split())

def public(value):
    if isinstance(value,list):return [public(v) for v in value]
    if not isinstance(value,dict):return value
    if isinstance(value.get('state'),dict) and value['state'].get('hidden'):
        return {'key':'hidden','value':{},'modifier':{},'state':{'hidden':True}}
    return {k:public(v) for k,v in value.items() if not any(x in k.lower() for x in ('seed','rng','draw_order'))}

def sanitize(state,previous=None):
    state=public(copy.deepcopy(state))
    for area in ('hand','jokers','consumables','shop','vouchers','packs','pack'):
        for card in state.get(area,{}).get('cards',[]):
            for key in ('value','modifier','state','cost'):
                if card.get(key)==[]:card[key]={}
    if isinstance(state.get('cards'),dict):state['cards']={k:v for k,v in state['cards'].items() if k in ('count','limit')}
    _history.enrich(state,previous)
    return state

def terminal(s):return s.get('state')=='GAME_OVER' or s.get('overlay')=='win' or bool(s.get('won'))

def canonical_state(state):
    """Comparable public gameplay state; transient object IDs are not mechanics."""
    def strip(v):
        if isinstance(v,list):return [strip(x) for x in v]
        if isinstance(v,dict):return {k:strip(x) for k,x in v.items() if k not in ('id','sort_id','unique_val')}
        return v
    return strip(sanitize(state))

class Environment:
    def __init__(self,port,identity,log_dir,*,registry=None,client=None):
        if port==12346:raise ValueError('The ongoing training backend is protected')
        if not re.fullmatch(r'Balatro-Lab-[A-Za-z0-9_-]+',identity):raise ValueError('Isolated identity required')
        self.port=port;self.identity=identity;self.root=Path(log_dir);self.root.mkdir(parents=True,exist_ok=True)
        self.registry=Path(registry) if registry else LAB.parents[1]/'work/experiments/registry.sqlite'
        self.client=None;self.state=None;self.pending=None;self.sequence=0;self.mutex=threading.RLock();self._lease=None
        self.path=self.root/'transitions.jsonl'
        if self.path.exists():
            for line in self.path.read_text(encoding='utf8').splitlines():
                row=json.loads(line);self.sequence=max(self.sequence,row['id'])
                if row['event']=='intent':self.pending=row
                elif row['event']=='result' and self.pending and row['id']==self.pending['id']:self.pending=None
        if self.pending:raise RuntimeError('Unresolved mutation; reconcile before resuming')
        locks=LAB.parents[1]/'work/headless-port-locks';locks.mkdir(parents=True,exist_ok=True)
        lease=(locks/f'{port}.lock').open('a+b')
        if lease.tell()==0:lease.write(b'0');lease.flush()
        lease.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:
            lease.close();raise RuntimeError('Another controller owns this engine port')
        self._lease=lease
        try:
            self.client=client or RpcClient(port,timeout=60)
            info=self.client.call('lab_info');sound=info.get('sound',{})
            if not (info.get('identity')==identity and info.get('headless') and not info.get('graphics_active')
                    and info.get('mute') and info.get('master_volume')==0 and all(sound.get(k)==0 for k in ('volume','music_volume','game_sounds_volume'))
                    and info.get('desktop','').startswith('BalatroLab-')):
                raise RuntimeError('Runtime isolation/mute verification failed')
            self.runtime=info
        except Exception:self.close();raise

    def _write(self,row):
        with self.path.open('a',encoding='utf8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())

    def observe(self):
        with self.mutex:
            self.state=sanitize(self.client.call('gamestate'),self.state)
            return copy.deepcopy(self.state)

    def context(self):
        with self.mutex:
            return {'collection':public(self.client.call('lab_context')),
                    'targets':public(self.client.call('dynamics',{'targets':True,'cards':False}))}

    def _mutate(self,method,params):
        if self.pending:raise RuntimeError('Previous mutation outcome unresolved')
        self.sequence+=1
        logged=public(params)
        if 'seed' in params:logged['start_commitment']=hashlib.sha256(params['seed'].encode()).hexdigest()
        self.pending={'event':'intent','id':self.sequence,'method':method,'params':logged,'before':copy.deepcopy(self.state)}
        self._write(self.pending)
        # Any exception leaves durable intent outstanding. No retry, including HTTP errors.
        result=self.client.call(method,params)
        self.state=sanitize(result,self.state)
        self._write({'event':'result','id':self.sequence,'after':self.state})
        self.pending=None
        return copy.deepcopy(self.state)

    def reset(self,seed,*,intended_partition='train',job_id=None):
        with self.mutex:
            if not re.fullmatch('[A-Z0-9]{1,8}',seed):raise ValueError('Invalid seed')
            with closing(sqlite3.connect(f'file:{self.registry.as_posix()}?mode=ro',uri=True)) as db:
                row=db.execute('SELECT partition FROM seeds WHERE seed=?',(seed,)).fetchone()
                if intended_partition=='validation':
                    binding=db.execute('SELECT j.status,c.partition FROM jobs j JOIN seeds s ON s.id=j.seed_id JOIN campaigns c ON c.id=j.campaign_id WHERE j.id=? AND s.seed=?',(job_id,seed)).fetchone()
                    if row!=('validation',) or binding!=('running','validation'):
                        raise ValueError('Validation reset requires a claimed matching validation job')
                elif intended_partition!='train' or row!=('train',):
                    raise ValueError('This development adapter accepts registered training seeds only')
            current=self.observe()
            if current['state']!='MENU':
                if not terminal(current):raise ValueError('Refusing to reset an unfinished episode')
                self._mutate('menu',{'reason':'保留已完成的隔离机制实验，进入下一训练种子。'})
            return self._mutate('start',{'seed':seed,'deck':'BLUE','stake':'GOLD','reason':'隔离 CLI 机制一致性与并发训练实验；不读取未来随机信息。'})

    def step(self,method,params=None):
        with self.mutex:
            if method not in ACTIONS:raise ValueError('Not an allowed gameplay action')
            params=copy.deepcopy(params or {})
            if not isinstance(params.get('reason'),str) or not params['reason'].strip():raise ValueError('Reason required')
            if 'seed' in params:raise ValueError('No seed in gameplay actions')
            if self.state is None:self.observe()
            if terminal(self.state):raise ValueError('Episode already terminal')
            if method in ('play','discard'):
                indices=params.get('cards');n=len(self.state.get('hand',{}).get('cards',[]))
                if self.state['state']!='SELECTING_HAND' or not isinstance(indices,list) or not 1<=len(indices)<=5 or any(type(i) is not int or not 0<=i<n for i in indices) or len(set(indices))!=len(indices):raise ValueError('Invalid hand action')
                if method=='play' and indices!=sorted(indices):raise ValueError('Rearrange actual hand first')
            return self._mutate(method,params)

    def action_space(self):
        """Structural method mask only, NOT a complete legal action enumerator."""
        s=self.state or self.observe();phase=s['state']
        methods={'BLIND_SELECT':['select','skip'],'SELECTING_HAND':['play','discard','use','sell','rearrange'],
            'SHOP':['buy','sell','use','reroll','next_round','rearrange'],
            'ROUND_EVAL':['cash_out'],'SMODS_BOOSTER_OPENED':['pack','use','sell']}.get(phase,[])
        if terminal(s):methods=[]
        return {'methods':methods,'semantics':'structural_only; engine validates targets, capacity, money and Boss constraints'}

    def close(self):
        if self.client:self.client.close()
        if self._lease:
            self._lease.close();self._lease=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
