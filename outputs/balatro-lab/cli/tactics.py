"""Bounded discard sampling, a heuristic over hypothetical standard-deck draws.

Uses only the current visible hand; does not model deck modifications or every previously
seen card. Thus the returned mean is a policy score, NOT a calibrated probability.
"""
import collections, copy, hashlib, json, random, re
import advisor as a
import routes

def discard(s,best,need):
    cards=s['hand']['cards']; n=len(cards); ks=a.keys(s)
    if any(a.st(c).get('hidden') for c in cards):return a.discard(s,best)
    candidates=set()
    def add_keep(keep):
        drop=tuple(i for i in range(n) if i not in keep)
        if 0<len(drop)<=5:candidates.add(drop)
    old=tuple(a.discard(s,best))
    if old:candidates.add(old)
    add_keep(best[1]); add_keep(best[3])
    byrank=collections.defaultdict(list); bysuit=collections.defaultdict(list)
    for i,c in enumerate(cards):
        byrank[a.rank(c)].append(i);bysuit[a.suit(c)].append(i)
    for group in bysuit.values():
        if len(group)>=3:add_keep(group)
    paths=[]
    for rr in [range(k,k+5) for k in range(2,11)]+[[14,2,3,4,5]]:
        keep=[byrank[r][0] for r in rr if r in byrank]
        if len(keep)>=3:paths.append(keep)
    for keep in sorted(paths,key=lambda x:(-len(x),x))[:3]:add_keep(keep)
    if 'j_blackboard' in ks:
        red=tuple(i for i,c in enumerate(cards) if a.suit(c) in ('H','D'))
        if 0<len(red)<=5:candidates.add(red)
    if not candidates:return []
    used={c.get('key') for c in cards}
    deck=[{'key':su+'_'+r,'value':{'rank':r,'suit':su},'modifier':{},'state':{}}
          for su in ('S','H','C','D') for r in ('2','3','4','5','6','7','8','9','T','J','Q','K','A') if su+'_'+r not in used]
    target=routes.main_hand(s)
    boss=next(b['name'] for b in s['blinds'].values() if b['status']=='CURRENT')
    best_value=-1;choice=[]
    # Identical sample streams across actions reduce arbitrary comparison noise.
    seed=int.from_bytes(hashlib.sha256(json.dumps(cards,sort_keys=True).encode()).digest()[:4],'little')
    for dropped in sorted(candidates):
        vals=[];rng=random.Random(seed)
        sim=copy.deepcopy(s);sim['round']['discards_left']-=1
        sim['cards']['count']=max(0,sim['cards']['count']-len(dropped))
        for j in sim['jokers']['cards']:
            if j['key'] in ('j_green_joker','j_ramen'):
                value=max(0,a.current_number(j)-(1 if j['key']=='j_green_joker' else .01*len(dropped)))
                j['value']['effect']=re.sub(r'(当前[^\d+-]*)([+-]?[\d.]+)',lambda m:m[1]+str(value),j['value']['effect'])
        for _ in range(12):
            hand=[copy.deepcopy(c) for i,c in enumerate(cards) if i not in dropped]+copy.deepcopy(rng.sample(deck,len(dropped)))
            banned={'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(boss)
            for c in hand:
                if a.suit(c)==banned or (boss=='The Plant' and a.rank(c) in(11,12,13)):c['state']['debuff']=True
            sim['hand']['cards']=hand
            opts=a.options(sim,optimize_order=False)
            value,_,name,_=opts[0]
            vals.append(min(value,need)*(1.04 if name==target else 1))
        vals.sort();v=.7*sum(vals)/len(vals)+.3*vals[2]
        if v>best_value:best_value=v;choice=list(dropped)
    # Do not break a sufficient existing hand merely because simulated outcomes fluctuate.
    threshold=1.15 if ks&{'j_green_joker','j_ramen'} else 1.04
    return choice if best_value>min(best[0],need)*threshold else []
