"""Paired TRAIN-only combat ablation; preregister before run, never retry episodes."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import importlib
import concurrent.futures
import copy
import os
import queue
import subprocess
import threading
import json
from pathlib import Path
import sqlite3
import sys
import time

from environment import Environment, terminal
from isolation import load

LAB = Path(__file__).resolve().parents[1]
REGISTRY = LAB.parents[1] / 'work/experiments/registry.sqlite'


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def training_seed(registry, seed_id):
    with closing(sqlite3.connect(f'file:{Path(registry).resolve().as_posix()}?mode=ro', uri=True)) as db:
        row = db.execute("SELECT seed,commitment FROM seeds WHERE id=? AND partition='train'", (seed_id,)).fetchone()
    if row is None:
        raise ValueError('Only registered training seeds are accepted')
    if hashlib.sha256(row[0].encode()).hexdigest() != row[1]:
        raise ValueError('Training seed commitment does not match registry value')
    return row


def append(path, value):
    with path.open('a', encoding='utf8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + '\n')
        stream.flush();os.fsync(stream.fileno())


def episode(plan_path, manifest_path, job_id):
    protocol = read_plan(plan_path)
    check_frozen(protocol)
    job = next(x for x in protocol['jobs'] if x['id'] == job_id)
    seed_id, policy_name = job['seed_id'], job['policy']
    max_actions = protocol['max_actions']
    registry = Path(protocol['registry'])
    if policy_name not in ('route_v3', 'route_v4'):
        raise ValueError('Explicit development policy required')
    seed, commitment = training_seed(registry, seed_id)
    manifest = load(manifest_path)
    source = LAB / 'experiments/policies' / policy_name
    frozen = protocol['policy_hashes'][policy_name]
    if commitment != job['seed_commitment']:
        raise ValueError('Training seed binding changed')
    if str(Path(manifest_path).resolve()) not in protocol['instance_manifests']:
        raise ValueError('Unregistered engine instance')
    if manifest['input_hashes'] != protocol['engine_input_hashes']:
        raise ValueError('Wrong engine version')
    if not frozen:
        raise ValueError('Policy source missing')
    for name, expected in manifest['input_hashes'].items():
        if hashlib.sha256((Path(manifest['checkout']) / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Staged engine fingerprint mismatch')
    output = Path(protocol['private_output']) / job_id
    output.mkdir(exist_ok=False)
    sys.path[:0] = [str(source), str(LAB / 'cli')]
    policy = importlib.import_module('policy')
    advisor = importlib.import_module('advisor')
    memory = importlib.import_module('belief').Belief()
    validate = importlib.import_module('execution').validate
    started = time.monotonic()
    counts = Counter()
    errors = []
    checks = []
    solver_counts = Counter()
    s = {}
    status = 'truncated'
    try:
        with Environment(manifest['port'], manifest['identity'], output, registry=registry) as env:
            s = env.reset(seed)
            if (s.get('deck'), s.get('stake')) != ('BLUE', 'GOLD'):
                raise ValueError('Wrong game conditions')
            for index in range(max_actions):
                if terminal(s):
                    break
                context = env.context()
                known = {card.get('key') for area in ('jokers', 'shop', 'pack')
                         for card in s.get(area, {}).get('cards', []) if not card.get('state', {}).get('hidden')}
                context['targets']['targets'] = [t for t in context['targets'].get('targets', []) if t.get('key') in known]
                visible = memory.observe(s, context['collection'], context['targets'])
                before_time = time.monotonic()
                chosen = policy.action(visible)
                combat_module = sys.modules.get('combat')
                diagnostics = copy.deepcopy(getattr(combat_module, 'last_diagnostics', None))
                if diagnostics:
                    solver_counts['decisions_with_diagnostics'] += 1
                if visible.get('state') == 'SELECTING_HAND':
                    solver_counts['combat_decisions'] += 1
                    if diagnostics:
                        for field in ('attempted', 'supported', 'used', 'action_changed'):
                            if diagnostics.get(field):solver_counts[field] += 1
                        if diagnostics.get('fallback_reason'):
                            solver_counts['fallback'] += 1
                            solver_counts['fallback_reason:'+str(diagnostics['fallback_reason'])] += 1
                if not chosen:
                    raise ValueError('Policy returned no action before terminal')
                method, params = chosen
                if method in ('start', 'menu', 'lab_stop', 'skip'):
                    raise ValueError('Disallowed development action')
                validate(s, method, params)
                predicted = advisor.score(visible, params['cards'])[0] if method == 'play' else None
                uncertain = advisor.uncertain(visible) if method == 'play' else None
                append(output / 'decisions.jsonl', {'action': index + 1, 'before': visible,
                       'method': method, 'params': params, 'predicted': predicted,
                       'uncertain': uncertain, 'solver_diagnostics': diagnostics,
                       'decision_seconds': time.monotonic() - before_time})
                before = s
                s = env.step(method, params)
                if method == 'select':
                    append(output/'blind_entries.jsonl', {'action':index+1,'before':before,'after':s})
                counts[method] += 1
                if method == 'play' and not uncertain:
                    actual = s.get('round', {}).get('last_hand', {}).get('total')
                    if s.get('round', {}).get('chips') == before.get('round', {}).get('chips'):
                        actual = 0
                    if actual is not None:
                        checks.append({'action': index + 1, 'predicted': predicted, 'actual': actual,
                                       'within_one': abs(predicted - actual) <= 1})
                (output / 'progress.json').write_text(json.dumps({'action': index + 1,
                    'ante': s.get('ante_num'), 'phase': s.get('state'), 'seconds': time.monotonic() - started}), encoding='utf8')
            if terminal(s):
                status = 'loss' if s.get('state') == 'GAME_OVER' else 'win' if s.get('ante_num', 0) >= 8 else 'error'
                if status == 'error':
                    errors.append({'type': 'InvalidTerminal', 'message': 'Early win flag'})
    except Exception as exc:
        status = 'error'
        errors.append({'type': type(exc).__name__, 'message': str(exc).replace(seed, '[private seed]')})
    if hashes(source) != frozen:
        status = 'error'
        errors.append({'type': 'IntegrityError', 'message': 'Policy source changed during run'})
    try:
        check_frozen(protocol)
    except Exception as exc:
        status='error'; errors.append({'type':'IntegrityError','message':str(exc)})
    result = {'job_id': job_id, 'purpose': 'paired_combat_ablation_train_only', 'strategy_winrate_eligible': False,
              'seed_id': seed_id, 'commitment': commitment, 'policy': policy_name,
              'policy_digest': digest(frozen), 'engine_digest': digest(manifest['input_hashes']),
              'status': status, 'terminal': terminal(s), 'ante': s.get('ante_num'),
              'actions': sum(counts.values()), 'counts': dict(counts), 'errors': errors,
              'solver_counts':dict(solver_counts),
              'seconds': time.monotonic() - started, 'prediction_checks': len(checks),
              'prediction_mismatches': [x for x in checks if not x['within_one']]}
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    return result



def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def dependency_hashes():
    paths = [Path(__file__).resolve(), *[LAB/'headless'/name for name in
             ('environment.py','isolation.py','transport.py')]]
    paths += sorted((LAB/'cli').glob('*.py'))
    return {p.relative_to(LAB).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def check_frozen(protocol):
    if dependency_hashes()!=protocol['dependency_hashes']:
        raise ValueError('Runner, adapter or CLI dependency changed after preregistration')
    for name, frozen in protocol['policy_hashes'].items():
        if hashes(LAB/'experiments/policies'/name)!=frozen:
            raise ValueError('Policy changed after preregistration: '+name)


def read_plan(plan_path):
    plan=json.loads(Path(plan_path).read_text(encoding='utf8'))
    protocol=json.loads(Path(plan['protocol_path']).read_text(encoding='utf8'))
    if digest(plan)!=protocol['private_plan_commitment']:
        raise ValueError('Private execution plan changed after preregistration')
    return dict(protocol, **plan)


def prepare(manifest_paths, output, registry=REGISTRY, max_actions=800):
    if max_actions!=800:raise ValueError('This preregistered comparison uses exactly 800 actions maximum')
    manifests=[load(p) for p in manifest_paths]
    if len(manifests)!=4 or len({m['port'] for m in manifests})!=4 or len({m['identity'] for m in manifests})!=4:
        raise ValueError('Four distinct isolated engines required')
    engine=manifests[0]['input_hashes']
    for m in manifests:
        if m['input_hashes']!=engine or m.get('readiness_patch',{}).get('version')!=3:
            raise ValueError('Identical readiness v3 engines required')
        for name, expected in engine.items():
            if hashlib.sha256((Path(m['checkout'])/name).read_bytes()).hexdigest()!=expected:
                raise ValueError('Staged engine fingerprint mismatch')
    policies={name:hashes(LAB/'experiments/policies'/name) for name in ('route_v3','route_v4')}
    if any(not files for files in policies.values()):raise ValueError('Both policy versions required')
    jobs=[]
    for seed_id in (16,17,18,19):
        _,commitment=training_seed(registry,seed_id)
        for policy in policies:
            jobs.append({'id':f'train-{seed_id}-{policy}','seed_id':seed_id,
                         'seed_commitment':commitment,'policy':policy})
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    private=LAB.parents[1]/'work/experiments'/output.name
    private.mkdir(parents=True,exist_ok=False)
    plan={'protocol_path':str(output/'protocol.json'),'registry':str(Path(registry).resolve()),
          'instance_manifests':[str(Path(p).resolve()) for p in manifest_paths],
          'private_output':str(private)}
    protocol={'schema':1,'purpose':'paired_combat_ablation_train_only','partition':'train',
        'fresh_validation':False,'strategy_winrate_eligible':False,
        'hypothesis':'Does replacing combat choices while retaining route_v3 growth decisions improve survival?',
        'conditions':{'deck':'BLUE','stake':'GOLD','max_ante_for_win':8,'seed_hidden_from_policy':True,
                      'restart_allowed':False,'mutation_retry_allowed':False},
        'jobs':jobs,'policy_hashes':policies,'dependency_hashes':dependency_hashes(),
        'engine_input_hashes':engine,'engine_digest':digest(engine),
        'instance_manifest_commitments':[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in manifest_paths],
        'max_actions':max_actions,'workers':4,'private_plan_commitment':digest(plan),
        'analysis':['paired survival/ante differences','technical error counts separate from losses',
                    'score prediction mismatches','hands, discards and economy traces'],
        'limitations':['four reused TRAIN seeds; development evidence only',
                      'no causal conclusion about all strategic weaknesses from this sample']}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf8')
    plan_path=private/'plan.json';plan_path.write_text(json.dumps(plan,indent=2),encoding='utf8')
    return {'protocol':str(output/'protocol.json'),'plan':str(plan_path),'jobs':len(jobs)}


def execute_child(plan_path, manifest, job_id, private):
    output=Path(private)/f'{job_id}.process.log'
    with output.open('x',encoding='utf8') as stream:
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'episode',
               '--plan',str(plan_path),'--manifest',str(manifest),'--job',job_id],
               stdout=stream,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONIOENCODING='utf-8'))
    result_path=Path(private)/job_id/'result.json'
    if not result_path.exists():
        return {'job_id':job_id,'status':'error','terminal':False,'actions':0,
                'errors':[{'type':'ChildFailure','message':f'Episode process exit {child.returncode} without durable result'}]}
    result=json.loads(result_path.read_text(encoding='utf8'))
    if child.returncode and result.get('status') not in ('error','truncated'):
        result['status']='error';result.setdefault('errors',[]).append({'type':'ChildExit','message':str(child.returncode)})
    return result


def schedule(protocol, launch, record):
    """No resubmission: failed or nonterminal episodes retire their worker."""
    waiting=queue.Queue()
    for job in protocol['jobs']:waiting.put(job)
    results=[];mutex=threading.Lock()
    def worker(index,manifest):
        while True:
            try:job=waiting.get_nowait()
            except queue.Empty:return
            with mutex:record({'event':'claimed','worker':index,'job_id':job['id']})
            try:result=launch(manifest,job['id'])
            except Exception as exc:
                result={'job_id':job['id'],'status':'error','terminal':False,'actions':0,
                        'errors':[{'type':type(exc).__name__,'message':'Episode launcher failed; private process log retained'}]}
            with mutex:
                results.append(result)
                record({'event':'completed','worker':index,'result':result})
            waiting.task_done()
            if result['status'] not in ('win','loss') or not result.get('terminal'):return
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(protocol['instance_manifests'])) as pool:
        tasks=[pool.submit(worker,i,m) for i,m in enumerate(protocol['instance_manifests'])]
        for task in tasks:task.result()
    return results,list(waiting.queue)


def campaign(plan_path, published_commit):
    if len(published_commit)!=40 or any(c not in '0123456789abcdef' for c in published_commit):
        raise ValueError('Record full published preregistration commit before execution')
    protocol=read_plan(plan_path);check_frozen(protocol)
    for path, expected in zip(protocol['instance_manifests'],protocol['instance_manifest_commitments']):
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:raise ValueError('Instance manifest changed')
    private=Path(protocol['private_output']);output=Path(protocol['protocol_path']).parent
    with (private/'started.json').open('x',encoding='utf8') as stream:
        json.dump({'published_commit':published_commit,'protocol_sha256':hashlib.sha256(Path(protocol['protocol_path']).read_bytes()).hexdigest()},stream)
    started=time.monotonic()
    def record(value):append(private/'scheduler.jsonl',value)
    results,not_run=schedule(protocol,lambda m,j:execute_child(plan_path,m,j,private),record)
    by_job={r['job_id']:r for r in results}
    pairs=[]
    for seed in (16,17,18,19):
        pair={'seed_id':seed}
        for name in ('route_v3','route_v4'):
            r=by_job.get(f'train-{seed}-{name}')
            pair[name]={k:r.get(k) for k in ('status','ante','actions')} if r else {'status':'not_run'}
        pairs.append(pair)
    summary={'purpose':protocol['purpose'],'strategy_winrate_eligible':False,'published_commit':published_commit,
        'seconds':time.monotonic()-started,'planned':len(protocol['jobs']),'completed':len(results),
        'status_counts':dict(Counter(r['status'] for r in results)),'pairs':pairs,
        'not_run':[j['id'] for j in not_run],'results':results}
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare');q.add_argument('--manifests',nargs=4,required=True);q.add_argument('--output',required=True)
    q.add_argument('--registry',default=str(REGISTRY))
    q=sub.add_parser('run');q.add_argument('--plan',required=True);q.add_argument('--published-commit',required=True)
    q=sub.add_parser('episode');q.add_argument('--plan',required=True);q.add_argument('--manifest',required=True);q.add_argument('--job',required=True)
    args=p.parse_args()
    if args.command=='prepare':result=prepare(args.manifests,args.output,args.registry)
    elif args.command=='run':result=campaign(args.plan,args.published_commit)
    else:result=episode(args.plan,args.manifest,args.job)
    print(json.dumps(result,ensure_ascii=False))
    if args.command=='episode':raise SystemExit(0 if result['status'] in ('win','loss') else 1)
