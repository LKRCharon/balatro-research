"""Independent read-only audit of the fixed eight-episode TRAIN comparison."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'headless'))
import combat_compare as runner
import protocol as registry
from audit_formal_result import public_check


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding='utf8').splitlines() if x.strip()]


def function_ast(path,name):
    tree=ast.parse(path.read_text(encoding='utf8'))
    return ast.dump(next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name),include_attributes=False)


def audit(plan_path):
    protocol=runner.read_plan(plan_path);runner.check_frozen(protocol)
    private=Path(protocol['private_output']);public=Path(protocol['protocol_path']).parent
    summary=json.loads((public/'summary.json').read_text(encoding='utf8'))
    expected={(seed,policy) for seed in (16,17,18,19) for policy in ('route_v3','route_v4')}
    assert {(j['seed_id'],j['policy']) for j in protocol['jobs']}==expected
    assert len(protocol['jobs'])==summary['planned']==summary['completed']==8
    assert not summary['not_run']
    jobs={j['id']:j for j in protocol['jobs']}
    results={r['job_id']:r for r in summary['results']}
    assert len(results)==8 and results.keys()==jobs.keys()
    scheduler=lines(private/'scheduler.jsonl')
    assert Counter(x['job_id'] for x in scheduler if x['event']=='claimed')==Counter(jobs.keys())
    assert Counter(x['result']['job_id'] for x in scheduler if x['event']=='completed')==Counter(jobs.keys())
    action_count=0;true_terminals=0
    for job_id,result in results.items():
        root=private/job_id;job=jobs[job_id]
        assert json.loads((root/'result.json').read_text(encoding='utf8'))==result
        assert result['commitment']==job['seed_commitment']
        assert result['seed_id']==job['seed_id'] and result['policy']==job['policy']
        events=lines(root/'transitions.jsonl');decisions=lines(root/'decisions.jsonl')
        intents={e['id']:e for e in events if e['event']=='intent'}
        outcomes={e['id']:e for e in events if e['event']=='result'}
        assert len(intents)+len(outcomes)==len(events) and outcomes.keys()<=intents.keys()
        starts=[x for x in intents.values() if x['method']=='start']
        assert len(starts)==1 and starts[0]['params']['start_commitment']==job['seed_commitment']
        initial=outcomes[starts[0]['id']]['after']
        assert (initial['deck'],initial['stake'])==('BLUE','GOLD')
        actual=Counter(intents[i]['method'] for i in outcomes if intents[i]['method'] not in ('start','menu'))
        assert dict(actual)==result['counts'] and sum(actual.values())==result['actions']
        if result['status'] in ('win','loss'):
            assert intents.keys()==outcomes.keys() and len(decisions)==result['actions']
            final=outcomes[max(outcomes)]['after']
            assert result['terminal'] and (final['state']=='GAME_OVER' or final.get('won') or final.get('overlay')=='win')
            assert (final['state']=='GAME_OVER')==(result['status']=='loss')
            if result['status']=='win':assert final.get('ante_num',0)>=8
            true_terminals+=1
        for row in decisions:
            public_check(row['before'])
            assert row['method'] not in ('start','menu','lab_stop','skip')
        action_count+=result['actions']
    v3=HERE/'policies/route_v3';v4=HERE/'policies/route_v4'
    changed=[p.name for p in v3.iterdir() if p.is_file() and p.read_bytes()!=(v4/p.name).read_bytes()]
    assert changed==['policy.py']
    assert function_ast(v3/'policy.py','_base_action')==function_ast(v4/'policy.py','_base_action')
    assert function_ast(v3/'policy.py','utility')==function_ast(v4/'policy.py','utility')
    old=json.loads((HERE.parent/'results/formal-validation-001/protocol.json').read_text(encoding='utf8'))
    with registry.connect(Path(protocol['registry'])) as con:
        old_manifest=registry.verify_policy(con,old['policy_id'])
        assert con.execute("SELECT COUNT(*) FROM campaigns WHERE partition='test'").fetchone()[0]==0
        for seed in (16,17,18,19):assert con.execute('SELECT partition FROM seeds WHERE id=?',(seed,)).fetchone()[0]=='train'
    backup=json.loads((registry.WORK/'original-save-backup.json').read_text(encoding='utf8'))
    for name,info in backup['files'].items():
        assert hashlib.sha256((Path(backup['source'])/name).read_bytes()).hexdigest()==info['sha256']
    return {'audit':'passed','jobs':8,'true_terminals':true_terminals,'completed_actions':action_count,
            'status_counts':dict(Counter(r['status'] for r in results.values())),
            'each_job_claimed_started_and_completed_once':True,'public_observation_key_audit':'passed',
            'policies_and_runner_frozen':'passed','growth_code_unchanged':True,
            'old_formal_source_files_verified':len(old_manifest['files']),
            'old_formal_context_files_verified':len(old_manifest['context']),
            'original_save_files_unchanged':len(backup['files']),
            'test_campaigns':0,'published_commit':summary['published_commit'],
            'scope':'Structural trace/source audit, not proof of exact mechanics or globally optimal combat.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=audit(args.plan)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))
