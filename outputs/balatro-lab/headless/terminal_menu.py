"""One authorized post-terminal menu transition, outside frozen game episodes.

Win overlays may block lab_info. Before mutation verify the TCP listener process
belongs to the staged checkout, source hashes, and live public terminal state.
After mutation verify MENU plus the full silent isolated lab identity. Never retry.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from environment import canonical_state,sanitize
from isolation import load,verify
from transport import RpcClient
from reconcile_rejected_pack import lease,digest
import hybrid_session as h


def listener_owner(port,checkout):
    command=f"$c=Get-NetTCPConnection -LocalPort {int(port)} -State Listen; if (@($c).Count -ne 1) {{throw 'Expected one listener'}}; $p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$c.OwningProcess); @{{address=$c.LocalAddress;pid=$c.OwningProcess;executable=$p.ExecutablePath}} | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
    info=json.loads(result.stdout)
    path=Path(info['executable']).resolve();allowed=Path(checkout).resolve()/'dist'
    if info['address']!='127.0.0.1' or allowed not in path.parents:raise ValueError('Listener is not the registered private engine process')
    return {'pid':info['pid'],'executable_relative':str(path.relative_to(Path(checkout).resolve()))}


def validate_terminal(result,state):
    if result.get('status')!='win' or not result.get('terminal') or result.get('ante',0)<8:
        raise ValueError('Persisted completed win required')
    if not state.get('won') or state.get('overlay')!='win' or state.get('ante_num',0)<8:
        raise ValueError('Live terminal win overlay required; unfinished games cannot return to menu')


def close_terminal(session,reason):
    if not reason.strip():raise ValueError('Explicit controller authorization reason required')
    root=Path(session).resolve();sidecar=root/'terminal-menu.jsonl'
    if sidecar.exists():raise ValueError('Cleanup already attempted; never automatically retry')
    config=json.loads((root/'session.json').read_text(encoding='utf8'));m=load(config['manifest'])
    if h.sha(config['manifest'])!=config['manifest_sha256']:raise ValueError('Manifest changed')
    for name,expected in m['input_hashes'].items():
        if h.sha(Path(m['checkout'])/name)!=expected:raise ValueError('Engine source changed')
    result=json.loads((root/'result.json').read_text(encoding='utf8'))
    journal=root/'transitions.jsonl';journal_hash=h.sha(journal)
    rows=[json.loads(line) for line in journal.read_text(encoding='utf8').splitlines()]
    last=rows[-1]
    if last.get('event')!='result' or last['id']!=result['transition_count']:raise ValueError('Game journal not resolved at terminal result')
    with lease(m['port']):
        owner=listener_owner(m['port'],m['checkout'])
        with RpcClient(m['port'],timeout=60) as client:
            before=sanitize(client.call('gamestate'),last['after']);validate_terminal(result,before)
            if canonical_state(before)!=canonical_state(last['after']):raise ValueError('Terminal public state differs from recorded result')
            with sidecar.open('x',encoding='utf8') as stream:pass
            h.append(sidecar,{'event':'intent','method':'menu','controller_origin':'controller','reason':reason,
                     'purpose':'post_terminal_cleanup_not_gameplay','at_utc':time.time(),
                     'before_public_sha256':digest(canonical_state(before)),
                     'terminal_game_journal_sha256':journal_hash,'engine_manifest_sha256':config['manifest_sha256'],
                     'listener':owner,'retry_allowed':False})
            after=sanitize(client.call('menu',{'reason':reason}))
            reread=sanitize(client.call('gamestate'))
            if after.get('state')!='MENU' or reread.get('state')!='MENU':raise RuntimeError('Menu transition not confirmed; do not retry')
        info=verify(m)
        if h.sha(journal)!=journal_hash:raise RuntimeError('Original episode journal changed')
        proof={'event':'result','method':'menu','controller_origin':'controller','state':'MENU',
               'terminal_episode_preserved':True,'identity_verified':info['identity']==m['identity'],
               'silent_and_headless_verified':True,'at_utc':time.time()}
        h.append(sidecar,proof)
        return proof

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',required=True);p.add_argument('--reason',required=True)
    a=p.parse_args();print(json.dumps(close_terminal(a.session,a.reason)))
