"""Parallel independent engines, stable output order, no shared game/RNG state."""
from concurrent.futures import ThreadPoolExecutor
import os

class VectorEnv:
    def __init__(self,environments):
        self.envs=list(environments)
        if not self.envs or len({e.port for e in self.envs})!=len(self.envs) or len({e.identity for e in self.envs})!=len(self.envs):
            raise ValueError('Each worker needs a unique port and save identity')
        if len({os.path.normcase(str(e.root.resolve())) for e in self.envs})!=len(self.envs):raise ValueError('Independent logs required')
        self.pool=ThreadPoolExecutor(max_workers=len(self.envs))

    def _map(self,method,args):
        if len(args)!=len(self.envs):raise ValueError('One command per environment required')
        futures=[self.pool.submit(getattr(env,method),*arg) for env,arg in zip(self.envs,args)]
        results=[]
        for future in futures:
            try:results.append({'ok':True,'result':future.result()})
            except Exception as exc:results.append({'ok':False,'error':str(exc),'type':type(exc).__name__})
        # Do not discard successful peers or retry a failed peer.
        return results

    def reset(self,seeds):return self._map('reset',[(seed,) for seed in seeds])
    def step(self,actions):return self._map('step',actions)
    def observe(self):return self._map('observe',[() for _ in self.envs])
    def close(self):
        self.pool.shutdown(wait=True)
        for env in self.envs:env.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
