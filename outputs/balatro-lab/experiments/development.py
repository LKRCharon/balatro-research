"""Full-card development runs on explicitly known training seeds; never validation/test."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import protocol as p
HERE=Path(__file__).resolve().parent;LAB=HERE.parent;ROOT=LAB.parents[1]
sys.path[:0]=[str(HERE/'policies/route_v2'),str(LAB/'cli')]
import balatro_cli as cli
import telemetry

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--replay-run',type=int,required=True);ap.add_argument('--continue-run',action='store_true');args=ap.parse_args()
    source=HERE/'policies/route_v2'
    files=sorted(f for f in source.glob('*') if f.is_file())
    digest=hashlib.sha256(b''.join(f.name.encode()+f.read_bytes() for f in files)).hexdigest()
    snapshot=HERE/'policies'/('route_v2_'+digest[:12])
    if not snapshot.exists():shutil.copytree(source,snapshot,ignore=shutil.ignore_patterns('__pycache__'))
    config={'name':'full_card_development_'+digest[:12],'tail_weight':.3,'discard_samples':12,'max_actions':800,
            'deck':'BLUE','stake':'GOLD','purpose':'mechanism_development_on_known_training_seed','no_acceleration':True}
    cfg=HERE/(config['name']+'.json');cli.write(cfg,config)
    contexts=[Path(__file__),HERE/'protocol.py',LAB/'cli/observations.py',LAB/'cli/telemetry.py']+sorted((ROOT/'work/balatro-source/mods').rglob('*.lua'))
    ident=p.register_policy(p.DEFAULT_DB,config['name'],snapshot,config,contexts)
    seed=cli.read(ROOT/'work/private-seeds.json')[str(args.replay_run)]
    p.assert_partition(p.DEFAULT_DB,seed,'train')
    with p.connect(p.DEFAULT_DB) as con:
        row=con.execute('SELECT id,commitment FROM seeds WHERE seed=? AND partition=\'train\'',(seed,)).fetchone()
        campaign=p.digest(p.json_text({'purpose':'full_card_development','policy_id':ident,'seed_id':row['id']}))
        job=p.digest(campaign+':'+ident)
        spec={'deck':'BLUE','stake':'GOLD','seed_grouped':True,'purpose':'development, not a fresh independent win-rate sample',
              'original_run':args.replay_run,'source_sha256':digest,'continuation':args.continue_run,'validation':'not allocated','test':'not allocated'}
        con.execute('INSERT INTO campaigns VALUES(?,?,?,?,?,?)',(campaign,'train',p.json_text([ident]),p.json_text([row['id']]),p.json_text(spec),p.now()))
        con.execute('INSERT INTO jobs(id,campaign_id,seed_id,policy_id) VALUES(?,?,?,?)',(job,campaign,row['id'],ident))
    s=cli.call('gamestate')
    if args.continue_run:
        active=cli.read(cli.RUNS/'session.json')
        if not active['active'] or cli.read(ROOT/'work/private-seeds.json')[str(active['run'])]!=seed:
            raise ValueError('Continuation requires the same unfinished training seed')
    elif s['state']!='MENU':
        if not cli.terminal(s):raise ValueError('Existing unfinished game must be retained')
        cli.call('menu',{'reason':'保留上一局数据，返回菜单进行完整卡牌策略的训练种子复打。'})
    claim=p.claim_job(p.DEFAULT_DB,job,'train')
    if not args.continue_run:
        cli.call('start',{'seed':claim['seed'],'reason':'蓝色金注训练种子复打：启用全小丑策略、复制链与动态牌组，核验新增机制；本局不计为独立验证样本。'})
    process=subprocess.run([sys.executable,str(snapshot/'worker.py'),'--config',str(cfg),'--job',job,'--partition','train','--policy-id',ident])
    target=LAB/'results/experiment-runs'/(job+'-result.json')
    result=cli.read(target) if target.exists() else {'status':'error','error':'Worker exited without report','returncode':process.returncode}
    p.record_result(p.DEFAULT_DB,job,'train',claim['seed'],ident,result)
    cli.write(LAB/'results/experiment-partitions.json',p.public_summary(p.DEFAULT_DB))
    if result.get('run') is not None:
        telemetry.build_run(result['run']);telemetry.dashboard()
    print(json.dumps({'run':result.get('run'),'status':result['status'],'original_run':args.replay_run,'snapshot':snapshot.name,'job_id':job}),flush=True)
    if result['status']=='error':raise SystemExit(1)

if __name__=='__main__':main()
