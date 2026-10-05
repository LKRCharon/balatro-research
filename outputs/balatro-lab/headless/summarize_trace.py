"""Read-only intent/result telemetry adapter; public-safe, standard library only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

AREAS = ('shop','vouchers','packs','pack')

def key(value):
    return value if isinstance(value,str) and re.fullmatch(r'(?:[jcvp]_[a-z0-9_]+|[SHCD]_[2-9TJQKA])',value) else 'unknown'

def cards(state, area):
    return (state.get(area) or {}).get('cards') or []

def number(value):
    return value if type(value) in (int,float) else None

def extract(events, decisions=(), catalog=None):
    """Count resolved actions and observable offer identities, never hidden content."""
    origins = {}
    for row in decisions:
        # New hybrid traces may bind transition_id; older traces use action
        # number but reset/menu transitions make positional joins unsafe.
        ident = row.get('transition_id', row.get('sequence'))
        if ident is not None: origins[ident] = row.get('controller_origin', row.get('origin'))
    offers = []
    seen = {}
    visits = 0
    generation = 0
    pack_generation = 0
    visit_round = None
    parent_pack = None
    pending = {}
    money = []
    selected = Counter()
    selections = []
    rarity = Counter()
    uncertain_ids = 0
    unresolved_origins = 0

    def observe(state):
        nonlocal visits,visit_round,generation,uncertain_ids
        phase = state.get('state')
        if phase not in ('SHOP','SMODS_BOOSTER_OPENED'): return
        if phase == 'SHOP':
            at = (state.get('ante_num'),state.get('round_num'))
            if visits == 0 or at != visit_round:
                visits += 1;visit_round = at;generation = 0
        for area in AREAS:
            if (area == 'pack') != (phase == 'SMODS_BOOSTER_OPENED'): continue
            repeated = Counter()
            for card in cards(state,area):
                if (card.get('state') or {}).get('hidden'): continue
                item_key = key(card.get('key'))
                identity = card.get('id')
                fallback = identity is None
                if fallback:
                    fingerprint = (item_key,str(card.get('set','unknown')),
                                   json.dumps(card.get('modifier') or {},sort_keys=True))
                    repeated[fingerprint] += 1
                    identity = (fingerprint,repeated[fingerprint])
                token = (area,visits,generation if area=='shop' else pack_generation if area=='pack' else 0,identity)
                price = number((card.get('cost') or {}).get('buy'))
                if token in seen:
                    offer = offers[seen[token]]
                    if price != offer['latest_price']:
                        offer['price_history'].append(price);offer['latest_price'] = price
                    continue
                seen[token] = len(offers)
                raw_rarity = card.get('rarity')
                rarity_source = 'observed_card'
                if raw_rarity not in (1,2,3,4,'1','2','3','4'):
                    raw_rarity = (catalog or {}).get(item_key,{}).get('rarity')
                    rarity_source = 'factual_catalog' if raw_rarity in (1,2,3,4,'1','2','3','4') else 'unknown'
                observed_rarity = str(raw_rarity) if raw_rarity in (1,2,3,4,'1','2','3','4') else 'unknown'
                if area=='shop' and str(card.get('set','')).upper()=='JOKER': rarity[observed_rarity] += 1
                offers.append({'area':area,'key':item_key,'visit':visits,
                    'inventory_generation':generation if area=='shop' else pack_generation if area=='pack' else 0,
                    'ante':number(state.get('ante_num')),'round':number(state.get('round_num')),
                    'observed_rarity':observed_rarity,'rarity_source':rarity_source,'first_price':price,'latest_price':price,
                    'price_history':[price],'cash_when_first_observed':number(state.get('money')),
                    'identity_quality':'fingerprint_fallback' if fallback else 'engine_id',
                    'parent_pack':parent_pack if area=='pack' else None})
                uncertain_ids += int(fallback)

    for event in events:
        ident = event.get('id')
        if event.get('event')=='intent':
            pending[ident] = event;observe(event.get('before') or {});continue
        if event.get('event')!='result': continue
        intent = pending.pop(ident,None)
        if intent is None: continue
        before = intent.get('before') or {};after = event.get('after') or {}
        method = intent.get('method');params = intent.get('params') or {}
        origin = intent.get('controller_origin') or origins.get(ident)
        if origin not in ('agent','script','manual','fallback','controller'): origin = 'unknown';unresolved_origins += 1
        b,a = number(before.get('money')),number(after.get('money'))
        money.append({'transition_id':ident,'method':method if method in ('start','menu','select','skip','play','discard','cash_out','next_round','buy','pack','use','sell','rearrange','reroll','reroll_boss','continue') else 'unknown',
            'ante':number(after.get('ante_num')),'round':number(after.get('round_num')),
            'money_before':b,'money_after':a,'net_money_delta':None if b is None or a is None else a-b,
            'controller_origin':origin})
        chosen = None
        if method=='buy':
            chosen = next(((area,params[param]) for param,area in [('card','shop'),('voucher','vouchers'),('pack','packs')] if param in params),None)
        elif method=='pack' and 'card' in params: chosen = ('pack',params['card'])
        if chosen:
            area,idx = chosen
            prior = cards(before,area)
            if type(idx) is int and 0<=idx<len(prior):
                selected_key = key(prior[idx].get('key'))
                selected[area+':'+selected_key] += 1
                selections.append({'transition_id':ident,'area':area,'key':selected_key,
                    'quoted_buy_price':number((prior[idx].get('cost') or {}).get('buy')),
                    'method':method,'controller_origin':origin})
                if area=='packs': parent_pack = selected_key
        if method=='pack' and params.get('skip'): selected['pack:skip'] += 1
        if method=='reroll': generation += 1
        if after.get('state')=='SMODS_BOOSTER_OPENED' and before.get('state')!='SMODS_BOOSTER_OPENED': pack_generation += 1
        # A cashout opens a fresh visit even if round numbering repeats; pack
        # return is not a new shop. Most visits are also distinguished by round.
        if method=='cash_out' and after.get('state')=='SHOP':
            visits += 1;visit_round=(after.get('ante_num'),after.get('round_num'));generation=0
        observe(after)
    return {'economy':money,'offers':offers,'resolved_selections':selections,
        'selection_counts':dict(selected),'offer_counts_by_area':dict(Counter(o['area'] for o in offers)),
        'observed_shop_joker_rarity_counts':dict(rarity),'observed_shop_joker_offer_denominator':sum(rarity.values()),
        'fingerprint_identity_exposures':uncertain_ids,'unresolved_intents':len(pending),
        'actions_without_explicit_origin':unresolved_origins}

def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []

def build(source, catalog_path=None):
    catalog_bytes = catalog_path.read_bytes() if catalog_path else None
    catalog = json.loads(catalog_bytes) if catalog_bytes else None
    jobs = []
    for folder in sorted(source.iterdir()):
        if not folder.is_dir() or not (folder/'transitions.jsonl').exists(): continue
        result_path = folder/'result.json'
        if not result_path.exists(): raise ValueError('Incomplete task: refusing final telemetry export')
        result = json.loads(result_path.read_text(encoding='utf-8'))
        status = result.get('status')
        if status not in ('win','loss','error','truncated'): raise ValueError('Unknown task status')
        jobs.append({'job_id':folder.name,'status':status,
                     **extract(read_rows(folder/'transitions.jsonl'),read_rows(folder/'decisions.jsonl'),catalog)})
    if not jobs: raise ValueError('No completed traces found')
    return {'schema':1,'purpose':'posthoc_observed_trace_accounting','jobs':jobs,'jobs_count':len(jobs),
        'rarity_catalog':None if catalog_bytes is None else {'sha256':hashlib.sha256(catalog_bytes).hexdigest(),
            'mapping':'card key -> frozen factual Joker metadata rarity; observed rarity takes precedence'},
        'caveats':[
            'Only visited shops and opened pack contents are observed; exposure is policy/survival selected.',
            'Rarity comes from observed card.rarity or optional hashed factual catalog; per-offer rarity_source states provenance; absent both stays unknown.',
            'Stable ids deduplicate within shop visit/reroll generation; fallback fingerprints can merge indistinguishable replacements.',
            'Voucher/pack offers persist across rerolls but count anew in a new shop visit.',
            'Net money differences are not component income attribution; buy/use effects may combine costs and payouts.',
            'Selections mean resolved engine actions with observed targets, not independently verified inventory acquisitions.',
            'Controller origin is preserved only with explicit intent origin or decision.transition_id/sequence; no positional inference.',
            'No raw seeds, future card order, full states, hand trajectories, descriptions or decision prose exported.'
        ]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--specs',type=Path)
    args=parser.parse_args();report=build(args.source,args.specs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'jobs':report['jobs_count'],'offers':sum(len(j['offers']) for j in report['jobs'])}))

if __name__=='__main__':main()
