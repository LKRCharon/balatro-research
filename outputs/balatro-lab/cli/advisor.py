"""Visible-information hand advisor, deliberately incomplete. Stops on unsupported scoring Jokers.

This is an exploratory baseline, not an optimal solver. Discard choice is a heuristic.
No game seed, future draws, or engine RNG is used. Predictions are checked against real results.
"""
import collections, itertools, json, math, re, sys
from pathlib import Path
import balatro_cli as cli

NAMES=['High Card','Pair','Two Pair','Three of a Kind','Straight','Flush','Full House','Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five']
RANK={**{str(i):i for i in range(2,10)},'T':10,'J':11,'Q':12,'K':13,'A':14}
SUPPORTED={'j_joker','j_half','j_abstract','j_mystic_summit','j_banner','j_gros_michel','j_popcorn','j_ice_cream','j_blue_joker',
 'j_even_steven','j_odd_todd','j_scholar','j_fibonacci','j_scary_face','j_splash','j_hanging_chad','j_smiley',
 'j_greedy_joker','j_lusty_joker','j_wrathful_joker','j_gluttenous_joker',
 'j_jolly','j_zany','j_mad','j_crazy','j_droll','j_sly','j_wily','j_clever','j_devious','j_crafty',
 'j_duo','j_trio','j_family','j_order','j_tribe','j_blackboard','j_flower_pot','j_photograph',
 'j_green_joker','j_supernova','j_ride_the_bus','j_runner','j_square','j_castle','j_trousers','j_flash','j_swashbuckler','j_fortune_teller',
 'j_loyalty_card','j_card_sharp','j_ramen','j_vampire','j_hologram','j_constellation','j_madness','j_obelisk',
 'j_raised_fist','j_baron','j_shoot_the_moon','j_steel_joker','j_drivers_license','j_baseball','j_bull','j_bootstraps','j_stuntman',
 'j_credit_card','j_to_the_moon','j_rocket','j_golden','j_egg','j_dna','j_todo_list','j_delayed_grat','j_diet_cola','j_luchador',
 'j_juggler','j_troubadour','j_turtle_bean','j_dusk','j_sock_and_buskin','j_seltzer','j_certificate','j_drifter',
 'j_mime','j_matador','j_mail','j_business','j_space','j_satellite','j_chaos','j_reserved_parking','j_faceless','j_trading','j_sixth_sense','j_8_ball','j_superposition'}

SUPPORTED -= {'j_vampire','j_drivers_license','j_baseball','j_space','j_loyalty_card'}
SUPPORTED |= {'j_walkie_talkie','j_red_card','j_misprint','j_cartomancer','j_golden_ticket','j_rough_gem'}

def uncertain(s):
    return 'j_misprint' in keys(s) or any(st(c).get('hidden') or mod(c).get('enhancement')=='LUCKY' for c in s['hand']['cards'])

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

def classify(cards, selected):
    nonstone=[i for i in selected if mod(cards[i]).get('enhancement')!='STONE' and not st(cards[i]).get('hidden')]
    counts=collections.Counter(rank(cards[i]) for i in nonstone)
    groups=sorted(counts.values(),reverse=True)
    suits=set(suit(cards[i]) for i in nonstone if mod(cards[i]).get('enhancement')!='WILD')
    flush=len(nonstone)==5 and len(suits)<=1
    ranks=sorted(counts)
    straight=len(ranks)==5 and (ranks[-1]-ranks[0]==4 or ranks==[2,3,4,5,14])
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
    scored=[i for i in selected if mod(cards[i]).get('enhancement')=='STONE' or
            cat in (4,5,6,8,9,10,11) or (cat==7 and counts[rank(cards[i])]==4) or
            (cat==3 and counts[rank(cards[i])]==3) or (cat in(1,2) and counts[rank(cards[i])]==2) or
            (cat==0 and rank(cards[i])==max(ranks,default=0))]
    return cat, scored, counts

def score(s, selected):
    cards=s['hand']['cards']; js=s['jokers']['cards']; ks=keys(s)
    cat,scored,counts=classify(cards,selected); name=NAMES[cat]
    h=s['hands'][name]; chips=float(h['chips']); mult=float(h['mult'])
    boss=next((b['name'] for b in s['blinds'].values() if b['status']=='CURRENT'),'')
    if boss=='The Psychic' and len(selected)!=5: return 0,name,scored
    if boss=='The Eye' and h.get('played_this_round',0)>0: return 0,name,scored
    if boss=='The Mouth':
        locked=s['round'].get('mouth_hand')
        prior=[n for n,h0 in s['hands'].items() if h0.get('played_this_round',0)>0]
        if not locked and len(prior)>1:raise ValueError('The Mouth requires public first-hand history')
        locked=locked or (prior[0] if prior else None)
        if locked and name!=locked:return 0,name,scored
    if boss=='The Flint': chips=math.floor(chips/2+0.5); mult=math.floor(mult/2+0.5)
    if 'j_splash' in ks: scored=list(selected)
    firstface=True
    for ordinal,i in enumerate(scored):
        c=cards[i]; r=rank(c); m=mod(c)
        if st(c).get('debuff'): continue
        face=r in(11,12,13)
        reps=1+(m.get('seal')=='RED')+(2 if ordinal==0 and 'j_hanging_chad' in ks else 0)
        reps+= int('j_sock_and_buskin' in ks and face)+int('j_seltzer' in ks)+int('j_dusk' in ks and s['round']['hands_left']==1)
        for _ in range(reps):
            chips+=50 if m.get('enhancement')=='STONE' else (11 if r==14 else min(r,10))
            if m.get('enhancement')=='BONUS': chips+=30
            if m.get('enhancement')=='MULT': mult+=4
            if m.get('enhancement')=='GLASS': mult*=2
            # Lucky multiplier is random: prediction uses its expectation, not future RNG.
            if m.get('enhancement')=='LUCKY': mult+=4
            if m.get('edition')=='FOIL': chips+=50
            if m.get('edition')=='HOLO': mult+=10
            if m.get('edition')=='POLYCHROME': mult*=1.5
            for j in js:
                if st(j).get('debuff'): continue
                k=j['key']
                if k=='j_even_steven' and r in(2,4,6,8,10): mult+=4
                if k=='j_odd_todd' and r in(3,5,7,9,14): chips+=31
                if k=='j_scholar' and r==14: chips+=20; mult+=4
                if k=='j_fibonacci' and r in(2,3,5,8,14): mult+=8
                if k=='j_walkie_talkie' and r in(4,10): chips+=10; mult+=4
                if k=='j_scary_face' and face: chips+=30
                if k=='j_smiley' and face: mult+=5
                if k=='j_photograph' and face and firstface: mult*=2
                if k in ('j_greedy_joker','j_lusty_joker','j_wrathful_joker','j_gluttenous_joker'):
                    target={'j_greedy_joker':'D','j_lusty_joker':'H','j_wrathful_joker':'S','j_gluttenous_joker':'C'}[k]
                    if suit(c)==target or m.get('enhancement')=='WILD': mult+=3
        if face: firstface=False
    held=[c for i,c in enumerate(cards) if i not in selected]
    for c in held:
        if st(c).get('debuff'): continue
        reps=1+int(mod(c).get('seal')=='RED')+int('j_mime' in ks)
        for _ in range(reps):
            if mod(c).get('enhancement')=='STEEL': mult*=1.5
            if 'j_baron' in ks and rank(c)==13: mult*=1.5
            if 'j_shoot_the_moon' in ks and rank(c)==12: mult+=13
    # Flat/X multipliers apply in held Joker order, including editions.
    for j in js:
        if st(j).get('debuff'): continue
        k=j['key']; val=current_number(j); jm=mod(j)
        if jm.get('edition')=='FOIL': chips+=50
        if jm.get('edition')=='HOLO': mult+=10
        if k=='j_joker': mult+=4
        elif k=='j_half' and len(selected)<=3: mult+=20
        elif k=='j_abstract': mult+=3*len(js)
        elif k=='j_mystic_summit' and s['round']['discards_left']==0: mult+=15
        elif k=='j_banner': chips+=30*s['round']['discards_left']
        elif k=='j_gros_michel': mult+=15
        elif k=='j_popcorn': mult+=val
        elif k=='j_ice_cream': chips+=val
        elif k=='j_blue_joker': chips+=2*s['cards']['count']
        elif k=='j_supernova': mult+=h.get('played',0)+1
        elif k=='j_green_joker': mult+=val+1
        elif k=='j_ride_the_bus': mult+=0 if any(rank(cards[i]) in(11,12,13) for i in scored) else val+1
        elif k=='j_trousers': mult+=val+(2 if sum(v>=2 for v in counts.values())>=2 else 0)
        elif k in('j_flash','j_swashbuckler','j_fortune_teller','j_red_card'): mult+=val
        elif k=='j_misprint': mult+=11.5
        elif k=='j_square': chips+=val+(4 if len(selected)==4 else 0)
        elif k=='j_runner': chips+=val+(15 if cat in(4,8) else 0)
        elif k=='j_castle': chips+=val
        elif k=='j_bull': chips+=2*max(0,s['money'])
        elif k=='j_bootstraps': mult+=2*math.floor(max(0,s['money'])/5)
        elif k=='j_stuntman': chips+=250
        elif k=='j_raised_fist' and held:
            c=min(held,key=rank)
            if not st(c).get('debuff'): mult+=2*(11 if rank(c)==14 else min(rank(c),10))
        elif k in('j_jolly','j_zany','j_mad','j_crazy','j_droll','j_sly','j_wily','j_clever','j_devious','j_crafty'):
            index=['j_jolly','j_zany','j_mad','j_crazy','j_droll','j_sly','j_wily','j_clever','j_devious','j_crafty'].index(k)
            cond=[max(counts.values(),default=0)>=2,max(counts.values(),default=0)>=3,sum(v>=2 for v in counts.values())>=2,cat in(4,8),cat in(5,8,10,11)][index%5]
            if cond:
                if index<5: mult+=[8,12,10,12,10][index]
                else: chips+=[50,100,80,100,80][index-5]
        elif k in('j_duo','j_trio','j_family','j_order','j_tribe'):
            idx=['j_duo','j_trio','j_family','j_order','j_tribe'].index(k)
            if [max(counts.values(),default=0)>=2,max(counts.values(),default=0)>=3,max(counts.values(),default=0)>=4,cat in(4,8),cat in(5,8,10,11)][idx]: mult*=[2,3,4,3,2][idx]
        elif k=='j_blackboard' and all(suit(c) in('S','C') for c in held): mult*=3
        elif k=='j_flower_pot' and len({suit(cards[i]) for i in scored if not st(cards[i]).get('debuff')})==4: mult*=3
        elif k=='j_card_sharp' and h.get('played_this_round',0)>0: mult*=3
        elif k in('j_ramen','j_hologram','j_constellation','j_madness','j_obelisk','j_steel_joker'): mult*=val or 1
        elif k=='j_loyalty_card' and ('0' in j['value']['effect']): mult*=4
        if jm.get('edition')=='POLYCHROME': mult*=1.5
    return math.floor(chips*mult),name,scored

def options(s,optimize_order=True):
    unsupported=keys(s)-SUPPORTED
    if unsupported: raise ValueError('Unsupported Joker(s): '+str(unsupported))
    result=[]
    reorder=optimize_order and bool(keys(s)&{'j_hanging_chad','j_photograph'})
    for n in range(1,min(5,len(s['hand']['cards']))+1):
        for indices in itertools.combinations(range(len(s['hand']['cards'])),n):
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
