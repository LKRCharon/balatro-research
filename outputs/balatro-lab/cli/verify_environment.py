"""Read-back checks for save isolation, mute and rendering; does not edit any player saves."""
import argparse, ctypes, datetime, hashlib, json, subprocess
from pathlib import Path
import balatro_cli as cli

def verify():
    saved=cli.read(cli.ROOT/'work/original-save-backup.json')
    root=Path(saved['source'])
    current={p.relative_to(root).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
             for p in root.rglob('*') if p.is_file()}
    info=cli.call('lab_info')
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype=ctypes.c_ulong
    user32.GetThreadDesktop.argtypes=[ctypes.c_ulong]; user32.GetThreadDesktop.restype=ctypes.c_void_p
    user32.OpenInputDesktop.argtypes=[ctypes.c_ulong,ctypes.c_bool,ctypes.c_ulong];user32.OpenInputDesktop.restype=ctypes.c_void_p
    user32.GetUserObjectInformationW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(ctypes.c_ulong)]
    user32.CloseDesktop.argtypes=[ctypes.c_void_p]
    def name(handle):
        b=ctypes.create_unicode_buffer(512); n=ctypes.c_ulong()
        if not user32.GetUserObjectInformationW(handle,2,b,ctypes.sizeof(b),ctypes.byref(n)): raise ctypes.WinError(ctypes.get_last_error())
        return b.value
    command=['powershell.exe','-NoProfile','-Command',"Get-Process -Name Balatro-console | Select-Object Id,MainWindowHandle,@{Name='ThreadId';Expression={$_.Threads[0].Id}} | ConvertTo-Json -Compress"]
    proc=json.loads(subprocess.check_output(command))
    if isinstance(proc,list): raise RuntimeError('More than one backend process')
    tid=proc['ThreadId']
    private=info.get('desktop','unverified')
    h=user32.OpenInputDesktop(0,False,1)
    try: visible=name(h)
    finally: user32.CloseDesktop(h)
    result={'original_saves_unchanged':current==saved['files'],'protected_files':len(current),'original_hashes':current,
            'save_backup':saved['backup'],'runtime':info,'backend_pid':proc['Id'],'game_desktop':private,'visible_desktop':visible,
            'desktop_isolated':private!=visible and private.startswith('BalatroLab-'),
            'muted':info.get('master_volume')==0 and info.get('mute') and all(info['sound'][k]==0 for k in ('volume','music_volume','game_sounds_volume'))}
    cli.write(cli.LAB/'results/cli-environment-verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    assert result['original_saves_unchanged'] and result['desktop_isolated'] and result['muted'] and not info['graphics_active']
def after_stop():
    saved=cli.read(cli.ROOT/'work/original-save-backup.json');root=Path(saved['source'])
    current={p.relative_to(root).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
             for p in root.rglob('*') if p.is_file()}
    path=cli.LAB/'results/cli-environment-verification.json';result=cli.read(path)
    pid=result['backend_pid']
    check=subprocess.run(['powershell.exe','-NoProfile','-Command',f'Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],capture_output=True)
    exited=not check.stdout.strip()
    exe=Path(r'D:\download\SteamGame\steamapps\common\Balatro\Balatro.exe')
    digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    result['shutdown']={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'backend_exited':exited,
                        'original_saves_unchanged_after_exit':current==saved['files'],
                        'original_game_sha256':digest,'original_game_unchanged':digest=='0d75fe164accf3312734d4b37ac98788dd15f0b8e4f9bb8b7f90c4e59de93f47'}
    cli.write(path,result)
    print(json.dumps(result['shutdown'],ensure_ascii=False,indent=2))
    assert exited and result['shutdown']['original_saves_unchanged_after_exit'] and result['shutdown']['original_game_unchanged']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--after-stop',action='store_true');args=p.parse_args()
    after_stop() if args.after_stop else verify()
