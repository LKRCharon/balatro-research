"""Bounded discard sampling, a heuristic over hypothetical standard-deck draws.

Uses only the current visible hand; does not model deck modifications or every previously
seen card. Thus the returned mean is a policy score, NOT a calibrated probability.
"""
import collections, copy, hashlib, json, random, re
import advisor as a
import routes
from belief import base_deck
import copying
from scoring import matches,face,rank_id

TAIL_WEIGHT=0.3
SAMPLES=12

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
    targets=s.get('_targets',{})
    su={'Spades':'S','Hearts':'H','Clubs':'C','Diamonds':'D'}.get(targets.get('j_castle',{}).get('suit'))
    raw=str(targets.get('j_mail',{}).get('rank',''))
    mail_rank=a.RANK.get({'Ace':'A','King':'K','Queen':'Q','Jack':'J','10':'T'}.get(raw,raw))
    for group in ([i for i,c in enumerate(cards) if 'j_mail' in ks and rank_id(c)==mail_rank],
                  [i for i,c in enumerate(cards) if 'j_castle' in ks and matches(c,su,ks)],
                  [i for i,c in enumerate(cards) if 'j_hit_the_road' in ks and rank_id(c)==11],
                  [i for i,c in enumerate(cards) if a.mod(c).get('seal')=='PURPLE']):
        if group:candidates.add(tuple(group[:5]))
    faces=[i for i,c in enumerate(cards) if face(c,ks)]
    if 'j_faceless' in ks and len(faces)>=3:candidates.add(tuple(faces[:5]))
    forced={i for i,c in enumerate(cards) if a.st(c).get('highlight')}
    if forced:candidates={tuple(sorted(set(c)|forced)) for c in candidates if len(set(c)|forced)<=5}
    if not candidates:return []
    used={c.get('key') for c in cards}
    deck=s.get('_belief',{}).get('unseen',[c for k,c in base_deck().items() if k not in used])
    target=routes.main_hand(s)
    boss=next(b['name'] for b in s['blinds'].values() if b['status']=='CURRENT')
    best_value=-1;choice=[]
    # Identical sample streams across actions reduce arbitrary comparison noise.
    visible=[{k:c.get(k) for k in ('key','value','modifier','state')} for c in cards]
    seed=int.from_bytes(hashlib.sha256(json.dumps(visible,sort_keys=True).encode()).digest()[:4],'little')
    for dropped in sorted(candidates):
        drawn=min(len(deck),3 if boss=='The Serpent' else max(0,s['hand']['limit']-(n-len(dropped))))
        vals=[];rng=random.Random(seed)
        sim=copy.deepcopy(s);sim['round']['discards_left']-=1
        sim['cards']['count']=max(0,sim['cards']['count']-drawn)
        cash_gain=5*copying.count(s,'j_mail')*sum(rank_id(cards[i])==mail_rank for i in dropped)
        cash_gain+=5*copying.count(s,'j_faceless')*(sum(face(cards[i],ks) for i in dropped)>=3)
        sim['money']+=cash_gain
        for j in sim['jokers']['cards']:
            if j['key'] in ('j_green_joker','j_ramen'):
                value=max(0,a.current_number(j)-(1 if j['key']=='j_green_joker' else .01*len(dropped)))
                j['value']['effect']=re.sub(r'(当前[^\d+-]*)([+-]?[\d.]+)',lambda m:m[1]+str(value),j['value']['effect'])
            if j['key'] in ('j_castle','j_hit_the_road'):
                delta=3*sum(matches(cards[i],su,ks) for i in dropped) if j['key']=='j_castle' else .5*sum(rank_id(cards[i])==11 for i in dropped)
                value=a.current_number(j)+delta
                j['value']['effect']=re.sub(r'(当前[^\d+-]*)([+-]?[\d.]+)',lambda m:m[1]+str(value),j['value']['effect'])
        for _ in range(SAMPLES):
            hand=[copy.deepcopy(c) for i,c in enumerate(cards) if i not in dropped]+copy.deepcopy(rng.sample(deck,drawn))
            # Bell chooses another card after a discard; no identity prediction is available.
            for c in hand:c['state'].pop('highlight',None)
            banned={'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(boss)
            for c in hand:
                if a.suit(c)==banned or (boss=='The Plant' and a.rank(c) in(11,12,13)):c['state']['debuff']=True
            sim['hand']['cards']=hand
            opts=a.options(sim,optimize_order=False)
            value,_,name,_=opts[0]
            vals.append(min(value,need)*(1.04 if name==target else 1))
        vals.sort();v=(1-TAIL_WEIGHT)*sum(vals)/len(vals)+TAIL_WEIGHT*vals[max(0,len(vals)//4-1)]
        slots=max(0,s['consumables']['limit']-len(s['consumables']['cards']))
        cash_gain+=3*min(slots,sum(a.mod(cards[i]).get('seal')=='PURPLE' for i in dropped))
        if 'j_delayed_grat' in ks and s['round']['discards_used']==0:cash_gain-=2*s['round']['discards_left']
        v+=cash_gain*max(8,best[0]/50)
        if v>best_value:best_value=v;choice=list(dropped)
    # Do not break a sufficient existing hand merely because simulated outcomes fluctuate.
    threshold=1.15 if ks&{'j_green_joker','j_ramen'} else 1.04
    return choice if best_value>min(best[0],need)*threshold else []

def choose(s,opts,need):
    """Survival first, then public economic/growth/held-seal value; no unseen outcomes."""
    ks=a.keys(s);cards=s['hand']['cards'];counts=collections.Counter(j['key'] for j in copying.effective(s) if not a.st(j).get('debuff'))
    normal=s.get('_normal_probability',1);slots=max(0,s['consumables']['limit']-len(s['consumables']['cards']))
    todo=s.get('_targets',{}).get('j_todo_list',{}).get('poker_hand')
    scale=max(8,min(300,need/50))
    def value(o):
        score,selected,name,scored=o;floor=a.conservative_score(s,selected,score)
        win=floor is not None and floor>=need;held=[c for i,c in enumerate(cards) if i not in selected]
        paying=[cards[i] for i in scored if not a.st(cards[i]).get('debuff')]
        dollars=counts['j_todo_list']*4*(name==todo)
        dollars+=counts['j_business']*2*min(1,normal/2)*sum(face(c,ks) for c in paying)
        dollars+=counts['j_rough_gem']*sum(matches(c,'D',ks) for c in paying)
        dollars+=counts['j_ticket']*4*sum(a.mod(c).get('enhancement')=='GOLD' for c in paying)
        tarot=counts['j_8_ball']*min(1,normal/4)*sum(rank_id(c)==8 for c in paying)
        tarot+=counts['j_superposition']*(name in ('Straight','Straight Flush') and any(rank_id(cards[i])==14 for i in selected))
        tarot+=counts['j_vagabond']*(s['money']<=4)+2*counts['j_seance']*(name=='Straight Flush')
        dollars+=3*min(slots,tarot)
        growth=.35*counts['j_hiker']*len(paying)+.8*counts['j_wee']*sum(rank_id(c)==2 for c in paying)
        if win:
            dollars+=sum((3*(a.mod(c).get('enhancement')=='GOLD')+5*(a.mod(c).get('seal')=='BLUE'))*(1+counts['j_mime']+int(a.mod(c).get('seal')=='RED')) for c in held if not a.st(c).get('debuff'))
        fragility=sum(a.mod(c).get('enhancement')=='GLASS' for c in paying)*min(1,normal/4)*2
        bonus=scale*(dollars+growth-fragility)
        return int(win),min(score,need)+bonus,-len(selected),score
    return max(opts,key=value)
