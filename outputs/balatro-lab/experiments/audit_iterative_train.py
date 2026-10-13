"""Independent read-only audit for iterative_train; never inspect active hands."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from audit_no_sl_campaign import read,lines,sha,check_hidden_stubs,REPLAY_IDS,NEW_IDS
import protocol as registry


LAB=Path(__file__).resolve().parents[1]


def source_path(name):
    path=Path(name)
    if path.is_absolute():return path
    return LAB.parents[1]/path if path.parts[0]=='work' else LAB/path


def audit(batch,manifest,baseline,complete=False,source_archive=None):
    batch=Path(batch);spec=read(batch/'protocol.json');base=read(baseline);engine=read(manifest)
    assert spec['partition']=='train' and spec['strategy_winrate_eligible'] is False
    assert spec['conditions']['no_restart_within_episode'] and spec['conditions']['no_mutation_retry']
    jobs={j['seed_id']:j['seed_commitment'] for j in spec['jobs']}
    assert len(jobs)==len(spec['jobs']) and set(jobs)<=REPLAY_IDS|NEW_IDS
    archived_source_count=0
    for name,digest in spec['source_hashes'].items():
        current_source=source_path(name)
        if current_source.exists() and sha(current_source)==digest:continue
        assert source_archive is not None, 'Current source differs; explicitly select historical source archive'
        assert sha(Path(source_archive)/digest)==digest
        archived_source_count+=1
    assert sha(manifest)==spec['engine_manifest_sha256'] and engine['input_hashes']==spec['engine_input_hashes']
    for name,digest in engine['input_hashes'].items():assert sha(Path(engine['checkout'])/name)==digest
    assert sha(base['prior_manual_protocol'])==base['prior_manual_protocol_sha256']
    for name,digest in base['prior_manual_source_hashes'].items():assert sha(LAB/name)==digest
    current={};historical=read(registry.WORK/'original-save-backup.json');save=Path(historical['source'])
    for f in save.rglob('*'):
        if f.is_file():current[f.relative_to(save).as_posix()]={'sha256':sha(f),'bytes':f.stat().st_size}
    assert current==base['current_save_hashes']
    with registry.connect(registry.DEFAULT_DB) as db:
        for seed_id,commitment in jobs.items():assert tuple(db.execute('SELECT partition,commitment FROM seeds WHERE id=?',(seed_id,)).fetchone())==('train',commitment)
        assert db.execute("SELECT COUNT(*) FROM campaigns WHERE partition='test'").fetchone()[0]==0
        old=read(LAB/'results/formal-validation-001/protocol.json');registry.verify_policy(db,old['policy_id'])
    finished=[];active=[];seen=set()
    for root in sorted(batch.glob('train-*')):
        if not root.is_dir():continue
        config=read(root/'session.json');seed_id=config['seed_id'];assert seed_id in jobs and seed_id not in seen;seen.add(seed_id)
        assert config['seed_commitment']==jobs[seed_id] and config['source_hashes']==spec['source_hashes']
        assert config['solver']==spec['solver'] and config['growth']==spec['growth']
        if not (root/'result.json').exists():active.append(seed_id);continue
        result=read(root/'result.json');assert result['status'] in ('win','loss','error','truncated')
        events=lines(root/'transitions.jsonl') if (root/'transitions.jsonl').exists() else []
        decisions=lines(root/'decisions.jsonl') if (root/'decisions.jsonl').exists() else []
        intents={r['id']:r for r in events if r['event']=='intent'};outcomes={r['id']:r for r in events if r['event']=='result'}
        assert len(intents)+len(outcomes)==len(events) and outcomes.keys()<=intents.keys()
        assert [r['id'] for r in events if r['event']=='intent']==list(range(1,len(intents)+1))
        starts=[r for r in intents.values() if r['method']=='start'];assert len(starts)<=1
        menus=[r for r in intents.values() if r['method']=='menu']
        for menu in menus:
            assert starts and menu['id']<starts[0]['id'] and (menu['before'].get('state')=='GAME_OVER' or menu['before'].get('won') or menu['before'].get('overlay')=='win')
        assert len(menus)<=1
        assert all(r['method'] not in ('load','save','load_state','restart','reset','skip') for r in intents.values())
        if starts:
            assert starts[0]['params']['start_commitment']==jobs[seed_id]
            claim=read(registry.DEFAULT_DB.parent/'manual-allocation-locks'/sha(batch/'protocol.json')/f'{seed_id}.json')
            assert Path(claim['session']).resolve()==root.resolve() and claim['seed_id']==seed_id
        dmap={d['sequence']:d for d in decisions};assert len(dmap)==len(decisions)
        for seq,d in dmap.items():
            assert d['origin']=='script' and d['method']==intents[seq]['method']
            if 'before' in d:check_hidden_stubs(d['before'])
        if result['status'] in ('win','loss','truncated'):
            assert len(starts)==1 and intents.keys()==outcomes.keys()
            assert set(dmap)==set(intents)-{r['id'] for r in menus}
            initial=outcomes[starts[0]['id']]['after'];assert (initial['deck'],initial['stake'])==('BLUE','GOLD')
            state=outcomes[max(outcomes)]['after'];terminal=state.get('state')=='GAME_OVER' or bool(state.get('won')) or state.get('overlay')=='win'
            assert result['terminal']==terminal
            assert (result['status']=='truncated')==(not terminal)
            if result['status']=='loss':assert state['state']=='GAME_OVER'
            if result['status']=='win':assert state.get('won') or state.get('overlay')=='win'
            counts=Counter(r['method'] for seq,r in intents.items() if r['method'] not in ('start','menu'))
            assert result['counts']==dict(counts) and result['actions']==sum(counts.values())
        predictions=lines(root/'predictions.jsonl') if (root/'predictions.jsonl').exists() else []
        assert len({p['transition_id'] for p in predictions})==len(predictions)
        for p in predictions:
            seq=p['transition_id'];assert intents[seq]['method']=='play' and p['origin']=='script'
            before=intents[seq]['before'];after=outcomes[seq]['after'];actual=after['round']['last_hand']['total']
            if before['round']['chips']==after['round']['chips']:actual=0
            assert p['actual']==actual
            assert p['within_one']==(abs(p['predicted']-actual)<=1 if not p['uncertain'] and actual is not None else None)
        if result['status'] in ('win','loss','truncated'):assert {p['transition_id'] for p in predictions}=={i for i,r in intents.items() if r['method']=='play'}
        solver=lines(root/'solver.jsonl') if (root/'solver.jsonl').exists() else []
        for row in solver:
            seq=row['transition_id']
            if seq in dmap:assert row['method']==dmap[seq]['method'] and row['params']==dmap[seq]['params']
            else:assert result['status']=='error'
        finished.append({'seed_id':seed_id,'status':result['status'],'terminal':result.get('terminal',False),
            'starts':len(starts),'decisions':len(decisions),'prestart_menus':len(menus),
            'gameplay_actions':sum(r['method'] not in ('menu','start') for i,r in intents.items() if i in outcomes),
            'pending_intents':len(intents)-len(outcomes),'predictions':len(predictions),
            'checkable':sum(p['within_one'] is not None for p in predictions),'mismatches':sum(p['within_one'] is False for p in predictions),
            'uncertain':sum(p['within_one'] is None for p in predictions),'ante':result.get('ante'),
            'old_no_sl_003_status':read(registry.WORK/f'experiments/no-sl-003/train-{seed_id}/result.json')['status']})
    if complete:assert len(finished)==len(jobs) and not active
    summary=read(batch/'summary.json') if (batch/'summary.json').exists() else None
    if summary:
        assert summary['completed']==len(summary['results']) and summary['wins']==sum(r['status']=='win' for r in summary['results'])
        for row in summary['results']:assert row==read(batch/f"train-{row['seed_id']}"/'result.json')
    return {'audit':'passed','complete':len(finished)==len(jobs),'assigned':len(jobs),'completed':len(finished),
        'active_uninspected':active,'not_started':sorted(set(jobs)-seen),'status_counts':dict(Counter(r['status'] for r in finished)),
        'totals':{key:sum(r[key] for r in finished) for key in ('decisions','prestart_menus','gameplay_actions','pending_intents','predictions','checkable','mismatches','uncertain')},
        'original_saves_unchanged':len(current),'test_campaigns':0,'frozen_hashes_verified':True,'sessions':finished,
        'historical_archived_sources_verified':archived_source_count,'current_sources_all_match':archived_source_count==0,
        'limitations':['Only completed/error/truncated episodes are inspected; active gameplay is not read.',
            'Engine imports or manifest failures before the try block can leave a session directory without result.json.',
            'Full 13-seed completion requires all results; batch summary may omit an error episode because main aborts.',
            'Source bytes are verified but Python runtime and imported module paths are not recorded in this runner.',
            'Repeated TRAIN regression is not an independent win-rate estimate.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--baseline',required=True);p.add_argument('--output',required=True);p.add_argument('--complete',action='store_true')
    p.add_argument('--source-archive');a=p.parse_args()
    result=audit(a.batch,a.manifest,a.baseline,a.complete,a.source_archive)
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='sessions'}))
