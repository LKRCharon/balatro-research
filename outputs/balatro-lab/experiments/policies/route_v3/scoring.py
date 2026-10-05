"""Ordered public-state scoring, including copier multiplicity and mutable deck effects.

Random branches use expectations and are marked uncertain by advisor. This is not a
perfect forward simulator: gameplay observations, rather than simulated mutations,
remain the authority for the next action.
"""
import collections,copy,math,re
import advisor as a
from copying import effective,SPECS

def rank_id(c):return 0 if a.mod(c).get('enhancement')=='STONE' else a.rank(c)
def face(c,ks):return not a.st(c).get('debuff') and (rank_id(c) in (11,12,13) or 'j_pareidolia' in ks)

def matches(c,su,ks,bypass=False):
    if a.mod(c).get('enhancement')=='STONE':return False
    if a.st(c).get('debuff') and not bypass:return False
    if a.mod(c).get('enhancement')=='WILD' and not a.st(c).get('debuff'):return True
    return a.suit(c)==su or ('j_smeared' in ks and (a.suit(c) in ('H','D'))==(su in ('H','D')))

def number(j,default=0):return a.current_number(j,default)

def score(s,selected):
    cards=s['hand']['cards'];physical=s['jokers']['cards'];ks=a.keys(s)
    js=effective(s);active=[j for j in js if not a.st(j).get('debuff') and not j.get('_inactive_copy')]
    multiplicity=collections.Counter(j['key'] for j in active)
    cat,scored,counts=a.classify(cards,selected,'j_four_fingers' in ks,'j_shortcut' in ks,'j_smeared' in ks)
    name=a.NAMES[cat];h=s['hands'][name];chips=float(h['chips']);mult=float(h['mult'])
    boss=next((b['name'] for b in s['blinds'].values() if b['status']=='CURRENT'),'')
    if 'j_chicot' in ks or s.get('_boss_disabled'):boss=''
    if boss=='The Psychic' and len(selected)!=5:return 0,name,scored
    if boss=='The Eye' and h.get('played_this_round',0)>0:return 0,name,scored
    if boss=='The Mouth':
        locked=s['round'].get('mouth_hand')
        if not locked:locked=next((n for n,h0 in s['hands'].items() if h0.get('played_this_round',0)),None)
        if locked and locked!=name:return 0,name,scored
    if boss=='The Arm' and h['level']>1:
        dc,dm=a.LEVEL_DELTA[name];chips-=dc;mult-=dm
    normal=s.get('_normal_probability',2**sum(j['key']=='j_oops' and not a.st(j).get('debuff') for j in physical))
    if multiplicity['j_space']:
        dc,dm=a.LEVEL_DELTA[name];p=min(1,normal/4)*multiplicity['j_space'];chips+=p*dc;mult+=p*dm
    if boss=='The Flint':chips=math.floor(chips/2+.5);mult=math.floor(mult/2+.5)
    if 'j_splash' in ks:scored=list(selected)
    cash=s['money']-(len(selected) if boss=='The Tooth' else 0)
    working={i:copy.deepcopy(cards[i]) for i in scored}
    growth=collections.defaultdict(float)
    # Before-hand effects execute once on the real growth object, never independently on a copier.
    for idx,j in enumerate(physical):
        if a.st(j).get('debuff'):continue
        if j['key']=='j_midas_mask':
            for c in working.values():
                if face(c,ks) and not a.st(c).get('debuff'):c.setdefault('modifier',{})['enhancement']='GOLD'
        if j['key']=='j_vampire':
            for c in working.values():
                if not a.st(c).get('debuff') and a.mod(c).get('enhancement'):
                    growth[idx]+=.1;c['modifier'].pop('enhancement',None)
                    # Losing Stone restores its printed suit/rank; set_ability rechecks the Boss.
                    banned={'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(boss)
                    if (banned and matches(c,banned,ks,True)) or (boss=='The Plant' and face(c,ks)):
                        c.setdefault('state',{})['debuff']=True
    firstface=next((i for i in scored if face(working[i],ks)),None)
    perma={i:working[i].get('permanent_bonus',0) for i in scored}
    for ordinal,i in enumerate(scored):
        c=working[i];r=rank_id(c);m=a.mod(c)
        if a.st(c).get('debuff'):continue
        isface=face(c,ks)
        reps=1+int(m.get('seal')=='RED')+2*multiplicity['j_hanging_chad']*(ordinal==0)
        reps+=multiplicity['j_sock_and_buskin']*isface+multiplicity['j_selzer']
        reps+=multiplicity['j_dusk']*(s['round']['hands_left']==1)+multiplicity['j_hack']*(r in (2,3,4,5))
        for _ in range(reps):
            chips+=(50 if m.get('enhancement')=='STONE' else 11 if r==14 else min(r,10))+perma[i]
            if m.get('enhancement')=='BONUS':chips+=30
            if m.get('enhancement')=='MULT':mult+=4
            if m.get('enhancement')=='GLASS':mult*=2
            if m.get('enhancement')=='LUCKY':mult+=20*min(1,normal/5);cash+=20*min(1,normal/15)
            if m.get('edition')=='FOIL':chips+=50
            if m.get('edition')=='HOLO':mult+=10
            if m.get('edition')=='POLYCHROME':mult*=1.5
            if m.get('seal')=='GOLD':cash+=3
            for j in active:
                k=j['key'];src=j['_source_index']
                if k=='j_even_steven' and r in (2,4,6,8,10):mult+=4
                elif k=='j_odd_todd' and r in (3,5,7,9,14):chips+=31
                elif k=='j_scholar' and r==14:chips+=20;mult+=4
                elif k=='j_fibonacci' and r in (2,3,5,8,14):mult+=8
                elif k=='j_walkie_talkie' and r in (4,10):chips+=10;mult+=4
                elif k=='j_scary_face' and isface:chips+=30
                elif k=='j_smiley' and isface:mult+=5
                elif k=='j_photograph' and i==firstface:mult*=2
                elif k=='j_triboulet' and r in (12,13):mult*=2
                elif k=='j_hiker':perma[i]+=5
                elif k=='j_wee' and r==2 and not j['_copied']:growth[src]+=8
                elif k=='j_lucky_cat' and m.get('enhancement')=='LUCKY' and not j['_copied']:
                    growth[src]+=.25*(1-(1-min(1,normal/5))*(1-min(1,normal/15)))
                elif k=='j_ticket' and m.get('enhancement')=='GOLD':cash+=4
                elif k=='j_business' and isface:cash+=2*min(1,normal/2)
                elif k in ('j_greedy_joker','j_lusty_joker','j_wrathful_joker','j_gluttenous_joker'):
                    su={'j_greedy_joker':'D','j_lusty_joker':'H','j_wrathful_joker':'S','j_gluttenous_joker':'C'}[k]
                    if matches(c,su,ks):mult+=3
                elif k=='j_arrowhead' and matches(c,'S',ks):chips+=50
                elif k=='j_onyx_agate' and matches(c,'C',ks):mult+=7
                elif k=='j_rough_gem' and matches(c,'D',ks):cash+=1
                elif k=='j_bloodstone' and matches(c,'H',ks):mult*=1+.5*min(1,normal/2)
                elif k in ('j_ancient','j_idol'):
                    t=s.get('_targets',{}).get(k,{})
                    su={'Spades':'S','Hearts':'H','Clubs':'C','Diamonds':'D'}.get(t.get('suit'),t.get('suit'))
                    rr={'Ace':'A','King':'K','Queen':'Q','Jack':'J','10':'T'}.get(str(t.get('rank')),str(t.get('rank')))
                    if matches(c,su,ks) and (k=='j_ancient' or a.RANK.get(rr)==r):mult*=1.5 if k=='j_ancient' else 2
    held=[(i,c) for i,c in enumerate(cards) if i not in selected]
    nonstone=[(i,c) for i,c in held if a.mod(c).get('enhancement')!='STONE']
    fist=min(nonstone,key=lambda ic:(a.rank(ic[1]),-ic[0]))[0] if nonstone else None
    for i,c in held:
        if a.st(c).get('debuff'):continue
        eligible=a.mod(c).get('enhancement')=='STEEL' or any(
            j['key']=='j_baron' and rank_id(c)==13 or j['key']=='j_shoot_the_moon' and rank_id(c)==12 or
            j['key']=='j_raised_fist' and i==fist or j['key']=='j_reserved_parking' and face(c,ks) for j in active)
        reps=1+(int(a.mod(c).get('seal')=='RED')+multiplicity['j_mime'] if eligible else 0)
        for _ in range(reps):
            if a.mod(c).get('enhancement')=='STEEL':mult*=1.5
            for j in active:
                if j['key']=='j_baron' and rank_id(c)==13:mult*=1.5
                elif j['key']=='j_shoot_the_moon' and rank_id(c)==12:mult+=13
                elif j['key']=='j_raised_fist' and i==fist:mult+=2*(11 if a.rank(c)==14 else min(10,a.rank(c)))
                elif j['key']=='j_reserved_parking' and face(c,ks):cash+=min(1,normal/2)
    deck=s.get('_belief',{}).get('deck',[])
    enh=collections.Counter(a.mod(c).get('enhancement') for c in deck)
    dna=multiplicity['j_dna'] if len(selected)==1 and s['round'].get('hands_played',0)==0 else 0
    for j in js:
        if a.st(j).get('debuff'):continue
        k=j['key'];val=number(j);m=a.mod(j);idx=j['_source_index']
        if m.get('edition')=='FOIL':chips+=50
        if m.get('edition')=='HOLO':mult+=10
        if k=='j_joker':mult+=4
        elif k=='j_half' and len(selected)<=3:mult+=20
        elif k=='j_abstract':mult+=3*len(physical)
        elif k=='j_mystic_summit' and s['round']['discards_left']==0:mult+=15
        elif k=='j_banner':chips+=30*s['round']['discards_left']
        elif k=='j_gros_michel':mult+=15
        elif k=='j_popcorn':mult+=val
        elif k=='j_ice_cream':chips+=val
        elif k=='j_blue_joker':chips+=2*s['cards']['count']
        elif k=='j_supernova':mult+=h.get('played',0)+1
        elif k=='j_green_joker':mult+=val+1
        elif k=='j_ride_the_bus':mult+=0 if any(face(working[i],ks) for i in scored) else val+1
        elif k=='j_trousers':mult+=val+2*(sum(v>=2 for v in counts.values())>=2)
        elif k in ('j_flash','j_swashbuckler','j_fortune_teller','j_red_card','j_ceremonial'):mult+=val
        elif k=='j_misprint':mult+=11.5
        elif k=='j_square':chips+=val+4*(len(selected)==4)
        elif k=='j_runner':chips+=val+15*(cat in (4,8))
        elif k=='j_castle':chips+=val
        elif k=='j_wee':chips+=val+growth[idx]
        elif k=='j_bull':chips+=2*max(0,cash)
        elif k=='j_bootstraps':mult+=2*math.floor(max(0,cash)/5)
        elif k=='j_stuntman':chips+=250
        elif k=='j_stone':chips+=25*enh['STONE'] if deck else val
        elif k=='j_erosion':mult+=4*max(0,s.get('_belief',{}).get('starting_size',52)-len(deck)) if deck else val
        elif k in ('j_jolly','j_zany','j_mad','j_crazy','j_droll','j_sly','j_wily','j_clever','j_devious','j_crafty'):
            ix=['j_jolly','j_zany','j_mad','j_crazy','j_droll','j_sly','j_wily','j_clever','j_devious','j_crafty'].index(k)
            condition=[max(counts.values(),default=0)>=2,max(counts.values(),default=0)>=3,sum(v>=2 for v in counts.values())>=2,cat in (4,8),cat in (5,8,10,11)][ix%5]
            if condition:
                if ix<5:mult+=[8,12,10,12,10][ix]
                else:chips+=[50,100,80,100,80][ix-5]
        elif k in ('j_duo','j_trio','j_family','j_order','j_tribe'):
            ix=['j_duo','j_trio','j_family','j_order','j_tribe'].index(k)
            if [max(counts.values(),default=0)>=2,max(counts.values(),default=0)>=3,max(counts.values(),default=0)>=4,cat in (4,8),cat in (5,8,10,11)][ix]:mult*=[2,3,4,3,2][ix]
        elif k=='j_blackboard' and all(matches(c,'S',ks,True) or matches(c,'C',ks,True) for _,c in held):mult*=3
        elif k=='j_card_sharp' and h.get('played_this_round',0)>0:mult*=3
        elif k=='j_cavendish':mult*=3
        elif k=='j_acrobat' and s['round']['hands_left']==1:mult*=3
        elif k=='j_stencil':mult*=max(1,s['jokers']['limit']-len(physical)+sum(c['key']=='j_stencil' for c in physical))
        elif k=='j_steel_joker':mult*=1+.2*enh['STEEL'] if deck else val or 1
        elif k=='j_hologram':mult*=(val or 1)+.25*dna
        elif k in ('j_vampire','j_lucky_cat'):mult*=(val or 1)+growth[idx]
        elif k=='j_obelisk':
            peak=max(v.get('played',0) for v in s['hands'].values())
            mult*=1 if h.get('played',0)>=peak else (val or 1)+.2
        elif k in ('j_ramen','j_constellation','j_madness','j_campfire','j_glass','j_throwback','j_hit_the_road','j_caino','j_yorick'):mult*=val or 1
        elif k=='j_drivers_license' and sum(v for k0,v in enh.items() if k0)>=16:mult*=3
        elif k=='j_loyalty_card':
            text=j.get('value',{}).get('effect','')
            if j.get('_loyalty_remaining')==0 or (j.get('_loyalty_remaining') is None and ('生效' in text or re.search(r'剩余\s*0|0\s*次',text))):mult*=4
        elif k=='j_flower_pot':
            covered=set()
            ordered=[working[i] for i in scored if a.mod(working[i]).get('enhancement')!='WILD']+[working[i] for i in scored if a.mod(working[i]).get('enhancement')=='WILD']
            for c in ordered:
                for su in 'HD SC'.replace(' ',''):
                    if su not in covered and matches(c,su,ks,a.mod(c).get('enhancement')!='WILD'):covered.add(su);break
            if len(covered)==4:mult*=3
        elif k=='j_seeing_double':
            covered=collections.Counter()
            for c in (working[i] for i in scored if a.mod(working[i]).get('enhancement')!='WILD'):
                for su in 'HDSC':covered[su]+=matches(c,su,ks)
            for c in (working[i] for i in scored if a.mod(working[i]).get('enhancement')=='WILD'):
                for su in 'CDSH':
                    if covered[su]==0 and matches(c,su,ks):covered[su]+=1;break
            if covered['C'] and sum(covered[su] for su in 'HDS'):mult*=2
        if m.get('edition')=='POLYCHROME':mult*=1.5
        if SPECS.get(j['_physical_key'],{}).get('rarity')==2:mult*=1.5**multiplicity['j_baseball']
    # Vanilla evaluates held consumables after all Jokers (state_events.lua).
    planets=dict(zip(a.NAMES,('c_pluto','c_mercury','c_uranus','c_venus','c_saturn','c_jupiter',
                             'c_earth','c_mars','c_neptune','c_planet_x','c_ceres','c_eris')))
    if 'v_observatory' in s.get('used_vouchers',[]):
        for c in s.get('consumables',{}).get('cards',[]):
            if c.get('key')==planets[name] and not a.st(c).get('debuff'):
                mult*=1.5
    # Match vanilla's floor of the binary floating-point result, without epsilon.
    return math.floor(chips*mult),name,scored
