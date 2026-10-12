"""Offline terminal TRAIN resource accounting. Never opens seed registries or plays."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median


def cards(state, area):
    value=state.get(area,{})
    return value.get('cards',[]) if isinstance(value,dict) else []


def interest(cash, vouchers=()):
    cap=20 if 'v_money_tree' in vouchers else 10 if 'v_seed_money' in vouchers else 5
    return min(cap,max(0,cash)//5)


def target_card(before,method,params):
    mapping={'voucher':'vouchers','pack':'packs','joker':'jokers','consumable':'consumables','card':'pack' if method=='pack' else 'shop'}
    for key,area in mapping.items():
        index=params.get(key)
        if isinstance(index,int) and not isinstance(index,bool):
            pool=cards(before,area)
            if 0<=index<len(pool):return area,pool[index]
    return None,{}


def lineup(state):
    return [{'key':c.get('key'),'perishable':c.get('modifier',{}).get('perishable'),
             'rental':bool(c.get('modifier',{}).get('rental')),'eternal':bool(c.get('modifier',{}).get('eternal'))}
            for c in cards(state,'jokers')]


def analyze(rows,run_id):
    intents={};events=[];exposures={};departures=[];combat={};net=Counter();quoted=Counter();rejected=0
    for row in rows:
        if row.get('event')=='intent':
            if row['id'] in intents:raise ValueError('Duplicate intent id')
            intents[row['id']]=row;continue
        if row.get('event')!='result':continue
        intent=intents.get(row.get('id'))
        if intent is None:raise ValueError('Unmatched result')
        if row.get('accepted') is False or row.get('applied') is False:
            rejected+=1;continue
        b=intent.get('before',{});a=row.get('after',{});method=intent['method'];params=intent.get('params',{})
        if not a:continue
        # ID-level deduplication: persistent offers are not counted each observation.
        for area in ('shop','vouchers','packs','pack'):
            for index,c in enumerate(cards(b,area)):
                identity=c.get('id')
                if identity is None:continue  # do not pretend structural equality is identity
                key=(area,identity)
                if key not in exposures:
                    price=c.get('cost',{}).get('buy')
                    exposures[key]={'area':area,'key':c.get('key'),'set':c.get('set'),'quoted_price':price,
                        'cash_covers_price_when_first_seen':isinstance(price,(int,float)) and price<=b.get('money',0),
                        'first_sequence':row['id']}
        cash=b.get('money',0);delta=a.get('money',cash)-cash;net[method]+=delta
        area,c=target_card(b,method,params)
        if method in ('buy','reroll','use','pack','sell'):
            category='reroll' if method=='reroll' else ('voucher' if area=='vouchers' else 'pack' if area=='packs' else 'joker' if c.get('set')=='JOKER' else 'consumable' if c.get('set') in ('TAROT','PLANET','SPECTRAL') else 'other')
            price=b.get('round',{}).get('reroll_cost') if method=='reroll' else c.get('cost',{}).get('buy') if method=='buy' else None
            if isinstance(price,(int,float)):quoted[category]+=price
            vouchers=b.get('used_vouchers',[])
            vouchers=[v.get('key') if isinstance(v,dict) else v for v in vouchers]
            events.append({'sequence':row['id'],'method':method,'category':category,'target_key':c.get('key'),
                'cash_before':cash,'cash_after':a.get('money'),'net_cash_delta':delta,'quoted_cost':price,
                'immediate_interest_capacity_delta':interest(a.get('money',cash),vouchers)-interest(cash,vouchers)})
        if method=='next_round':
            departures.append({'sequence':row['id'],'ante':b.get('ante_num'),'round':b.get('round_num'),
                'cash':cash,'lineup':lineup(b),'consumable_count':len(cards(b,'consumables')),
                'forward_power_estimate':None,'power_estimate_missing':True})
        if method=='play':
            blind=next((x for x in b.get('blinds',{}).values() if x.get('status')=='CURRENT'),{})
            key=(b.get('round_num'),b.get('ante_num'),blind.get('name'))
            item=combat.setdefault(key,{'round':key[0],'ante':key[1],'blind':key[2],'target':blind.get('score'),
                'initial_hands_observed':b.get('round',{}).get('hands_left'),'scores':[],'terminal_score':0})
            # last_hand.total is actual hand score; chips deltas can reset on a win.
            score=a.get('round',{}).get('last_hand',{}).get('total')
            if isinstance(score,(int,float)):item['scores'].append(score)
            item['terminal_score']=a.get('round',{}).get('chips')
    combats=list(combat.values())
    for item in combats:
        target=item['target'];scores=item['scores'];total=item['terminal_score']
        item['score_target_ratio']=total/target if target and total is not None else None
        item['median_hand_score']=median(scores) if scores else None
        item['required_average_at_first_play']=target/item['initial_hands_observed'] if target and item['initial_hands_observed'] else None
        item['remaining_shortfall']=max(0,target-total) if target and total is not None else None
    for previous,current in zip(combats,combats[1:]):
        old=previous['median_hand_score'];new=current['median_hand_score']
        current['observed_median_score_growth']=new/old if old and new is not None else None
        current['target_growth']=current['target']/previous['target'] if previous['target'] and current['target'] else None
    last=combats[-1] if combats else None
    return {'run_id':run_id,'resource_events':events,'offer_exposures':list(exposures.values()),
        'quoted_acquisition_costs':dict(quoted),'net_cash_delta_by_method':dict(net),'rejected_no_mutation':rejected,
        'shop_departures':departures,'combat_observations':combats,'last_combat':last,
        'last_departure':departures[-1] if departures else None}


def markdown(report):
    lines=['# 已终局 TRAIN 资源复盘','','仅描述观测与机会成本，不把购买相关性解释为卡牌因果强度。离店前未记录完整前瞻估分时保留缺失，不以最终失败倒填预测。','',
        '|局|最后盲注|得分/目标|缺口|最后离店现金|易腐组件|报价支出（非净支出）|','|---|---|---|---|---|---|---|']
    for run in report['runs']:
        c=run['last_combat'] or {};d=run['last_departure'] or {}
        perishable=', '.join(f"{x['key']}:{x['perishable']}" for x in d.get('lineup',[]) if x['perishable'] is not None) or '无'
        lines.append(f"|{run['run_id']}|{c.get('blind')}|{c.get('terminal_score')}/{c.get('target')}|{c.get('remaining_shortfall')}|{d.get('cash')}|{perishable}|{json.dumps(run['quoted_acquisition_costs'],ensure_ascii=False)}|")
    lines+=['','金币变化含触发收入、租金等；商品报价和净金币变化分别统计。利息指标是立即可得利息容量变化，并非实际损失的未来收益。易腐剩余数来自离店公开状态，不估算其单独战力。实际出牌中位分与目标比仅为回顾指标，不保证未来抽牌可重复。']
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs-root',type=Path,required=True);p.add_argument('--runs',nargs='+',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report={'schema':1,'purpose':'offline_train_resource_observations','causal_strength_estimate':False,'runs':[]}
    for n in a.runs:
        folder=a.runs_root/f'train-{n}';result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        if result.get('terminal') is not True or result.get('status') not in ('win','loss'):raise ValueError('Only terminal TRAIN runs allowed')
        data=(folder/'transitions.jsonl').read_bytes();run=analyze([json.loads(x) for x in data.decode('utf-8').splitlines() if x.strip()],n)
        run['status']=result['status'];run['source_sha256']=hashlib.sha256(data).hexdigest();report['runs'].append(run)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');a.output.with_suffix('.md').write_text(markdown(report),encoding='utf-8')
    print(json.dumps({'runs':len(report['runs']),'output':str(a.output)}))

if __name__=='__main__':main()
