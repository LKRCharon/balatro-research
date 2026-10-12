"""Finished TRAIN visible-hand structural sensitivity; never an execution policy."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'policies/route_v3'),str(HERE.parent/'cli')]
import advisor as a
import shop_planning as planner


def refresh(s):
    """Refresh dependent counters without mutating frozen scoring code."""
    held=s['jokers']['cards'];s['jokers']['count']=len(held)
    for i,c in enumerate(held):
        if c['key']=='j_swashbuckler':
            value=sum(x.get('cost',{}).get('sell',0) for j,x in enumerate(held) if i!=j)
            c.setdefault('value',{})['effect']=str(value)
    return s


def best(s):
    if a.uncertain(s):return None
    if a.keys(s)-a.SUPPORTED:return None
    candidates=a.options(s)
    return candidates[0][0] if candidates else None


def difference(base,value):
    return {'score':value,'delta':value-base if value is not None else None,
            'relative_delta':value/base-1 if value is not None and base else None,
            'deterministic_model_eligible':value is not None}


def probe(s,score_fn=best):
    s=refresh(copy.deepcopy(s))
    base=score_fn(s)
    if base is None:return {'eligible':False,'reason':'uncertain_or_unsupported','baseline':None}
    result={'eligible':True,'baseline':base,'exactness':'deterministic_route_v3_model_not_engine_proof',
            'joker_marginals':[],'planet_upgrades':[],'shop_candidates':[]}
    held=s['jokers']['cards']
    for i,c in enumerate(held):
        sim=copy.deepcopy(s);sim['jokers']['cards'].pop(i)
        sim['jokers']['limit']-=int(a.mod(c).get('edition')=='NEGATIVE')
        removal=score_fn(refresh(sim))
        entry={'index':i,'key':c['key'],'structural_removal':difference(base,removal),
            'sale_legal_by_eternal_flag':not bool(a.mod(c).get('eternal')),
            'rental_cash_per_round':3 if a.mod(c).get('rental') else 0,'reslots':[]}
        for destination in range(len(held)):
            if destination==i:continue
            moved=copy.deepcopy(s);card=moved['jokers']['cards'].pop(i);moved['jokers']['cards'].insert(destination,card)
            entry['reslots'].append({'destination':destination,**difference(base,score_fn(refresh(moved)))})
        result['joker_marginals'].append(entry)
    for planet,hand in planner.PLANETS.items():
        sim=planner.upgraded(s,{'key':planet},0)
        if sim:result['planet_upgrades'].append({'key':planet,'hand_type':hand,**difference(base,score_fn(sim))})
    # All affordable direct additions/replacements, no tier blacklist. Same observed
    # hand: no future shop/deck sampling, no claimed causal purchase payoff.
    for offer in s.get('shop',{}).get('cards',[]):
        if offer.get('set')!='JOKER':continue
        price=offer.get('cost',{}).get('buy')
        if not isinstance(price,(int,float)):continue
        targets=[None]+[i for i,c in enumerate(held) if not a.mod(c).get('eternal')]
        for target in targets:
            sim=copy.deepcopy(s);sale=0
            if target is not None:
                old=sim['jokers']['cards'].pop(target);sale=old.get('cost',{}).get('sell',0)
                sim['jokers']['limit']-=int(a.mod(old).get('edition')=='NEGATIVE')
            sim['jokers']['cards'].insert(len(sim['jokers']['cards']) if target is None else target,copy.deepcopy(offer))
            sim['jokers']['limit']+=int(a.mod(offer).get('edition')=='NEGATIVE')
            sim['money']=s.get('money',0)+sale-price
            if sim['money']<0 or len(sim['jokers']['cards'])>sim['jokers']['limit']:continue
            result['shop_candidates'].append({'key':offer['key'],'replacement_index':target,'quoted_price':price,
                'cash_after':sim['money'],'execution_legal_verified':False,**difference(base,score_fn(refresh(sim)))})
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs-root',type=Path,required=True);p.add_argument('--runs',nargs='+',type=int,required=True)
    p.add_argument('--max-per-run',type=int,default=3);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.max_per_run<1:raise ValueError('max-per-run must be positive')
    report={'schema':1,'purpose':'retrospective_visible_hand_sensitivity','causal_winrate':False,'runs':[]}
    for n in args.runs:
        folder=args.runs_root/f'train-{n}';meta=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        if not meta.get('terminal') or meta.get('status') not in ('win','loss'):raise ValueError('Terminal TRAIN runs only')
        data=(folder/'decisions.jsonl').read_bytes();rows=[json.loads(x) for x in data.decode('utf-8').splitlines()]
        # End-of-run observed hands are a diagnostic sample, explicitly not random.
        rows=[r for r in rows if r.get('method')=='play' and r.get('before',{}).get('hand',{}).get('cards')][-args.max_per_run:]
        observations=[]
        for r in rows:
            value=probe(r['before']);value['sequence']=r.get('sequence');observations.append(value)
        report['runs'].append({'run_id':n,'source_sha256':hashlib.sha256(data).hexdigest(),'observations':observations})
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'runs':len(report['runs']),'observations':sum(len(r['observations']) for r in report['runs'])}))

if __name__=='__main__':main()
