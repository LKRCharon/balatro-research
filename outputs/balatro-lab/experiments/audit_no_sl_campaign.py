"""Audit one-attempt TRAIN replay/new-seed research, without touching an engine.

Evidence establishes recorded no-restart provenance, not independent observation
of every operating-system action. Hindsight replays never estimate fresh winrate.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'headless'))
import protocol as registry
from audit_formal_result import public_check
from environment import canonical_state
from reconcile_rejected_pack import digest as evidence_digest,validate_rejection


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def lines(path):return [json.loads(x) for x in Path(path).read_text(encoding='utf8').splitlines() if x.strip()]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

REPLAY_IDS={32,33,34,36,37,38,40,41}
NEW_IDS={42,43,44,45,46}


def validate_jobs(spec):
    jobs=spec['jobs'];expected={j['seed_id']:j['seed_commitment'] for j in jobs}
    assert len(jobs)==len(expected)==13 and set(expected)==REPLAY_IDS|NEW_IDS
    assert spec['partition']=='train' and spec['strategy_winrate_eligible'] is False
    assert spec['automatic_gameplay'] is True and set(spec['automatic_methods'])=={'play','discard','rearrange'}
    assert spec['conditions']['no_restart'] is True and spec['conditions']['no_mutation_retry'] is True
    for j in jobs:
        assert j['cohort']==('hindsight_replay' if j['seed_id'] in REPLAY_IDS else 'new_train')
    return expected


def validate_action_boundaries(intents,decisions,automatic_methods):
    """No gameplay reset and no strategic move delegated to the combat solver."""
    starts=[e for e in intents.values() if e['method']=='start']
    assert len(starts)==1
    for e in intents.values():
        assert e['method'] not in ('load','save','restart','reset','load_run','load_state')
        if e['method']=='menu':
            assert e['id']<starts[0]['id']
            before=e['before']
            assert before.get('state')=='GAME_OVER' or before.get('won') or before.get('overlay')=='win'
    for d in decisions:
        assert d['origin'] in ('controller','script') and d['method']==intents[d['sequence']]['method']
        if d['origin']=='script':
            assert d['method'] in automatic_methods and d['before']['state']=='SELECTING_HAND'


def check_hidden_stubs(state):
    public_check(state)
    count=0
    for area in ('hand','jokers','consumables','shop','vouchers','packs','pack'):
        for card in state.get(area,{}).get('cards',[]):
            if card.get('state',{}).get('hidden'):
                assert card.get('key')=='hidden' and not card.get('value') and not card.get('modifier')
                count+=1
    return count


def capture_baseline(output):
    output=Path(output)
    if output.exists():raise ValueError('Never overwrite an existing audit baseline')
    historical=read(registry.WORK/'original-save-backup.json');save=Path(historical['source'])
    current={f.relative_to(save).as_posix():{'sha256':sha(f),'bytes':f.stat().st_size} for f in save.rglob('*') if f.is_file()}
    assert len(current)==4 and all(current.get(k,{}).get('sha256')==v['sha256'] for k,v in historical['files'].items())
    prior_path=HERE.parent/'results/manual-ten-002/protocol.json';prior=read(prior_path)
    for name,value in prior['source_hashes'].items():assert sha(HERE.parent/name)==value
    prior_results={}
    for seed_id in REPLAY_IDS:
        path=registry.WORK/f'experiments/manual-ten-002/train-{seed_id}/result.json'
        assert read(path)['status']=='loss' and read(path)['terminal']
        prior_results[str(seed_id)]={'path':str(path.resolve()),'sha256':sha(path)}
    for path in registry.WORK.rglob('session.json'):
        assert read(path).get('seed_id') not in NEW_IDS, 'New TRAIN ID already has a session'
    with registry.connect(registry.DEFAULT_DB) as con:
        rows=[dict(r) for r in con.execute('SELECT id,partition,commitment,already_seen FROM seeds WHERE id>=32 AND id<=46 ORDER BY id')]
        for row in rows:
            assert row['partition']=='train'
            if row['id'] in NEW_IDS:
                assert row['already_seen']==0 and con.execute('SELECT COUNT(*) FROM jobs WHERE seed_id=?',(row['id'],)).fetchone()[0]==0
        partitions=[tuple(r) for r in con.execute('SELECT id,partition,commitment FROM seeds ORDER BY id')]
        tests=con.execute("SELECT COUNT(*) FROM campaigns WHERE partition='test'").fetchone()[0];assert tests==0
        old=read(HERE.parent/'results/formal-validation-001/protocol.json');manifest=registry.verify_policy(con,old['policy_id'])
    result={'captured_utc':datetime.now(timezone.utc).isoformat(),'registered':rows,
        'current_save_hashes':current,'partition_commitment':hashlib.sha256(json.dumps(partitions,separators=(',',':')).encode()).hexdigest(),
        'test_campaigns':tests,'prior_manual_protocol':str(prior_path),'prior_manual_protocol_sha256':sha(prior_path),
        'prior_manual_source_hashes':prior['source_hashes'],'prior_loss_results':prior_results,
        'old_formal_source_files':len(manifest['files']),'old_formal_context_files':len(manifest['context']),
        'new_train_ids':sorted(NEW_IDS),'hindsight_replay_ids':sorted(REPLAY_IDS)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2)
    return {'baseline':str(output),'original_save_files':len(current),'new_train_ids':sorted(NEW_IDS),'raw_seeds_disclosed':False}


def audit(protocol_path,sessions,baseline_path,complete=True):
    spec=read(protocol_path);baseline=read(baseline_path)
    expected=validate_jobs(spec)
    registered={row['id']:row for row in baseline['registered']}
    for seed_id,commitment in expected.items():assert registered[seed_id]['commitment']==commitment and registered[seed_id]['partition']=='train'
    assert sha(baseline['prior_manual_protocol'])==baseline['prior_manual_protocol_sha256']
    for name,value in baseline['prior_manual_source_hashes'].items():assert sha(HERE.parent/name)==value
    for row in baseline['prior_loss_results'].values():assert sha(row['path'])==row['sha256']
    for name,digest in spec['source_hashes'].items():assert sha(HERE.parent/name)==digest
    configs=list(Path(sessions).glob('*/session.json'))
    assert len({read(p)['seed_id'] for p in configs})==len(configs)
    completed=[];incomplete=[]
    for config_path in configs:
        root=config_path.parent;config=read(config_path);seed_id=config['seed_id']
        assert seed_id in expected and config['seed_commitment']==expected[seed_id]
        assert config['automatic_methods']==spec['automatic_methods']
        assert config['cohort']==('hindsight_replay' if seed_id in REPLAY_IDS else 'new_train')
        assert config['source_hashes']==spec['source_hashes']
        assert config['protocol_sha256']==sha(protocol_path)
        claim_path=Path(config['registry']).resolve().parent/'manual-allocation-locks'/sha(protocol_path)/f'{seed_id}.json'
        claim=read(claim_path)
        assert claim['seed_id']==seed_id and Path(claim['session']).resolve()==root.resolve()
        assert sha(config['manifest'])==config['manifest_sha256']==spec['engine_manifest_sha256']
        engine=read(config['manifest']);assert engine['input_hashes']==spec['engine_input_hashes']
        for relative,digest in engine['input_hashes'].items():assert sha(Path(engine['checkout'])/relative)==digest
        if not (root/'result.json').exists():incomplete.append(seed_id);continue
        result=read(root/'result.json')
        assert result['status'] in ('win','loss','error') and result['strategy_winrate_eligible'] is False
        decisions=lines(root/'decisions.jsonl');events=lines(root/'transitions.jsonl')
        hidden_stubs=sum(check_hidden_stubs(e.get('before',e.get('after',{}))) for e in events)
        predictions=lines(root/'predictions.jsonl') if (root/'predictions.jsonl').exists() else []
        intents={e['id']:e for e in events if e['event']=='intent'}
        outcomes={e['id']:e for e in events if e['event']=='result'}
        rejections={e['id']:e for e in events if e['event']=='rejection_reconciliation'}
        assert len(intents)+len(outcomes)+len(rejections)==len(events) and outcomes.keys()<=intents.keys()
        assert rejections.keys()<=outcomes.keys()
        for ident,proof in rejections.items():
            intent=intents[ident];resolution=outcomes[ident]
            validate_rejection(intent,proof['explicit_rpc_rejection'])
            assert proof['original_intent_sha256']==evidence_digest(intent)
            assert proof['before_public_sha256']==evidence_digest(canonical_state(intent['before']))
            assert proof['after_public_sha256']==evidence_digest(canonical_state(resolution['after']))==proof['before_public_sha256']
            assert proof['engine_manifest_sha256']==config['manifest_sha256'] and proof['method_resent'] is False
            for record in (proof,resolution):
                assert record['outcome']=='rejected_no_mutation' and record['accepted'] is False and record['applied'] is False
            assert resolution['reconciliation_record']==f'rejection-reconciliation-{ident}.json'
            assert read(root/resolution['reconciliation_record'])==proof
        assert all(i in rejections for i,e in outcomes.items() if e.get('accepted') is False or e.get('applied') is False or e.get('outcome')=='rejected_no_mutation')
        assert [e['id'] for e in events if e['event']=='intent']==list(range(1,len(intents)+1))
        starts=[e for e in intents.values() if e['method']=='start']
        assert all(e['method'] not in ('load','save','restart','reset','load_run','load_state') for e in intents.values())
        assert len(starts)==1 and starts[0]['params']['start_commitment']==expected[seed_id]
        initial=outcomes[starts[0]['id']]['after'];assert(initial['deck'],initial['stake'])==('BLUE','GOLD')
        menus=[e for e in intents.values() if e['method']=='menu']
        for menu in menus:
            assert menu['id']<starts[0]['id']
            assert menu['before'].get('state')=='GAME_OVER' or menu['before'].get('won') or menu['before'].get('overlay')=='win'
        assert len(menus)<=1
        assert len({d['sequence'] for d in decisions})==len(decisions)
        validate_action_boundaries(intents,decisions,spec['automatic_methods'])
        for d in decisions:
            assert d['origin'] in ('controller','script') and d['method']==intents[d['sequence']]['method']
            if d['origin']=='script':
                assert d['method'] in spec['automatic_methods'] and d['before']['state']=='SELECTING_HAND'
            if 'before' in d:public_check(d['before'])
        assert {d['sequence'] for d in decisions}==set(intents)-{m['id'] for m in menus}
        decision_by_id={d['sequence']:d for d in decisions}
        script_decisions=[d for d in decisions if d['origin']=='script']
        solver=lines(root/'solver.jsonl') if (root/'solver.jsonl').exists() else []
        assert len({row['transition_id'] for row in solver})==len(solver)
        assert {row['transition_id'] for row in solver}=={d['sequence'] for d in script_decisions}
        for row in solver:
            d=decision_by_id[row['transition_id']]
            assert row['method']==d['method'] and row['params']==d['params']
        final=outcomes[max(outcomes)]['after']
        cleanup=lines(root/'terminal-menu.jsonl') if (root/'terminal-menu.jsonl').exists() else []
        if cleanup:
            assert len(cleanup)==2 and [e['event'] for e in cleanup]==['intent','result']
            request,response=cleanup
            assert request['purpose']=='post_terminal_cleanup_not_gameplay'
            assert request['terminal_game_journal_sha256']==sha(root/'transitions.jsonl')
            assert request['before_public_sha256']==evidence_digest(canonical_state(final))
            assert request['engine_manifest_sha256']==config['manifest_sha256']
            assert all(e['method']=='menu' and e['controller_origin']=='controller' for e in cleanup)
            assert response['state']=='MENU' and response['terminal_episode_preserved'] and response['identity_verified'] and response['silent_and_headless_verified']
        if result['status'] in ('win','loss'):
            assert intents.keys()==outcomes.keys() and result['terminal']
            assert (final.get('state')=='GAME_OVER')==(result['status']=='loss')
            if result['status']=='win':assert (final.get('won') or final.get('overlay')=='win') and final.get('ante_num',0)>=8
            assert result['decision_count']==len(decisions)
            assert result['transition_count']==max(intents)==len(decisions)+len(menus)
            assert result['controller_decisions']==len(decisions)-len(script_decisions) and result['script_decisions']==len(script_decisions)
            assert result['cohort']==config['cohort']
        for prediction in predictions:
            ident=prediction['transition_id'];assert intents[ident]['method']=='play' and prediction['origin']==decision_by_id[ident]['origin']
            before=intents[ident]['before'];after=outcomes[ident]['after']
            actual=after.get('round',{}).get('last_hand',{}).get('total')
            if before.get('round',{}).get('chips')==after.get('round',{}).get('chips'):actual=0
            assert prediction['actual']==actual
            check=abs(prediction['predicted']-actual)<=1 if not prediction['uncertain'] and prediction['predicted'] is not None and actual is not None else None
            assert prediction['within_one']==check
        completed.append({'seed_id':seed_id,'status':result['status'],'terminal':result.get('terminal',False),
            'cohort':config['cohort'],'ante':result.get('ante'),'controller_decisions':len(decisions)-len(script_decisions),'script_decisions':len(script_decisions),
            'gameplay_actions':sum(e['method'] not in ('menu','start') for i,e in intents.items() if i in outcomes and i not in rejections),
            'rejected_no_mutation_attempts':len(rejections),
            'post_terminal_cleanup_actions':len(cleanup)//2,
            'pre_start_terminal_menu_actions':len(menus),'transition_count':len(intents),
            'hidden_stub_occurrences':hidden_stubs,
            'starts':len(starts),'pending_mutations':len(intents)-len(outcomes),
            'error_log_entries':len(lines(root/'errors.jsonl')) if (root/'errors.jsonl').exists() else 0,
            'prediction_checks':sum(p.get('within_one') is not None for p in predictions),
            'prediction_mismatches':sum(p.get('within_one') is False for p in predictions),
            'predicted_plays_recorded':len(predictions),
            'uncertain_or_unavailable_predictions':sum(p.get('within_one') is None for p in predictions),
            'numerical_adviser_errors':sum(bool(p.get('numerical_error')) for p in predictions),
            'evidence_sha256':{name:sha(root/name) for name in ('session.json','decisions.jsonl','transitions.jsonl','result.json')}})
    if complete:assert len(completed)==13 and not incomplete
    historical=read(registry.WORK/'original-save-backup.json');save=Path(historical['source'])
    current={f.relative_to(save).as_posix():{'sha256':sha(f),'bytes':f.stat().st_size} for f in save.rglob('*') if f.is_file()}
    assert current==baseline['current_save_hashes']
    with registry.connect(registry.DEFAULT_DB) as con:
        partitions=[tuple(r) for r in con.execute('SELECT id,partition,commitment FROM seeds ORDER BY id')]
        assert hashlib.sha256(json.dumps(partitions,separators=(',',':')).encode()).hexdigest()==baseline['partition_commitment']
        assert con.execute("SELECT COUNT(*) FROM campaigns WHERE partition='test'").fetchone()[0]==baseline['test_campaigns']==0
        old=read(HERE.parent/'results/formal-validation-001/protocol.json');old_manifest=registry.verify_policy(con,old['policy_id'])
    cohorts={label:{'assigned':len(ids),'completed':sum(r['seed_id'] in ids for r in completed),
        'status_counts':dict(Counter(r['status'] for r in completed if r['seed_id'] in ids))}
        for label,ids in [('hindsight_replay',REPLAY_IDS),('new_train',NEW_IDS)]}
    return {'audit':'passed','complete':len(completed)==13,'assigned':13,'completed':len(completed),'cohorts':cohorts,
            'true_terminals':sum(r['terminal'] for r in completed),'incomplete_seed_ids':incomplete,
            'not_started_seed_ids':sorted(set(expected)-{read(p)['seed_id'] for p in configs}),
            'status_counts':dict(Counter(r['status'] for r in completed)),
            'controller_decisions':sum(r['controller_decisions'] for r in completed),'script_decisions':sum(r['script_decisions'] for r in completed),
            'gameplay_actions':sum(r['gameplay_actions'] for r in completed),
            'rejected_no_mutation_attempts':sum(r['rejected_no_mutation_attempts'] for r in completed),
            'post_terminal_cleanup_actions':sum(r['post_terminal_cleanup_actions'] for r in completed),
            'pre_start_terminal_menu_actions':sum(r['pre_start_terminal_menu_actions'] for r in completed),
            'transition_count':sum(r['transition_count'] for r in completed),
            'hidden_stub_occurrences':sum(r['hidden_stub_occurrences'] for r in completed),
            'hidden_identity_violations':0,
            'prediction_checks':sum(r['prediction_checks'] for r in completed),
            'prediction_mismatches':sum(r['prediction_mismatches'] for r in completed),
            'predicted_plays_recorded':sum(r['predicted_plays_recorded'] for r in completed),
            'uncertain_or_unavailable_predictions':sum(r['uncertain_or_unavailable_predictions'] for r in completed),
            'numerical_adviser_errors':sum(r['numerical_adviser_errors'] for r in completed),
            'error_log_entries':sum(r['error_log_entries'] for r in completed),
            'pending_mutations':sum(r['pending_mutations'] for r in completed),
            'all_completed_actions_have_matched_decisions':True,'script_actions_limited_to_combat':True,'no_duplicate_seed_sessions':True,
            'partition_commitment_unchanged':True,'test_campaigns':0,'original_save_files_unchanged':len(current),
            'historical_save_hashes_still_match':all(current.get(k,{}).get('sha256')==v['sha256'] for k,v in historical['files'].items()),
            'old_formal_source_files_verified':len(old_manifest['files']),'old_formal_context_files_verified':len(old_manifest['context']),
            'sessions':sorted(completed,key=lambda r:r['seed_id']),
            'limitations':[
                'error_log_entries counts only errors.jsonl; local wrapper refusals before journal creation are not comprehensively captured.',
                'Explicit reconciliations retain controller-reported RPC error text and equal public-state hashes; the static early-validation guard supports no mutation, not public equality alone.',
                'Uncertain predictions are excluded from numerical mismatch counts; zero mismatches does not mean complete scoring coverage.'
            ],
            'scope':'One recorded start per campaign seed. Hindsight replays and new TRAIN results reported separately; neither is frozen-policy validation. No hidden-future or raw-seed reads by this auditor.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-baseline',action='store_true')
    parser.add_argument('--protocol');parser.add_argument('--sessions')
    parser.add_argument('--baseline');parser.add_argument('--output',required=True)
    parser.add_argument('--allow-incomplete',action='store_true');args=parser.parse_args()
    if args.capture_baseline:result=capture_baseline(args.output)
    else:
        result=audit(args.protocol,args.sessions,args.baseline,not args.allow_incomplete)
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='sessions'}))
