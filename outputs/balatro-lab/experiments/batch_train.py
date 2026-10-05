"""Serial frozen training campaign. Never schedules validation or test; stop on errors."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
import protocol as p
HERE=Path(__file__).resolve().parent;LAB=HERE.parent;ROOT=LAB.parents[1]
sys.path.insert(0,str(LAB/'cli'))
import balatro_cli as cli
import telemetry

def prepare(seeds):
    source=HERE/'policies/route_v2'
    files=sorted(f for f in source.glob('*.py'))
    digest=hashlib.sha256(b''.join(f.name.encode()+f.read_bytes() for f in files)).hexdigest()
    snapshot=HERE/'policies'/('route_v2_'+digest[:12])
    if not snapshot.exists():shutil.copytree(source,snapshot,ignore=shutil.ignore_patterns('__pycache__'))
    contexts=[Path(__file__),HERE/'protocol.py',LAB/'cli/balatro_cli.py',LAB/'cli/observations.py']+sorted((ROOT/'work/balatro-source/mods').rglob('*.lua'))
    ids=[]
    for weight in (.3,.65):
        config={'name':f'batch_tail_{weight}_{digest[:12]}','tail_weight':weight,'discard_samples':12,'max_actions':800,
                'deck':'BLUE','stake':'GOLD','purpose':'paired_training_only','no_acceleration':True}
        ids.append(p.register_policy(p.DEFAULT_DB,config['name'],snapshot,config,contexts))
    return p.schedule(p.DEFAULT_DB,'train',ids,seeds)

def summary(campaign):
    with p.connect(p.DEFAULT_DB) as con:
        rows=con.execute('SELECT j.id,j.seed_id,j.policy_id,j.status,j.result FROM jobs j WHERE campaign_id=? ORDER BY rowid',(campaign,)).fetchall()
    result={'campaign':campaign,'partition':'train','jobs':[]}
    for row in rows:
        r=json.loads(row['result']) if row['result'] else {}
        result['jobs'].append({k:row[k] for k in ('id','seed_id','policy_id','status')}|{k:r.get(k) for k in ('run','ante','actions','elapsed_seconds','errors','predictions')})
    cli.write(LAB/'results/experiment-runs'/('batch-'+campaign[:12]+'.json'),result)
    cli.write(LAB/'results/experiment-partitions.json',p.public_summary(p.DEFAULT_DB))
    return result

def execute(campaign,limit):
    with p.connect(p.DEFAULT_DB) as con:
        c=con.execute('SELECT partition FROM campaigns WHERE id=?',(campaign,)).fetchone()
        if c is None or c['partition']!='train':raise ValueError('Only training allowed')
        rows=con.execute('SELECT id,status,policy_id FROM jobs WHERE campaign_id=? ORDER BY rowid',(campaign,)).fetchall()
    if any(r['status'] in ('running','error') for r in rows):raise ValueError('Reconcile running/error jobs before continuing campaign')
    done=0
    for row in rows:
        if row['status']!='planned':continue
        if done>=limit:break
        state=cli.call('gamestate')
        if state['state']!='MENU':
            if not cli.terminal(state):raise ValueError('Unfinished game retained; refusing reset')
            cli.call('menu',{'reason':'保留完整训练结果，进入已登记的下一个训练任务。'})
        with p.connect(p.DEFAULT_DB) as con:manifest=p.verify_policy(con,row['policy_id'])
        claim=p.claim_job(p.DEFAULT_DB,row['id'],'train')
        cfg=ROOT/'work'/('batch-config-'+row['policy_id'][:12]+'.json');cli.write(cfg,manifest['config'])
        try:
            cli.call('start',{'seed':claim['seed'],'deck':'BLUE','stake':'GOLD','reason':'冻结脚本成对训练；种子仅属训练分区，不重置开局。'})
            outdir=LAB/'results/experiment-runs';outdir.mkdir(exist_ok=True)
            with (outdir/(row['id']+'-stdout.log')).open('w',encoding='utf8') as log:
                proc=subprocess.run([sys.executable,str(Path(manifest['source_root'])/'worker.py'),'--config',str(cfg),'--job',row['id'],'--partition','train','--policy-id',row['policy_id']],stdout=log,stderr=subprocess.STDOUT)
            report=outdir/(row['id']+'-result.json')
            result=cli.read(report) if report.exists() else {'status':'error','error':'Worker ended without report','returncode':proc.returncode}
        except Exception as exc:result={'status':'error','error':str(exc)}
        p.record_result(p.DEFAULT_DB,row['id'],'train',claim['seed'],row['policy_id'],result)
        if result.get('run') is not None:telemetry.build_run(result['run']);telemetry.dashboard()
        summary(campaign);done+=1
        print(json.dumps({'campaign':campaign,'run':result.get('run'),'status':result['status'],'ante':result.get('ante'),'actions':result.get('actions'),'seconds':result.get('elapsed_seconds')},ensure_ascii=False),flush=True)
        if result['status']=='error':raise RuntimeError('Technical error retained; batch stopped without retry')
    summary(campaign)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--prepare',type=int);ap.add_argument('--campaign');ap.add_argument('--limit',type=int,default=1000);args=ap.parse_args()
    if args.prepare:
        campaign=prepare(args.prepare);summary(campaign);print(json.dumps({'campaign':campaign}))
    elif args.campaign:execute(args.campaign,args.limit)
    else:ap.error('Use --prepare SEEDS or --campaign ID')
