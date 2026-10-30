"""Independent grouped-master audit: original fields, families, PP and real exports."""
import argparse,collections,hashlib,json,csv,re,unicodedata
from pathlib import Path
from audit_job_codes import audit_jobs
from audit_unified_master_codes import xlsx
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'主库职能序列整合_20261030'
BASE=ROOT/'主库编码统一_20261030/主库.json'
ADDED={'function_group_id','function_group_name','function_direction_id','function_direction_name'}
def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ident(kind,*parts):return kind+'-'+hashlib.sha256('\x1f'.join(parts).encode()).hexdigest()[:14].upper()
def build_report():
    old=read(BASE);m=read(OUT/'主库.json');rules=read(OUT/'职能序列整合规则.json');report=read(OUT/'核验报告.json')
    by={j['id']:j for j in m['jobs']};before={j['id']:j for j in old['jobs']};groups={g['id']:g for g in m['function_groups']};directions={d['id']:d for d in m['function_directions']};series={s['id']:s for s in m['series']};oldseries={s['id']:s for s in old['series']}
    checks,code_errors=audit_jobs(m['jobs'])
    checks['9111原岗位ID及顺序保持']=len(by)==9111 and list(by)==list(before)
    checks['原字段仅code和series_prefix变化']=all({k:v for k,v in j.items() if k not in ADDED|{'code','series_prefix'}}=={k:v for k,v in before[j['id']].items() if k not in {'code','series_prefix'}} for j in by.values())
    checks['主库版本与当前名码版本一致']=m['name_code_version']==m['version']
    checks['当前编码核验版本与主库一致']=m['code_review']['version']==m['version'] and m['code_review']['changed_codes']==89
    checks['原263职能来源字段完整保留']=len({j['function_id'] for j in by.values()})==263 and all(j['function_id']==before[j['id']]['function_id'] and j['function_name']==before[j['id']]['function_name'] for j in by.values())
    checks['名称JD层级行业来源逐值保持']=all(all(j[k]==before[j['id']][k] for k in ['name','jd','jd_clauses','level','industries','source_ids']) for j in by.values())
    checks['3077职责系列ID及岗位索引保持']=len(series)==len({s['prefix'] for s in series.values()})==3077 and set(series)==set(oldseries) and all(s['job_ids']==oldseries[s['id']]['job_ids'] for s in series.values())
    checks['所有系列非编码非新增字段保持']=all({k:v for k,v in s.items() if k not in ADDED|{'prefix'}}=={k:v for k,v in oldseries[s['id']].items() if k!='prefix'} for s in series.values())
    assignments={};reasons={}
    for g in rules['groups']:
        for f in g['source_functions']:
            assert f not in assignments;assignments[f]=g['name'];reasons[f]=g['reason']
    overrides={r['series_id']:r for r in rules['series_overrides']};bad=[]
    for j in by.values():
        previous=before[j['id']];rule=overrides.get(j['series_id'],{});f=previous['function_name']
        target=rule.get('group',assignments.get(f,rules.get('default_group_labels',{}).get(f,f)))
        label=rule.get('direction_name',rules.get('direction_labels',{}).get(f,f));gid=ident('FG',target);did=ident('FD',target,previous['function_id'],label)
        if (j['function_group_name'],j['function_group_id'],j['function_direction_name'],j['function_direction_id'])!=(target,gid,label,did):bad.append(j['id'])
    checks['全部岗位按明示规则和边界分流']=not bad
    checks['每岗唯一主序列和专业方向']=all(j['function_group_id'] in groups and j['function_direction_id'] in directions and groups[j['function_group_id']]['name']==j['function_group_name'] and directions[j['function_direction_id']]['name']==j['function_direction_name'] and directions[j['function_direction_id']]['group_id']==j['function_group_id'] for j in by.values())
    checks['原专业及主序列职责系列没有拼接']=all(len({(by[i]['function_group_id'],by[i]['function_direction_id']) for i in s['job_ids']})==1 and all(by[i]['series_prefix']==s['prefix']==by[i]['code'][:4] for i in s['job_ids']) for s in series.values())
    checks['主序列统计与实际岗位逐项一致']=len(groups)==len({g['name'] for g in groups.values()}) and sum(g['jobs'] for g in groups.values())==9111 and all(g['jobs']==sum(j['function_group_id']==gid for j in by.values()) and g['professional_directions']==len({j['function_direction_id'] for j in by.values() if j['function_group_id']==gid}) and g['code_blocks']==dict(collections.Counter(j['code'][:2] for j in by.values() if j['function_group_id']==gid)) for gid,g in groups.items())
    checks['专业方向来源及数量准确']=sum(d['jobs'] for d in directions.values())==9111 and all(d['jobs']==sum(j['function_direction_id']==did for j in by.values()) and all(j['function_id']==d['source_function_id'] and j['function_name']==d['source_function_name'] for j in by.values() if j['function_direction_id']==did) for did,d in directions.items())
    product=[j for j in by.values() if j['function_group_name']=='产品'];changed=[j for j in by.values() if j['code']!=before[j['id']]['code']]
    checks['产品108岗统一PP且完整六类78岗纳入']=len(product)==108 and all(j['code'].startswith('PP') for j in product) and all(j['function_group_name']=='产品' for j in by.values() if j['function_name'] in {'产品','产品项目部','产品运营','产品规划','产品营销','产品研发'})
    checks['产品研发按用户要求PP覆盖旧R规则']=all(j['code'].startswith('PP') for j in by.values() if j['function_name']=='产品研发')
    checks['仅89个非PP产品岗位换码且达到必要下界']=len(changed)==sum(j['function_group_name']=='产品' and not before[j['id']]['code'].startswith('PP') for j in by.values())==89 and all(j['function_group_name']=='产品' for j in changed)
    checks['原PP产品岗位原码保留']=all(j['code']==before[j['id']]['code'] for j in product if before[j['id']]['code'].startswith('PP'))
    checks['非产品全部原码及基础HR_FA_GM保持']=all(j['code']==before[j['id']]['code'] for j in by.values() if j['function_group_name']!='产品') and all(j['code'][:2]=={'人力资源':'HR','财务':'FA','综合管理':'GM'}[j['function_name']] for j in by.values() if j['function_name'] in {'人力资源','财务','综合管理'})
    oldcodes={j['code']:j['id'] for j in before.values()}
    checks['相较父版没有同码换身份']=all(j['code'] not in oldcodes or oldcodes[j['code']]==j['id'] for j in by.values())
    checks['生产计划PP共享段未误纳产品']=all(j['function_group_name']!='产品' and j['code']==before[j['id']]['code'] for j in by.values() if j['function_name']=='生产管理')
    checks['招募正确归临床研究非HR']=all(j['function_group_name']=='临床研究' for j in by.values() if j['function_name']=='招募')
    checks['核磁维修与质谱实验保持不同专业']=all(j['function_group_name']=='设备工程' for j in by.values() if j['function_name']=='核磁') and all(j['function_group_name']=='实验室' for j in by.values() if j['function_name']=='质谱')
    checks['酒店收益不并入投资']=all(j['function_group_name']=='运营管理' for j in by.values() if j['function_name']=='收益')
    checks['IB期货经纪与国际银行分开']=all(j['function_group_name']=='证券期货经纪' for j in by.values() if j['function_name']=='IB业务') and all(j['function_group_name']=='银行业务' for j in by.values() if j['function_name']=='国际业务')
    audit=read(OUT/'分类审核台账.json');checks['263原职能包括101小职能均有处置']=len(audit)==len({r['source_function_id'] for r in audit})==263 and sum(r['small_function'] for r in audit)==101 and all(r['jobs']==sum(j['function_name']==r['source_function_name'] for j in by.values()) and r['small_function']==(r['jobs']<=10) and r['target_groups']==dict(collections.Counter(j['function_group_name'] for j in by.values() if j['function_name']==r['source_function_name'])) for r in audit)
    maps=read(OUT/'新旧分类与代码映射.json');mapby={r['job_id']:r for r in maps}
    checks['9111全量新旧映射准确']=len(maps)==len(mapby)==9111 and set(mapby)==set(by) and all(r['name']==by[jid]['name'] and r['previous_code']==before[jid]['code'] and r['current_code']==by[jid]['code'] and r['function_group_id']==by[jid]['function_group_id'] and r['function_direction_id']==by[jid]['function_direction_id'] for jid,r in mapby.items())
    header=['岗位ID','岗位代码','岗位名称','主职能序列','专业方向','职责系列','层级','适用行业','岗位JD','旧代码','原规范职能']
    rows=[header]+[[j['id'],j['code'],j['name'],j['function_group_name'],j['function_direction_name'],j['series_name'],str(j['level']),'、'.join(j['industries']),j['jd'],before[j['id']]['code'],j['function_name']] for j in m['jobs']]
    with (OUT/'岗位主序列名称代码及JD.tsv').open(encoding='utf-8-sig',newline='') as f:tsv=list(csv.reader(f,delimiter='\t'))
    checks['TSV与JSON9111岗全部展示字段一致']=tsv==rows
    excel=xlsx(OUT/'主库主序列及岗位JD.xlsx');checks['Excel主表与JSON全部字段一致']=excel['岗位主序列及JD']==rows
    checks['Excel产品对照108岗代码准确']=len(excel['产品PP对照'])==109 and {tuple(r[:2]+r[5:7]) for r in excel['产品PP对照'][1:]}=={(j['id'],j['name'],before[j['id']]['code'],j['code']) for j in product}
    checks['Excel全量分类审核页完整']=len(excel['原职能审核对照'])==264 and len(excel['主序列总览'])==len(groups)+1 and len(excel['专业方向字典'])==len(directions)+1
    issues=read(OUT/'JD边界问题.json');checks['3条已知JD问题保留原稿并单列']=len(issues)==3 and all(r['current_jd']==by[r['job_id']]['jd']==before[r['job_id']]['jd'] for r in issues) and len(excel['JD边界待修订'])==4
    checks['根字典文件与主库一致']=read(OUT/'主序列总览.json')==m['function_groups'] and read(OUT/'专业方向字典.json')==m['function_directions']
    s=report['summary'];checks['报告全部核心统计可独立复算']=s['function_groups']==len(groups) and s['professional_directions']==len(directions) and s['changed_codes']==len(changed) and s['product_jobs']==len(product) and s['series']==len(series)
    checks['原输入指纹保持']=all(sha(ROOT/n)==h for n,h in report['input_sha256'].items())
    manifest=read(ROOT/'项目文件清单.json');protected={n:v['sha256'] for n,v in manifest['files'].items() if n.startswith(('主库编码统一_20261030/','岗位JD匹配审查_20261029/','行业一级子库_20261029/','行业专业JD优化_20261029/','BMJD客户查岗平台_20261030/','BMJD主库复核页面_20261030/','BMJD持续补全工具_20261029/','customer_portal/','completion_tool/'))}
    checks['前版主库子库HTML与新增工具保持']=bool(protected) and all(sha(ROOT/n)==h for n,h in protected.items())
    return {'version':m['version'],'reviewer':'Codex独立产物核验','all_passed':all(checks.values()),'passed':sum(checks.values()),'total':len(checks),'summary':s,'checks':checks,'code_errors':code_errors,'classification_errors':bad,
      'sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(OUT.iterdir()) if p.suffix in {'.json','.tsv','.xlsx'} and p.name not in {'独立核验报告.json','页面构建核验.json','页面浏览器核验.json'}},'protected_sha256':protected,
      'scope':'主序列规则、边界分流、产品PP、名称代码唯一、字段不变及真实导出；已知3条JD错配未在本轮改写，不声称所有JD无问题。'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write',action='store_true');p.add_argument('--check',action='store_true');a=p.parse_args();r=build_report();assert r['all_passed'],[k for k,v in r['checks'].items() if not v]
    data=(json.dumps(r,ensure_ascii=False,indent=2)+'\n').encode();path=OUT/'独立核验报告.json'
    if a.write:
        if path.exists() and path.read_bytes()!=data:raise ValueError('不覆盖不同报告。')
        path.write_bytes(data)
    if a.check:assert path.read_bytes()==data
    print(json.dumps({'all_passed':r['all_passed'],'checks':f"{r['passed']}/{r['total']}",'summary':r['summary']},ensure_ascii=False))
if __name__=='__main__':main()
