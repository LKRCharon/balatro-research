"""Deterministic route baseline v3 development candidate. No LLM calls.

This is a candidate policy to measure, NOT a proven high-win-rate strategy.
Usage: python policy.py [--seed ABC12345] [--continue] [--max-actions 500]
"""
from __future__ import annotations
import argparse, copy, hashlib, json, time
from pathlib import Path
import advisor as a
import balatro_cli as cli
import forecast
import routes
import tactics
import strategy,copying,phases,consumables
import shop_planning

PRIORITY=strategy.PRIORS
ECON={'j_rocket','j_golden','j_to_the_moon','j_mail','j_egg','j_trading','j_chaos','j_reserved_parking','j_cartomancer','j_ticket','j_rough_gem'}
XMULT={'j_stencil','j_vampire','j_steel_joker','j_cavendish','j_obelisk','j_lucky_cat','j_campfire','j_acrobat','j_throwback','j_glass','j_seeing_double','j_hit_the_road','j_drivers_license','j_caino','j_yorick','j_blackboard','j_card_sharp','j_duo','j_trio','j_family','j_order','j_tribe','j_hologram','j_constellation','j_ramen'}
CHIPS={'j_blue_joker','j_banner','j_ice_cream','j_odd_todd','j_scary_face','j_sly','j_wily','j_clever','j_crafty','j_devious','j_bull','j_stuntman','j_runner','j_square','j_castle'}
GROWTH={'j_supernova','j_green_joker','j_ride_the_bus','j_trousers','j_runner','j_square','j_castle','j_flash','j_fortune_teller'}
PLANETS={'c_planet_x':'Five of a Kind','c_ceres':'Flush House','c_eris':'Flush Five','c_pluto':'High Card','c_mercury':'Pair','c_uranus':'Two Pair','c_venus':'Three of a Kind','c_saturn':'Straight','c_jupiter':'Flush','c_earth':'Full House','c_mars':'Four of a Kind','c_neptune':'Straight Flush'}

def utility(c,s):
    k=c.get('key'); m=a.mod(c)
    if k not in PRIORITY:raise ValueError('Unknown original Joker key '+str(k))
    held=c in s['jokers']['cards']
    rentals=sum(bool(a.mod(j).get('rental')) for j in s['jokers']['cards'])
    v=strategy.value(c,s)
    if m.get('rental'): v-=55 if s['money']<30 else 30
    if m.get('perishable'): v*=0.72
    if a.st(c).get('debuff'): v=0
    if m.get('edition')=='HOLO': v+=35
    if m.get('edition')=='FOIL': v+=28
    if m.get('edition')=='POLYCHROME': v+=32
    if m.get('edition')=='NEGATIVE': v+=40
    ks=a.keys(s)
    if k=='j_photograph' and 'j_hanging_chad' in ks: v+=55
    if k=='j_hanging_chad' and ks.intersection({'j_photograph','j_fibonacci','j_smiley','j_scholar'}): v+=25
    if k in CHIPS and not (ks&CHIPS): v+=20
    if k in XMULT and not (ks&XMULT): v+=35 if s['ante_num']>=3 else 10
    if k in ECON and ks&ECON: v-=25
    if k in ECON and s['ante_num']>=6: v-=40
    if k=='j_joker' and s['ante_num']>=3: v-=20
    if k in('j_crazy','j_devious') and routes.main_hand(s)=='Straight':v+=25
    if k in('j_mad','j_clever') and routes.main_hand(s)=='Two Pair':v+=25
    if k in('j_jolly','j_sly','j_duo') and routes.main_hand(s)=='Pair':v+=12
    if k=='j_ride_the_bus' and ks&{'j_photograph','j_smiley','j_scary_face'}:v-=45
    if k=='j_mystic_summit' and 'j_green_joker' in ks:v-=50
    if k in GROWTH: v+=(15 if s['ante_num']<=3 else -25)
    if m.get('eternal'):
        locked=sum(bool(a.mod(j).get('eternal')) for j in s['jokers']['cards'])
        if not held and locked>=3 and v<100:v-=35
        if v<60 or k in ECON:v-=18
    return v

def main_hand(s):
    return routes.main_hand(s)

def choose_joker(cards,s):
    js=s['jokers']['cards']; free=s['jokers']['limit']-len(js)
    best=max(enumerate(cards),key=lambda ic:utility(ic[1],s),default=(None,None))
    if best[1] is None: return None
    i,c=best; v=utility(c,s)
    if v<30: return None
    if free>0 or a.mod(c).get('edition')=='NEGATIVE': return i,None
    candidates=[(utility(j,s),idx) for idx,j in enumerate(js) if not a.mod(j).get('eternal')]
    if not candidates: return None
    # Replacing a component is judged on the resulting lineup, not an isolated tier score.
    base=forecast.estimate(s);base_strength=.4*base['q25']+.6*base['median']
    proposals=[]
    for old_value,idx in candidates:
        sim=copy.deepcopy(s)
        sim['jokers']['cards'][idx]=c
        sim['jokers']['cards'].sort(key=lambda j:int(j['key'] in XMULT or a.mod(j).get('edition')=='POLYCHROME'))
        sim['money']=max(0,s['money']-c.get('cost',{}).get('buy',0)+js[idx].get('cost',{}).get('sell',0))
        outlook=forecast.estimate(sim)
        strength=.4*outlook['q25']+.6*outlook['median']
        if strength>base_strength*1.12:
            proposals.append((strength,idx))
        elif c['key'] in ECON and not base['pressure'] and strength>=base_strength*.9 and v>old_value+25:
            proposals.append((strength,idx))
        elif c['key'] in {'j_dna','j_burnt','j_perkeo','j_trading','j_certificate','j_hiker','j_wee','j_invisible'} and s['ante_num']<=5 and not base['pressure'] and strength>=base_strength*.8 and v>old_value+20:
            # Development tools need future value: immediate score alone would
            # silently recreate a no-DNA whitelist whenever all slots are full.
            # This is an explicit heuristic, not a fitted value function.
            proposals.append((strength,idx))
    if proposals:return i,max(proposals)[1]
    return None

def _base_action(s):
    state=s['state']; ks=a.keys(s)
    if s.get('overlay')=='unlock': return 'continue',{'reason':'关闭解锁提示，继续当前实验局，不改变路线。'}
    if cli.terminal(s): return None
    if state=='ROUND_EVAL': return 'cash_out',{'reason':'已达到本轮目标，领取收入；核对到账金额后进入下一次商店决策。'}
    if state=='BLIND_SELECT': return 'select',{'reason':'固定基线不跳盲注，保留商店次数与成长机会，先检查本轮首领限制。'}
    if state=='SELECTING_HAND':
        boss=next(b['name'] for b in s['blinds'].values() if b['status']=='CURRENT')
        if boss=='Verdant Leaf' and any(a.st(c).get('debuff') for c in s['hand']['cards']):
            candidates=[(utility(j,s),i) for i,j in enumerate(s['jokers']['cards']) if not a.mod(j).get('eternal')]
            if candidates:return 'sell',{'joker':min(candidates)[1],'reason':'翠绿之叶使全部扑克牌失效，先卖掉可出售且作用最小的小丑解除限制，再出牌。'}
        opts=a.options(s);best=opts[0]; need=next(b['score'] for b in s['blinds'].values() if b['status']=='CURRENT')-s['round']['chips']
        best=tactics.choose(s,opts,need)
        # Preserve accumulated bus scaling unless the immediate survival cost is large.
        if 'j_ride_the_bus' in ks:
            safe=next((o for o in opts if not any(a.rank(s['hand']['cards'][i]) in(11,12,13) for i in o[3])),None)
            if safe and (safe[0]>=need or safe[0]>=best[0]*.7):best=safe
        if tuple(sorted(best[1]))!=best[1]:
            order=list(best[1])+[i for i in range(len(s['hand']['cards'])) if i not in best[1]]
            return 'rearrange',{'hand':order,'reason':'调整计分先后，把重触发收益更高的牌放在前面，再按实际顺序计算本手得分。'}
        hidden=[i for i,c in enumerate(s['hand']['cards']) if a.st(c).get('hidden')]
        if hidden and s['round']['discards_left']>0 and best[0]<need:
            return 'discard',{'cards':hidden[:5],'reason':'背面牌没有点数或花色信息，先用弃牌换取可见手牌，再按已知信息组合；不读取隐藏身份。'}
        if hidden and len(s['hand']['cards'])-len(hidden)<3 and best[0]<need:
            cap=3 if 'j_half' in ks else 5
            chosen=list(best[1])[:cap]
            chosen+= [i for i in hidden if i not in chosen][:max(0,cap-len(chosen))]
            return 'play',{'cards':sorted(chosen),'reason':'可见牌太少且无法继续弃牌，保留已知计分核心并打出背面杂牌换取信息；本手估分存在不确定性。'}
        # Buy growth with spare hands while preserving a currently winning combination.
        boss=next(b['name'] for b in s['blinds'].values() if b['status']=='CURRENT')
        floor=a.conservative_score(s,best[1],best[0])
        if ks&{'j_green_joker','j_supernova','j_ride_the_bus'} and (s['ante_num']<=2 or s['money']>=25) and s['round']['hands_left']>=3 and floor is not None and floor>=need and boss not in('The Hook','The Tooth','The Eye','The Mouth','The Psychic','The Ox','Cerulean Bell'):
            held=s['hand']['cards']
            extras=[i for i,c in enumerate(held) if i not in best[1] and not a.st(c).get('hidden') and a.rank(c) not in(11,12,13)]
            if extras:
                i=min(extras,key=lambda i:a.rank(held[i]))
                q=a.score(s,(i,))[0]
                if 0<q<need:
                    return 'play',{'cards':[i],'reason':f'保留现成过关组合，用额外出牌积累成长；这张高牌约{q}分，仍留至少两手完成本轮。'}
        discard_costly=bool(ks&{'j_green_joker','j_banner','j_ramen'})
        score_pressure=best[0]*s['round']['hands_left']<need*1.3
        if s['round']['discards_left']>0 and best[0]<need and (not discard_costly or score_pressure):
            ds=tactics.discard(s,best,need)
            if ds:return 'discard',{'cards':ds,'reason':f'按假想补牌样本比较弃牌选择，主线{a.name_zh(main_hand(s))}；当前约{best[0]}分，本轮尚差{need}分。'}
        if best[0]==0 and s['round']['hands_left']>1 and boss!='Cerulean Bell':
            cycle=a.discard(s,best)
            if cycle:return 'play',{'cards':sorted(cycle),'reason':'当前没有可得分的合法牌型，保留最接近成型的组合，借这手打出杂牌补牌；本手按零分计算。'}
        return 'play',{'cards':list(best[1]),'reason':f'规则选择{a.name_zh(best[2])}，可见信息估分{best[0]}，本轮尚差{need}。使用真实计分检查效果。'}
    if state=='SMODS_BOOSTER_OPENED':
        cs=s.get('pack',{}).get('cards',[])
        if not cs: raise ValueError('Open pack without cards')
        if cs[0]['set']=='JOKER':
            pick=choose_joker(cs,s)
            if pick:
                i,j=pick
                if j is not None: return 'sell',{'joker':j,'reason':'固定评分规则发现更强替代，出售当前可卖的最低效槽位，再取补充包核心。'}
                return 'pack',{'card':i,'reason':f'按稳定得分、成长、经济与贴纸成本选择{cs[i]["key"]}，补足当前路线。'}
        elif cs[0]['set']=='PLANET':
            target=main_hand(s)
            i=max(range(len(cs)),key=lambda i:100*(PLANETS.get(cs[i]['key'])==target)+s['hands'].get(PLANETS.get(cs[i]['key']),{}).get('played',0)*2+int(cs[i]['key']=='c_mercury'))
            return 'pack',{'card':i,'reason':f'优先升级主路线{a.name_zh(target)}；包内按主牌型匹配度与实际出牌次数选择星球。'}
        elif cs[0]['set']=='TAROT':
            order={'c_hermit':100,'c_temperance':95,'c_empress':70,'c_heirophant':65,'c_magician':50,'c_chariot':40}
            i=max(range(len(cs)),key=lambda i:order.get(cs[i]['key'],0))
            key=cs[i]['key']; p={'card':i,'reason':'塔罗包优先补经济或稳定强化，现金能换取后续商店和成长资源。'}
            hand=s.get('hand',{}).get('cards',[])
            if key in('c_empress','c_heirophant','c_magician'): p['targets']=sorted(range(len(hand)),key=lambda k:a.rank(hand[k]),reverse=True)[:2]
            elif key in('c_justice','c_chariot'): p['targets']=sorted(range(len(hand)),key=lambda k:a.rank(hand[k]),reverse=True)[:1]
            elif key=='c_death' and len(hand)>1: p['targets']=[len(hand)-1,0]
            if key in order: return 'pack',p
        return 'pack',{'skip':True,'reason':'此补充包没有当前固定规则能稳定利用的选项，跳过并保留既定路线。'}
    if state=='SHOP':
        js=s['jokers']['cards']
        for i,c in enumerate(js):
            if a.st(c).get('debuff') and not a.mod(c).get('eternal'):
                return 'sell',{'joker':i,'reason':'临时小丑已经失效，及时回收售价并腾出槽位；租赁贴纸即使失效仍会收费。'}
        order=sorted(range(len(js)),key=lambda i:int(js[i]['key'] in XMULT or a.mod(js[i]).get('edition')=='POLYCHROME'))
        if order!=list(range(len(js))) and not ks&copying.COPY:
            return 'rearrange',{'jokers':order,'reason':'固定把加法倍率组件放左侧、乘倍组件放右侧，让同一套卡的乘法作用于更多倍率。'}
        outlook=forecast.estimate(s)
        pressured=outlook['pressure']
        # Consume planets immediately, independently of store purchases.
        money=s['money']; shop=s.get('shop',{}).get('cards',[])
        acquisition=shop_planning.choose(s,utility,XMULT)
        if acquisition:return acquisition
        for i,c in enumerate(shop):
            if c['key'] in('c_hermit','c_temperance'):
                gain=min(20,max(0,money-c['cost']['buy'])) if c['key']=='c_hermit' else min(50,sum(j['cost']['sell'] for j in js))
                if money>=c['cost']['buy'] and gain>c['cost']['buy']:
                    return 'buy',{'card':i,'use':True,'reason':'这张经济塔罗可立即回收超过买价的现金，增加后续补强资源。'}
        for i,c in enumerate(s.get('vouchers',{}).get('cards',[])):
            if c['key'] in('v_grabber','v_nacho_tong','v_paint_brush','v_palette','v_telescope') and money>=c['cost']['buy']+15:
                return 'buy',{'voucher':i,'reason':'购买增加出牌或手牌上限的长期资源，并保留15元现金，不影响下一轮补强。'}
        for i,c in enumerate(s.get('packs',{}).get('cards',[])):
            cost=c['cost']['buy']; key=c['key']; free=s['jokers']['limit']-len(s['jokers']['cards'])
            if ('buffoon' in key and money>=cost+(0 if pressured or len(s['jokers']['cards'])<2 else 8) and (free>0 or money>=25)):
                return 'buy',{'pack':i,'reason':'丑角包提供两次以上路线选择机会，优先补足空槽或替换低效小丑。'}
            if 'celestial' in key and (cost==0 or money>=cost+(4 if pressured else 10)):
                return 'buy',{'pack':i,'reason':'保留10元后开星球包，寻找主路线升级，将基础筹码和倍率一起提高。'}
            if 'standard' in key and money>=cost+10 and ks&{'j_hologram','j_dna','j_certificate','j_baron','j_triboulet'}:
                return 'buy',{'pack':i,'reason':'为加牌成长、蜡封或集中点数路线寻找牌组组件，买后按实际加入的牌更新抽样。'}
            if 'spectral' in key and money>=cost+15 and ks&{'j_dna','j_hologram','j_perkeo','j_caino'}:
                return 'buy',{'pack':i,'reason':'保留现金后寻找幻灵改造或复制机会，只在目标和槽位可满足时使用。'}
            if 'arcana' in key and money>=cost+15:
                return 'buy',{'pack':i,'reason':'保留15元后开塔罗包，优先经济或稳定强化，为后续利息和商店增加资源。'}
        reroll=s['round'].get('reroll_cost',5)
        if money>=reroll+(3 if pressured else 18) and reroll<=7 and (pressured or len(s['jokers']['cards'])<5 or (s['ante_num']>=3 and not ks&XMULT) or money>=38):
            return 'reroll',{'reason':f'抽样得分覆盖率约{outlook["coverage"]:.2f}，下一盲注目标{outlook["target"]}；优先补强，避免保留现金却无法过关。'}
        return 'next_round',{'reason':'现有选项未通过价格、贴纸和路线规则，保留本金进入下一轮，避免无目标刷新。'}
    raise ValueError('Unhandled state '+state)

def action(s):
    if cli.terminal(s) or s.get('overlay')=='unlock':return _base_action(s)
    if s['state'] in ('SELECTING_HAND','SHOP','BLIND_SELECT','SMODS_BOOSTER_OPENED'):
        chosen=consumables.held_action(s)
        if chosen:return chosen
    if s['state']=='SMODS_BOOSTER_OPENED':
        chosen=consumables.pack_action(s)
        if chosen:return chosen
    chosen=phases.before(s)
    if chosen:return chosen
    chosen=_base_action(s)
    if chosen:
        method,params=chosen
        if method=='next_round':
            redirect=phases.copy_action(s,'exit')
            if redirect:return redirect
        if method=='buy' and params.get('use') and 'j_perkeo' in a.keys(s) and not s['consumables']['cards']:
            params['use']=False;params['reason']='先保留这张消耗牌作为帕奇欧离店复制模板，后续使用额外复制品。'
    return chosen

def run(args):
    if args.continue_run:
        s=cli.call('gamestate')
    else:
        s=cli.call('gamestate')
        if s.get('state')!='MENU':
            if cli.terminal(s): s=cli.call('menu',{'reason':'本局已结束，记录结果，返回菜单开始下一组独立或同种子对照。'})
            else: raise ValueError('Active run exists; use --continue')
        params={'reason':'按固定规则基线试运行蓝色牌组金注，所有胜负保留，种子重复单独标记。'}
        if args.seed: params['seed']=args.seed
        s=cli.call('start',params)
    run_id=cli.read(cli.RUNS/'session.json')['run']
    sources=[Path(x) for x in (__file__,a.__file__,forecast.__file__,routes.__file__,tactics.__file__)]
    policy_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sources)).hexdigest()
    snapshot=cli.LAB/'cli/versions'/policy_hash[:12];snapshot.mkdir(parents=True,exist_ok=True)
    for p in sources:(snapshot/p.name).write_bytes(p.read_bytes())
    path=cli.RUNS/('run-%02d-policy.json'%run_id)
    history=cli.read(path,[])
    if isinstance(history,dict): history=[history]
    history.append({'policy':'deterministic_route_v0.8.1','code_sha256':policy_hash,'source_snapshot':str(snapshot.relative_to(cli.LAB)),'sampling':cli.read(cli.RUNS/'session.json')['sampling'],'continued':args.continue_run,'warning':'Exploratory candidate, not a proven high-success policy'})
    cli.write(path,history)
    for n in range(args.max_actions):
        if cli.terminal(s): cli.show(s); return
        chosen=action(s)
        if chosen is None: return
        method,params=chosen
        prediction=None
        uncertain=False
        if method=='play':
            prediction=a.score(s,params['cards'])[0]
            uncertain=a.uncertain(s)
        print(f'run={run_id} action={n} ante={s.get("ante_num")} round={s.get("round_num")} ${s.get("money")} {method} {params}',flush=True)
        s=cli.call(method,params)
        if method=='play':
            actual=s.get('round',{}).get('last_hand',{}).get('total')
            with (cli.RUNS/'predictions.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'run':run_id,'ante':s.get('ante_num'),'round':s.get('round_num'),'predicted':prediction,'actual':actual,'uncertain':uncertain},ensure_ascii=False)+'\n')
            if actual is not None and actual!=prediction and not uncertain:
                cli.show(s); raise ValueError(f'Deterministic prediction mismatch: {prediction} vs {actual}')
    raise ValueError('Action limit reached; run preserved for continuation')

if __name__=='__main__':
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed'); p.add_argument('--replay-run',type=int); p.add_argument('--continue',dest='continue_run',action='store_true')
    p.add_argument('--max-actions',type=int,default=500)
    args=p.parse_args()
    if args.replay_run:
        args.seed=cli.read(cli.RUNS/('run-%02d-outcome.json'%args.replay_run))['seed']
    run(args)
