"""TRAIN-only hybrid session: controller owns strategy; route_v3 plays combat.

One CLI invocation owns the engine lease, then exits. No automatic shops, blind
selection, pack choices, cash-out, consumable use or sales. A pending RPC intent
blocks subsequent mutations; no retries or invisible recovery.
"""
from __future__ import annotations
import argparse
import copy
from contextlib import closing
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from environment import Environment, public, terminal
from isolation import load

LAB=Path(__file__).resolve().parents[1]
REGISTRY=LAB.parents[1]/'work/experiments/registry.sqlite'
AUTO_METHODS={'play','discard','rearrange'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files():
    paths=list((LAB/'experiments/policies/route_v3').glob('*'))
    paths += list((LAB/'cli').glob('*.py'))
    paths += [Path(__file__),*[LAB/'headless'/n for n in ('environment.py','transport.py','isolation.py')]]
    return {p.relative_to(LAB).as_posix():sha(p) for p in paths if p.is_file()}


def append(path,row):
    with Path(path).open('a',encoding='utf8') as out:
        out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush();os.fsync(out.fileno())


def atomic(path,value):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf8') as out:
        json.dump(value,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
    os.replace(temp,path)


def training_seed(registry,seed_id):
    with closing(sqlite3.connect(f'file:{Path(registry).resolve().as_posix()}?mode=ro',uri=True)) as db:
        row=db.execute("SELECT seed,commitment FROM seeds WHERE id=? AND partition='train'",(seed_id,)).fetchone()
    if not row or hashlib.sha256(row[0].encode()).hexdigest()!=row[1]:
        raise ValueError('Registered TRAIN seed and valid commitment required')
    return row


def modules():
    source=LAB/'experiments/policies/route_v3'
    sys.path[:0]=[str(source),str(LAB/'cli')]
    return (importlib.import_module('policy'),importlib.import_module('advisor'),
            importlib.import_module('belief'),importlib.import_module('execution'))


def restore_journal(path):
    state=None;jokers=[]
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf8').splitlines():
            row=json.loads(line)
            if row['event']=='result':
                state=row['after']
                cards=state.get('jokers',{}).get('cards',[])
                if not any(c.get('state',{}).get('hidden') for c in cards):jokers=copy.deepcopy(cards)
    return state,jokers


def visible(env,memory):
    context=env.context();s=env.state
    known={card.get('key') for area in ('jokers','shop','pack')
           for card in s.get(area,{}).get('cards',[]) if not card.get('state',{}).get('hidden')}
    context['targets']['targets']=[t for t in context['targets'].get('targets',[]) if t.get('key') in known]
    return memory.observe(s,context['collection'],context['targets'])


def auto_allowed(state,chosen):
    return (state.get('state')=='SELECTING_HAND' and not terminal(state) and chosen
            and chosen[0] in AUTO_METHODS)


def snapshot(root,env,memory,suggestion=None):
    state=visible(env,memory) if not terminal(env.state) else env.state
    output={'purpose':'controller_strategy_script_combat_train_only','strategy_winrate_eligible':False,
            'sequence':env.sequence,'terminal':terminal(env.state),'state':state,
            'action_space':env.action_space(),'suggestion':suggestion}
    atomic(root/'observation.json',output)
    if terminal(env.state):
        status='loss' if env.state.get('state')=='GAME_OVER' else 'win' if env.state.get('ante_num',0)>=8 else 'error'
        decisions=[json.loads(line) for line in (root/'decisions.jsonl').read_text(encoding='utf8').splitlines()]
        atomic(root/'result.json',{'purpose':'hybrid_train_only','strategy_winrate_eligible':False,
              'status':status,'terminal':True,'ante':env.state.get('ante_num'),
              'transition_count':env.sequence,'decision_count':len(decisions),
              'controller_decisions':sum(r.get('origin')=='controller' for r in decisions),
              'script_decisions':sum(r.get('origin')=='script' for r in decisions)})
    compact=copy.deepcopy(output)
    compact['state'].pop('_belief',None)
    for hand in compact['state'].get('hands',{}).values():
        if isinstance(hand,dict):hand.pop('example',None)
    return compact


def perform(root,env,memory,execution,advisor,method,params,origin):
    if method in ('start','menu','lab_stop'):raise ValueError('Disallowed gameplay action')
    if method not in env.action_space()['methods']:raise ValueError('Action not available in this phase')
    if method=='skip':
        if origin!='controller' or set(params)!={'reason'} or not isinstance(params['reason'],str) or not params['reason'].strip():
            raise ValueError('Manual blind skip requires an explicit reason only')
    else:execution.validate(env.state,method,params)
    before=visible(env,memory)
    prediction=advisor.score(before,params['cards'])[0] if method=='play' else None
    uncertain=advisor.uncertain(before) if method=='play' else None
    append(root/'decisions.jsonl',{'sequence':env.sequence+1,'transition_id':env.sequence+1,'origin':origin,'before':before,
          'method':method,'params':public(params),'predicted':prediction,'uncertain':uncertain,'at_utc':time.time()})
    state=env.step(method,params)
    if method=='play':
        actual=state.get('round',{}).get('last_hand',{}).get('total')
        if state.get('round',{}).get('chips')==before.get('round',{}).get('chips'):actual=0
        append(root/'predictions.jsonl',{'transition_id':env.sequence,'origin':origin,
               'predicted':prediction,'actual':actual,'uncertain':uncertain,
               'within_one':abs(prediction-actual)<=1 if not uncertain and actual is not None else None})
    append(root/'economy.jsonl',{'sequence':env.sequence,'origin':origin,'method':method,
           'ante':state.get('ante_num'),'round':state.get('round_num'),'phase':state.get('state'),
           'money_before':before.get('money'),'money_after':state.get('money'),
           'shop':state.get('shop'),'packs':state.get('packs'),'pack':state.get('pack'),
           'vouchers':state.get('vouchers'),'consumables':state.get('consumables'),
           'jokers':state.get('jokers')})
    return state


def start(manifest_path,registry,seed_id,root):
    root=Path(root).resolve()
    if root.exists():raise ValueError('Session directory already exists; never overwrite or restart')
    seed,commitment=training_seed(registry,seed_id)
    m=load(manifest_path)
    if m.get('readiness_patch',{}).get('version')!=3:raise ValueError('Readiness v3 required')
    for name,h in m['input_hashes'].items():
        if sha(Path(m['checkout'])/name)!=h:raise ValueError('Engine source mismatch')
    root.mkdir(parents=True)
    config={'schema':1,'purpose':'hybrid_train_only','policy':'route_v3','seed_id':seed_id,
            'seed_commitment':commitment,'manifest':str(Path(manifest_path).resolve()),
            'manifest_sha256':sha(manifest_path),'registry':str(Path(registry).resolve()),
            'source_hashes':files(),'automatic_methods':sorted(AUTO_METHODS)}
    atomic(root/'session.json',config)
    _,advisor,belief,execution=modules()
    with Environment(m['port'],m['identity'],root,registry=registry) as env:
        current=env.observe()
        if current['state']!='MENU' and not terminal(current):raise ValueError('MENU or finished engine required; no unfinished episode reset')
        start_id=env.sequence+(2 if terminal(current) else 1)
        append(root/'decisions.jsonl',{'sequence':start_id,'transition_id':start_id,'origin':'controller',
               'method':'start','seed_commitment':commitment,'at_utc':time.time()})
        env.reset(seed)
        if (env.state.get('deck'),env.state.get('stake'))!=('BLUE','GOLD'):raise ValueError('Wrong conditions')
        return snapshot(root,env,belief.Belief())


def operate(root,command,*,method=None,params=None,expected_sequence=None,max_actions=100):
    root=Path(root).resolve();config=json.loads((root/'session.json').read_text(encoding='utf8'))
    if files()!=config['source_hashes']:raise ValueError('Hybrid policy or driver changed; preserve frozen session')
    if sha(config['manifest'])!=config['manifest_sha256']:raise ValueError('Instance manifest changed')
    m=load(config['manifest'])
    for name,h in m['input_hashes'].items():
        if sha(Path(m['checkout'])/name)!=h:raise ValueError('Engine source mismatch')
    policy,advisor,belief,execution=modules()
    with Environment(m['port'],m['identity'],root,registry=config['registry']) as env:
        env.state,jokers=restore_journal(root/'transitions.jsonl')
        memory=belief.Belief();memory.jokers=jokers
        env.observe()
        if command=='view':return snapshot(root,env,memory)
        if expected_sequence!=env.sequence:raise ValueError('Stale sequence; observe before a new command, never replay actions')
        if terminal(env.state):return snapshot(root,env,memory)
        if command=='act':
            perform(root,env,memory,execution,advisor,method,params or {},'controller')
            return snapshot(root,env,memory)
        if command!='step':raise ValueError('Unknown session command')
        if not 1<=max_actions<=100:raise ValueError('A combat batch must contain 1..100 actions')
        for _ in range(max_actions):
            if env.state.get('state')!='SELECTING_HAND' or terminal(env.state):break
            chosen=policy.action(visible(env,memory))
            if not auto_allowed(env.state,chosen):return snapshot(root,env,memory,chosen)
            perform(root,env,memory,execution,advisor,*chosen,'script')
        return snapshot(root,env,memory)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('start');q.add_argument('--manifest',required=True);q.add_argument('--registry',default=str(REGISTRY))
    q.add_argument('--seed-id',type=int,required=True);q.add_argument('--session',required=True)
    for name in ('view','step','act'):
        q=sub.add_parser(name);q.add_argument('--session',required=True)
        if name!='view':q.add_argument('--expected-sequence',type=int,required=True)
        if name=='step':q.add_argument('--max-actions',type=int,default=100)
        if name=='act':
            q.add_argument('--method',required=True)
            group=q.add_mutually_exclusive_group(required=True);group.add_argument('--params');group.add_argument('--params-file')
    args=p.parse_args()
    try:
        if args.command=='start':result=start(args.manifest,args.registry,args.seed_id,args.session)
        else:
            params=None
            if args.command=='act':params=json.loads(Path(args.params_file).read_text(encoding='utf8-sig') if args.params_file else args.params)
            result=operate(args.session,args.command,method=getattr(args,'method',None),params=params,
                           expected_sequence=getattr(args,'expected_sequence',None),max_actions=getattr(args,'max_actions',100))
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        # No potentially private RPC error string reaches the controller. Durable
        # pending intent is kept by Environment and prevents any replay.
        root=Path(args.session)
        if root.exists():
            append(root/'errors.jsonl',{'type':type(exc).__name__,'command':args.command,'at_utc':time.time()})
            if (root/'transitions.jsonl').exists():
                rows=[json.loads(line) for line in (root/'transitions.jsonl').read_text(encoding='utf8').splitlines()]
                if rows and rows[-1].get('event')=='intent':
                    atomic(root/'result.json',{'purpose':'hybrid_train_only','strategy_winrate_eligible':False,
                          'status':'error','terminal':False,'outcome_unknown':True,'error_type':type(exc).__name__})
        print(json.dumps({'error':type(exc).__name__,'message':'Session action stopped; inspect durable journal, do not retry blindly.'}))
        raise SystemExit(1)
