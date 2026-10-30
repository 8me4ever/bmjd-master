"""Independently verify approved-master industry migration and real exports."""
import collections
import csv
import hashlib
import json
import re
from pathlib import Path
from audit_unified_master_codes import xlsx

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'行业子库同步_20261030'
MASTER=ROOT/'原版分类编码收口_20261030/主库.json'
INDUSTRIES=('传媒','制造','医药','地产','教育','消费品','物流','综合服务','能源化工','金融','高科技')
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text_sha(t):return hashlib.sha256(t.encode()).hexdigest()


def audit():
    parent=read(MASTER);by={j['id']:j for j in parent['jobs']};parent_hash=sha(MASTER)
    routes=read(ROOT/'全量名称代码统一_20261029/来源去向映射.json');expected={i:collections.defaultdict(set) for i in INDUSTRIES}
    for r in routes:
        if r['state']=='用户暂缓':assert not r['target_job_ids']
        else:
            for jid in r['target_job_ids']:expected[r['industry']][jid].add(r['source_id'])
    overview=read(OUT/'子库总览.json');report=read(OUT/'核验报告.json');migration=read(OUT/'行业迁移对照.json');special=read(OUT/'行业JD保留索引.json')
    original=read(ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json');oldby={j['id']:j for j in original['jobs']}
    checks={};all_ids=set();special_ids=set();all_codes=collections.defaultdict(set);all_sources=set();rows_by_industry={};total=0;special_count=0
    migration_by={(r['industry'],r['job_id']):r for r in migration};special_by={(r['industry'],r['job_id']):r for r in special}
    jd_fields={'jd','jd_clauses','jd_version','industry_jd_revision'}
    for industry in INDUSTRIES:
        child=read(OUT/industry/'岗位主库.json');old=read(ROOT/'行业专业JD优化_20261029'/industry/'岗位主库.json');previous={j['id']:j for j in old['jobs']}
        jobs=child['jobs'];ids={j['id'] for j in jobs};total+=len(jobs);all_ids.update(ids)
        checks[industry+'父库与名码版本及指纹准确']=child['parent_version']==child['name_code_version']==parent['version'] and child['parent_master_sha256']==parent_hash
        checks[industry+'岗位范围顺序及原活动来源完整']=ids==set(expected[industry]) and [j['id'] for j in jobs]==[j['id'] for j in parent['jobs'] if industry in j['industries']] and ids==set(previous)
        checks[industry+'ID名称代码唯一且严格五位']=len(jobs)==len(ids)==len({j['name'] for j in jobs})==len({j['code'] for j in jobs}) and all(re.fullmatch('[A-Z]{2}[0-9]{2}[1-7]',j['code']) and j['code'][-1]==str(j['level']) for j in jobs)
        identity=True;jd_ok=True;source_ok=True;mapping_ok=True;count=0
        for j in jobs:
            p=by[j['id']];before=previous[j['id']]
            all_codes[j['code']].add(j['id']);all_sources.update(j['industry_membership']['source_ids'])
            identity &= all(j[k]==v for k,v in p.items() if k not in jd_fields) and set(j)-set(p)<= {'industry_membership','industry_jd_revision'}
            source_ok &= j['industry_membership']=={'industry':industry,'source_ids':sorted(expected[industry][j['id']])}
            specialized=before['jd']!=oldby[j['id']]['jd']
            if specialized:
                count+=1;special_count+=1;special_ids.add(j['id'])
                jd_ok &= all(j[k]==before[k] for k in jd_fields) and j['industry_jd_revision']['parent_jd_sha256']==text_sha(p['jd'])
                r=special_by.get((industry,j['id']),{})
                mapping_ok &= r.get('code')==j['code'] and r.get('industry_jd_sha256')==text_sha(j['jd']) and r.get('parent_jd_sha256')==text_sha(p['jd']) and r.get('local_source_ids')==j['industry_membership']['source_ids']
            else:jd_ok &= all(j[k]==v for k,v in p.items()) and 'industry_jd_revision' not in j
            r=migration_by.get((industry,j['id']),{})
            mapping_ok &= r.get('current_code')==j['code'] and r.get('previous_code')==before['code'] and r.get('jd_sha256')==text_sha(j['jd']) and r.get('industry_jd_retained')==specialized
        checks[industry+'所有非JD岗位字段与确认主库逐值一致']=identity
        checks[industry+'专业JD及条款版本原样保留其余沿用主库']=jd_ok
        checks[industry+'本行业来源不遗漏不串行不恢复暂缓']=source_ok
        checks[industry+'迁移映射与专业JD索引逐条可复算']=mapping_ok
        checks[industry+'行业根字典统计按实际岗位重算']=all(g['jobs']==sum(j['function_group_id']==g['id'] for j in jobs) and g['code_blocks']==dict(sorted(collections.Counter(j['code'][:2] for j in jobs if j['function_group_id']==g['id']).items())) for g in child['function_groups']) and all(d['jobs']==sum(j['function_direction_id']==d['id'] for j in jobs) for d in child['function_directions']) and sum(g['jobs'] for g in child['function_groups'])==len(jobs)
        series_ok=True
        for s in child['series']:
            original_s=next(t for t in parent['series'] if t['id']==s['id'])
            series_ok &= s==dict(original_s,job_ids=[i for i in original_s['job_ids'] if i in ids])
        checks[industry+'系列与职能索引无子库外引用']=series_ok and {i for f in child['functions'] for i in f['job_ids']}==ids and all(f['job_ids']==[j['id'] for j in jobs if j['function_id']==f['id']] for f in child['functions'])
        with (OUT/industry/'岗位名称代码及JD.tsv').open(encoding='utf-8-sig',newline='') as f:table=list(csv.reader(f,delimiter='\t'))
        expected_rows=[[j['id'],j['code'],j['name'],j['function_name'],j['function_group_name'],j['function_direction_name'],j['series_name'],str(j['level']),industry,'、'.join(j['industries']),'保留行业专业JD' if j['id'] in {x['job_id'] for x in special if x['industry']==industry} else '沿用主库JD',j['jd'],parent['version'],child['version']] for j in jobs]
        checks[industry+'实际TSV及Excel全岗位14列逐值一致']=len(table)==len(jobs)+1 and len(table[0])==14 and table[1:]==expected_rows and xlsx(OUT/industry/'岗位主库.xlsx')['岗位主库']==table
        rows_by_industry[industry]=table
        s=child['summary'];checks[industry+'数量与专业JD保留统计准确']=s['jobs']==len(jobs) and s['industry_jd_retained']==count and s['master_jd_retained']==len(jobs)-count
    combined=xlsx(OUT/'BMJD_11行业子库.xlsx')
    checks['汇总Excel11行业全量逐列一致']=all(combined[i]==t for i,t in rows_by_industry.items())
    checks['9111主库岗位全覆盖无额外岗位']=all_ids==set(by) and len(all_ids)==9111
    checks['19018行业记录跨行业同码必为同一岗位']=total==19018 and len(all_codes)==9111 and all(len(ids)==1 for ids in all_codes.values())
    checks['843条专业JD及832岗位全部保留无新改写']=special_count==len(special)==len(special_by)==843 and len(special_ids)==832 and overview['summary']['new_jd_rewrites']==0
    checks['全部19226活动来源覆盖且23暂缓不恢复']=len(all_sources)==19226 and all_sources=={r['source_id'] for r in routes if r['state']!='用户暂缓'} and sum(r['state']=='用户暂缓' for r in routes)==23
    checks['19018迁移记录无遗漏无重复']=len(migration)==len(migration_by)==total
    checks['11行业划分及根总览准确']=len(overview['industries'])==11 and {s['industry'] for s in overview['industries']}==set(INDUSTRIES) and overview['summary']['industry_job_memberships']==total and overview['parent_master_sha256']==parent_hash
    index=read(OUT/'岗位行业索引.json');checks['9111岗位行业索引全量准确']=len(index)==9111 and all(r['job_id']==j['id'] and r['code']==j['code'] and r['name']==j['name'] and r['industries']==j['industries'] for r,j in zip(index,parent['jobs']))
    confirmation=read(OUT/'主库确认记录.json');checks['用户确认记录固定主库版本指纹']=confirmation['version']==parent['version'] and confirmation['master_sha256']==parent_hash and overview['approved_master']
    checks['全部生成输入指纹保持']=all(sha(ROOT/p)==h for p,h in report['input_sha256'].items())
    manifest=read(ROOT/'项目文件清单.json')['files'];protected={p:d['sha256'] for p,d in manifest.items() if p.startswith(('原版分类编码收口_20261030/','行业一级子库_','行业专业JD优化_','BMJD主库汇总预览_','semantic_portal/','BMJD持续补全工具_','completion_tool/'))}
    checks['确认主库所有文件旧子库旧HTML新增工具未改']=all(sha(ROOT/p)==h for p,h in protected.items())
    assert all(checks.values()),{k:v for k,v in checks.items() if not v}
    result={'version':overview['version'],'parent_version':parent['version'],'all_passed':True,'passed':sum(checks.values()),'total':len(checks),'summary':overview['summary'],'checks':checks,
      'sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.suffix in {'.json','.tsv','.xlsx'} and p.name!='独立核验报告.json'},
      'protected_sha256':protected,'scope':'独立核验全部19,018条岗位、原分类来源、JSON/TSV/实际Excel及旧文件指纹；不导入迁移生成器。'}
    (OUT/'独立核验报告.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'all_passed':True,'passed':result['passed'],'total':result['total'],'summary':result['summary']},ensure_ascii=False))


if __name__=='__main__':audit()
