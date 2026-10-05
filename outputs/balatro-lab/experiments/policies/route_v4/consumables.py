"""Target-aware Tarot/Spectral use and deck-building choices; mutations remain in real engine."""
import advisor as a
import strategy,routes

ENHANCE={'c_magician':('LUCKY',2),'c_empress':('MULT',2),'c_heirophant':('BONUS',2),'c_lovers':('WILD',1),
         'c_chariot':('STEEL',1),'c_justice':('GLASS',1),'c_devil':('GOLD',1),'c_tower':('STONE',1)}
SUITS={'c_star':'D','c_moon':'C','c_sun':'H','c_world':'S'}
SEALS={'c_talisman':'GOLD','c_deja_vu':'RED','c_trance':'BLUE','c_medium':'PURPLE'}

def plan(c,s):
    """Return (utility, targets, preparatory action). Nonpositive = defer/decline, not unsupported."""
    key=c['key'];ks=a.keys(s);hand=s.get('hand',{}).get('cards',[])
    visible=[i for i,x in enumerate(hand) if not a.st(x).get('hidden')]
    best=sorted(visible,key=lambda i:strategy.card_value(hand[i],s),reverse=True);worst=list(reversed(best))
    free=s['jokers']['limit']-len(s['jokers']['cards']);slots=s['consumables']['limit']-len(s['consumables']['cards'])
    available=s['state'] in ('SELECTING_HAND','SMODS_BOOSTER_OPENED') and bool(hand)
    if key in ENHANCE and available:
        enh,count=ENHANCE[key];eligible=[i for i in best if not a.mod(hand[i]).get('enhancement')]
        if not eligible:return 0,[],None
        if enh=='STEEL':eligible.sort(key=lambda i:(a.rank(hand[i])==13 and 'j_baron' in ks,strategy.card_value(hand[i],s)),reverse=True)
        if enh=='STONE':eligible=list(reversed(eligible))
        value={'LUCKY':65,'MULT':75,'BONUS':70,'WILD':35,'STEEL':75,'GLASS':80,'GOLD':65,'STONE':30}[enh]
        if enh=='STONE' and ks&{'j_stone','j_erosion'}:value+=35
        if enh=='LUCKY' and ks&{'j_lucky_cat','j_oops'}:value+=35
        if enh=='GLASS' and ks&{'j_glass','j_hanging_chad','j_hack'}:value+=25
        return value,eligible[:count],None
    if key=='c_death' and available and len(best)>=2:
        donor=best[0];recipient=worst[0]
        if strategy.card_value(hand[donor],s)<=strategy.card_value(hand[recipient],s)+4:return 0,[],None
        if donor<recipient:
            order=[i for i in range(len(hand)) if i!=donor]+[donor]
            return 95,[],('rearrange',{'hand':order,'reason':'先把死亡要复制的高价值牌放到右侧；右牌覆盖左牌，避免反向毁掉强化或蜡封。'})
        return 95,[recipient,donor],None
    if key=='c_hanged_man' and available and len(visible)>=1:
        targets=worst[:2]
        if 'j_caino' in ks:targets=sorted(visible,key=lambda i:(a.rank(hand[i]) in (11,12,13),-strategy.card_value(hand[i],s)),reverse=True)[:2]
        return 85,targets,None
    if key=='c_strength' and available:
        eligible=sorted(visible,key=lambda i:(a.rank(hand[i])==12 and 'j_baron' in ks,a.rank(hand[i])==14 and 'j_wee' in ks,-strategy.card_value(hand[i],s)),reverse=True)
        return 45,eligible[:2],None
    if key in SUITS and available:
        desired=SUITS[key];targets=[i for i in best if a.suit(hand[i])!=desired][:3]
        synergy={'D':'j_rough_gem','H':'j_bloodstone','S':'j_arrowhead','C':'j_onyx_agate'}[desired]
        deck=s.get('_belief',{}).get('deck',[]);most=max('SHCD',key=lambda su:sum(a.suit(x)==su for x in deck)) if deck else desired
        return (70 if synergy in ks or desired==most else 35) if targets else 0,targets,None
    if key in SEALS and available:
        targets=[i for i in best if not a.mod(hand[i]).get('seal')]
        return (110 if key=='c_trance' else 90) if targets else 0,targets[:1],None
    if key=='c_aura' and available:
        targets=[i for i in best if not a.mod(hand[i]).get('edition')]
        return 90 if targets else 0,targets[:1],None
    if key=='c_cryptid' and available:return 100,best[:1],None
    if key=='c_immolate' and available:
        safe=len(visible)>=5 and max((strategy.card_value(hand[i],s) for i in visible),default=0)<65
        return 85 if safe else 0,[],None
    if key in ('c_familiar','c_grim','c_incantation') and available:
        safe=max((strategy.card_value(hand[i],s) for i in visible),default=0)<65
        synergy=(key=='c_grim' and 'j_scholar' in ks) or (key=='c_familiar' and bool(ks&{'j_triboulet','j_baron','j_photograph'}))
        return (80 if synergy else 35) if safe else 0,[],None
    if key in ('c_sigil','c_ouija') and available:
        return 55 if key=='c_sigil' and routes.main_hand(s)=='Flush' else 35 if key=='c_ouija' and s['hand']['limit']>=8 and not ks&{'j_baron','j_triboulet'} else 0,[],None
    if key in ('c_soul','c_judgement'):
        value=180 if key=='c_soul' else 65
        if free>0:return value,[],None
        sellable=[(strategy.value(j,s),i) for i,j in enumerate(s['jokers']['cards']) if not a.mod(j).get('eternal')]
        if sellable and min(sellable)[0]<(120 if key=='c_soul' else 30):
            return value,[],('sell',{'joker':min(sellable)[1],'reason':'先腾出可替换槽位，确保生成的小丑有位置；新牌出现后按完整机制重新估值。'})
        return 0,[],None
    if key=='c_hermit':return min(20,max(0,s['money']))*4,[],None
    if key=='c_temperance':return min(50,sum(j['cost']['sell'] for j in s['jokers']['cards']))*4,[],None
    if key=='c_fool':return 60 if s.get('_last_consumable') and s['_last_consumable']!='c_fool' and slots>=0 else 0,[],None
    if key in ('c_emperor','c_high_priestess'):return 60 if slots>0 or c in s['consumables']['cards'] else 0,[],None
    if key=='c_wheel_of_fortune':return 45 if any(not a.mod(j).get('edition') for j in s['jokers']['cards']) else 0,[],None
    if key=='c_wraith':return 80 if free>0 and s['money']<=10 else 0,[],None
    if key=='c_ankh':return 115 if len(s['jokers']['cards'])==1 and free>0 else 0,[],None
    if key=='c_hex':return 100 if len(s['jokers']['cards'])==1 and not a.mod(s['jokers']['cards'][0]).get('edition') else 0,[],None
    if key=='c_ectoplasm':return 85 if s['hand']['limit']>=7 and any(not a.mod(j).get('edition') for j in s['jokers']['cards']) else 0,[],None
    if key=='c_black_hole':return 160,[],None
    if c.get('set')=='PLANET':
        return 100 if key in ('c_pluto','c_mercury','c_uranus','c_venus','c_saturn','c_jupiter','c_earth','c_mars','c_neptune','c_planet_x','c_ceres','c_eris') else 0,[],None
    return 0,[],None

def held_action(s):
    candidates=[];cards=s.get('consumables',{}).get('cards',[]);ks=a.keys(s)
    # Keep one valuable item as the Perkeo template; spend generated extra copies normally.
    reserve=None
    if 'j_perkeo' in ks and cards:
        reserve=max(range(len(cards)),key=lambda i:{'c_cryptid':200,'c_black_hole':170,'c_soul':150,'c_death':120,'c_hermit':90}.get(cards[i]['key'],plan(cards[i],s)[0]))
    for i,c in enumerate(cards):
        value,targets,prep=plan(c,s)
        if i==reserve:continue
        if value<=0:continue
        if c.get('set')=='PLANET' and s['state']!='SHOP':continue
        if c['key'] in ('c_hermit','c_temperance') and s['state'] not in ('SHOP','BLIND_SELECT'):continue
        if prep:return prep
        candidates.append((value,i,targets))
    if not candidates:return None
    value,i,targets=max(candidates)
    params={'consumable':i,'reason':'兑现消耗牌的经济、强化或牌组改造收益；根据实际结果更新牌组，不再按固定52张假设抽牌。'}
    if targets:params['cards']=targets
    return 'use',params

def pack_action(s):
    cards=s.get('pack',{}).get('cards',[])
    if not cards or cards[0]['set']=='JOKER':return None
    if cards[0]['set']=='PLANET':return None
    if cards[0]['set'] in ('DEFAULT','ENHANCED'):
        i=max(range(len(cards)),key=lambda i:strategy.card_value(cards[i],s))
        return 'pack',{'card':i,'reason':'选择强化、蜡封或路线点数价值最高的牌；加入真实牌组后重建不放回抽样。'}
    candidates=[(plan(c,s)[0],i,plan(c,s)) for i,c in enumerate(cards)]
    value,i,(_,targets,prep)=max(candidates,key=lambda x:x[0])
    if value<=0:return 'pack',{'skip':True,'reason':'当前包内选项会损害已有核心或不满足使用条件，保留现有牌组；这是局面取舍，不是未识别卡牌。'}
    if prep:return prep
    params={'card':i,'reason':'按当前阵容选择经济、强化或牌组改造；先核对目标和槽位，实际变化由游戏执行。'}
    if targets:params['targets']=targets
    return 'pack',params
