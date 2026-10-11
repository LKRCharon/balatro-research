"""Full controller manual TRAIN session. No step command or policy action calls.

Numerical output describes scored visible hands; it never chooses an action.
Frozen hybrid helpers supply journaling/observation only, never their controller.
"""
from __future__ import annotations
import argparse
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import hybrid_session as h

LAB=h.LAB
SEED_IDS=tuple(range(32,42))


class ManualEnvironment(h.Environment):
    def _write(self,row):
        super()._write(dict(row,controller_origin='controller'))


def source_hashes():
    result=h.files()
    result['headless/manual_session.py']=h.sha(Path(__file__))
    return result


def modules():
    sys.path[:0]=[str(LAB/'experiments/policies/route_v3'),str(LAB/'cli')]
    # Deliberately no import of policy and no action()/auto() call.
    return tuple(importlib.import_module(name) for name in ('advisor','belief','execution'))


def verify_engine(path,expected=None):
    if expected and h.sha(path)!=expected:raise ValueError('Instance manifest changed')
    m=h.load(path)
    if m.get('readiness_patch',{}).get('version')!=3:raise ValueError('Readiness v3 required')
    for name,digest in m['input_hashes'].items():
        if h.sha(Path(m['checkout'])/name)!=digest:raise ValueError('Engine input changed')
    return m


def prepare(manifest,registry,output):
    m=verify_engine(manifest)
    commitments=[{'seed_id':i,'seed_commitment':h.training_seed(registry,i)[1]} for i in SEED_IDS]
    output=Path(output).resolve()
    if output.exists():raise ValueError('Protocol output already exists')
    pub=LAB.parent/'balatro-research-public'
    result=subprocess.run(['git','rev-parse','HEAD'],cwd=pub,capture_output=True,text=True)
    protocol={'schema':1,'purpose':'full_controller_train_data','partition':'train',
        'strategy_winrate_eligible':False,'jobs':commitments,'controller':'root agent chooses every gameplay action',
        'automatic_gameplay':False,'numerical_tools':'visible-hand score estimates only, no action selection',
        'conditions':{'deck':'BLUE','stake':'GOLD','no_restart':True,'no_mutation_retry':True},
        'source_hashes':source_hashes(),'engine_input_hashes':m['input_hashes'],
        'engine_manifest_sha256':h.sha(manifest),'readiness_version':3,
        'prior_repository_commit':result.stdout.strip() if result.returncode==0 else None,
        'limitations':['TRAIN data with controller intervention, not frozen-policy validation',
                      'score estimates may be uncertain; actual scoring logged separately']}
    output.mkdir(parents=True);h.atomic(output/'protocol.json',protocol)
    return {'protocol':str(output/'protocol.json'),'training_jobs':len(commitments),'seed_values_disclosed':False}


def numerical_scores(state,advisor):
    if state.get('state')!='SELECTING_HAND' or h.terminal(state):return []
    selected=[];categories=set()
    for value,indices,name,scored in advisor.options(state):
        if name in categories:continue
        categories.add(name)
        selected.append({'hand_type':name,'estimated_score':value,'indices':list(indices),
                         'scoring_indices':list(scored),'requires_rearrange':list(indices)!=sorted(indices),
                         'uncertain':advisor.uncertain(state)})
        if len(selected)==6:break
    return selected


def compact(state):
    fields=('state','ante_num','round_num','money','round','blinds','used_vouchers','won','overlay')
    s={k:copy.deepcopy(state[k]) for k in fields if k in state}
    s['hands']={name:{k:row.get(k) for k in ('level','chips','mult')} for name,row in state.get('hands',{}).items()}
    areas=['hand','jokers','consumables']
    if state.get('state')=='SHOP':areas+=['shop','packs','vouchers']
    if state.get('state')=='SMODS_BOOSTER_OPENED':areas+=['pack']
    for area in areas:
        source=state.get(area,{})
        rows=[]
        for i,c in enumerate(source.get('cards',[])):
            row={'index':i,'key':c.get('key')}
            for k in ('modifier','state','cost','label','value','set','permanent_bonus'):
                if c.get(k) and (area!='hand' or k not in ('label','value','set','cost')):row[k]=copy.deepcopy(c[k])
            rows.append(row)
        s[area]={'limit':source.get('limit'),'cards':rows}
    return s


def snapshot(root,env,memory,advisor):
    state=h.visible(env,memory) if not h.terminal(env.state) else env.state
    numeric_error=None
    try:scores=numerical_scores(state,advisor)
    except Exception as exc:scores=[];numeric_error=type(exc).__name__
    output={'purpose':'full_controller_train_data','strategy_winrate_eligible':False,
       'sequence':env.sequence,'terminal':h.terminal(env.state),'state':compact(state),
       'structural_actions':env.action_space(),'numerical_scores':scores}
    if numeric_error:output['numerical_error']=numeric_error
    h.atomic(root/'observation.json',output)
    if h.terminal(env.state):
        status='loss' if env.state.get('state')=='GAME_OVER' else 'win' if env.state.get('ante_num',0)>=8 else 'error'
        decisions=[json.loads(x) for x in (root/'decisions.jsonl').read_text(encoding='utf8').splitlines()]
        h.atomic(root/'result.json',{'purpose':'full_controller_train_data','status':status,'terminal':True,
            'ante':env.state.get('ante_num'),'transition_count':env.sequence,'decision_count':len(decisions),
            'controller_decisions':len(decisions),'script_decisions':0,'strategy_winrate_eligible':False})
    return output


def claim_seed(registry,protocol_path,seed_id,session):
    claims=Path(registry).resolve().parent/'manual-allocation-locks'/h.sha(protocol_path)
    claims.mkdir(parents=True,exist_ok=True)
    with (claims/f'{seed_id}.json').open('x',encoding='utf8') as out:
        json.dump({'seed_id':seed_id,'session':str(Path(session).resolve()),'claimed_utc':time.time()},out)
        out.flush();os.fsync(out.fileno())


def perform(root,env,memory,execution,advisor,method,params):
    if method in ('start','menu','lab_stop'):raise ValueError('Disallowed gameplay action')
    if method not in env.action_space()['methods']:raise ValueError('Action not available in this phase')
    if method=='skip':
        if set(params)!={'reason'} or not isinstance(params['reason'],str) or not params['reason'].strip():
            raise ValueError('Manual skip requires explicit reason only')
    else:execution.validate(env.state,method,params)
    before=h.visible(env,memory);prediction=None;uncertain=None;numeric_error=None
    if method=='play':
        try:
            prediction=advisor.score(before,params['cards'])[0]
            uncertain=advisor.uncertain(before)
        except Exception as exc:
            prediction=None;uncertain=True;numeric_error=type(exc).__name__
    h.append(root/'decisions.jsonl',{'sequence':env.sequence+1,'transition_id':env.sequence+1,
        'origin':'controller','before':before,'method':method,'params':h.public(params),
        'predicted':prediction,'uncertain':uncertain,'numerical_error':numeric_error,'at_utc':time.time()})
    state=env.step(method,params)
    if method=='play':
        actual=state.get('round',{}).get('last_hand',{}).get('total')
        if state.get('round',{}).get('chips')==before.get('round',{}).get('chips'):actual=0
        h.append(root/'predictions.jsonl',{'transition_id':env.sequence,'origin':'controller',
            'predicted':prediction,'actual':actual,'uncertain':uncertain,'numerical_error':numeric_error,
            'within_one':abs(prediction-actual)<=1 if not uncertain and prediction is not None and actual is not None else None})
    h.append(root/'economy.jsonl',{'sequence':env.sequence,'origin':'controller','method':method,
        'ante':state.get('ante_num'),'round':state.get('round_num'),'phase':state.get('state'),
        'money_before':before.get('money'),'money_after':state.get('money'),
        **{k:state.get(k) for k in ('shop','packs','pack','vouchers','consumables','jokers')}})
    return state


def start(manifest,registry,seed_id,root,protocol_path,reason):
    root=Path(root).resolve()
    if root.exists():raise ValueError('Existing session cannot be restarted or overwritten')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('Controller reason required')
    protocol=json.loads(Path(protocol_path).read_text(encoding='utf8'))
    if protocol['source_hashes']!=source_hashes():raise ValueError('Source differs from protocol')
    if seed_id not in SEED_IDS:raise ValueError('Seed ID not preregistered')
    seed,commitment=h.training_seed(registry,seed_id)
    if {'seed_id':seed_id,'seed_commitment':commitment} not in protocol['jobs']:raise ValueError('Seed commitment mismatch')
    m=verify_engine(manifest,protocol['engine_manifest_sha256'])
    if m['input_hashes']!=protocol['engine_input_hashes']:raise ValueError('Engine differs from protocol')
    root.mkdir(parents=True)
    h.atomic(root/'session.json',{'purpose':'full_controller_train_data','seed_id':seed_id,
        'seed_commitment':commitment,'manifest':str(Path(manifest).resolve()),'manifest_sha256':h.sha(manifest),
        'registry':str(Path(registry).resolve()),'source_hashes':source_hashes(),'automatic_methods':[],
        'protocol_path':str(Path(protocol_path).resolve()),'protocol_sha256':h.sha(protocol_path)})
    advisor,belief,execution=modules()
    with ManualEnvironment(m['port'],m['identity'],root,registry=registry) as env:
        current=env.observe()
        if current['state']!='MENU' and not h.terminal(current):raise ValueError('Unfinished engine cannot be reset')
        claim_seed(registry,protocol_path,seed_id,root)
        start_id=env.sequence+(2 if h.terminal(current) else 1)
        h.append(root/'decisions.jsonl',{'sequence':start_id,'transition_id':start_id,'origin':'controller',
              'method':'start','params':{'reason':reason},'seed_commitment':commitment,'at_utc':time.time()})
        env.reset(seed)
        if (env.state.get('deck'),env.state.get('stake'))!=('BLUE','GOLD'):raise ValueError('Wrong game conditions')
        return snapshot(root,env,belief.Belief(),advisor)


def operate(root,command,*,method=None,params=None,expected_sequence=None,note=None):
    if command not in ('view','act','note'):raise ValueError('Only view, act and note are supported; no automatic gameplay')
    root=Path(root).resolve();config=json.loads((root/'session.json').read_text(encoding='utf8'))
    if source_hashes()!=config['source_hashes']:raise ValueError('Frozen controller tools changed')
    if h.sha(config['protocol_path'])!=config['protocol_sha256']:raise ValueError('Protocol changed')
    m=verify_engine(config['manifest'],config['manifest_sha256']);advisor,belief,execution=modules()
    with ManualEnvironment(m['port'],m['identity'],root,registry=config['registry']) as env:
        env.state,jokers=h.restore_journal(root/'transitions.jsonl')
        memory=belief.Belief();memory.jokers=jokers;env.observe()
        if command!='view' and expected_sequence!=env.sequence:raise ValueError('Stale sequence; do not replay actions')
        if command=='note':
            if not isinstance(note,str) or not note.strip():raise ValueError('Nonempty strategy note required')
            h.append(root/'strategy.jsonl',{'sequence':env.sequence,'origin':'controller','phase':env.state.get('state'),
                      'ante':env.state.get('ante_num'),'money':env.state.get('money'),'note':note,'at_utc':time.time()})
        elif command=='act' and not h.terminal(env.state):
            perform(root,env,memory,execution,advisor,method,params or {})
        return snapshot(root,env,memory,advisor)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare');q.add_argument('--manifest',required=True);q.add_argument('--registry',default=str(h.REGISTRY));q.add_argument('--output',required=True)
    q=sub.add_parser('start');q.add_argument('--manifest',required=True);q.add_argument('--registry',default=str(h.REGISTRY));q.add_argument('--seed-id',type=int,required=True)
    q.add_argument('--session',required=True);q.add_argument('--protocol',required=True);q.add_argument('--reason',required=True)
    for name in ('view','act','note'):
        q=sub.add_parser(name);q.add_argument('--session',required=True)
        if name!='view':q.add_argument('--expected-sequence',type=int,required=True)
        if name=='note':q.add_argument('--text',required=True)
        if name=='act':
            q.add_argument('--method',required=True);g=q.add_mutually_exclusive_group(required=True);g.add_argument('--params');g.add_argument('--params-file')
    a=p.parse_args()
    try:
        if a.command=='prepare':result=prepare(a.manifest,a.registry,a.output)
        elif a.command=='start':result=start(a.manifest,a.registry,a.seed_id,a.session,a.protocol,a.reason)
        else:
            params=json.loads(Path(a.params_file).read_text(encoding='utf-8-sig') if a.params_file else a.params) if a.command=='act' else None
            result=operate(a.session,a.command,method=getattr(a,'method',None),params=params,expected_sequence=getattr(a,'expected_sequence',None),note=getattr(a,'text',None))
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        root=Path(a.session) if hasattr(a,'session') else None
        if root and root.exists():
            h.append(root/'errors.jsonl',{'type':type(exc).__name__,'command':a.command,'at_utc':time.time()})
            journal=root/'transitions.jsonl'
            if journal.exists():
                rows=[json.loads(line) for line in journal.read_text(encoding='utf8').splitlines()]
                if rows and rows[-1].get('event')=='intent':h.atomic(root/'result.json',{'purpose':'full_controller_train_data','status':'error','terminal':False,'outcome_unknown':True,'strategy_winrate_eligible':False})
        print(json.dumps({'error':type(exc).__name__,'message':'Operation stopped; preserve pending journal and do not retry blindly.'}))
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())

