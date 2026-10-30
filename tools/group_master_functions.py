"""Group flat BMJD functions into navigable families, retaining professional data.

Only the user-directed product family receives new PP codes. Prior catalogs,
canonical source function fields, actual job identities, JDs and children stay intact.
"""
import argparse
import collections
import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'主库编码统一_20261030/主库.json'
OUT=ROOT/'主库职能序列整合_20261030'
RULES=OUT/'职能序列整合规则.json'
META=ROOT/'全量名称代码统一_20261029/全量原表元数据.json'
VERSION='BMJD-FUNCTION-GROUPED-20261030-01'
ADDED={'function_group_id','function_group_name','function_direction_id','function_direction_name'}
HEADER=['岗位ID','岗位代码','岗位名称','主职能序列','专业方向','职责系列','层级','适用行业','岗位JD','旧代码','原规范职能']


def read(p):return json.loads(p.read_text('utf-8'))
def encoded(d):return (json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ident(kind,*parts):return kind+'-'+hashlib.sha256('\x1f'.join(parts).encode()).hexdigest()[:14].upper()


def classify(master,policy):
    existing={j['function_name'] for j in master['jobs']};rules={};reasons={}
    for g in policy['groups']:
        reasons[g['name']]=g['reason']
        for f in g['source_functions']:
            if f not in existing or f in rules:raise ValueError('职能合并规则缺失或重复：'+f)
            rules[f]=g['name']
    overrides={r['series_id']:r for r in policy['series_overrides']}
    if len(overrides)!=len(policy['series_overrides']) or set(overrides)-{s['id'] for s in master['series']}:raise ValueError('系列分流规则重复或指向未知系列。')
    classified={}
    for s in master['series']:
        old=s['function_name'];override=overrides.get(s['id'],{})
        group=override.get('group',rules.get(old,policy.get('default_group_labels',{}).get(old,old)))
        direction=override.get('direction_name',policy.get('direction_labels',{}).get(old,old))
        classified[s['id']]={'group_name':group,'group_id':ident('FG',group),
          'direction_name':direction,'direction_id':ident('FD',group,s['function_id'],direction),
          'reason':override.get('reason',reasons.get(group,policy['retain_reasons'].get(group,policy['retain_reasons'].get(old,'专业对象与职责成果独立，未找到足以整包并入另一主序列的明确依据，保留入口。'))))}
    return classified


def allocate_product(master,classified,metadata):
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import min_weight_full_bipartite_matching
    product=[s for s in master['series'] if classified[s['id']]['group_name']=='产品']
    locked={s['prefix'] for s in master['series'] if classified[s['id']]['group_name']!='产品' or s['prefix'].startswith('PP')}
    kept={s['id']:s['prefix'] for s in product if s['prefix'].startswith('PP')}
    pending=[s for s in product if s['id'] not in kept]
    slots=['PP'+f'{n:02}' for n in range(100) if 'PP'+f'{n:02}' not in locked]
    if len(slots)<len(pending):raise ValueError('PP码段容量不足；不改变非产品岗位来腾位。')
    src={r['source_id']:r['原版BMJD'] for r in metadata};by_id={j['id']:j for j in master['jobs']}
    ri=[];ci=[];weights=[]
    for i,s in enumerate(pending):
        votes=collections.Counter(src[sid]['code'][:4] for jid in s['job_ids'] for sid in by_id[jid]['source_ids'] if src[sid]['code'].startswith('PP'))
        for col,p in enumerate(slots):
            cost=10001+col  # positive, source-supported PP first
            if p in votes:cost=1+col+1000-min(votes[p],999)
            ri.append(i);ci.append(col);weights.append(cost)
    if pending:
        rows,cols=min_weight_full_bipartite_matching(csr_matrix((weights,(ri,ci)),shape=(len(pending),len(slots))))
        kept.update({pending[int(i)]['id']:slots[int(c)] for i,c in zip(rows,cols)})
    assert len(kept)==len(product) and len(set(kept.values()))==len(kept)
    return kept


def expected_rows(master,mappings):
    before={r['job_id']:r for r in mappings}
    return [HEADER]+[[j['id'],j['code'],j['name'],j['function_group_name'],j['function_direction_name'],j['series_name'],j['level'],'、'.join(j['industries']),j['jd'],before[j['id']]['previous_code'],j['function_name']] for j in master['jobs']]


def build():
    base=read(BASE);policy=read(RULES);metadata=read(META)
    selected=classify(base,policy);product_codes=allocate_product(base,selected,metadata)
    out=copy.deepcopy(base);out['parent_version']=base['version'];out['version']=VERSION
    out['previous_name_code_version']=base.get('name_code_version',base['version']);out['name_code_version']=VERSION
    out['previous_code_review']=copy.deepcopy(base.get('code_review',{}))
    out['code_review']={'version':VERSION,'status':'VERIFIED_PENDING_USER_REVIEW','changed_codes':89,
      'policy':'产品主序列按用户要求PP，非产品原码保持；旧码回查使用版本和岗位ID。','subcatalogs_updated':False,'maintenance_updated':False}
    out['phase']='主序列/专业方向分层整合工作版；产品统一PP，待用户复核'
    out['classification_review']={'version':VERSION,'status':'VERIFIED_PENDING_USER_REVIEW','source_functions_retained':True,
      'product_code_override':'产品主序列全部PP，产品研发亦按本次用户要求PP；其他代码不因导航归并重排。',
      'children_updated':False,'maintenance_updated':False}
    old_by={j['id']:j for j in base['jobs']};mappings=[];group_jobs=collections.defaultdict(list);direction_jobs=collections.defaultdict(list)
    for j in out['jobs']:
        c=selected[j['series_id']];old=old_by[j['id']]
        j.update(function_group_id=c['group_id'],function_group_name=c['group_name'],function_direction_id=c['direction_id'],function_direction_name=c['direction_name'])
        if c['group_name']=='产品':j['series_prefix']=product_codes[j['series_id']];j['code']=j['series_prefix']+str(j['level'])
        group_jobs[c['group_name']].append(j);direction_jobs[c['direction_id']].append(j)
        mappings.append({'job_id':j['id'],'name':j['name'],'previous_code':old['code'],'current_code':j['code'],'code_changed':j['code']!=old['code'],
          'source_function_id':old['function_id'],'source_function_name':old['function_name'],
          'function_group_id':c['group_id'],'function_group_name':c['group_name'],'function_direction_id':c['direction_id'],'function_direction_name':c['direction_name'],
          'series_id':j['series_id'],'reason':c['reason']})
    for s in out['series']:
        c=selected[s['id']];s.update(function_group_id=c['group_id'],function_group_name=c['group_name'],function_direction_id=c['direction_id'],function_direction_name=c['direction_name'])
        if s['id'] in product_codes:s['prefix']=product_codes[s['id']]
    directions=[]
    for did,jobs in sorted(direction_jobs.items(),key=lambda kv:(kv[1][0]['function_group_name'],kv[1][0]['function_direction_name'],kv[0])):
        j=jobs[0];directions.append({'id':did,'name':j['function_direction_name'],'group_id':j['function_group_id'],'group_name':j['function_group_name'],
          'source_function_id':j['function_id'],'source_function_name':j['function_name'],'jobs':len(jobs),'series':len({j['series_id'] for j in jobs})})
    groups=[]
    for name,jobs in sorted(group_jobs.items()):
        groups.append({'id':ident('FG',name),'name':name,'jobs':len(jobs),'professional_directions':len({j['function_direction_id'] for j in jobs}),
          'series':len({j['series_id'] for j in jobs}),'source_functions':sorted({j['function_name'] for j in jobs}),'code_blocks':dict(sorted(collections.Counter(j['code'][:2] for j in jobs).items())),
          'code_policy':'统一PP' if name=='产品' else '保留各原专业方向合理代码，不将两个字母强行视为一个职能独占'})
    out['function_groups']=groups;out['function_directions']=directions
    out['summary'].update(function_groups=len(groups),professional_directions=len(directions))
    all_old_funcs=collections.defaultdict(list)
    for j in out['jobs']:all_old_funcs[j['function_name']].append(j)
    audit=[]
    threshold=policy['small_function_threshold']
    for f,jobs in sorted(all_old_funcs.items(),key=lambda kv:(len(kv[1]),kv[0])):
        targets=dict(sorted(collections.Counter(j['function_group_name'] for j in jobs).items()))
        state='按职责分流到多个主序列' if len(targets)>1 else '纳入上级主序列' if next(iter(targets))!=f or len(next(g for g in groups if g['name']==next(iter(targets)))['source_functions'])>1 else '保留独立入口'
        audit.append({'source_function_id':jobs[0]['function_id'],'source_function_name':f,'jobs':len(jobs),'small_function':len(jobs)<=threshold,
          'decision':state,'target_groups':targets,'direction_names':sorted({j['function_direction_name'] for j in jobs}),
          'reasons':list(dict.fromkeys(selected[j['series_id']]['reason'] for j in jobs)),
          'job_ids':[j['id'] for j in jobs],'evidence_samples':[{'id':j['id'],'name':j['name'],'source_ids':j['source_ids'],'jd_excerpt':'\n'.join(j['jd'].splitlines()[:2])} for j in jobs[:3]]})
    issues=[]
    for r in policy.get('jd_issues',[]):
        for j in out['jobs']:
            if j['series_id']==r['series_id']:issues.append({**r,'job_id':j['id'],'name':j['name'],'code':j['code'],'source_ids':j['source_ids'],'current_jd':j['jd']})
    product=group_jobs['产品'];summary={'jobs':len(out['jobs']),'unique_names':len({j['name'] for j in out['jobs']}),'unique_codes':len({j['code'] for j in out['jobs']}),
      'previous_flat_functions':len(all_old_funcs),'function_groups':len(groups),'professional_directions':len(directions),'series':len(out['series']),
      'product_jobs':len(product),'product_directions':len({j['function_direction_id'] for j in product}),'product_series':len(product_codes),
      'changed_codes':sum(r['code_changed'] for r in mappings),'nonproduct_code_changes':sum(r['code_changed'] and r['function_group_name']!='产品' for r in mappings),
      'reviewed_small_functions':sum(r['small_function'] for r in audit),'small_functions_integrated':sum(r['small_function'] and r['decision']!='保留独立入口' for r in audit),
      'remaining_independent_small_groups':sum(g['jobs']<=threshold for g in groups),'changed_names':0,'changed_jds':0,'retained_jd_issues':len(issues),'children_updated':False,'maintenance_updated':False}
    checks={
      '9111岗位名称ID代码唯一':len(out['jobs'])==len({j['id'] for j in out['jobs']})==summary['unique_names']==summary['unique_codes']==9111,
      '旧岗位字段仅产品代码和系列前缀改变':all({k:v for k,v in j.items() if k not in ADDED|{'code','series_prefix'}}=={k:v for k,v in old_by[j['id']].items() if k not in {'code','series_prefix'}} for j in out['jobs']),
      '产品主序列全部PP':all(j['code'].startswith('PP') for j in product),
      '非产品岗位原码全部保持':summary['nonproduct_code_changes']==0,
      '3077原职责系列ID索引保留':len(out['series'])==3077 and [s['id'] for s in out['series']]==[s['id'] for s in base['series']],
      '所有系列前四位唯一':len({s['prefix'] for s in out['series']})==3077,
      '字母段共享不把生产计划并入产品':all(j['function_group_name']!='产品' for j in out['jobs'] if j['function_name']=='生产管理'),
      '全部263原职能有审查结论':len(audit)==263,
      '岗位层级原样且与末位一致':all(j['level']==old_by[j['id']]['level']==int(j['code'][-1]) for j in out['jobs']),
      '全部岗位唯一归属一个主序列方向':all(j['function_group_id'] in {g['id'] for g in groups} and j['function_direction_id'] in {d['id'] for d in directions} for j in out['jobs'])}
    assert all(checks.values()),checks
    report={'version':VERSION,'all_passed':True,'status':'VERIFIED_PENDING_USER_REVIEW','summary':summary,'checks':checks,
      'input_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in [BASE,RULES,META]},
      'scope':'全量旧职能/岗位/原来源映射、主序列归并与重点边界自审；不是逐句人工复核全部JD。已知3条原稿错配原样保留并单列。'}
    stream=io.StringIO(newline='');csv.writer(stream,delimiter='\t',lineterminator='\n').writerows(expected_rows(out,mappings))
    return {'主库.json':encoded(out),'主序列总览.json':encoded(groups),'专业方向字典.json':encoded(directions),'分类审核台账.json':encoded(audit),
      '新旧分类与代码映射.json':encoded(mappings),'JD边界问题.json':encoded(issues),'核验报告.json':encoded(report),
      '岗位主序列名称代码及JD.tsv':stream.getvalue().encode('utf-8-sig')},report


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true');args=p.parse_args()
    files,report=build()
    if args.write:OUT.mkdir(exist_ok=True)
    for name,data in files.items():
        path=OUT/name
        if path.exists() and path.read_bytes()!=data:raise ValueError('已有不同版本，不覆盖：'+str(path))
        if args.check:assert path.read_bytes()==data,name
    if args.write:
        for name,data in files.items():
            path=OUT/name
            if not path.exists():path.write_bytes(data)
    print(json.dumps(report['summary'],ensure_ascii=False))

if __name__=='__main__':main()
