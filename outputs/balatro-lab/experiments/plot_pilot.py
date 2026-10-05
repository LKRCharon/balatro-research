"""Standalone research figure. Run only after the pilot report is complete."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
LAB=Path(__file__).resolve().parents[1]

def main():
    r=json.loads((LAB/'results/pilot-v1-report.json').read_text(encoding='utf-8'))
    if any(x['status'] in {'planned','running'} for x in r['runs']):raise ValueError('Pilot not finished')
    for f in (r'C:\Windows\Fonts\msyh.ttc',r'C:\Windows\Fonts\simhei.ttf'):
        if Path(f).exists():
            font_manager.fontManager.addfont(f);plt.rcParams['font.family']=font_manager.FontProperties(fname=f).get_name();break
    plt.rcParams['axes.unicode_minus']=False
    fig,axes=plt.subplots(1,2,figsize=(12,4.7),gridspec_kw={'width_ratios':[1,1.15]})
    colors=['#367cd0','#e09036']
    for c,(i,label) in zip(colors,[(0,'低分风险权重 0.2'),(1,'低分风险权重 0.6')]):
        axes[0].plot(range(1,len(r['paired_training'])+1),[b['completed_blinds'][i] for b in r['paired_training']],
                     marker='o',color=c,label=label,lw=1.8)
    axes[0].set(title='训练：同一批种子的配对比较',xlabel='训练种子编号',ylabel='已通过的盲注数')
    axes[0].legend(frameon=False,loc='upper left')
    val=[x for x in r['runs'] if x['partition']=='validation']
    values=[24 if x['status']=='win' else max(0,(x['round'] or 1)-1) for x in val]
    axes[1].bar(range(1,len(val)+1),values,color=['#29916c' if x['status']=='win' else '#6c87a4' for x in val],width=.64)
    for i,(x,y) in enumerate(zip(val,values),1):axes[1].text(i,y+.45,'通关' if x['status']=='win' else f'止于底注{x["ante"]}',ha='center',fontsize=8)
    axes[1].set(title='验证：训练优胜者原样运行',xlabel='独立验证种子编号')
    for ax in axes:
        ax.set_ylim(0,28);ax.set_yticks([0,6,12,18,24]);ax.axhline(24,color='#29916c',ls='--',alpha=.5,lw=1)
        ax.grid(axis='y',alpha=.14);ax.spines[['top','right']].set_visible(False)
    fig.suptitle('蓝色牌组 · 金注｜首批固定策略训练与验证',fontsize=15,y=1.01)
    fig.text(.5,-.015,'训练 6 个种子 × 2 组参数；验证 8 个新种子；最终测试集 0 局。小样本不能证明高成功率。',ha='center',fontsize=10,color='#53606d')
    fig.tight_layout()
    for suffix in ('png','svg'):fig.savefig(LAB/f'figures/pilot-v1-train-validation.{suffix}',dpi=180,bbox_inches='tight')

if __name__=='__main__':main()
