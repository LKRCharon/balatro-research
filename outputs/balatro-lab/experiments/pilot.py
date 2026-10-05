"""Predeclared paired parameter search followed by validation of its training winner.

No test seed values are queried. Policies cannot obtain seeds from worker arguments.
"""
import argparse, hashlib, json, os, subprocess, sys, time
from collections import Counter
from pathlib import Path
import protocol as p
LAB=p.LAB;ROOT=LAB.parents[1];HERE=Path(__file__).resolve().parent
sys.path.append(str(LAB/'cli'))
import balatro_cli as cli

PLAN=HERE/'pilot-v1-plan.json'
SELECTION=LAB/'results/pilot-v1-selection.json'

def write(path,data):cli.write(path,data)
def refresh():write(LAB/'results/experiment-partitions.json',p.public_summary(p.DEFAULT_DB))

def setup():
    if PLAN.exists():raise ValueError('Plan already exists; resume instead')
    source=HERE/'policies/route_v1'
    context=[Path(__file__),HERE/'protocol.py',LAB/'cli/balatro_cli.py',LAB/'cli/observations.py',LAB/'backend/provenance.json']
    context+=sorted((ROOT/'work/balatro-source/mods').rglob('*.lua'))
    variants=[]
    for tail in (.2,.6):
        name='route_v1_tail_'+str(int(tail*100))
        config={'name':name,'tail_weight':tail,'discard_samples':12,'max_actions':700,
                'no_skips':True,'no_acceleration':True,'deck':'BLUE','stake':'GOLD'}
        path=HERE/(name+'.json');write(path,config)
        ident=p.register_policy(p.DEFAULT_DB,name,source,config,context)
        variants.append({'policy_id':ident,'name':name,'config_path':str(path),'config':config})
    campaign=p.schedule(p.DEFAULT_DB,'train',[v['policy_id'] for v in variants],6)
    plan={'created_utc':p.now(),'train_seeds':6,'validation_seeds':8,'variants':variants,'train_campaign':campaign,
          'selection_rule':['maximum wins / all 6 assigned jobs','maximum mean completed blinds',
                            'maximum mean terminal target fraction capped at 1','lower tail_weight'],
          'validation_rule':'Only the training winner, unchanged, on first 8 reserved validation seeds. No tuning from validation.',
          'technical_errors':'Retained. Stop campaign with unfinished game; never silently skip or reset.',
          'model_errors':'Score mismatches logged; frozen strategy continues. Forecast score is not a calibrated probability.',
          'final_test':'Unallocated and untouched','assumptions':'No deck creation/destruction/conversion; observed enhancements tracked.',
          'assignment_sha256':p.public_summary(p.DEFAULT_DB)['assignment_sha256']}
    write(PLAN,plan);refresh();print(json.dumps(plan,ensure_ascii=False,indent=2))

def jobs(campaign):
    with p.connect(p.DEFAULT_DB) as con:
        return [dict(r) for r in con.execute('SELECT * FROM jobs WHERE campaign_id=? ORDER BY rowid',(campaign,))]

def execute(campaign,role,plan):
    variants={v['policy_id']:v for v in plan['variants']}
    for job in jobs(campaign):
        if job['status'] in {'win','loss','error'}:continue
        if job['status']!='planned':raise ValueError('Outstanding claimed job requires audit before resume')
        s=cli.call('gamestate')
        if s['state']!='MENU':
            if not cli.terminal(s):raise ValueError('Unfinished game retained; cannot launch next seed')
            cli.call('menu',{'reason':'已保存这局结果，返回菜单继续同一批固定规则实验。'})
        claim=p.claim_job(p.DEFAULT_DB,job['id'],role);variant=variants[job['policy_id']]
        print(json.dumps({'event':'starting','partition':role,'job':job['id'],'policy':variant['name']}),flush=True)
        result_path=LAB/'results/experiment-runs'/(job['id']+'-result.json')
        try:
            cli.call('start',{'seed':claim['seed'],'reason':f'蓝色牌组金注：开始{ "训练" if role=="train" else "验证"}实验，固定弃牌风险权重{variant["config"]["tail_weight"]}；按完整胜负统计。'})
            with p.connect(p.DEFAULT_DB) as con:manifest=p.verify_policy(con,job['policy_id'])
            if cli.read(Path(variant['config_path']))!=manifest['config']:
                raise ValueError('Config file does not match the frozen manifest')
            env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
            command=[sys.executable,str(Path(manifest['source_root'])/'worker.py'),'--config',variant['config_path'],
                     '--job',job['id'],'--partition',role,'--policy-id',job['policy_id']]
            process=subprocess.run(command,env=env)
            if not result_path.exists():raise RuntimeError('Worker failed without terminal report; returncode='+str(process.returncode))
            result=cli.read(result_path)
        except Exception as exc:
            result={'status':'error','error':str(exc),'terminal':False,'job_id':job['id']}
            write(result_path,result)
        p.record_result(p.DEFAULT_DB,job['id'],role,claim['seed'],job['policy_id'],result);refresh()
        print(json.dumps({'event':'completed','partition':role,'policy':variant['name'],
                          **{k:result.get(k) for k in ('status','run','ante','round','elapsed_seconds')}}),flush=True)
        if result['status']=='error':raise RuntimeError('Technical error retained; campaign stopped for audit')

def completed_blinds(r):
    if r['status']=='win':return 24
    return max(0,(r.get('round') or 1)-1)

def select(plan):
    if SELECTION.exists():return cli.read(SELECTION)
    rows=jobs(plan['train_campaign'])
    if any(j['status'] not in {'win','loss','error'} for j in rows):raise ValueError('Training incomplete')
    metrics=[]
    for v in plan['variants']:
        rr=[json.loads(j['result']) for j in rows if j['policy_id']==v['policy_id']]
        scores=[min(1,(r.get('score') or 0)/max(1,r.get('target') or 1)) for r in rr]
        metric={'policy_id':v['policy_id'],'name':v['name'],'assigned':len(rr),'counts':dict(Counter(r['status'] for r in rr)),
                'mean_completed_blinds':sum(completed_blinds(r) for r in rr)/len(rr),'mean_target_fraction':sum(scores)/len(rr),
                'tail_weight':v['config']['tail_weight']}
        metric['rank']=[metric['counts'].get('win',0),metric['mean_completed_blinds'],metric['mean_target_fraction'],-metric['tail_weight']]
        metrics.append(metric)
    winner=max(metrics,key=lambda m:m['rank'])
    # This commitment is written before any validation job is claimed.
    result={'selected_utc':p.now(),'train_campaign':plan['train_campaign'],'winner':winner,'metrics':metrics,
            'selection_rule':plan['selection_rule'],'based_on':'training_only',
            'plan_sha256':hashlib.sha256(PLAN.read_bytes()).hexdigest()}
    write(SELECTION,result)
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['setup','train','validate']);args=ap.parse_args()
    if args.command=='setup':setup();return
    plan=cli.read(PLAN)
    if args.command=='train':execute(plan['train_campaign'],'train',plan);print(json.dumps(select(plan),ensure_ascii=False,indent=2));return
    selection=select(plan);schedule_path=LAB/'results/pilot-v1-validation-plan.json'
    if schedule_path.exists():campaign=cli.read(schedule_path)['campaign']
    else:
        campaign=p.schedule(p.DEFAULT_DB,'validation',[selection['winner']['policy_id']],plan['validation_seeds'])
        write(schedule_path,{'campaign':campaign,'created_utc':p.now(),'selection_sha256':hashlib.sha256(SELECTION.read_bytes()).hexdigest()})
    execute(campaign,'validation',plan);refresh()

if __name__=='__main__':main()
