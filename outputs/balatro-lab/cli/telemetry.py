"""Read-only, idempotent extraction of public decision telemetry from RPC logs."""
import argparse,collections,hashlib,html,json,sqlite3
from pathlib import Path
LAB=Path(__file__).resolve().parents[1]
DEST=LAB/'results/telemetry'
MUTATIONS={'select','skip','play','discard','cash_out','next_round','buy','pack','use','sell','rearrange','reroll','reroll_boss'}

def read(path,default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def extract(run,rows,catalog,metadata=None):
    actions=[];offers=[];rounds={};seen={};last={};visit=0;generation=0;pack_generation=0;last_pack=None;malformed=0
    def cards(s,area):return (s.get(area) or {}).get('cards') or []
    for line,e in enumerate(rows,1):
        s=e.get('result') or {};method=e.get('method');params=e.get('params') or {}
        if e.get('error') or 'state' not in s:continue
        if method=='start':last={}
        if s['state']=='MENU':continue
        if s['state']=='SHOP' and (not last or method=='cash_out'):
            visit+=1;generation=0
        if method=='reroll':generation+=1
        # Link the chosen item to the previously visible offer, before processing
        # the result in which that card may already have disappeared.
        if method in ('buy','pack') and last:
            selected=None
            if method=='buy':
                selected=next(((area,params[p]) for p,area in [('card','shop'),('voucher','vouchers'),('pack','packs')] if p in params),None)
            elif 'card' in params:selected=('pack',params['card'])
            if selected:
                area,index=selected;cs=cards(last,area)
                if isinstance(index,int) and 0<=index<len(cs):
                    c=cs[index]
                    candidates=[o for o in offers if o['area']==area and o['card_id']==c.get('id') and o['key']==c.get('key') and o['selected_line'] is None]
                    if candidates:
                        chosen=candidates[-1]
                        chosen['selected_line']=line;chosen['selected_method']=method
                        chosen['selected_price']=(c.get('cost') or {}).get('buy')
                        chosen['selected_modifier']=c.get('modifier') or {}
                    if area=='packs':last_pack=c.get('key')
        if s['state']=='SMODS_BOOSTER_OPENED' and last.get('state')!='SMODS_BOOSTER_OPENED':pack_generation+=1
        for area in ('shop','vouchers','packs','pack'):
            if area=='pack' and s['state']!='SMODS_BOOSTER_OPENED':continue
            if area!='pack' and s['state']!='SHOP':continue
            for index,c in enumerate(cards(s,area)):
                if (c.get('state') or {}).get('hidden'):continue
                token=(area,visit,generation if area=='shop' else pack_generation if area=='pack' else 0,c.get('id',('index',index,c.get('key'))))
                observation={'line':line,'time':e.get('time'),'price':(c.get('cost') or {}).get('buy'),
                             'modifier':c.get('modifier') or {}}
                if token in seen:
                    o=seen[token];previous=o['observations'][-1]
                    if any(previous[k]!=observation[k] for k in ('price','modifier')):
                        o['observations'].append(observation)
                    o['latest_price']=observation['price'];o['latest_modifier']=observation['modifier']
                    continue
                spec=catalog.get(c.get('key'),{});modifier=c.get('modifier') or {}
                o={'offer_id':len(offers)+1,'line':line,'time':e.get('time'),'ante':s.get('ante_num'),'round':s.get('round_num'),
                   'visit':visit,'reroll_generation':generation,'area':area,'key':c.get('key'),'card_id':c.get('id'),
                   'identity_quality':'engine_id' if c.get('id') is not None else 'index_fallback',
                   'name':spec.get('name_zh',c.get('label')),'category':spec.get('category',c.get('set')),
                   'rarity':spec.get('rarity'),'price':(c.get('cost') or {}).get('buy'),'money':s.get('money'),
                   'affordable':None if (c.get('cost') or {}).get('buy') is None else s.get('money',0)>=c['cost']['buy'],
                   'modifier':modifier,'pack_kind':spec.get('kind'),'pack_config':spec.get('config') if area=='packs' else None,
                   'owned_vouchers':s.get('used_vouchers',[]),'joker_count':len(cards(s,'jokers')),
                   'joker_limit':(s.get('jokers') or {}).get('limit'),
                   'parent_pack':last_pack if area=='pack' else None,'selected_line':None,'selected_method':None}
                o.update(first_seen_price=o['price'],latest_price=o['price'],latest_modifier=modifier,
                         observations=[observation],selected_price=None,selected_modifier=None)
                seen[token]=o;offers.append(o)
        r=s.get('round_num');rd=s.get('round') or {};blind=next((b for b in (s.get('blinds') or {}).values() if b.get('status')=='CURRENT'),{})
        if method in MUTATIONS:
            before=last.get('money');after=s.get('money')
            actions.append({'line':line,'time':e.get('time'),'method':method,'ante':s.get('ante_num'),'round':r,'state':s['state'],
                            'money_before':before,'money_after':after,'money_delta':None if before is None or after is None else after-before,
                            'blind':blind.get('name'),'target':blind.get('score'),'score':rd.get('chips'),'hands_left':rd.get('hands_left'),
                            'discards_left':rd.get('discards_left'),'reroll_cost':rd.get('reroll_cost'),'jokers':[{'key':j.get('key'),'modifier':j.get('modifier') or {}} for j in cards(s,'jokers')],
                            'consumable_count':len(cards(s,'consumables')),'reason':params.get('reason','')})
            actions[-1]['owned_vouchers']=s.get('used_vouchers',[])
            actions[-1]['cashout_display']=rd.get('cashout_dollars')
        if r is not None:
            rr=rounds.setdefault(r,{'round':r,'ante':s.get('ante_num'),'entry_money':None,'clear_money':None,'cashout_money':None,'shop_exit_money':None,'purchases':0,'rerolls':0,'plays':0,'discards':0})
            if method=='select':rr.update(entry_money=s.get('money'),blind=blind.get('name'),target=blind.get('score'))
            if s['state']=='ROUND_EVAL':rr.update(clear_money=s.get('money'),score=rd.get('chips'),cashout_display=rd.get('cashout_dollars'))
            if method=='cash_out':rr['cashout_money']=s.get('money')
            if method=='next_round':rr['shop_exit_money']=s.get('money')
            for m,k in [('buy','purchases'),('reroll','rerolls'),('play','plays'),('discard','discards')]:rr[k]+=method==m
        last=s
    ordinary=[o for o in offers if o['area']=='shop' and o['category']=='Joker']
    rarities=collections.Counter(str(o['rarity']) for o in ordinary)
    return {'schema':2,'run':run,'metadata':metadata or {},'terminal_state':last.get('state'),
            'won':last.get('state')!='GAME_OVER' and bool(last.get('won') or last.get('overlay')=='win'),
            'actions':actions,'offers':offers,'rounds':list(rounds.values()),
            'summary':{'ordinary_shop_joker_offers':len(ordinary),'rarity_counts':dict(rarities),
                       'rarity_rates':{k:v/len(ordinary) for k,v in rarities.items()},
                       'voucher_offers':sum(o['area']=='vouchers' for o in offers),'pack_offers':sum(o['area']=='packs' for o in offers),
                       'pack_contents_observed':sum(o['area']=='pack' for o in offers),'fallback_identities':sum(o['identity_quality']!='engine_id' for o in offers)}}

def build_run(run):
    path=LAB/f'results/cli-runs/run-{run:02d}.jsonl';rows=[];incomplete=0
    for line in path.read_text(encoding='utf-8').splitlines():
        try:rows.append(json.loads(line))
        except json.JSONDecodeError:incomplete+=1
    catalog={r['id']:r for r in read(LAB/'data/catalog.json')['records']}
    meta=read(LAB/f'results/cli-runs/run-{run:02d}-policy.json',{})
    # Hash allows grouping identical seeds without distributing their values.
    outcome=read(LAB/f'results/cli-runs/run-{run:02d}-outcome.json',{})
    seed=outcome.get('seed')
    meta={k:meta[k] for k in ('partition','policy_id','job_id','controller','cohort','script_policy','hidden_information','resets') if k in meta}
    meta['seed_group_sha256']=hashlib.sha256(seed.encode()).hexdigest() if isinstance(seed,str) else None
    meta['partition']=meta.get('partition','historical_development')
    data=extract(run,rows,catalog,meta);data['incomplete_log_lines']=incomplete
    data['source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    DEST.mkdir(parents=True,exist_ok=True)
    (DEST/f'run-{run:02d}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    with sqlite3.connect(DEST/'telemetry.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS runs(run INTEGER PRIMARY KEY, metadata TEXT, summary TEXT, source_sha256 TEXT)')
        for table in ('actions','offers','rounds'):
            db.execute(f'CREATE TABLE IF NOT EXISTS {table}(run INTEGER, ordinal INTEGER, data TEXT, PRIMARY KEY(run,ordinal))')
            db.execute(f'DELETE FROM {table} WHERE run=?',(run,))
            db.executemany(f'INSERT INTO {table} VALUES(?,?,?)',[(run,n,json.dumps(x,ensure_ascii=False)) for n,x in enumerate(data[table])])
        db.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?)',(run,json.dumps(meta),json.dumps(data['summary']),data['source_sha256']))
    return data

def dashboard():
    data=[read(p) for p in sorted(DEST.glob('run-*.json')) if int(p.stem.split('-')[1])>0]
    chunks=['<!doctype html><meta charset="utf-8"><title>Balatro 决策数据</title><style>body{background:#141921;color:#e8edf5;font:16px system-ui;max-width:1100px;margin:35px auto;padding:20px}article{border-top:1px solid #465064;padding:22px 0}svg{width:100%;height:150px}table{width:100%;text-align:left}td,th{padding:7px}small{color:#abb9ca}a{color:#83c8ff}</style><h1>每局决策数据</h1><p>金币为动作后的实测余额；稀有度比例只统计去重后的普通商店小丑报价。重放不当作独立样本，卡包内容单独统计。</p>']
    for d in data:
        vals=[a['money_after'] for a in d['actions'] if a['money_after'] is not None]
        lo=min([0]+vals);hi=max([1]+vals);points=' '.join(f'{i*1000/max(1,len(vals)-1):.2f},{140-130*(v-lo)/(hi-lo):.2f}' for i,v in enumerate(vals))
        ss=d['summary'];counts=ss['rarity_counts'];rates=ss['rarity_rates']
        chunks.append(f'<article><h2>第 {d["run"]} 局</h2><small>{html.escape(d["metadata"]["partition"])} · {len(d["rounds"])} 个轮次记录 · 金币范围 {lo}–{hi}</small><svg viewBox="0 0 1000 150" preserveAspectRatio="none"><polyline points="{points}" stroke="#edc66f" stroke-width="2" fill="none"/></svg>')
        chunks.append('<table><tr><th>普通商店小丑报价</th><th>普通 / 罕见 / 稀有</th><th>优惠券报价</th><th>卡包报价 / 已见包内选项</th></tr>')
        distribution=' / '.join(f'{counts.get(str(k),0)} ({rates.get(str(k),0):.1%})' for k in (1,2,3))
        chunks.append(f'<tr><td>{ss["ordinary_shop_joker_offers"]}</td><td>{distribution}</td><td>{ss["voucher_offers"]}</td><td>{ss["pack_offers"]} / {ss["pack_contents_observed"]}</td></tr></table>')
        chunks.append('<details><summary>每轮金币节点与商店结构</summary><table><tr><th>底注 / 轮次</th><th>进盲注</th><th>过关</th><th>结算后</th><th>离店</th><th>购买 / 刷新</th></tr>')
        for r in d['rounds']:
            chunks.append(f'<tr><td>{r["ante"]} / {r["round"]}</td>'+''.join('<td>'+('—' if r[k] is None else str(r[k]))+'</td>' for k in ('entry_money','clear_money','cashout_money','shop_exit_money'))+f'<td>{r["purchases"]} / {r["rerolls"]}</td></tr>')
        chunks.append('</table><p>卡包结构（报价数 / 购买数）：</p><ul>')
        for key in sorted({o['key'] for o in d['offers'] if o['area']=='packs'}):
            group=[o for o in d['offers'] if o['area']=='packs' and o['key']==key];cfg=group[0]['pack_config'] or {}
            chunks.append(f'<li>{html.escape(group[0]["name"] or key)} · {cfg.get("extra","?")} 选 {cfg.get("choose","?")}：{len(group)} / {sum(o["selected_line"] is not None for o in group)}</li>')
        chunks.append('</ul><p>优惠券（进店可购次数 / 购买次数）：</p><ul>')
        for key in sorted({o['key'] for o in d['offers'] if o['area']=='vouchers'}):
            group=[o for o in d['offers'] if o['area']=='vouchers' and o['key']==key]
            chunks.append(f'<li>{html.escape(group[0]["name"] or key)}：{len(group)} / {sum(o["selected_line"] is not None for o in group)}</li>')
        chunks.append(f'</ul></details><p><a href="run-{d["run"]:02d}.json">逐动作、报价、购买关联和轮次数据</a></p></article>')
    (DEST/'index.html').write_text('\n'.join(chunks),encoding='utf-8')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--run',type=int);args=ap.parse_args()
    runs=[args.run] if args.run else sorted({int(p.stem.split('-')[1]) for p in (LAB/'results/cli-runs').glob('run-*.jsonl') if p.stem.split('-')[1].isdigit() and len(p.stem.split('-'))==2 and int(p.stem.split('-')[1])>0})
    for run in runs:
        d=build_run(run);print(json.dumps({'run':run,**d['summary']},ensure_ascii=False))
    dashboard()
