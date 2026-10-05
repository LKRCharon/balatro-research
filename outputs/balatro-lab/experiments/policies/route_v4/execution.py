"""Pure action checks and durable intent journal; no automatic mutation retries."""
import hashlib,json,os

def fingerprint(state):
    return hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def validate(state,method,params):
    if method not in {'play','discard','rearrange','sell','use','buy','pack','select','cash_out','next_round','reroll','continue'}:
        raise ValueError('Action not permitted in worker: '+method)
    if not isinstance(params.get('reason'),str) or not params['reason'].strip():
        raise ValueError('Decision reason required')
    def indices(values,size,permutation=False):
        if not isinstance(values,(list,tuple)) or any(type(i) is not int or not 0<=i<size for i in values) or len(set(values))!=len(values):
            raise ValueError('Invalid or duplicate card indices')
        if permutation and set(values)!=set(range(size)):raise ValueError('Incomplete permutation')
    if method in ('play','discard'):
        if state['state']!='SELECTING_HAND':raise ValueError('No active hand')
        selected=params.get('cards');indices(selected,len(state['hand']['cards']))
        if not 1<=len(selected)<=5:raise ValueError('Select 1 to 5 cards')
        if state['round']['hands_left' if method=='play' else 'discards_left']<=0:raise ValueError('Resource exhausted')
        if method=='play' and list(selected)!=sorted(selected):
            raise ValueError('Explicitly rearrange hand before submitting nonascending play indices')
    if method=='rearrange':
        areas=[k for k in ('hand','jokers') if k in params]
        if len(areas)!=1:raise ValueError('Rearrange exactly one area')
        area=areas[0];indices(params[area],len(state[area]['cards']),True)
        if list(params[area])==list(range(len(state[area]['cards']))):raise ValueError('No-op rearrangement')
    if method=='sell':
        areas=[(k,area) for k,area in [('joker','jokers'),('consumable','consumables')] if k in params]
        if len(areas)!=1:raise ValueError('Sell exactly one item')
        key,area=areas[0];indices([params[key]],len(state[area]['cards']))
        if key=='joker' and (state[area]['cards'][params[key]].get('modifier') or {}).get('eternal'):
            raise ValueError('Cannot sell an eternal Joker')

class Journal:
    def __init__(self,path):
        self.path=path;self.path.parent.mkdir(parents=True,exist_ok=True);self.pending=None;self.seen=set()
        if path.exists():
            for line in path.read_text(encoding='utf8').splitlines():
                row=json.loads(line)
                if row['event']=='intent':
                    self.pending=row;self.seen.add(row['id'])
                elif row['event']=='result':
                    if self.pending and row['id']==self.pending['id']:self.pending=None
            if self.pending:raise RuntimeError('Unresolved action intent; reconcile engine state before resuming')
    def write(self,row):
        with self.path.open('a',encoding='utf8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    def begin(self,state,method,params):
        validate(state,method,params)
        if self.pending:raise RuntimeError('Previous mutation unresolved')
        identity=fingerprint({'state':state,'method':method,'params':{k:v for k,v in params.items() if k!='reason'}})
        if identity in self.seen:raise RuntimeError('Repeated identical state/action; possible decision loop')
        self.seen.add(identity);self.pending={'event':'intent','id':identity,'before_sha256':fingerprint(state),'method':method,'params':params}
        self.write(self.pending);return identity
    def finish(self,state):
        if not self.pending:raise RuntimeError('No pending mutation')
        self.write({'event':'result','id':self.pending['id'],'after_sha256':fingerprint(state),'state':state.get('state')})
        self.pending=None
