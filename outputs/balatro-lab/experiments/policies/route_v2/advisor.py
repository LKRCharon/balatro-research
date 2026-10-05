"""Visible-information hand advisor, deliberately incomplete. Stops on unsupported scoring Jokers.

This is an exploratory baseline, not an optimal solver. Discard choice is a heuristic.
No game seed, future draws, or engine RNG is used. Predictions are checked against real results.
"""
import collections, itertools, json, math, re, sys
from pathlib import Path
import balatro_cli as cli

NAMES=['High Card','Pair','Two Pair','Three of a Kind','Straight','Flush','Full House','Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five']
RANK={**{str(i):i for i in range(2,10)},'T':10,'J':11,'Q':12,'K':13,'A':14}
from copying import SPECS
SUPPORTED=set(SPECS)
LEVEL_DELTA=dict(zip(NAMES,[(10,1),(15,1),(20,1),(20,2),(30,3),(15,2),(25,2),(30,3),(40,4),(35,3),(40,4),(50,3)]))

def uncertain(s):
    boss=next((b['name'] for b in s.get('blinds',{}).values() if b['status']=='CURRENT'),'')
    return bool(s.get('_uncertain_jokers')) or boss in {'The Hook','The Ox'} or bool(keys(s)&{'j_misprint','j_space','j_bloodstone','j_lucky_cat','j_business','j_reserved_parking','j_loyalty_card'}) or any(st(c).get('hidden') or mod(c).get('enhancement')=='LUCKY' for c in s['hand']['cards'])

def mod(c): return c.get('modifier') or {}
def st(c): return c.get('state') or {}
def rank(c): return RANK.get((c.get('value') or {}).get('rank'),0)
def suit(c): return (c.get('value') or {}).get('suit')
def keys(s): return {c['key'] for c in s.get('jokers',{}).get('cards',[]) if not st(c).get('debuff')}
def current_number(c, default=0):
    t=c.get('value',{}).get('effect','')
    m=re.search(r'当前[^\d+-]*([+-]?[\d.]+)',t)
    if m: return float(m[1])
    m=re.search(r'([+-]?[\d.]+)',t)
    return float(m[1]) if m else default

def classify(cards, selected, four_fingers=False, shortcut=False, smeared=False):
    nonstone=[i for i in selected if mod(cards[i]).get('enhancement')!='STONE' and not st(cards[i]).get('hidden')]
    counts=collections.Counter(rank(cards[i]) for i in nonstone)
    groups=sorted(counts.values(),reverse=True)
    minimum=4 if four_fingers else 5
    flush_cards=[]
    for su in ('S','H','C','D'):
        candidate=[i for i in nonstone if suit(cards[i])==su or (smeared and (suit(cards[i]) in ('H','D'))==(su in ('H','D'))) or
                   (mod(cards[i]).get('enhancement')=='WILD' and not st(cards[i]).get('debuff'))]
        if len(candidate)>=minimum:
            flush_cards=candidate;break
    # Match the original ascending Ace-low then Ace-high scan, retaining duplicate ranks.
    straight_cards=[]; length=0; found=False; skipped=False
    for scan,r in enumerate([14]+list(range(2,15))):
        if counts[r]:
            length+=1; skipped=False
            straight_cards.extend(i for i in nonstone if rank(cards[i])==r)
        elif shortcut and not skipped and scan!=13:
            skipped=True
        else:
            length=0; skipped=False
            if found:break
            straight_cards=[]
        if length>=minimum:found=True
    if not found:straight_cards=[]
    flush=bool(flush_cards);straight=bool(straight_cards)
    ranks=sorted(counts)
    if groups==[5]: cat=11 if flush else 9
    elif groups==[3,2]: cat=10 if flush else 6
    elif straight and flush: cat=8
    elif 4 in groups: cat=7
    elif flush: cat=5
    elif straight: cat=4
    elif 3 in groups: cat=3
    elif groups.count(2)==2: cat=2
    elif 2 in groups: cat=1
    else: cat=0
    group=set(straight_cards if cat==4 else flush_cards if cat==5 else
              straight_cards+flush_cards if cat==8 else [])
    scored=[i for i in selected if mod(cards[i]).get('enhancement')=='STONE' or i in group or
            (i in nonstone and (cat in (6,9,10,11) or (cat==7 and counts[rank(cards[i])]==4) or
            (cat==3 and counts[rank(cards[i])]==3) or (cat in(1,2) and counts[rank(cards[i])]==2) or
            (cat==0 and rank(cards[i])==max(ranks,default=0))))]
    return cat, scored, counts

def score(s, selected):
    from scoring import score as implementation
    return implementation(s,selected)

def conservative_score(s,selected,expected=None):
    """Conservative score only for deterministic or Lucky-only supported states.

    None means unverified, not zero or a calibrated failure probability.
    """
    if not uncertain(s):return score(s,selected)[0] if expected is None else expected
    boss=next((b['name'] for b in s.get('blinds',{}).values() if b['status']=='CURRENT'),'')
    if s.get('_uncertain_jokers') or boss in {'The Hook','The Ox'} or keys(s)&{'j_misprint','j_space','j_bloodstone','j_lucky_cat','j_business','j_reserved_parking','j_loyalty_card'}:
        return None
    if any(st(c).get('hidden') for c in s['hand']['cards']):return None
    # Lucky chips are deterministic; zero all lucky mult and cash successes.
    import copy
    lower=copy.deepcopy(s);lower['_normal_probability']=0
    return score(lower,selected)[0]

def options(s,optimize_order=True):
    unsupported=keys(s)-SUPPORTED
    if unsupported: raise ValueError('Unsupported Joker(s): '+str(unsupported))
    result=[]
    boss=next((b['name'] for b in s.get('blinds',{}).values() if b['status']=='CURRENT'),'')
    forced={i for i,c in enumerate(s['hand']['cards']) if st(c).get('highlight')} if boss=='Cerulean Bell' else set()
    reorder=optimize_order and bool(keys(s)&{'j_hanging_chad','j_photograph'})
    for n in range(1,min(5,len(s['hand']['cards']))+1):
        for indices in itertools.combinations(range(len(s['hand']['cards'])),n):
            if not forced.issubset(indices):continue
            value,name,scored=score(s,indices)
            result.append((value,indices,name,scored))
            if reorder and len(scored)>1:
                # Try each scoring card first; exact hand permutations are unnecessary here.
                for first in scored:
                    ordered=(first,)+tuple(i for i in indices if i!=first)
                    if ordered==indices:continue
                    value2,name2,scored2=score(s,ordered)
                    if value2>value:result.append((value2,ordered,name2,scored2))
    return sorted(result,key=lambda x:(-x[0],len(x[1]),x[1]))

def discard(s,best):
    cards=s['hand']['cards']; n=len(cards)
    bysuit=collections.defaultdict(list); byrank=collections.defaultdict(list)
    for i,c in enumerate(cards):
        if not st(c).get('debuff') and not st(c).get('hidden'): bysuit[suit(c)].append(i); byrank[rank(c)].append(i)
    same=max(bysuit.values(),key=len,default=[])
    keep=list(best[3])
    if best[2] in ('Flush','Full House','Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five','Straight'):
        return [i for i in range(n) if i not in keep][:5]
    if len(same)==4 and 'j_half' not in keys(s): keep=same
    elif best[2] in('Pair','Two Pair','Three of a Kind'): pass
    else:
        paths=[]
        for ranks in [set(range(i,i+5)) for i in range(2,11)]+[{14,2,3,4,5}]:
            chosen=[byrank[r][0] for r in ranks if byrank[r]]
            paths.append(chosen)
        straight=max(paths,key=len)
        if len(straight)==4: keep=straight
        elif len(same)>=3: keep=same
    omitted=[i for i in range(n) if i not in keep]
    return sorted(omitted,key=lambda i:rank(cards[i]))[:5]

def auto(limit=20):
    s=cli.read(cli.RUNS/'current.json',{})
    for _ in range(limit):
        if s.get('overlay'): cli.show(s); return
        if s['state']=='ROUND_EVAL':
            s=cli.call('cash_out',{'reason':'本轮已过关，领取剩余出牌与利息收入，进入商店检查阵容和经济。'}); cli.show(s); return
        if s['state']!='SELECTING_HAND': cli.show(s); return
        opts=options(s); best=opts[0]
        target=next(b['score'] for b in s['blinds'].values() if b['status']=='CURRENT')
        remaining=target-s['round']['chips']
        discarded=discard(s,best)
        ks=keys(s)
        # Save discards when they directly supply multiplier/chips; otherwise spend them to improve a weak hand.
        should_discard=s['round']['discards_left']>0 and best[0]<remaining and bool(discarded) and not ks.intersection({'j_green_joker','j_banner','j_ramen'})
        if should_discard:
            print('discard',discarded,'current best',best[:3],flush=True)
            s=cli.call('discard',{'cards':discarded,'reason':f'当前最佳{name_zh(best[2])}预计{best[0]}分，尚差{remaining}分；利用免费弃牌保留组合核心，提高这手质量。'})
        else:
            print('play',best[:3],flush=True)
            s=cli.call('play',{'cards':list(best[1]),'reason':f'选择{name_zh(best[2])}，当前可见信息估分约{best[0]}；本轮尚差{remaining}分。按实际结算核对预测。'})
            actual=s.get('round',{}).get('last_hand',{}).get('total')
            with (cli.RUNS/'predictions.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'run':cli.read(cli.RUNS/'session.json')['run'],'ante':s.get('ante_num'),'round':s.get('round_num'),'cards':list(best[1]),'predicted':best[0],'actual':actual},ensure_ascii=False)+'\n')
            if actual is not None and abs(actual-best[0])>0.5:
                print('Prediction mismatch: automatic play paused for inspection.',flush=True);cli.show(s);return
        if cli.terminal(s): cli.show(s); return
    cli.show(s)

def name_zh(n): return dict(zip(NAMES,['高牌','对子','两对','三条','顺子','同花','葫芦','四条','同花顺','五条','同花葫芦','同花五条']))[n]
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='auto': auto()
    else:
        s=cli.read(cli.RUNS/'current.json'); print(json.dumps(options(s)[:12],ensure_ascii=False))
