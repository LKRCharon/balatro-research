"""Resolve Blueprint/Brainstorm chains; ability copies exclude editions and passive effects."""
import copy,json,itertools
from pathlib import Path
SPECS=json.loads(Path(__file__).with_name('joker_specs.json').read_text(encoding='utf-8'))
COPY={'j_blueprint','j_brainstorm'}

def target(cards,index):
    seen=set();i=index
    while 0<=i<len(cards):
        if i in seen or cards[i].get('state',{}).get('debuff'):return None
        seen.add(i);key=cards[i]['key']
        if key not in COPY:
            return i if i==index or SPECS.get(key,{}).get('blueprint_compat',False) else None
        i=i+1 if key=='j_blueprint' else 0
    return None

def effective(s):
    cards=s['jokers']['cards'];out=[]
    for i,physical in enumerate(cards):
        dest=target(cards,i)
        if dest is None:
            c=copy.deepcopy(physical);c['_inactive_copy']=physical['key'] in COPY
        else:
            c=copy.deepcopy(cards[dest]);c['modifier']=copy.deepcopy(physical.get('modifier',{}));c['state']=copy.deepcopy(physical.get('state',{}))
        c['_physical_key']=physical['key'];c['_source_index']=dest;c['_copied']=dest is not None and dest!=i
        out.append(c)
    return out

def count(s,key):return sum(c['key']==key and not c.get('state',{}).get('debuff') and not c.get('_inactive_copy') for c in effective(s))

def candidate_orders(s):
    cards=s['jokers']['cards'];n=len(cards);current=tuple(range(n));orders={current}
    bps=[i for i,c in enumerate(cards) if c['key']=='j_blueprint'];brains=[i for i,c in enumerate(cards) if c['key']=='j_brainstorm']
    plain=[i for i,c in enumerate(cards) if c['key'] not in COPY]
    if not bps and not brains:return [current]
    # Five-slot lineups are cheap enough to enumerate: ordering flat Mult before
    # XMult and splitting multiple copiers across targets can change the optimum.
    if n<=5:
        return [current]+[p for p in itertools.permutations(range(n)) if p!=current]
    compatible=[i for i in plain if SPECS[cards[i]['key']]['blueprint_compat'] and not cards[i].get('state',{}).get('debuff')]
    for left in compatible or plain:
        for right in compatible or plain:
            base=([left] if brains else [])+[i for i in plain if not brains or i!=left]
            if bps:
                at=base.index(right);base[at:at]=bps
            base+=brains
            if len(base)==n:orders.add(tuple(base))
    return [current]+sorted(orders-{current})
