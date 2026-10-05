"""Unattended serial training supervisor. Durable progress, no retries/resets on errors."""
import argparse,datetime,json,os,subprocess,sys,traceback
from pathlib import Path
import protocol as p
from batch_report import build
HERE=Path(__file__).resolve().parent;LAB=HERE.parent
sys.path.insert(0,str(LAB/'cli'))
import balatro_cli as cli

def run(campaign):
    target=LAB/'results/experiment-runs'/('supervisor-'+campaign[:12]+'.json')
    record={'campaign':campaign,'pid':os.getpid(),'state':'running','started_utc':p.now(),'partition':'train'}
    cli.write(target,record)
    try:
        while True:
            with p.connect(p.DEFAULT_DB) as con:
                c=con.execute('SELECT partition FROM campaigns WHERE id=?',(campaign,)).fetchone()
                if c is None or c['partition']!='train':raise ValueError('Only training campaigns allowed')
                counts=dict(con.execute('SELECT status,count(*) FROM jobs WHERE campaign_id=? GROUP BY status',(campaign,)))
            record.update(counts=counts,updated_utc=p.now());cli.write(target,record)
            if counts.get('error') or counts.get('running'):raise RuntimeError('Error/unfinished task retained; no automatic retry')
            if not counts.get('planned'):break
            result=subprocess.run([sys.executable,str(HERE/'batch_train.py'),'--campaign',campaign,'--limit','1'])
            build(campaign)
            if result.returncode:raise RuntimeError('Batch worker stopped; inspect retained result and engine state')
        subprocess.run([sys.executable,str(LAB/'cli/verify_environment.py')],check=True)
        cli.call('lab_stop')
        subprocess.run([sys.executable,str(LAB/'cli/verify_environment.py'),'--after-stop'],check=True)
        record.update(state='complete',finished_utc=p.now())
    except Exception as exc:
        record.update(state='needs_attention',error=str(exc),traceback=traceback.format_exc(),updated_utc=p.now())
        raise
    finally:cli.write(target,record)
    if record['state']=='complete':
        subprocess.run([sys.executable,str(LAB.parents[1]/'work/package_final.py')],check=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('campaign');ap.add_argument('--background',action='store_true');args=ap.parse_args()
    if args.background:
        log=LAB/'results/experiment-runs'/('supervisor-'+args.campaign[:12]+'.log')
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUNBUFFERED']='1'
        with log.open('a',encoding='utf8') as f:
            proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),args.campaign],stdout=f,stderr=subprocess.STDOUT,
                env=env,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP,stdin=subprocess.DEVNULL)
        print(json.dumps({'pid':proc.pid,'log':str(log),'campaign':args.campaign}))
    else:
        import msvcrt
        lock=LAB.parents[1]/'work'/('train-supervisor-'+args.campaign[:12]+'.lock')
        with lock.open('a+b') as f:
            if f.tell()==0:f.write(b'0');f.flush()
            f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            try:run(args.campaign)
            finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
