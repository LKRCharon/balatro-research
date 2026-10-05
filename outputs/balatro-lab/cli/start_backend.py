"""Start the patched Windows backend on a private desktop with audio and rendering disabled."""
import argparse, json, os, socket, subprocess, sys
from pathlib import Path
import balatro_cli as cli

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=cli.REPO)
    p.add_argument('--just',type=Path,default=cli.JUST)
    p.add_argument('--python',type=Path,default=Path(r'C:\Users\charon\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'))
    args=p.parse_args()
    if sys.platform!='win32':raise SystemExit('This private-desktop adapter currently requires Windows.')
    for path in (args.just,args.python,args.repo/'scripts/private_process.py',args.repo/'mods/lab_cli/main.lua'):
        if not path.is_file():raise SystemExit('Missing prerequisite: '+str(path))
    with socket.socket() as sock:
        sock.settimeout(.3)
        if sock.connect_ex(('127.0.0.1',12346))==0:
            raise SystemExit('Port 12346 is already in use. Inspect the existing backend before starting another.')
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUNBUFFERED']='1'
    git_sh=Path(r'C:\Program Files\Git\bin')
    env['PATH']=os.pathsep.join([str(args.python.parent),str(args.just.parent),str(git_sh),env['PATH']])
    logs=cli.ROOT/'work';logs.mkdir(parents=True,exist_ok=True)
    outpath=logs/'cli-launcher-muted.log';errpath=logs/'cli-launcher-muted.err'
    with outpath.open('wb') as out,errpath.open('wb') as err:
        proc=subprocess.Popen([str(args.just),'windows','run-cli'],cwd=args.repo,env=env,
                              stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    print(json.dumps({'launcher_pid':proc.pid,'stdout':str(outpath),'stderr':str(errpath),
                      'identity':'Balatro-Lab-20261004-CLI','next':'python cli/balatro_cli.py lab_info'},ensure_ascii=False))

if __name__=='__main__':main()
