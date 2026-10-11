"""Read-only evidence audit of ten fully controller-directed TRAIN sessions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'headless'))
import protocol as registry
from audit_formal_result import public_check


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def lines(path):return [json.loads(x) for x in Path(path).read_text(encoding='utf8').splitlines() if x.strip()]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(protocol_path,sessions,baseline_path,complete=True):
    spec=read(protocol_path);baseline=read(baseline_path)
    expected={j['seed_id']:j['seed_commitment'] for j in spec['jobs']}
    assert len(spec['jobs'])==len(expected)==10 and set(expected)==set(range(32,42))
    assert spec['automatic_gameplay'] is False and spec['partition']=='train'
    for name,digest in spec['source_hashes'].items():assert sha(HERE.parent/name)==digest
    configs=list(Path(sessions).glob('*/session.json'))
    assert len({read(p)['seed_id'] for p in configs})==len(configs)
    completed=[];incomplete=[]
    for config_path in configs:
        root=config_path.parent;config=read(config_path);seed_id=config['seed_id']
        assert seed_id in expected and config['seed_commitment']==expected[seed_id]
        assert config['automatic_methods']==[]
        assert config['source_hashes']==spec['source_hashes']
        assert config['protocol_sha256']==sha(protocol_path)
        assert sha(config['manifest'])==config['manifest_sha256']==spec['engine_manifest_sha256']
        engine=read(config['manifest']);assert engine['input_hashes']==spec['engine_input_hashes']
        for relative,digest in engine['input_hashes'].items():assert sha(Path(engine['checkout'])/relative)==digest
        if not (root/'result.json').exists():incomplete.append(seed_id);continue
        result=read(root/'result.json')
        assert result['status'] in ('win','loss','error') and result['strategy_winrate_eligible'] is False
        decisions=lines(root/'decisions.jsonl');events=lines(root/'transitions.jsonl')
        predictions=lines(root/'predictions.jsonl') if (root/'predictions.jsonl').exists() else []
        intents={e['id']:e for e in events if e['event']=='intent'}
        outcomes={e['id']:e for e in events if e['event']=='result'}
        assert len(intents)+len(outcomes)==len(events) and outcomes.keys()<=intents.keys()
        assert all(e.get('controller_origin')=='controller' for e in events)
        starts=[e for e in intents.values() if e['method']=='start']
        assert len(starts)==1 and starts[0]['params']['start_commitment']==expected[seed_id]
        initial=outcomes[starts[0]['id']]['after'];assert(initial['deck'],initial['stake'])==('BLUE','GOLD')
        menus=[e for e in intents.values() if e['method']=='menu']
        for menu in menus:
            assert menu['id']<starts[0]['id']
            assert menu['before'].get('state')=='GAME_OVER' or menu['before'].get('won') or menu['before'].get('overlay')=='win'
        assert len(menus)<=1
        assert len({d['sequence'] for d in decisions})==len(decisions)
        for d in decisions:
            assert d['origin']=='controller' and d['method']==intents[d['sequence']]['method']
            if 'before' in d:public_check(d['before'])
        assert {d['sequence'] for d in decisions}==set(intents)-{m['id'] for m in menus}
        final=outcomes[max(outcomes)]['after']
        if result['status'] in ('win','loss'):
            assert intents.keys()==outcomes.keys() and result['terminal']
            assert (final.get('state')=='GAME_OVER')==(result['status']=='loss')
            if result['status']=='win':assert (final.get('won') or final.get('overlay')=='win') and final.get('ante_num',0)>=8
            assert result['controller_decisions']==result['decision_count']==len(decisions) and result['script_decisions']==0
        for prediction in predictions:
            ident=prediction['transition_id'];assert intents[ident]['method']=='play' and prediction['origin']=='controller'
            before=intents[ident]['before'];after=outcomes[ident]['after']
            actual=after.get('round',{}).get('last_hand',{}).get('total')
            if before.get('round',{}).get('chips')==after.get('round',{}).get('chips'):actual=0
            assert prediction['actual']==actual
        completed.append({'seed_id':seed_id,'status':result['status'],'terminal':result.get('terminal',False),
            'ante':result.get('ante'),'controller_decisions':len(decisions),'script_decisions':0,
            'gameplay_actions':sum(e['method'] not in ('menu','start') for i,e in intents.items() if i in outcomes),
            'starts':len(starts),'pending_mutations':len(intents)-len(outcomes),
            'error_log_entries':len(lines(root/'errors.jsonl')) if (root/'errors.jsonl').exists() else 0,
            'prediction_checks':sum(p.get('within_one') is not None for p in predictions),
            'prediction_mismatches':sum(p.get('within_one') is False for p in predictions),
            'evidence_sha256':{name:sha(root/name) for name in ('session.json','decisions.jsonl','transitions.jsonl','result.json')}})
    if complete:assert len(completed)==10 and not incomplete
    historical=read(registry.WORK/'original-save-backup.json');save=Path(historical['source'])
    current={f.relative_to(save).as_posix():{'sha256':sha(f),'bytes':f.stat().st_size} for f in save.rglob('*') if f.is_file()}
    assert current==baseline['current_save_hashes']
    with registry.connect(registry.DEFAULT_DB) as con:
        partitions=[tuple(r) for r in con.execute('SELECT id,partition,commitment FROM seeds ORDER BY id')]
        assert hashlib.sha256(json.dumps(partitions,separators=(',',':')).encode()).hexdigest()==baseline['partition_commitment']
        assert con.execute("SELECT COUNT(*) FROM campaigns WHERE partition='test'").fetchone()[0]==baseline['test_campaigns']==0
        old=read(HERE.parent/'results/formal-validation-001/protocol.json');old_manifest=registry.verify_policy(con,old['policy_id'])
    return {'audit':'passed','complete':len(completed)==10,'assigned':10,'completed':len(completed),
            'true_terminals':sum(r['terminal'] for r in completed),'incomplete_seed_ids':incomplete,
            'not_started_seed_ids':sorted(set(expected)-{read(p)['seed_id'] for p in configs}),
            'status_counts':dict(Counter(r['status'] for r in completed)),
            'controller_decisions':sum(r['controller_decisions'] for r in completed),'script_decisions':0,
            'gameplay_actions':sum(r['gameplay_actions'] for r in completed),
            'prediction_checks':sum(r['prediction_checks'] for r in completed),
            'prediction_mismatches':sum(r['prediction_mismatches'] for r in completed),
            'all_observed_actions_controller_origin':True,'no_duplicate_seed_sessions':True,
            'partition_commitment_unchanged':True,'test_campaigns':0,'original_save_files_unchanged':len(current),
            'historical_save_hashes_still_match':all(current.get(k,{}).get('sha256')==v['sha256'] for k,v in historical['files'].items()),
            'old_formal_source_files_verified':len(old_manifest['files']),'old_formal_context_files_verified':len(old_manifest['context']),
            'sessions':sorted(completed,key=lambda r:r['seed_id']),
            'scope':'Provenance and consistency audit of controller-directed TRAIN data; not frozen-policy win-rate or global strategic optimality proof.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',required=True);parser.add_argument('--sessions',required=True)
    parser.add_argument('--baseline',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--allow-incomplete',action='store_true');args=parser.parse_args()
    result=audit(args.protocol,args.sessions,args.baseline,not args.allow_incomplete)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='sessions'}))
