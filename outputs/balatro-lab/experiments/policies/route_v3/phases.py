"""Phase-sensitive activation and copy allocation; no look-ahead to actual draws."""
import copy,re,json
import advisor as a
import copying,strategy

def reordered(s,order):
    t=copy.deepcopy(s);t['jokers']['cards']=[t['jokers']['cards'][i] for i in order];return t

def can_feed(j,s):return not a.mod(j).get('eternal') and (j['key']=='j_egg' or strategy.value(j,s)<35 or a.st(j).get('debuff'))

def safe_entry(s,order):
    cards=[s['jokers']['cards'][i] for i in order]
    return all(j['key']!='j_ceremonial' or n==len(cards)-1 or a.mod(cards[n+1]).get('eternal') or can_feed(cards[n+1],s) for n,j in enumerate(cards))

def phase_value(s,phase,selected=()):
    effects=copying.effective(s);counts={k:sum(j['key']==k and not a.st(j).get('debuff') and not j.get('_inactive_copy') for j in effects) for k in copying.SPECS}
    if phase in ('dna','burnt','trading'):return counts[{'dna':'j_dna','burnt':'j_burnt','trading':'j_trading'}[phase]]
    if phase=='exit':return counts['j_perkeo']*bool(s['consumables']['cards'])
    if phase=='entry':
        free=max(0,s['jokers']['limit']-len(s['jokers']['cards']));slots=max(0,s['consumables']['limit']-len(s['consumables']['cards']))
        return 24*counts['j_burglar']+13*counts['j_certificate']+10*min(slots,counts['j_cartomancer'])+8*min(free,2*counts['j_riff_raff'])+counts['j_marble']*(12 if a.keys(s)&{'j_stone','j_hologram'} else 1)
    if phase=='income':
        total=0
        for j in effects:
            k=j['key']
            if a.st(j).get('debuff'):continue
            if k=='j_golden':total+=4
            elif k in ('j_rocket','j_satellite','j_cloud_9'):total+=a.current_number(j,1)
            elif k=='j_to_the_moon':total+=max(0,s['money']//5)
            elif k=='j_delayed_grat' and s['round']['discards_used']==0:total+=2*s['round']['discards_left']
        for i,c in enumerate(s.get('hand',{}).get('cards',[])):
            if i in selected or a.st(c).get('debuff') or a.st(c).get('hidden'):continue
            # Passive dollar-bonus Jokers themselves are incompatible. Mime is compatible
            # and repeats held Gold/Blue-seal end-of-round effects.
            total+=(3*(a.mod(c).get('enhancement')=='GOLD')+5*(a.mod(c).get('seal')=='BLUE'))*(1+counts['j_mime']+int(a.mod(c).get('seal')=='RED'))
        return total
    return 0

def copy_action(s,phase,options=None):
    if not a.keys(s)&copying.COPY or s.get('_uncertain_jokers'):return None
    orders=copying.candidate_orders(s);current=orders[0];best_order=current;best_rank=None
    if phase=='combat':
        canonical=copy.deepcopy(s)
        canonical['jokers']['cards'].sort(key=lambda j:(j['key'],j.get('value',{}).get('effect',''),json.dumps(a.mod(j),sort_keys=True)))
        # A layout-independent candidate pool makes strict improvements monotonic,
        # preventing repeated rearrangements from oscillating between two layouts.
        opts=a.options(canonical);representatives={}
        for o in opts:representatives.setdefault(o[2],o[1])
        chosen=list(representatives.values())+list(o[1] for o in opts[:5])+[(i,) for i in range(len(s['hand']['cards']))]
        forced={i for i,c in enumerate(s['hand']['cards']) if a.st(c).get('highlight')}
        chosen=[x for x in chosen if forced.issubset(x)]
        need=next(b['score'] for b in s['blinds'].values() if b['status']=='CURRENT')-s['round']['chips']
    for order in orders:
        if phase=='entry' and not safe_entry(s,order):continue
        sim=reordered(s,order)
        if phase=='combat':
            values=[]
            for indices in chosen:
                score=a.score(sim,indices)[0];floor=a.conservative_score(sim,indices,score)
                safe=floor is not None and floor>=need
                values.append((int(safe),phase_value(sim,'income',indices) if safe else 0,score))
            rank=max(values)
        else:rank=(phase_value(sim,phase),)
        if best_rank is None or rank>best_rank:best_rank=rank;best_order=order
    if best_order!=current:
        zh={'entry':'进盲注资源','dna':'首手DNA复制','burnt':'首次弃牌升级','trading':'首次弃牌精简','exit':'离店消耗牌复制','combat':'本手计分与过关后收入'}[phase]
        return 'rearrange',{'jokers':list(best_order),'reason':f'为{zh}重新排列蓝图/头脑风暴；只复制兼容能力，不复制版本，完成该阶段后再比较目标。'}

def before(s):
    ks=a.keys(s);state=s['state'];cards=s['jokers']['cards']
    if s.get('overlay') or s.get('won'):return None
    if state=='BLIND_SELECT':
        for i,j in enumerate(cards[:-1]):
            if j['key']=='j_ceremonial' and not a.mod(cards[i+1]).get('eternal') and not can_feed(cards[i+1],s):
                order=[k for k in range(len(cards)) if k!=i]+[i]
                return 'rearrange',{'jokers':order,'reason':'把仪式匕首移到最右，避免进盲注时误吃主力；只给它可牺牲的低效牌或鸡蛋。'}
        return copy_action(s,'entry')
    if state=='SHOP':
        for i,j in enumerate(cards):
            if a.mod(j).get('eternal'):continue
            if j['key']=='j_diet_cola':return 'sell',{'joker':i,'reason':'出售零糖可乐兑现双倍标签并腾出槽位，后续跳过仍按收益独立判断。'}
            if j['key']=='j_invisible' and len(cards)>1:
                match=re.search(r'当前[^\d]*(\d+)',j.get('value',{}).get('effect',''))
                if match and int(match[1])>=2:return 'sell',{'joker':i,'reason':'隐形小丑已持有两回合，出售以复制现有小丑；复制结果随机，随后重新评估阵容。'}
    if state!='SELECTING_HAND':return None
    boss=next(b for b in s['blinds'].values() if b['status']=='CURRENT');need=boss['score']-s['round']['chips']
    for i,j in enumerate(cards):
        if j['key']=='j_luchador' and not a.mod(j).get('eternal') and s['blinds']['boss']['status']=='CURRENT' and not s.get('_boss_disabled'):
            return 'sell',{'joker':i,'reason':'当前已进入Boss，出售摔跤手解除本轮限制，再重新计算手牌。'}
    opts=a.options(s);best=opts[0];hand=s['hand']['cards'];forced={i for i,c in enumerate(hand) if a.st(c).get('highlight')}
    first=s['round'].get('hands_played',0)==0
    if 'j_dna' in ks and first and s['round']['hands_left']>=3 and best[0]*max(1,s['round']['hands_left']-1)>=need*1.4:
        candidates=[i for i,c in enumerate(hand) if not a.st(c).get('hidden') and (not forced or forced=={i})]
        if candidates:
            choice=max(candidates,key=lambda i:strategy.card_value(hand[i],s))
            action=copy_action(s,'dna')
            if action:return action
            return 'play',{'cards':[choice],'reason':f'首手单出高价值牌触发DNA，当前复制链共{copying.count(s,"j_dna")}份能力；剩余手数保留过关空间，之后转回计分复制。'}
    if first and 'j_sixth_sense' in ks and s['round']['hands_left']>=3 and len(s['consumables']['cards'])<s['consumables']['limit']:
        six=next((i for i,c in enumerate(hand) if a.rank(c)==6 and not a.st(c).get('hidden') and not forced-{i}),None)
        if six is not None and best[0]*(s['round']['hands_left']-1)>need*1.5:return 'play',{'cards':[six],'reason':'首手单出6触发第六感，以剩余出牌余量换取幻灵与牌组精简。'}
    if s['round'].get('discards_used',0)==0 and s['round']['discards_left']>0:
        if 'j_trading' in ks and len(forced)<=1:
            candidates=[i for i,c in enumerate(hand) if not a.st(c).get('hidden') and (not forced or i in forced)]
            if candidates:
                choice=min(candidates,key=lambda i:strategy.card_value(hand[i],s))
                if strategy.card_value(hand[choice],s)<25:
                    action=copy_action(s,'trading')
                    if action:return action
                    return 'discard',{'cards':[choice],'reason':'首次只弃一张低价值牌，触发交易卡获得现金并永久精简牌组；随后按新牌组重新抽样。'}
        if 'j_burnt' in ks and s['round']['hands_left']>=2:
            import routes
            target=routes.main_hand(s);choice=next((o for o in opts if o[2]==target),best)
            action=copy_action(s,'burnt')
            if action:return action
            return 'discard',{'cards':list(choice[1]),'reason':f'利用首次弃牌触发烧焦小丑，为{a.name_zh(choice[2])}升级；复制链可增加等级，弃后再调整为计分用途。'}
    return copy_action(s,'combat',opts)
