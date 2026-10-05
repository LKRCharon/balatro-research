"""Document controller coverage; never a card power ranking."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;LAB=HERE.parent
sys.path[:0]=[str(HERE/'policies/route_v1'),str(LAB/'cli')]
import advisor,policy

def main():
    catalog=json.loads((LAB/'data/catalog.json').read_text(encoding='utf-8'))
    records=[]
    for c in catalog['records']:
        if c['category']!='Joker':continue
        key=c['id'];allow=key in policy.PRIORITY and key in advisor.SUPPORTED
        reason='进入购买候选，仍受现金/贴纸/阵容条件限制' if allow else '未接入该版计分模型' if key not in advisor.SUPPORTED else '计分模型有分支，但购买规则未启用'
        records.append({'key':key,'name':c['name_zh'],'purchase_candidate':allow,'reason':reason})
    result={'version':'route_v1','meaning':'Implementation coverage only, not power or balance.',
            'candidate_count':sum(r['purchase_candidate'] for r in records),'total':len(records),'records':records}
    (LAB/'results/route-v1-coverage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 固定策略 v1 的小丑覆盖范围','','这是程序的实现范围，不是强度排行。全部150种仍按游戏规则出现；79种进入购买候选，71种会因本版规则范围被跳过。白名单内也可能因价格、贴纸、组合要求而不购买。',
           '','本轮结果不能用来判断白名单外小丑的强弱。尤其复制、增删牌等路线缺失，会使通关率受到控制器能力限制。',
           '','| 小丑 | Key | v1 购买规则 |','|---|---|---|']
    lines += [f'| {r["name"]} | {r["key"]} | {r["reason"]} |' for r in sorted(records,key=lambda r:(not r['purchase_candidate'],r['key']))]
    (LAB/'experiments/小丑支持范围.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False))

if __name__=='__main__':main()
