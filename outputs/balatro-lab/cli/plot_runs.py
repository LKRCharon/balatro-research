"""Descriptive full-run results; seed comparisons and random tests are labelled separately."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

LAB=Path(__file__).resolve().parents[1]
def main():
    ss=json.loads((LAB/'results/cli-summary.json').read_text(encoding='utf-8'))['runs']
    colors={'unseeded':'#b08950','seeded_repeat':'#667cb6','randomized_seed':'#298778'}
    fig,ax=plt.subplots(figsize=(10,max(5,len(ss)*.31+1.7)),layout='constrained')
    counts=[s['round'] if s['win'] else s['round']-1 for s in ss]
    ax.barh(range(len(ss)),counts,color=[colors[s['sampling']] for s in ss],height=.66)
    for i,(s,v) in enumerate(zip(ss,counts)):
        ax.text(v+.2,i,f'A{s["ante"]} | final {s["score"]/max(1,s["target"]):.0%} of target',va='center',fontsize=8)
    ax.set_yticks(range(len(ss)),[f'Run {s["run"]:02d}  {s["policy"].removeprefix("deterministic_route_")}' for s in ss])
    ax.invert_yaxis();ax.set_xlim(0,28);ax.set_xticks(range(0,25,3));ax.axvline(24,linestyle='--',color='#555',linewidth=1)
    ax.text(24.3,-.6,'Ante 8 clear',fontsize=8)
    ax.set_xlabel('Blinds cleared (no skips)');ax.set_title('Blue Deck / Gold Stake: observed runs, not validated route win rates',loc='left',fontsize=12,pad=30)
    ax.spines[['top','right','left']].set_visible(False);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.legend(handles=[Patch(color=colors[k],label=l) for k,l in [('unseeded','Native cursor seed (not IID)'),('seeded_repeat','Chosen/repeated seed'),('randomized_seed','Independent sampled seed')]],
              loc='lower left',bbox_to_anchor=(0,1.01),ncol=3,frameon=False,fontsize=8)
    out=LAB/'figures';out.mkdir(exist_ok=True)
    for ext in ('png','svg'):fig.savefig(out/('cli_runs.'+ext),dpi=180)
    plt.close(fig)
if __name__=='__main__':main()
