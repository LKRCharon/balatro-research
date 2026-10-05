"""Run several complete independent trials without any model calls. Stops on unhandled mechanics/errors."""
import argparse
import policy

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=int,default=3)
    args=p.parse_args()
    for _ in range(args.runs):
        policy.run(argparse.Namespace(seed=None,continue_run=False,max_actions=500))
