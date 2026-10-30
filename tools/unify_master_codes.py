"""Build a versioned BMJD master code correction; no child catalog or HTML writes.

Requires SciPy for sparse minimum-cost matching. Audits use the standard library.
The original draft and all prior business catalogs remain immutable inputs.
"""
import argparse
import collections
import copy
import csv
import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'主库编码统一_20261030'
BASE = ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json'
META = ROOT/'全量名称代码统一_20261029/全量原表元数据.json'
DICTIONARY = ROOT/'全库统一完成_20261029/规范职能字典.json'
HISTORY = [ROOT/p for p in ['全库统一完成_20261029/统一主库.json','主库推定整理_20261029/统一主库.json','岗位名称代码统一_20261029/名称代码主库.json','全量名称代码统一_20261029/名称代码主库.json']]
VERSION = 'BMJD-CODE-UNIFIED-20261030-01'
CORE = {'人力资源':'HR','财务':'FA','综合管理':'GM','行政':'OA','信息技术':'IT','市场':'MK','销售':'MS','销售管理':'SA','法律合规':'LE','质量管理':'QA','EHS':'SE','物流管理':'LO','物流':'LO','仓储':'LO','运输':'LO','进出口事务':'LO'}
RESEARCH = {'研发','软件开发','设计研发','产品研发','药品研发'}
RESERVED_R = {'RA','RC','RM','RP'}
PROTECTED = {'GM001','HR963','DP203','DP204','DP205','DP206','AC435','CT205'}
PREFIX = re.compile(r'^[A-Z]{2}[0-9]{2}$')
HEADER = ['岗位ID','岗位代码','岗位名称','职能','职责系列','层级','适用行业','岗位JD','旧代码','本轮处置']


def read(p): return json.loads(p.read_text('utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(x): return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def normalized(x): return ''.join(c for c in unicodedata.normalize('NFKC',x) if not c.isspace() and unicodedata.category(c)!='Cf').casefold()
def code(x): return unicodedata.normalize('NFKC',str(x)).strip().upper()


def facts(master, metadata, dictionary):
    originals={r['source_id']:{**r['原版BMJD'],'code':code(r['原版BMJD']['code'])} for r in metadata}
    raw=collections.defaultdict(collections.Counter)
    for x in originals.values():
        if PREFIX.fullmatch(x['code'][:4]):raw[x['function']][x['code'][:2]]+=1
    systems={f['name']:f.get('original_systems',[]) for f in dictionary}
    by_id={j['id']:j for j in master['jobs']}
    rows=[]
    for s in master['series']:
        jobs=[by_id[i] for i in s['job_ids']]
        source_ids=sorted({sid for j in jobs for sid in j['source_ids']})
        entries=[originals[sid] for sid in source_ids]
        own=collections.Counter(x['code'][:2] for x in entries if PREFIX.fullmatch(x['code'][:4]))
        f=s['function_name'];old=s['prefix']
        # A function-wide union of unrelated routed professions cannot justify a
        # series: use its own original sources, plus exact original function.
        allowed={CORE[f]} if f in CORE else set(raw[f])|set(own)
        legacy_r=(old.startswith('R') and old[:2] not in RESERVED_R and
                  (any('研发' in x for x in systems.get(f,[])) or f=='畜牧饲料'))
        research=f in RESEARCH or legacy_r
        pinned=any(j['code'] in PROTECTED for j in jobs) or f in CORE and old[:2]==CORE[f]
        reasonable=pinned or old[:2] in allowed or research and old.startswith('R') and old[:2] not in RESERVED_R
        # New targets must be linked to this series' sources, not borrowed from
        # another specialization merely because its normalized function matches.
        blocks={CORE[f]} if f in CORE else set(own)
        if research:blocks={b for b in blocks if b.startswith('R') and b not in RESERVED_R}
        counts=collections.Counter();exact=collections.Counter();names=collections.Counter()
        for j in jobs:
            aliases={normalized(j['name']),*(normalized(x) for x in j.get('aliases',[]))}
            for sid in j['source_ids']:
                x=originals[sid];p=x['code'][:4]
                if PREFIX.fullmatch(p) and p[:2] in blocks:
                    counts[p]+=1
                    exact[p]+=int(x['code']==p+str(j['level']))
                    names[p]+=int(normalized(x['name']) in aliases)
        rows.append({'series_id':s['id'],'function_id':s['function_id'],'function_name':f,'series_name':s['name'],
          'previous_prefix':old,'job_ids':list(s['job_ids']),'levels':sorted(j['level'] for j in jobs),'job_count':len(jobs),
          'original_function_blocks':sorted(raw[f]),'own_source_blocks':sorted(own),'allowed_existing_blocks':sorted(allowed),
          'extension_blocks':sorted(blocks),'research_policy':research,'pinned':pinned,'previous_reasonable':reasonable,
          'source_ids':source_ids,'original_candidates':[{'prefix':p,'source_count':counts[p],'exact_level_matches':exact[p],'name_matches':names[p]} for p in sorted(counts,key=lambda p:(-names[p],-exact[p],-counts[p],p))]})
    return rows


def options_for(row, historical):
    # Lexicographic objective: one changed job outweighs ALL secondary costs.
    options={row['previous_prefix']:1} if row['previous_reasonable'] else {}
    if row['pinned']:return options
    weight=row['job_count']*10_000_000_000
    originals={x['prefix']:n for n,x in enumerate(row['original_candidates'])}
    for p,rank in originals.items():options.setdefault(p,weight+1000+rank)
    blocks=set(row['extension_blocks'])
    if row['research_policy']:blocks|={'R'+c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if 'R'+c not in RESERVED_R}
    for block in sorted(blocks):
        for n in range(100):
            p=block+f'{n:02}'
            # Occupancy is decided jointly, not by a greedy first-block scan.
            # Versioned reuse of historical prefixes is explicit in a separate
            # ledger; old-code lookup must always use version and job ID.
            penalty=500_000 if p in historical else 20_000
            if block not in row['extension_blocks']:penalty+=10_000
            options.setdefault(p,weight+penalty+n)
    if not options:raise ValueError('没有有据码段：'+row['series_id'])
    return options


def minimum_assignment(rows, historical):
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import min_weight_full_bipartite_matching
    choices=[options_for(r,historical) for r in rows]
    slots=sorted({p for c in choices for p in c});columns={p:i for i,p in enumerate(slots)}
    ri=[];ci=[];weights=[]
    for i,options in enumerate(choices):
        for p,w in sorted(options.items()):ri.append(i);ci.append(columns[p]);weights.append(w)
    graph=csr_matrix((weights,(ri,ci)),shape=(len(rows),len(slots)),dtype='float64')
    try:rs,cs=min_weight_full_bipartite_matching(graph)
    except ValueError as error:raise ValueError('有据码段容量不足；停止交付，不以随机字母段替代。') from error
    selected={rows[int(i)]['series_id']:slots[int(c)] for i,c in zip(rs,cs)}
    assert len(selected)==len(rows)==len(set(selected.values()))
    # Bound guarantees secondary preferences cannot trade extra changed jobs.
    assert sum(max(w%10_000_000_000 for w in o.values()) for o in choices)<10_000_000_000
    return selected


def table_rows(master, mappings):
    by_id={r['job_id']:r for r in mappings}
    return [HEADER]+[[j['id'],j['code'],j['name'],j['function_name'],j['series_name'],j['level'],'、'.join(j['industries']),j['jd'],by_id[j['id']]['previous_code'],by_id[j['id']]['decision']] for j in master['jobs']]


def build():
    master=read(BASE);metadata=read(META);dictionary=read(DICTIONARY)
    inputs=[BASE,META,DICTIONARY,*HISTORY]
    historical=set();historical_codes=set()
    for p in [BASE,*HISTORY]:
        for j in read(p)['jobs']:historical.add(j['code'][:4]);historical_codes.add(j['code'])
    for r in metadata:
        for version in ['原版BMJD','最新输入_修改版6']:
            c=code(r[version]['code'])
            if PREFIX.fullmatch(c[:4]):historical.add(c[:4])
            if re.fullmatch(r'[A-Z]{2}[0-9]{2}[1-7]',c):historical_codes.add(c)
    rows=facts(master,metadata,dictionary);selection=minimum_assignment(rows,historical)
    out=copy.deepcopy(master);out['version']=VERSION;out['parent_version']=master['version'];out['name_code_version']=VERSION
    out['phase']='仅主库编码校正；待用户确认后再拆分子库及更新HTML'
    out['code_review']={'version':VERSION,'status':'VERIFIED_PENDING_USER_CONFIRMATION','job_fields_changed':['code','series_prefix'],
      'subcatalogs_updated':False,'html_updated':False,'historical_code_lookup':'使用版本和岗位ID，旧码不作为跨版本唯一定位键。'}
    ledger={r['series_id']:r for r in rows};mappings=[]
    for s in out['series']:s['prefix']=selection[s['id']]
    for old,j in zip(master['jobs'],out['jobs']):
        row=ledger[j['series_id']];p=selection[j['series_id']];j['code']=p+str(j['level']);j['series_prefix']=p
        original={x['prefix'] for x in row['original_candidates']}
        decision='保留合理既有码' if j['code']==old['code'] else '恢复本系列原版码段' if p in original else '在原版有据字母段内扩展系列' if p[:2] in row['extension_blocks'] else '保留研发R规则，冲突时使用有序空位'
        if j['code']!=old['code'] and row['previous_reasonable']:decision='最少必要冲突腾挪；'+decision
        mappings.append({'job_id':j['id'],'name':j['name'],'function_id':j['function_id'],'function_name':j['function_name'],
          'series_id':j['series_id'],'series_name':j['series_name'],'level':j['level'],'previous_code':old['code'],'current_code':j['code'],
          'changed':old['code']!=j['code'],'decision':decision,'source_ids':j['source_ids']})
    for row in rows:
        p=selection[row['series_id']];row['current_prefix']=p;row['changed']=p!=row['previous_prefix']
        row['target_basis']='原码保留' if not row['changed'] else '本系列原版四位码段' if any(x['prefix']==p for x in row['original_candidates']) else '本系列原版字母段扩展' if p[:2] in row['extension_blocks'] else '已有研发R规则的最小冲突调整'
        row['historical_prefix_extension']=row['changed'] and p in historical and not any(x['prefix']==p for x in row['original_candidates'])
    functions=[]
    for f in sorted({j['function_name'] for j in master['jobs']}):
        before=[j for j in master['jobs'] if j['function_name']==f];after=[j for j in out['jobs'] if j['function_name']==f]
        functions.append({'function_name':f,'jobs':len(after),'previous_blocks':dict(sorted(collections.Counter(j['code'][:2] for j in before).items())),
          'current_blocks':dict(sorted(collections.Counter(j['code'][:2] for j in after).items())),
          'changed_jobs':sum(a['code']!=b['code'] for a,b in zip(before,after)),'core_expected_block':CORE.get(f)})
    previous_code_owner={j['code']:j for j in master['jobs']}
    reused=[]
    for j in out['jobs']:
        previous=previous_code_owner.get(j['code'])
        if previous and previous['id']!=j['id']:
            reused.append({'code':j['code'],'previous_job_id':previous['id'],'previous_name':previous['name'],'current_job_id':j['id'],'current_name':j['name'],
                          'notice':'跨版本代码身份改变，查询旧稿必须带旧版本或岗位ID；当前主库没有重码。'})
    summary={'jobs':len(out['jobs']),'unique_codes':len({j['code'] for j in out['jobs']}),'unique_names':len({normalized(j['name']) for j in out['jobs']}),
      'functions':len(functions),'series':len(rows),'changed_jobs':sum(r['changed'] for r in mappings),'retained_jobs':sum(not r['changed'] for r in mappings),
      'changed_series':sum(r['changed'] for r in rows),'affected_functions':sum(f['changed_jobs']>0 for f in functions),
      'necessary_collision_moves':sum(r['changed'] and r['previous_reasonable'] for r in rows),'cross_version_code_reassignments':len(reused),
      'historical_prefix_extensions':sum(r['historical_prefix_extension'] for r in rows),'unresolved_series':0,
      'changed_names':0,'changed_jds':0,'subcatalogs_updated':False,'html_updated':False}
    checks={'9111岗代码名称ID一一对应':len(out['jobs'])==len({j['id'] for j in out['jobs']})==summary['unique_codes']==summary['unique_names']==9111,
      '仅修改岗位code及series_prefix':all({k:v for k,v in a.items() if k not in {'code','series_prefix'}}=={k:v for k,v in b.items() if k not in {'code','series_prefix'}} for a,b in zip(master['jobs'],out['jobs'])),
      '人资HR财务FA综合GM':all(j['code'].startswith(CORE[j['function_name']]) for j in out['jobs'] if j['function_name'] in CORE),
      '指定保护代码不改':all(next(j for j in out['jobs'] if j['id']==a['id'])['code']==a['code'] for a in master['jobs'] if a['code'] in PROTECTED),
      '层级及五位码正确':all(re.fullmatch(r'[A-Z]{2}[0-9]{2}[1-7]',j['code']) and int(j['code'][-1])==j['level'] for j in out['jobs']),
      '3077系列前四位全局唯一':len({s['prefix'] for s in out['series']})==len(out['series'])==3077,
      '每系列有原版或明确研发规则依据':all(not r['changed'] or selection[r['series_id']][:2] in r['extension_blocks'] or r['research_policy'] and selection[r['series_id']].startswith('R') and selection[r['series_id']][:2] not in RESERVED_R for r in rows)}
    assert all(checks.values()),checks
    report={'version':VERSION,'status':'VERIFIED_PENDING_USER_CONFIRMATION','all_passed':True,'summary':summary,'checks':checks,
            'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},'dependencies':{'optimizer':'scipy.sparse.csgraph.min_weight_full_bipartite_matching'},
            'policy':'先保证当前名称代码一一对应与原版字母依据；在这些约束下优先最少变更岗位数，再优先恢复本系列原四位码、避让历史码；历史码位必要复用全部留痕。'}
    stream=io.StringIO(newline='');csv.writer(stream,delimiter='\t',lineterminator='\n').writerows(table_rows(out,mappings))
    return {'主库.json':encoded(out),'新旧岗位代码映射.json':encoded(mappings),'系列编码核查台账.json':encoded(rows),
      '职能代码核查.json':encoded(functions),'跨版本代码身份变更.json':encoded(reused),'核验报告.json':encoded(report),
      '岗位名称代码及JD.tsv':stream.getvalue().encode('utf-8-sig')},report


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');args=p.parse_args()
    files,report=build()
    if args.write:OUT.mkdir(exist_ok=True)
    for name,data in files.items():
        path=OUT/name
        if path.exists():
            if path.read_bytes()!=data:raise ValueError('已有不同内容，不覆盖：'+str(path))
        elif args.check:raise ValueError('缺少文件：'+str(path))
    if args.write:
        for name,data in files.items():
            path=OUT/name
            if not path.exists():path.write_bytes(data)
    print(json.dumps(report['summary'],ensure_ascii=False))


if __name__=='__main__':main()
