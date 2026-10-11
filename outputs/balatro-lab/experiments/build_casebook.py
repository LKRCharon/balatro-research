"""Build a public-safe, evidence-linked casebook from already observed traces.

Never reads a seed registry or test partition. Inputs and hindsight labels remain
separate. No full hands, descriptions, raw seeds, rationale prose or plans copied.
"""
import argparse
from collections import Counter
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import re

METHODS=set('select skip play discard cash_out next_round buy pack use sell rearrange reroll reroll_boss continue'.split())
HANDS=('High Card','Pair','Two Pair','Three of a Kind','Straight','Flush','Full House','Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five')

@lru_cache(maxsize=None)
def blob(path):
    return path.read_bytes() if path.exists() else None

def rows(path):
    data=blob(path)
    return [json.loads(line) for line in data.decode('utf-8').splitlines()] if data else []

def read(path):
    data=blob(path)
    return json.loads(data) if data else {}

@lru_cache(maxsize=None)
def digest(path):
    data=blob(path)
    return hashlib.sha256(data).hexdigest() if data is not None else None

def number(value):
    return value if type(value) in (int,float) else None

def cardkey(value):
    return value if isinstance(value,str) and re.fullmatch('[jcvp]_[a-z0-9_]+',value) else 'unknown'

def public_features(state):
    blind=next((b for b in state.get('blinds',{}).values() if b.get('status')=='CURRENT'),{})
    lineup=[]
    for card in state.get('jokers',{}).get('cards',[]):
        mod=card.get('modifier') or {}
        lineup.append({'key':cardkey(card.get('key')),
            'edition':mod.get('edition') if mod.get('edition') in ('FOIL','HOLO','POLYCHROME','NEGATIVE') else None,
            'eternal':bool(mod.get('eternal')),'perishable':bool(mod.get('perishable')),
            'rental':bool(mod.get('rental')),'debuff':bool((card.get('state') or {}).get('debuff'))})
    phase=state.get('state')
    return {'phase':phase if phase in ('SHOP','SELECTING_HAND','BLIND_SELECT','ROUND_EVAL','SMODS_BOOSTER_OPENED','GAME_OVER') else 'unknown',
        'ante':number(state.get('ante_num')),'round':number(state.get('round_num')),'cash':number(state.get('money')),
        'blind':{'name':blind.get('name') if isinstance(blind.get('name'),str) and re.fullmatch('[A-Za-z ]{1,40}',blind['name']) else None,
                 'target':number(blind.get('score'))},
        'resources':{k:number(state.get('round',{}).get(k)) for k in ('hands_left','discards_left','chips','reroll_cost')},
        'lineup':lineup,'joker_limit':number(state.get('jokers',{}).get('limit')),
        'hand_levels':{name:{k:number(state['hands'][name].get(k)) for k in ('level','chips','mult','played')} for name in HANDS if name in state.get('hands',{})}}

def make_case(case_id,state,decision,lineage,evidence,after=None,outcome=None):
    method=decision.get('method',decision.get('action'))
    if method not in METHODS:return None
    params=decision.get('params') or {}
    target=None
    for param,area in (('card','pack' if method=='pack' else 'shop'),('joker','jokers'),('consumable','consumables'),('voucher','vouchers'),('pack','packs')):
        index=params.get(param);available=(state.get(area) or {}).get('cards') or []
        if type(index) is int and 0<=index<len(available):target=cardkey(available[index].get('key'));break
    origin=decision.get('origin',decision.get('controller_origin',lineage.get('controller')))
    if origin not in ('root_agent','controller','script','manual','agent','fallback'):origin='unknown'
    last=(after or {}).get('round',{}).get('last_hand') or {}
    label={'run_outcome':outcome if outcome in ('win','loss','error','truncated') else 'unknown',
        'actual_score':number(last.get('total')) if method=='play' else None,
        'actual_score_components':{k:number(last.get(k)) for k in ('chips','mult')} if method=='play' else None,
        'cash_after':number((after or {}).get('money')),
        'action_error':bool(decision.get('error')) if 'error' in decision or after is not None else None,
        'optimal_action_label':False,'after_linked':after is not None}
    label['execution_status']='rejected_no_mutation' if decision.get('rejected_no_mutation') else 'result_linked' if after is not None else 'unlinked'
    if decision.get('rejected_no_mutation'):label['action_error']=True
    if method=='play' and 'actual_score' in decision:label['actual_score']=number(decision['actual_score'])
    if method=='play' and after is not None and state.get('round',{}).get('chips') == after.get('round',{}).get('chips'):
        label['actual_score']=0;label['actual_score_components']=None
    if 'money_after' in decision:label['cash_after']=number(decision['money_after'])
    return {'case_id':case_id,'lineage':lineage,'controller_origin':origin,
        'plan':{'recorded':bool(decision.get('plan') or decision.get('parent_plan_id') or decision.get('plan_id')),
                'details_exported':False,'reason':'historical plans absent or unstructured; do not infer retrospectively'},
        'input':public_features(state),'decision':{'method':method,'target_key':target,
            'selected_count':len(params['cards']) if isinstance(params.get('cards'),list) else None,
            'predicted_score':number(decision.get('predicted')),'uncertain':decision.get('uncertain') if type(decision.get('uncertain')) is bool else None},
        'labels':label,'evidence':evidence,'rationale_exported':False}

def trace_cases(folder,cohort,partition,controller,version=None):
    decisions=rows(folder/'decisions.jsonl');events=rows(folder/'transitions.jsonl')
    intents={e['id']:e for e in events if e.get('event')=='intent'}
    rejected={e['id'] for e in events if 'id' in e and (e.get('accepted') is False or e.get('applied') is False)}
    results={e['id']:e.get('after') for e in events if e.get('event')=='result' and e['id'] not in rejected}
    result=read(folder/'result.json')
    gameplay=[e for e in events if e.get('event')=='intent' and e.get('method') in METHODS]
    relevant=[d for d in decisions if d.get('method') in METHODS]
    verified_order=(len(gameplay)==len(relevant) and all((i.get('method'),i.get('params'))==(d.get('method'),d.get('params')) for i,d in zip(gameplay,relevant)))
    cases=[]
    for index,d in enumerate(relevant):
        d=dict(d)
        ident=d.get('sequence',d.get('transition_id'))
        join='explicit_transition_id'
        if ident is None and verified_order:ident=gameplay[index]['id'];join='entire_action_sequence_method_params_verified'
        if ident not in intents or (intents[ident].get('method'),intents[ident].get('params')) != (d.get('method'),d.get('params')):
            join='unlinked';after=None;ident=None
        else:after=results.get(ident)
        if ident in rejected:d['rejected_no_mutation']=True
        state=d.get('before') or (intents.get(ident) or {}).get('before') or {}
        lineage={'cohort':cohort,'partition':partition,'controller':controller,'version':version or result.get('policy','unknown'),
                 'policy_hash':result.get('policy_digest',result.get('policy_id')),'seed_group':'not_exported; local registry retains grouping',
                 'valid_use':'mechanism_and_strategy_development_only' if partition!='test' else 'forbidden'}
        trace_id=hashlib.sha256(folder.name.encode()).hexdigest()[:16]
        case=make_case(f'{cohort}/trace-{trace_id}/{index+1}',state,d,lineage,
            {'trace_sha256':digest(folder/'decisions.jsonl'),'decision_ordinal':index+1,'transition_id':ident,'join':join},after,result.get('status'))
        if case:cases.append(case)
    return cases

def build(lab,work,manual_runs=None):
    blob.cache_clear()
    digest.cache_clear()
    cases=[];inventory=[]
    manual=lab/'results/manual-ten';manifest=read(manual/'manifest.json')
    labels={r['id']:r for r in rows(manual/'labels.jsonl')}
    for record in rows(manual/'decisions.jsonl'):
        label=labels.get(record['id'],{})
        case=make_case('manual-ten/'+record['id'],record['features'],label,
            {'cohort':'manual-ten','partition':'train','controller':'root_agent','version':'adaptive_historical_manual',
             'valid_use':'demonstration_not_optimal_or_frozen_policy','run':record.get('run')},
            {'input_sha256':digest(manual/'decisions.jsonl'),'labels_sha256':digest(manual/'labels.jsonl'),
             'source_line':record.get('source_line'),'stable_id':record['id']},outcome=label.get('run_outcome'))
        if case:cases.append(case)
    inventory.append({'cohort':'manual-ten','runs':len(manifest.get('runs',[])),'partition':'train','source_manifest_sha256':digest(manual/'manifest.json'),
                      'control':'root_agent_adaptive','not_independent_of_replays':True})
    for cohort,base,partition,controller in (
        ('formal-validation-001',lab/'results/formal-validation-001/jobs','validation_already_consumed','script'),
        ('combat-compare-001',work/'experiments/combat-compare-001','train','script'),
        ('hybrid-pilot-001',work/'experiments/hybrid-pilot-001','train','mixed'),
        ('manual-ten-002',work/'experiments/manual-ten-002','train','root_agent')):
        folders=([base] if (base/'decisions.jsonl').exists() else sorted(p.parent for p in base.rglob('decisions.jsonl'))) if base.exists() else []
        discovered=len(folders)
        if cohort=='manual-ten-002':
            if manual_runs is not None:folders=[folder for folder in folders if folder.name in {'train-'+str(n) for n in manual_runs}]
            # Do not even open decisions/hand observations for a live episode.
            folders=[folder for folder in folders if (folder/'result.json').exists()
                     and read(folder/'result.json').get('status') in ('win','loss','error','truncated')]
        versions={'formal-validation-001':'formal_route_v2','hybrid-pilot-001':'hybrid_root_and_route_v3',
                  'manual-ten-002':'adaptive_root_manual'}
        for folder in folders:cases+=trace_cases(folder,cohort,partition,controller,versions.get(cohort))
        inventory.append({'cohort':cohort,'trace_folders':len(folders),'partition':partition,'control':controller,
                          'presence':'available' if folders else 'pending_or_absent','unfinished_or_unselected_folders_excluded':discovered-len(folders),
                          'not_a_new_validation_sample':True})
    old=lab/'results/experiment-runs';result_files=list(old.glob('*-result.json'))
    old_results=[read(p) for p in result_files]
    # Original v2 worker has a stable intent_id joining observations and decisions.
    for result_path,result in zip(result_files,old_results):
        prefix=result_path.name[:-len('-result.json')]
        obs={r['intent_id']:r['features'] for r in rows(old/(prefix+'-observations.jsonl'))}
        for index,d in enumerate(rows(old/(prefix+'-decisions.jsonl'))):
            state=obs.get(d.get('intent_id'))
            if state is None:continue
            c=make_case('scripted-training/'+prefix+'/'+str(index+1),state,d,
                {'cohort':'scripted-training','partition':result.get('partition','unknown'),'controller':'script','version':result.get('policy','unknown'),
                 'policy_hash':result.get('policy_id'),'valid_use':'development_not_independent_winrate'},
                {'decisions_sha256':digest(old/(prefix+'-decisions.jsonl')),'intent_id':d.get('intent_id'),'join':'stable_intent_id'},outcome=result.get('status'))
            if c:cases.append(c)
    inventory.append({'cohort':'scripted-training','result_files':len(old_results),'outcomes':dict(Counter(r.get('status','unknown') for r in old_results)),
                      'partition_counts':dict(Counter(r.get('partition','unknown') for r in old_results)),
                      'control':'script','note':'multiple versions and repeated seeds; not a pooled independent win-rate cohort'})
    primary_rpc=[p for p in (lab/'results/cli-runs').glob('run-*.jsonl') if re.fullmatch(r'run-\d+\.jsonl',p.name)]
    inventory.append({'cohort':'legacy-rpc-source-archive','primary_logs':len(primary_rpc),
        'partition':'mixed_or_unverified','control':'mixed_or_unverified',
        'note':'Overlaps normalized manual and script records; early probes and replay run21 remain archived, not independently counted or silently promoted to training labels.'})
    return {'schema':1,'purpose':'reusable_development_cases_not_optimal_labels','inventory':inventory,'case_count':len(cases),
        'cases':cases,'restrictions':['Never input labels or case outcome to decision policy.',
            'Split and compare by private seed grouping; this public export omits raw seeds and grouping secrets.',
            'Already-consumed validation is diagnostic evidence only; do not claim it is a fresh holdout.',
            'No game test partition is read. No full hands, raw seeds, game descriptions, rationale prose or raw plan text exported.']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lab',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manual-runs',type=int,nargs='+',help='Explicit completed manual run allowlist; never inspect other manual traces')
    args=parser.parse_args();report=build(args.lab,args.work,args.manual_runs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(json.dumps({'cases':report['case_count'],'inventory':report['inventory']},ensure_ascii=False))

if __name__=='__main__':main()
