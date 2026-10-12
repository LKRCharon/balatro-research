"""TRAIN replay/new cohort: controller strategy, no-SL scripted combat only."""
import argparse
import copy
import importlib
import json
from pathlib import Path
import time
import hybrid_session as h
import manual_session as manual

REPLAYS=(32,33,34,36,37,38,40,41)
NEW=(42,43,44,45,46)


def hashes():
    result=manual.source_hashes()
    for name in ('research_session.py','no_sl_solver.py'):
        result['headless/'+name]=h.sha(h.LAB/'headless'/name)
    result.update({'experiments/policies/route_v4/'+p.name:h.sha(p)
                   for p in (h.LAB/'experiments/policies/route_v4').glob('*.py')})
    return result


def prepare(manifest,registry,output):
    m=manual.verify_engine(manifest)
    jobs=[{'seed_id':i,'seed_commitment':h.training_seed(registry,i)[1],
           'cohort':'hindsight_replay' if i in REPLAYS else 'new_train'} for i in REPLAYS+NEW]
    root=Path(output)
    if root.exists():raise ValueError('Protocol already exists')
    root.mkdir(parents=True)
    protocol={'schema':1,'purpose':'no_sl_controller_strategy_script_combat','partition':'train',
        'strategy_winrate_eligible':False,'jobs':jobs,'source_hashes':hashes(),
        'engine_manifest_sha256':h.sha(manifest),'engine_input_hashes':m['input_hashes'],
        'automatic_gameplay':True,'automatic_methods':['play','discard','rearrange'],
        'conditions':{'deck':'BLUE','stake':'GOLD','no_restart':True,'no_mutation_retry':True,
                      'public_information_only':True},
        'solver_config':{'samples':8,'max_candidates':10,'time_budget':3.0},
        'limitations':['Adaptive TRAIN experiment, not held-out evaluation.',
                      'Replays have prior strategic knowledge; fresh TRAIN separate.',
                      'Local scoring/search is not a global optimality certificate.']}
    h.atomic(root/'protocol.json',protocol)
    return {'jobs':len(jobs),'replays':len(REPLAYS),'new_train':len(NEW)}


def snapshot(root,env,memory,advisor):
    state=h.visible(env,memory) if not h.terminal(env.state) else env.state
    numeric_error=None
    try:scores=manual.numerical_scores(state,advisor)
    except Exception as exc:scores=[];numeric_error=type(exc).__name__
    output={'purpose':'no_sl_controller_strategy_script_combat','strategy_winrate_eligible':False,
        'sequence':env.sequence,'terminal':h.terminal(env.state),'state':manual.compact(state),
        'structural_actions':env.action_space(),'numerical_scores':scores}
    if numeric_error:output['numerical_error']=numeric_error
    h.atomic(root/'observation.json',output)
    if h.terminal(env.state):
        decisions=[json.loads(x) for x in (root/'decisions.jsonl').read_text(encoding='utf8').splitlines()]
        config=json.loads((root/'session.json').read_text(encoding='utf8'))
        h.atomic(root/'result.json',{'purpose':output['purpose'],'cohort':config['cohort'],
            'status':'loss' if env.state.get('state')=='GAME_OVER' else 'win',
            'terminal':True,'ante':env.state.get('ante_num'),'transition_count':env.sequence,
            'controller_decisions':sum(x.get('origin')=='controller' for x in decisions),
            'script_decisions':sum(x.get('origin')=='script' for x in decisions),
            'decision_count':len(decisions),'strategy_winrate_eligible':False})
    return output


def start(manifest,registry,seed_id,root,protocol_path,reason):
    root=Path(root).resolve()
    if root.exists():raise ValueError('Existing session cannot be restarted')
    protocol=json.loads(Path(protocol_path).read_text(encoding='utf8'))
    if protocol['source_hashes']!=hashes():raise ValueError('Source differs from protocol')
    job=next((j for j in protocol['jobs'] if j['seed_id']==seed_id),None)
    if job is None:raise ValueError('Seed not assigned')
    seed,commitment=h.training_seed(registry,seed_id)
    if commitment!=job['seed_commitment']:raise ValueError('Commitment mismatch')
    m=manual.verify_engine(manifest,protocol['engine_manifest_sha256'])
    root.mkdir(parents=True)
    h.atomic(root/'session.json',{'purpose':protocol['purpose'],'cohort':job['cohort'],
        'seed_id':seed_id,'seed_commitment':commitment,'manifest':str(Path(manifest).resolve()),
        'manifest_sha256':h.sha(manifest),'registry':str(Path(registry).resolve()),
        'source_hashes':hashes(),'automatic_methods':protocol['automatic_methods'],
        'protocol_path':str(Path(protocol_path).resolve()),'protocol_sha256':h.sha(protocol_path)})
    advisor,belief,execution=manual.modules()
    with h.Environment(m['port'],m['identity'],root,registry=registry) as env:
        current=env.observe()
        if current['state']!='MENU' and not h.terminal(current):raise ValueError('Unfinished engine')
        manual.claim_seed(registry,protocol_path,seed_id,root)
        h.append(root/'decisions.jsonl',{'sequence':env.sequence+(2 if h.terminal(current) else 1),
            'origin':'controller','method':'start','seed_commitment':commitment,
            'params':{'reason':reason},'at_utc':time.time()})
        env.reset(seed)
        return snapshot(root,env,belief.Belief(),advisor)


def operate(root,command,method=None,params=None,expected_sequence=None,max_actions=100,note=None):
    root=Path(root).resolve();config=json.loads((root/'session.json').read_text(encoding='utf8'))
    if config['source_hashes']!=hashes():raise ValueError('Frozen tools changed')
    if h.sha(config['protocol_path'])!=config['protocol_sha256']:raise ValueError('Protocol changed')
    m=manual.verify_engine(config['manifest'],config['manifest_sha256'])
    protocol=json.loads(Path(config['protocol_path']).read_text(encoding='utf8'))
    advisor,belief,execution=manual.modules()
    with h.Environment(m['port'],m['identity'],root,registry=config['registry']) as env:
        env.state,jokers=h.restore_journal(root/'transitions.jsonl')
        memory=belief.Belief();memory.jokers=jokers;env.observe()
        if command!='view' and expected_sequence!=env.sequence:raise ValueError('Stale sequence')
        if command=='act' and not h.terminal(env.state):
            h.perform(root,env,memory,execution,advisor,method,params,'controller')
        elif command=='note':
            if not note:raise ValueError('Nonempty note required')
            h.append(root/'strategy.jsonl',{'sequence':env.sequence,'origin':'controller',
                'phase':env.state['state'],'ante':env.state.get('ante_num'),'note':note,'at_utc':time.time()})
        elif command=='step':
            if not 1<=max_actions<=100:raise ValueError('Batch must be 1..100')
            solver=importlib.import_module('no_sl_solver')
            for _ in range(max_actions):
                if h.terminal(env.state) or env.state['state']!='SELECTING_HAND':break
                state=h.visible(env,memory)
                choice=solver.choose(state,protocol['solver_config'])
                h.append(root/'solver.jsonl',{'transition_id':env.sequence+1,
                    'diagnostics':choice['diagnostics'],'method':choice['method'],'params':choice['params']})
                method=choice['method'];params=choice['params']
                if method not in h.AUTO_METHODS:raise ValueError('Solver attempted strategy action')
                h.perform(root,env,memory,execution,advisor,method,params,'script')
        elif command not in ('view','act'):raise ValueError('Unknown command')
        return snapshot(root,env,memory,advisor)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','start','view','act','step','note'])
    p.add_argument('--manifest');p.add_argument('--registry',default=str(h.REGISTRY));p.add_argument('--output')
    p.add_argument('--protocol');p.add_argument('--session');p.add_argument('--seed-id',type=int)
    p.add_argument('--reason',default='Controller choice');p.add_argument('--method');p.add_argument('--params',default='{}')
    p.add_argument('--expected-sequence',type=int);p.add_argument('--max-actions',type=int,default=100)
    a=p.parse_args()
    if a.command=='prepare':out=prepare(a.manifest,a.registry,a.output)
    elif a.command=='start':out=start(a.manifest,a.registry,a.seed_id,a.session,a.protocol,a.reason)
    else:out=operate(a.session,a.command,a.method,json.loads(a.params),a.expected_sequence,a.max_actions,a.reason)
    print(json.dumps(out,ensure_ascii=False))
